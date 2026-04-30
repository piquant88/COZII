import React, { useState } from 'react';
import {
  View, Text, StyleSheet, TouchableOpacity, TextInput,
  KeyboardAvoidingView, Platform, ScrollView,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { useAuth } from '../src/AuthContext';
import { colors, radius, spacing, shadows } from '../src/theme';
import { Icon } from '../src/Icon';

export default function Signup() {
  const router = useRouter();
  const { register } = useAuth();
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const onSubmit = async () => {
    if (!name || !email || !password) {
      setErr('Please fill in all fields.');
      return;
    }
    if (password.length < 6) {
      setErr('Password must be at least 6 characters.');
      return;
    }
    setLoading(true);
    setErr(null);
    try {
      await register(email.trim(), password, name.trim());
      router.replace('/');
    } catch (e: any) {
      setErr(e?.message || 'Signup failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <SafeAreaView style={styles.container} edges={['top', 'bottom']}>
      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={{ flex: 1 }}>
        <ScrollView contentContainerStyle={styles.scroll} keyboardShouldPersistTaps="handled">
          <TouchableOpacity style={styles.backBtn} onPress={() => router.back()} testID="signup-back">
            <Icon name="ArrowLeft" color={colors.textMain} />
          </TouchableOpacity>

          <Text style={styles.title}>Make yourself at home</Text>
          <Text style={styles.subtitle}>Create your Cozii account</Text>

          <View style={styles.field}>
            <Text style={styles.label}>Your name</Text>
            <TextInput
              style={styles.input}
              placeholder="Ex. Jamie"
              placeholderTextColor="#95A5A6"
              value={name}
              onChangeText={setName}
              testID="signup-name"
            />
          </View>
          <View style={styles.field}>
            <Text style={styles.label}>Email</Text>
            <TextInput
              style={styles.input}
              placeholder="you@home.com"
              placeholderTextColor="#95A5A6"
              autoCapitalize="none"
              autoCorrect={false}
              keyboardType="email-address"
              value={email}
              onChangeText={setEmail}
              testID="signup-email"
            />
          </View>
          <View style={styles.field}>
            <Text style={styles.label}>Password</Text>
            <TextInput
              style={styles.input}
              placeholder="At least 6 characters"
              placeholderTextColor="#95A5A6"
              secureTextEntry
              value={password}
              onChangeText={setPassword}
              testID="signup-password"
            />
          </View>

          {err && <Text style={styles.error} testID="signup-error">{err}</Text>}

          <TouchableOpacity
            style={[styles.primaryBtn, loading && { opacity: 0.6 }]}
            onPress={onSubmit}
            disabled={loading}
            activeOpacity={0.85}
            testID="signup-submit"
          >
            <Text style={styles.primaryText}>{loading ? 'Creating...' : 'Create account'}</Text>
          </TouchableOpacity>

          <TouchableOpacity onPress={() => router.replace('/login')} testID="signup-to-login">
            <Text style={styles.altLink}>
              Have an account? <Text style={{ fontWeight: '700', color: colors.textMain }}>Log in</Text>
            </Text>
          </TouchableOpacity>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background },
  scroll: { padding: spacing.lg, paddingTop: spacing.md },
  backBtn: {
    width: 44, height: 44, borderRadius: 22,
    backgroundColor: colors.surface,
    alignItems: 'center', justifyContent: 'center',
    marginBottom: spacing.lg,
    ...shadows.card,
  },
  title: { fontSize: 28, fontWeight: '900', color: colors.textMain, letterSpacing: -0.5 },
  subtitle: { fontSize: 14, color: colors.textMuted, marginTop: 6, marginBottom: spacing.xl },
  field: { marginBottom: spacing.md },
  label: { fontSize: 12, fontWeight: '700', color: colors.textMuted, marginBottom: 8, textTransform: 'uppercase', letterSpacing: 0.5 },
  input: {
    backgroundColor: colors.surfaceAlt,
    borderRadius: radius.md,
    paddingHorizontal: spacing.md,
    paddingVertical: 14,
    fontSize: 15,
    color: colors.textMain,
  },
  error: { color: colors.dangerText, marginBottom: spacing.sm, fontSize: 13 },
  primaryBtn: {
    backgroundColor: colors.primary,
    paddingVertical: 16,
    borderRadius: radius.full,
    alignItems: 'center',
    marginTop: spacing.sm,
    ...shadows.button,
  },
  primaryText: { color: '#fff', fontWeight: '800', fontSize: 15 },
  altLink: { textAlign: 'center', color: colors.textMuted, marginTop: spacing.lg, fontSize: 14 },
});
