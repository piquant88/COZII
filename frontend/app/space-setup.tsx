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
  const { createSpace, joinSpace, logout, spaces } = useAuth();
  const [mode, setMode] = useState<'create' | 'join'>('create');
  const [step, setStep] = useState<'form' | 'pickType'>('form');
  const [spaceName, setSpaceName] = useState('');
  const [inviteCode, setInviteCode] = useState('');
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const hasExistingSpace = spaces.length > 0;

  const goBack = () => {
    if (step === 'pickType') {
      setStep('form');
      return;
    }
    if (hasExistingSpace) {
      router.back();
    }
  };

  const onContinue = () => {
    setErr(null);
    if (mode === 'join') {
      if (!inviteCode.trim()) { setErr('Enter an invite code'); return; }
      onJoin();
      return;
    }
    if (!spaceName.trim()) { setErr('Give your home a name'); return; }
    setStep('pickType');
  };

  const onJoin = async () => {
    setErr(null); setLoading(true);
    try {
      await joinSpace(inviteCode.trim());
      router.replace('/(tabs)/home');
    } catch (e: any) { setErr(e?.message || 'Something went wrong'); }
    finally { setLoading(false); }
  };

  const onCreate = async (space_type: 'roommates' | 'household') => {
    setErr(null); setLoading(true);
    try {
      await createSpace(spaceName.trim(), { space_type });
      router.replace('/(tabs)/home');
    } catch (e: any) { setErr(e?.message || 'Something went wrong'); }
    finally { setLoading(false); }
  };

  return (
    <SafeAreaView style={styles.container} edges={['top', 'bottom']}>
      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={{ flex: 1 }}>
        <ScrollView contentContainerStyle={styles.scroll} keyboardShouldPersistTaps="handled">
          <View style={styles.topRow}>
            {hasExistingSpace ? (
              <TouchableOpacity
                style={styles.backBtn}
                onPress={goBack}
                testID="space-setup-back"
              >
                <Icon name="X" color={colors.textMain} size={20} />
              </TouchableOpacity>
            ) : (
              <View style={{ width: 40 }} />
            )}
            <View style={{ flex: 1 }} />
            {!hasExistingSpace && (
              <TouchableOpacity onPress={logout} testID="space-setup-logout">
                <Text style={styles.logoutTxt}>Log out</Text>
              </TouchableOpacity>
            )}
          </View>

          <Text style={styles.title}>{step === 'pickType' ? 'What kind of space?' : 'Set up your space'}</Text>
          <Text style={styles.subtitle}>
            {step === 'pickType'
              ? `For "${spaceName}", pick the experience that fits best. You can change this later.`
              : 'A space is a shared home — pantry, toiletries, budget — synced with the people you live with.'}
          </Text>

          {step === 'form' && (
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
          )}

          {step === 'form' && mode === 'create' && (
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
          )}
          {step === 'form' && mode === 'join' && (
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

          {step === 'pickType' && (
            <View style={{ gap: spacing.md, marginTop: spacing.sm }}>
              <TouchableOpacity
                style={styles.typeCard}
                onPress={() => onCreate('roommates')}
                disabled={loading}
                testID="space-setup-type-roommates"
                activeOpacity={0.85}
              >
                <View style={[styles.typeIcon, { backgroundColor: '#FFE4DC' }]}>
                  <Icon name="Users" color="#D45B43" size={28} />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={styles.typeTitle}>Roommates</Text>
                  <Text style={styles.typeSub}>Shared rent + groceries with friends or housemates. Focus on splitting costs and shared inventory.</Text>
                </View>
                <Icon name="ChevronRight" size={18} color={colors.textMuted} />
              </TouchableOpacity>

              <TouchableOpacity
                style={styles.typeCard}
                onPress={() => onCreate('household')}
                disabled={loading}
                testID="space-setup-type-household"
                activeOpacity={0.85}
              >
                <View style={[styles.typeIcon, { backgroundColor: '#E8F0FA' }]}>
                  <Icon name="Home" color="#5079A8" size={28} />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={styles.typeTitle}>Household</Text>
                  <Text style={styles.typeSub}>You manage a home with family + helpers (maids, drivers, nannies). Adds Family directory, Staff roster, Roles & Handbook.</Text>
                </View>
                <Icon name="ChevronRight" size={18} color={colors.textMuted} />
              </TouchableOpacity>
            </View>
          )}

          {err && <Text style={styles.error} testID="space-setup-error">{err}</Text>}

          {step === 'form' && (
            <TouchableOpacity
              style={[styles.primaryBtn, loading && { opacity: 0.6 }]}
              onPress={onContinue}
              disabled={loading}
              activeOpacity={0.85}
              testID="space-setup-submit"
            >
              <Text style={styles.primaryText}>
                {loading ? 'Please wait...' : mode === 'create' ? 'Continue' : 'Join space'}
              </Text>
            </TouchableOpacity>
          )}
          {step === 'pickType' && loading && (
            <Text style={[styles.hint, { textAlign: 'center', marginTop: spacing.md }]}>Creating space…</Text>
          )}
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background },
  scroll: { padding: spacing.lg },
  topRow: { flexDirection: 'row', alignItems: 'center', marginBottom: spacing.xl },
  backBtn: {
    width: 40, height: 40, borderRadius: 20,
    backgroundColor: colors.surface,
    alignItems: 'center', justifyContent: 'center',
    ...shadows.card,
  },
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
  typeCard: {
    flexDirection: 'row', alignItems: 'center', gap: 14,
    backgroundColor: colors.surface, borderRadius: radius.lg,
    padding: spacing.md, borderWidth: 1, borderColor: colors.border,
    ...shadows.card,
  },
  typeIcon: { width: 56, height: 56, borderRadius: 18, alignItems: 'center', justifyContent: 'center' },
  typeTitle: { fontSize: 16, fontWeight: '800', color: colors.textMain },
  typeSub: { fontSize: 12, color: colors.textMuted, marginTop: 4, lineHeight: 18 },
});
