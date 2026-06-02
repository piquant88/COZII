import { Platform } from 'react-native';
import * as WebBrowser from 'expo-web-browser';
import * as Linking from 'expo-linking';
import Constants from 'expo-constants';
import { BASE_URL } from './api';

// Pre-warm the WebBrowser auth session for snappier opens on Android.
try { (WebBrowser as any).maybeCompleteAuthSession?.(); } catch {}

// Resolve the Google OAuth landing URL on the Cozii backend.
// Priority:
//   1. EXPO_PUBLIC_GOOGLE_AUTH_URL (build-time env override, rarely used)
//   2. app.json → expo.extra.googleAuthUrl
//   3. `${BASE_URL}/auth/google/start` (the Cozii Render backend OAuth entrypoint)
function resolveGoogleAuthUrl(): string {
  const fromEnv = (process.env.EXPO_PUBLIC_GOOGLE_AUTH_URL || '').trim();
  if (fromEnv) return fromEnv.replace(/\/+$/, '');
  const fromExtra = (Constants as any)?.expoConfig?.extra?.googleAuthUrl
    || (Constants as any)?.manifest?.extra?.googleAuthUrl;
  if (typeof fromExtra === 'string' && fromExtra.trim()) {
    return fromExtra.trim().replace(/\/+$/, '');
  }
  return `${BASE_URL}/auth/google/start`;
}

export const GOOGLE_AUTH_URL = resolveGoogleAuthUrl();

/** Parse a redirect URL like `cozii://auth-callback#session_id=xyz` and pull
 *  out the session_id. Supports both hash-fragment and query-string variants. */
function extractSessionId(url: string | null | undefined): string | null {
  if (!url) return null;
  try {
    // Hash fragment form
    const hashIdx = url.indexOf('#');
    if (hashIdx >= 0) {
      const hash = url.slice(hashIdx + 1);
      const params = new URLSearchParams(hash);
      const sid = params.get('session_id');
      if (sid) return sid;
    }
    // Query-string form
    const qIdx = url.indexOf('?');
    if (qIdx >= 0) {
      const params = new URLSearchParams(url.slice(qIdx + 1));
      const sid = params.get('session_id');
      if (sid) return sid;
    }
  } catch {}
  return null;
}

function extractAuthError(url: string | null | undefined): string | null {
  if (!url) return null;
  try {
    const qIdx = url.indexOf('?');
    if (qIdx >= 0) {
      const params = new URLSearchParams(url.slice(qIdx + 1));
      const e = params.get('auth_error');
      if (e) return decodeURIComponent(e);
    }
  } catch {}
  return null;
}

export type GoogleSignInResult =
  | { status: 'success'; sessionId: string }
  | { status: 'cancel' }
  | { status: 'dismiss' }
  | { status: 'error'; message: string };

/** Open the Cozii-hosted Google OAuth flow on the Render backend, capture the
 *  session_id from the redirect URL, and resolve. On web, the caller should
 *  use the existing full-page redirect path instead. */
export async function googleSignInNative(): Promise<GoogleSignInResult> {
  if (Platform.OS === 'web') {
    return { status: 'error', message: 'Use the web redirect flow on web.' };
  }

  // Build a redirect URL that matches the app's scheme. e.g. `cozii://auth-callback`
  // We let expo-linking generate it so it's correct in both dev (Expo Go) and
  // production builds.
  const redirectUrl = Linking.createURL('auth-callback');
  const authUrl = `${GOOGLE_AUTH_URL}?redirect=${encodeURIComponent(redirectUrl)}`;

  let result;
  try {
    result = await WebBrowser.openAuthSessionAsync(authUrl, redirectUrl, {
      showInRecents: false,
      // iOS: prefer ASWebAuthenticationSession (built-in), more reliable
      preferEphemeralSession: false,
    });
  } catch (e: any) {
    return { status: 'error', message: e?.message || 'Browser failed to open' };
  }

  if (result.type === 'success' && (result as any).url) {
    const url = (result as any).url as string;
    const errMsg = extractAuthError(url);
    if (errMsg) return { status: 'error', message: errMsg };
    const sessionId = extractSessionId(url);
    if (sessionId) return { status: 'success', sessionId };
    return { status: 'error', message: 'OAuth completed but no session_id in callback URL' };
  }
  if (result.type === 'cancel') return { status: 'cancel' };
  if (result.type === 'dismiss') return { status: 'dismiss' };
  return { status: 'error', message: `Unknown WebBrowser result: ${result.type}` };
}
