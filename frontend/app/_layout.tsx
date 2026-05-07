import React, { useEffect, useRef } from 'react';
import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import { AuthProvider, useAuth } from '../src/AuthContext';
import { Platform } from 'react-native';
import { useRouter } from 'expo-router';
import * as Notifications from 'expo-notifications';
import { installNotificationHandler, routeFromNotificationData } from '../src/pushNotifications';

// Install the foreground notification handler at module load (must be early).
installNotificationHandler();

function GoogleSessionInterceptor({ children }: { children: React.ReactNode }) {
  const { loginWithGoogleSession } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (Platform.OS !== 'web') return;
    const hash = typeof window !== 'undefined' ? window.location.hash : '';
    if (!hash || !hash.includes('session_id=')) return;
    const match = hash.match(/session_id=([^&]+)/);
    if (!match) return;
    const sessionId = decodeURIComponent(match[1]);
    if (typeof window !== 'undefined' && window.history && window.history.replaceState) {
      window.history.replaceState(null, '', window.location.pathname + window.location.search);
    }
    (async () => {
      try {
        await loginWithGoogleSession(sessionId);
        router.replace('/(tabs)/home');
      } catch (e) {
        console.warn('Google session exchange failed', e);
      }
    })();
  }, []);

  return <>{children}</>;
}

/** Listens for notification taps and deep-links into the right route.
 *  Also handles cold-start where the app is opened *from* a notification. */
function NotificationDeepLinker({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const { user } = useAuth();
  const handledColdStartRef = useRef(false);

  useEffect(() => {
    if (Platform.OS === 'web') return;

    // Foreground / background tap: user tapped a notification while app was running.
    const sub = Notifications.addNotificationResponseReceivedListener((response) => {
      try {
        const data = response?.notification?.request?.content?.data;
        const route = routeFromNotificationData(data);
        if (route) {
          // Slight delay so router is mounted
          setTimeout(() => {
            try { (router as any).push(route); } catch (e) { console.warn('deep link nav failed', e); }
          }, 50);
        }
      } catch (e) {
        console.warn('notification response handler error', e);
      }
    });

    // Cold start: app was launched directly from a notification tap.
    (async () => {
      if (handledColdStartRef.current) return;
      handledColdStartRef.current = true;
      try {
        const last = await Notifications.getLastNotificationResponseAsync();
        const data = last?.notification?.request?.content?.data;
        const route = routeFromNotificationData(data);
        if (route) {
          // Wait for auth + router to be ready before pushing
          setTimeout(() => {
            if (user) {
              try { (router as any).push(route); } catch (e) { console.warn('cold-start nav failed', e); }
            }
          }, 800);
        }
      } catch (e) {
        console.warn('cold-start notification check failed', e);
      }
    })();

    return () => { sub.remove(); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user]);

  return <>{children}</>;
}

export default function RootLayout() {
  return (
    <GestureHandlerRootView style={{ flex: 1 }}>
      <SafeAreaProvider>
        <AuthProvider>
          <GoogleSessionInterceptor>
            <NotificationDeepLinker>
              <StatusBar style="dark" />
              <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: '#FEF9F8' } }} />
            </NotificationDeepLinker>
          </GoogleSessionInterceptor>
        </AuthProvider>
      </SafeAreaProvider>
    </GestureHandlerRootView>
  );
}
