import React from 'react';
import {
  View, Text, StyleSheet, TouchableOpacity, Image, Platform,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { colors, radius, spacing, shadows } from '../src/theme';

export default function Welcome() {
  const router = useRouter();

  const handleGoogle = () => {
    if (Platform.OS === 'web' && typeof window !== 'undefined') {
      // REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
      const redirectUrl = window.location.origin + '/';
      window.location.href = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(redirectUrl)}`;
    } else {
      // On native, fallback to email login for now
      router.push('/login');
    }
  };

  return (
    <View style={styles.container} testID="welcome-screen">
      <View style={styles.heroWrap}>
        <Image
          source={{ uri: 'https://images.unsplash.com/photo-1774578341766-081a4996a067?crop=entropy&cs=srgb&fm=jpg&q=85&w=1080' }}
          style={styles.hero}
          resizeMode="cover"
        />
        <View style={styles.heroOverlay} />
      </View>
      <SafeAreaView style={styles.bottomWrap} edges={['bottom']}>
        <View style={styles.textBlock}>
          <Text style={styles.brand}>Cozii</Text>
          <Text style={styles.tagline}>Your home, perfectly in place.</Text>
          <Text style={styles.subtitle}>
            Track what's in your pantry, closet, and wallet — together with the people you live with.
          </Text>
        </View>

        <View style={styles.actions}>
          <TouchableOpacity
            style={styles.googleBtn}
            onPress={handleGoogle}
            activeOpacity={0.85}
            testID="welcome-google-btn"
          >
            <Image
              source={{ uri: 'https://upload.wikimedia.org/wikipedia/commons/thumb/c/c1/Google_%22G%22_logo.svg/512px-Google_%22G%22_logo.svg.png' }}
              style={styles.googleIcon}
            />
            <Text style={styles.googleText}>Continue with Google</Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={styles.primaryBtn}
            onPress={() => router.push('/signup')}
            activeOpacity={0.85}
            testID="welcome-signup-btn"
          >
            <Text style={styles.primaryText}>Create account</Text>
          </TouchableOpacity>

          <TouchableOpacity onPress={() => router.push('/login')} testID="welcome-login-link">
            <Text style={styles.loginLink}>
              Already have an account? <Text style={styles.loginLinkBold}>Log in</Text>
            </Text>
          </TouchableOpacity>
        </View>
      </SafeAreaView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background },
  heroWrap: { flex: 1, overflow: 'hidden', borderBottomLeftRadius: 40, borderBottomRightRadius: 40 },
  hero: { width: '100%', height: '100%' },
  heroOverlay: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: 'rgba(255, 181, 167, 0.12)',
  },
  bottomWrap: {
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.xl,
    paddingBottom: spacing.md,
    backgroundColor: colors.background,
  },
  textBlock: { marginBottom: spacing.xl },
  brand: {
    fontSize: 42,
    fontWeight: '900',
    color: colors.textMain,
    letterSpacing: -1,
  },
  tagline: {
    fontSize: 18,
    fontWeight: '700',
    color: colors.textMain,
    marginTop: 4,
  },
  subtitle: {
    fontSize: 14,
    color: colors.textMuted,
    marginTop: spacing.sm,
    lineHeight: 20,
  },
  actions: { gap: spacing.sm },
  googleBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.surface,
    paddingVertical: 16,
    borderRadius: radius.full,
    borderWidth: 1,
    borderColor: colors.border,
    gap: 10,
  },
  googleIcon: { width: 20, height: 20 },
  googleText: { color: colors.textMain, fontWeight: '700', fontSize: 15 },
  primaryBtn: {
    backgroundColor: colors.primary,
    paddingVertical: 16,
    borderRadius: radius.full,
    alignItems: 'center',
    ...shadows.button,
  },
  primaryText: { color: '#fff', fontWeight: '800', fontSize: 15 },
  loginLink: {
    textAlign: 'center',
    color: colors.textMuted,
    marginTop: spacing.sm,
    fontSize: 14,
  },
  loginLinkBold: { color: colors.textMain, fontWeight: '700' },
});
