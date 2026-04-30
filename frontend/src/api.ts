import AsyncStorage from '@react-native-async-storage/async-storage';

const BASE_URL = process.env.EXPO_PUBLIC_BACKEND_URL;

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

  const res = await fetch(`${BASE_URL}/api${path}`, {
    method,
    headers,
    credentials: 'include',
    body: body ? JSON.stringify(body) : undefined,
  });

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
