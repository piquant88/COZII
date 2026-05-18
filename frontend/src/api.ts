import AsyncStorage from '@react-native-async-storage/async-storage';
import { Platform } from 'react-native';
import Constants from 'expo-constants';

/**
 * Backend URL resolution order:
 *   1. EXPO_PUBLIC_BACKEND_URL (set in /app/frontend/.env at build time)
 *   2. expo.extra.backendUrl from app.json (always shipped in the JS bundle)
 *   3. Hardcoded production fallback (last-resort safety net so native builds
 *      NEVER hit "Network request failed" because of a missing env var).
 *
 * On web in local dev we ALSO accept window.location.origin as a fallback so
 * `/api/*` routes go through the dev proxy, but for native builds we always
 * want the deployed URL.
 */

//const PROD_BACKEND_FALLBACK = 'https://family-wallet-21.preview.emergentagent.com';
const PROD_BACKEND_FALLBACK = 'https://cozii.onrender.com';

function resolveBackendUrl(): string {
  // 1) Build-time env var
  const fromEnv = (process.env.EXPO_PUBLIC_BACKEND_URL || '').trim();
  if (fromEnv) return fromEnv.replace(/\/+$/, '');

  // 2) app.json `expo.extra.backendUrl`
  const fromExtra = (Constants as any)?.expoConfig?.extra?.backendUrl
    || (Constants as any)?.manifest?.extra?.backendUrl
    || (Constants as any)?.manifest2?.extra?.expoClient?.extra?.backendUrl;
  if (typeof fromExtra === 'string' && fromExtra.trim()) {
    return fromExtra.trim().replace(/\/+$/, '');
  }

  // 3) Web local dev: same-origin proxy
  if (Platform.OS === 'web' && typeof window !== 'undefined' && window.location?.origin) {
    return window.location.origin.replace(/\/+$/, '');
  }

  // 4) Hardcoded prod fallback (never gives up)
  return PROD_BACKEND_FALLBACK;
}

const BASE_URL = resolveBackendUrl();

if (__DEV__) {
  // eslint-disable-next-line no-console
  console.log('[api] BASE_URL =', BASE_URL, '| platform =', Platform.OS);
}

const TOKEN_KEY = 'cozii_token';
const SPACE_KEY = 'cozii_active_space';

export const tokenStorage = {
  async get(): Promise<string | null> {
    try { return await AsyncStorage.getItem(TOKEN_KEY); } catch { return null; }
  },
  async set(token: string) {
    try { await AsyncStorage.setItem(TOKEN_KEY, token); } catch {}
  },
  async clear() {
    try { await AsyncStorage.removeItem(TOKEN_KEY); } catch {}
  },
};

export const activeSpaceStorage = {
  async get(): Promise<string | null> {
    try { return await AsyncStorage.getItem(SPACE_KEY); } catch { return null; }
  },
  async set(id: string) {
    try { await AsyncStorage.setItem(SPACE_KEY, id); } catch {}
  },
  async clear() {
    try { await AsyncStorage.removeItem(SPACE_KEY); } catch {}
  },
};

async function request<T = any>(
  method: string,
  path: string,
  body?: any,
): Promise<T> {
  const token = await tokenStorage.get();
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (token) headers['Authorization'] = `Bearer ${token}`;

  // `credentials: 'include'` is a web-only fetch option (for cookie-based
  // session). Including it on native is harmless but `fetch` polyfills behave
  // differently on some RN versions, so we omit it there.
  const init: RequestInit = {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  };
  if (Platform.OS === 'web') {
    (init as any).credentials = 'include';
  }

  let res: Response;
  try {
    res = await fetch(`${BASE_URL}/api${path}`, init);
  } catch (e: any) {
    // Surface a clearer message than "Network request failed"
    const reason = e?.message || 'unknown';
    const err: any = new Error(`Network error reaching ${BASE_URL}${path}: ${reason}`);
    err.cause = e;
    err.isNetworkError = true;
    throw err;
  }

  let data: any = null;
  const text = await res.text();
  try { data = text ? JSON.parse(text) : null; } catch { data = { raw: text }; }

  if (!res.ok) {
    const detail = (data && (data.detail || data.message)) || `Request failed (${res.status})`;
    const error: any = new Error(typeof detail === 'string' ? detail : 'Request failed');
    error.status = res.status;
    error.data = data;
    throw error;
  }
  return data as T;
}

export const api = {
  get: <T = any>(path: string) => request<T>('GET', path),
  post: <T = any>(path: string, body?: any) => request<T>('POST', path, body),
  patch: <T = any>(path: string, body?: any) => request<T>('PATCH', path, body),
  put: <T = any>(path: string, body?: any) => request<T>('PUT', path, body),
  delete: <T = any>(path: string) => request<T>('DELETE', path),
};

export { BASE_URL };
