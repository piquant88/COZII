import React, { useEffect } from 'react';
import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import { AuthProvider, useAuth } from '../src/AuthContext';
import { Platform } from 'react-native';
import { useRouter } from 'expo-router';

function GoogleSessionInterceptor({ children }: { children: React.ReactNode }) {
  const { loginWithGoogleSession } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (Platform.OS !== 'web') return;
    const hash = typeof window !== 'undefined' ? window.location.hash : '';
    if (!hash || !hash.includes('session_id=')) return;
    // Parse session_id from URL fragment
    const match = hash.match(/session_id=([^&]+)/);
    if (!match) return;
    const sessionId = decodeURIComponent(match[1]);
    // Clear fragment
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

export default function RootLayout() {
  return (
    <GestureHandlerRootView style={{ flex: 1 }}>
      <SafeAreaProvider>
        <AuthProvider>
          <GoogleSessionInterceptor>
            <StatusBar style="dark" />
            <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: '#FEF9F8' } }} />
          </GoogleSessionInterceptor>
        </AuthProvider>
      </SafeAreaProvider>
    </GestureHandlerRootView>
  );
}
