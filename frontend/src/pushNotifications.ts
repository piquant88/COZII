import { Platform } from 'react-native';
import * as Notifications from 'expo-notifications';
import * as Device from 'expo-device';
import Constants from 'expo-constants';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { api } from './api';

const STORED_TOKEN_KEY = 'cozii_expo_push_token';

// Handler that decides what to do when a notification arrives while the app
// is in the foreground. We always show banner + list + sound for parity with
// the lockscreen experience.
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
  // Try multiple known locations across Expo versions.
  const c: any = Constants;
  return (
    c?.expoConfig?.extra?.eas?.projectId ||
    c?.easConfig?.projectId ||
    c?.manifest2?.extra?.eas?.projectId ||
    c?.manifest?.extra?.eas?.projectId ||
    null
  );
}

async function ensurePermissionsAsync(): Promise<boolean> {
  try {
    const existing = await Notifications.getPermissionsAsync();
    if (existing.status === 'granted') return true;
    if (!existing.canAskAgain) return false;
    const req = await Notifications.requestPermissionsAsync();
    return req.status === 'granted';
  } catch (e) {
    console.warn('[push] permission error', e);
    return false;
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

/** Register this device for push notifications and POST the token to the backend.
 *  Idempotent: safe to call multiple times. Silently no-ops on web / simulators / when
 *  no projectId is configured.
 */
export async function registerForPushAsync(): Promise<string | null> {
  if (Platform.OS === 'web') return null; // Expo push is mobile-only
  try {
    if (!Device.isDevice) {
      console.log('[push] skipping: not a physical device');
      return null;
    }
    await ensureAndroidChannel();
    const ok = await ensurePermissionsAsync();
    if (!ok) {
      console.log('[push] permission not granted');
      return null;
    }
    const projectId = resolveProjectId();
    let tokenData;
    try {
      tokenData = projectId
        ? await Notifications.getExpoPushTokenAsync({ projectId })
        : await Notifications.getExpoPushTokenAsync();
    } catch (e: any) {
      // Most common cause in dev: no EAS projectId configured. Don't crash the app.
      console.warn('[push] getExpoPushTokenAsync failed:', e?.message || e);
      return null;
    }
    const token = tokenData?.data || null;
    if (!token) return null;

    // Avoid POSTing the same token to the server on every cold start.
    const cached = await AsyncStorage.getItem(STORED_TOKEN_KEY).catch(() => null);
    if (cached === token) {
      return token;
    }

    try {
      await api.post('/users/push-token', {
        token,
        platform: Platform.OS,
        device_name: Device.deviceName || Device.modelName || null,
      });
      await AsyncStorage.setItem(STORED_TOKEN_KEY, token);
    } catch (e) {
      console.warn('[push] failed to register token with backend', e);
    }

    return token;
  } catch (e) {
    console.warn('[push] registerForPushAsync outer failure', e);
    return null;
  }
}

/** Best-effort: tell backend to deactivate the cached token (called on logout). */
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

/** Extract the deep-link route from a notification payload. */
export function routeFromNotificationData(data: any): string | null {
  if (!data || typeof data !== 'object') return null;
  const r = data.route || data.screen || data.url;
  if (typeof r === 'string' && r.startsWith('/')) return r;
  return null;
}
