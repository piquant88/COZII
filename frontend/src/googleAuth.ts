import { Platform } from 'react-native';
import * as WebBrowser from 'expo-web-browser';
import * as Linking from 'expo-linking';

// Pre-warm the WebBrowser auth session for snappier opens on Android.
try { (WebBrowser as any).maybeCompleteAuthSession?.(); } catch {}

// We hand off Google sign-in to Emergent's hosted OAuth page. After the user
// finishes signing in there, Emergent redirects back to our `redirect_url`
// with `#session_id=...` appended. We then call the backend
// `POST /api/auth/google-session` to exchange that for a real Cozii token.
//
// This keeps the same architecture we already use for web — we just need to
// open it in an in-app browser on native and listen for the callback URL.

//const EMERGENT_AUTH_BASE = 'https://auth.emergentagent.com/';
const EMERGENT_AUTH_BASE = 'https://cozii.onrender.com/api/auth/google/login';

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

export type GoogleSignInResult =
  | { status: 'success'; sessionId: string }
  | { status: 'cancel' }
  | { status: 'dismiss' }
  | { status: 'error'; message: string };

/** Open Emergent OAuth and resolve with the session_id (mobile native).
 *  On web, the caller should use the existing full-page redirect path. */
export async function googleSignInNative(): Promise<GoogleSignInResult> {
  if (Platform.OS === 'web') {
    return { status: 'error', message: 'Use the web redirect flow on web.' };
  }

  // Build a redirect URL that matches the app's scheme. e.g. `cozii://auth-callback`
  // We let expo-linking generate it so it's correct in both dev (Expo Go) and
  // production builds.
  const redirectUrl = Linking.createURL('auth-callback');
 // const authUrl = `${EMERGENT_AUTH_BASE}?redirect=${encodeURIComponent(redirectUrl)}`;
  const authUrl = `${EMERGENT_AUTH_BASE}?redirect_url=${encodeURIComponent(redirectUrl)}`;

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
    const sessionId = extractSessionId((result as any).url);
    if (sessionId) return { status: 'success', sessionId };
    return { status: 'error', message: 'OAuth completed but no session_id in callback URL' };
  }
  if (result.type === 'cancel') return { status: 'cancel' };
  if (result.type === 'dismiss') return { status: 'dismiss' };
  return { status: 'error', message: `Unknown WebBrowser result: ${result.type}` };
}
