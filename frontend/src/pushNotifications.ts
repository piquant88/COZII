import { Platform } from 'react-native';
import * as Notifications from 'expo-notifications';
import * as Device from 'expo-device';
import Constants from 'expo-constants';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { api } from './api';

const STORED_TOKEN_KEY = 'cozii_expo_push_token';

let _handlerInstalled = false;
export function installNotificationHandler() {
  if (_handlerInstalled) return;
  _handlerInstalled = true;
  try {
    Notifications.setNotificationHandler({
      handleNotification: async () => ({
        shouldPlaySound: true,
        shouldSetBadge: false,
        // SDK 53+: replaces deprecated shouldShowAlert
        shouldShowBanner: true,
        shouldShowList: true,
      }),
    });
  } catch (e) {
    console.warn('[push] setNotificationHandler failed', e);
  }
}

function resolveProjectId(): string | null {
  const c: any = Constants;
  return (
    c?.expoConfig?.extra?.eas?.projectId ||
    c?.easConfig?.projectId ||
    c?.manifest2?.extra?.eas?.projectId ||
    c?.manifest?.extra?.eas?.projectId ||
    null
  );
}

function isExpoGo(): boolean {
  // Constants.appOwnership === 'expo' means running in Expo Go
  const ownership = (Constants as any)?.appOwnership;
  const exec = (Constants as any)?.executionEnvironment;
  return ownership === 'expo' || exec === 'storeClient';
}

async function ensurePermissionsAsync(): Promise<{ ok: boolean; status: string }> {
  try {
    const existing = await Notifications.getPermissionsAsync();
    if (existing.status === 'granted') return { ok: true, status: 'granted' };
    if (!existing.canAskAgain) return { ok: false, status: existing.status || 'denied' };
    const req = await Notifications.requestPermissionsAsync();
    return { ok: req.status === 'granted', status: req.status };
  } catch (e: any) {
    return { ok: false, status: `error: ${e?.message || e}` };
  }
}

async function ensureAndroidChannel() {
  if (Platform.OS !== 'android') return;
  try {
    await Notifications.setNotificationChannelAsync('default', {
      name: 'Cozii alerts',
      importance: Notifications.AndroidImportance.HIGH,
      vibrationPattern: [0, 250, 250, 250],
      lightColor: '#FF8C73',
    });
  } catch (e) {
    console.warn('[push] android channel failed', e);
  }
}

export type PushDiagnostics = {
  platform: string;
  isDevice: boolean;
  isExpoGo: boolean;
  permission: string;
  projectId: string | null;
  token: string | null;
  lastError: string | null;
};

export async function getPushDiagnostics(): Promise<PushDiagnostics> {
  const out: PushDiagnostics = {
    platform: Platform.OS,
    isDevice: !!Device.isDevice,
    isExpoGo: isExpoGo(),
    permission: 'unknown',
    projectId: resolveProjectId(),
    token: null,
    lastError: null,
  };
  try {
    const p = await Notifications.getPermissionsAsync();
    out.permission = p.status;
  } catch (e: any) {
    out.permission = `error: ${e?.message || e}`;
  }
  try {
    out.token = await AsyncStorage.getItem(STORED_TOKEN_KEY);
  } catch {}
  return out;
}

export async function registerForPushAsync(opts?: { force?: boolean }): Promise<{ token: string | null; error: string | null }> {
  if (Platform.OS === 'web') return { token: null, error: 'web (push not supported)' };
  try {
    if (!Device.isDevice) return { token: null, error: 'simulator (must run on a real device)' };
    await ensureAndroidChannel();
    const perm = await ensurePermissionsAsync();
    if (!perm.ok) return { token: null, error: `permission ${perm.status}` };

    const projectId = resolveProjectId();
    if (!projectId) {
      return {
        token: null,
        error: isExpoGo()
          ? 'Expo Go SDK 53+ no longer supports push notifications. Build a dev client (eas build --profile development) or set extra.eas.projectId in app.json.'
          : 'No EAS projectId configured. Run `eas init` once and add it to app.json under expo.extra.eas.projectId.',
      };
    }

    let tokenData;
    try {
      tokenData = await Notifications.getExpoPushTokenAsync({ projectId });
    } catch (e: any) {
      const msg = e?.message || String(e);
      console.warn('[push] getExpoPushTokenAsync failed:', msg);
      return { token: null, error: msg };
    }
    const token = tokenData?.data || null;
    if (!token) return { token: null, error: 'empty token' };

    if (!opts?.force) {
      const cached = await AsyncStorage.getItem(STORED_TOKEN_KEY).catch(() => null);
      if (cached === token) return { token, error: null };
    }

    try {
      await api.post('/users/push-token', {
        token,
        platform: Platform.OS,
        device_name: Device.deviceName || Device.modelName || null,
      });
      await AsyncStorage.setItem(STORED_TOKEN_KEY, token);
    } catch (e: any) {
      return { token, error: `backend register failed: ${e?.message || e}` };
    }
    return { token, error: null };
  } catch (e: any) {
    return { token: null, error: `outer: ${e?.message || e}` };
  }
}

export async function unregisterPushAsync(): Promise<void> {
  try {
    const cached = await AsyncStorage.getItem(STORED_TOKEN_KEY).catch(() => null);
    if (cached) {
      try {
        await api.delete(`/users/push-token?token=${encodeURIComponent(cached)}`);
      } catch {}
    }
    await AsyncStorage.removeItem(STORED_TOKEN_KEY).catch(() => {});
  } catch {}
}

/** Schedule a LOCAL notification right now. Used as a fallback in Expo Go where
 *  remote push is unsupported. The notification still goes through the same
 *  foreground/response listeners, so deep linking works for testing. */
export async function scheduleLocalTest(opts: { title: string; body: string; data?: Record<string, any> }) {
  await ensureAndroidChannel();
  await Notifications.scheduleNotificationAsync({
    content: {
      title: opts.title,
      body: opts.body,
      data: opts.data || {},
      sound: 'default',
    },
    trigger: null, // fire immediately
  });
}

// =====================================================================
// Notification → app route resolver. Used for both OS taps and in-app taps.
// =====================================================================

/** Build the deep-link route given a notification kind + payload data. */
export function routeForNotification(kind: string | undefined, data: any): string | null {
  if (!data || typeof data !== 'object') data = {};
  // Explicit override always wins
  const explicit = data.route || data.screen || data.url;
  if (typeof explicit === 'string' && explicit.startsWith('/')) return explicit;

  const k = (kind || '').toLowerCase();
  switch (k) {
    case 'daily_digest':
      return '/shopping-list';
    case 'contract_assigned':
    case 'contract_owner_signed':
    case 'contract_staff_signed':
      if (data.contract_id) return `/contract-view?id=${encodeURIComponent(String(data.contract_id))}`;
      return '/contracts';
    case 'task_assigned':
    case 'task_done':
    case 'task_comment':
      return '/(tabs)/household';
    case 'wage_paid':
    case 'wage_confirmed':
      return '/(tabs)/household';
    case 'shopping_request':
    case 'shopping_status':
      return '/(tabs)/household';
    default:
      return null;
  }
}

/** Convenience wrapper used by the OS notification response listener. */
export function routeFromNotificationData(data: any): string | null {
  return routeForNotification(data?.kind, data);
}
