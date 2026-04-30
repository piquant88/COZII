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

export default function SpaceSetup() {
  const router = useRouter();
  const { createSpace, joinSpace, logout } = useAuth();
  const [mode, setMode] = useState<'create' | 'join'>('create');
  const [spaceName, setSpaceName] = useState('');
  const [inviteCode, setInviteCode] = useState('');
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const onSubmit = async () => {
    setErr(null);
    setLoading(true);
    try {
      if (mode === 'create') {
        if (!spaceName.trim()) {
          setErr('Give your home a name');
          setLoading(false);
          return;
        }
        await createSpace(spaceName.trim());
      } else {
        if (!inviteCode.trim()) {
          setErr('Enter an invite code');
          setLoading(false);
          return;
        }
        await joinSpace(inviteCode.trim());
      }
      router.replace('/(tabs)/home');
    } catch (e: any) {
      setErr(e?.message || 'Something went wrong');
    } finally {
      setLoading(false);
    }
  };

  return (
    <SafeAreaView style={styles.container} edges={['top', 'bottom']}>
      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={{ flex: 1 }}>
        <ScrollView contentContainerStyle={styles.scroll} keyboardShouldPersistTaps="handled">
          <View style={styles.topRow}>
            <View style={{ flex: 1 }} />
            <TouchableOpacity onPress={logout} testID="space-setup-logout">
              <Text style={styles.logoutTxt}>Log out</Text>
            </TouchableOpacity>
          </View>

          <Text style={styles.title}>Set up your space</Text>
          <Text style={styles.subtitle}>
            A space is a shared home — pantry, toiletries, budget — synced with the people you live with.
          </Text>

          <View style={styles.tabRow}>
            <TouchableOpacity
              style={[styles.tab, mode === 'create' && styles.tabActive]}
              onPress={() => setMode('create')}
              testID="space-setup-tab-create"
            >
              <Text style={[styles.tabTxt, mode === 'create' && styles.tabTxtActive]}>Create</Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={[styles.tab, mode === 'join' && styles.tabActive]}
              onPress={() => setMode('join')}
              testID="space-setup-tab-join"
            >
              <Text style={[styles.tabTxt, mode === 'join' && styles.tabTxtActive]}>Join</Text>
            </TouchableOpacity>
          </View>

          {mode === 'create' ? (
            <View style={styles.field}>
              <Text style={styles.label}>Home name</Text>
              <TextInput
                style={styles.input}
                placeholder="Ex. The Apartment"
                placeholderTextColor="#95A5A6"
                value={spaceName}
                onChangeText={setSpaceName}
                testID="space-setup-name"
              />
              <Text style={styles.hint}>We'll create starter categories (Food, Skincare, Closet...) you can customize.</Text>
            </View>
          ) : (
            <View style={styles.field}>
              <Text style={styles.label}>Invite code</Text>
              <TextInput
                style={[styles.input, { letterSpacing: 3, fontWeight: '700', textAlign: 'center' }]}
                placeholder="XXXXXX"
                placeholderTextColor="#95A5A6"
                autoCapitalize="characters"
                maxLength={6}
                value={inviteCode}
                onChangeText={(t) => setInviteCode(t.toUpperCase())}
                testID="space-setup-invite"
              />
              <Text style={styles.hint}>Ask your roommate for the 6-character code from their Profile.</Text>
            </View>
          )}

          {err && <Text style={styles.error} testID="space-setup-error">{err}</Text>}

          <TouchableOpacity
            style={[styles.primaryBtn, loading && { opacity: 0.6 }]}
            onPress={onSubmit}
            disabled={loading}
            activeOpacity={0.85}
            testID="space-setup-submit"
          >
            <Text style={styles.primaryText}>
              {loading ? 'Please wait...' : mode === 'create' ? 'Create space' : 'Join space'}
            </Text>
          </TouchableOpacity>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background },
  scroll: { padding: spacing.lg },
  topRow: { flexDirection: 'row', alignItems: 'center', marginBottom: spacing.xl },
  logoutTxt: { color: colors.textMuted, fontWeight: '600' },
  title: { fontSize: 28, fontWeight: '900', color: colors.textMain, letterSpacing: -0.5 },
  subtitle: { fontSize: 14, color: colors.textMuted, marginTop: 6, marginBottom: spacing.xl, lineHeight: 20 },
  tabRow: {
    flexDirection: 'row',
    backgroundColor: colors.surfaceAlt,
    borderRadius: radius.full,
    padding: 4,
    marginBottom: spacing.lg,
  },
  tab: { flex: 1, alignItems: 'center', paddingVertical: 10, borderRadius: radius.full },
  tabActive: { backgroundColor: colors.surface, ...shadows.card },
  tabTxt: { fontSize: 14, fontWeight: '700', color: colors.textMuted },
  tabTxtActive: { color: colors.textMain },
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
  hint: { fontSize: 12, color: colors.textMuted, marginTop: 8 },
  error: { color: colors.dangerText, marginBottom: spacing.sm, fontSize: 13 },
  primaryBtn: {
    backgroundColor: colors.primary,
    paddingVertical: 16,
    borderRadius: radius.full,
    alignItems: 'center',
    marginTop: spacing.md,
    ...shadows.button,
  },
  primaryText: { color: '#fff', fontWeight: '800', fontSize: 15 },
});
