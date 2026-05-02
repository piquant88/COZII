import React, { useState, useCallback } from 'react';
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity, Alert, Platform, Modal,
} from 'react-native';
import * as Clipboard from 'expo-clipboard';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter, useFocusEffect } from 'expo-router';
import { useAuth } from '../../src/AuthContext';
import { colors, radius, spacing, shadows } from '../../src/theme';
import { Icon } from '../../src/Icon';
import { api } from '../../src/api';
import { CURRENCIES, getCurrency } from '../../src/currency';
import type { User, FamilySpace } from '../../src/types';

export default function Profile() {
  const router = useRouter();
  const { user, logout, activeSpace, spaces, setActiveSpaceId, refreshSpaces } = useAuth() as any;
  const [members, setMembers] = useState<User[]>([]);
  const [copied, setCopied] = useState(false);
  const [showCurrency, setShowCurrency] = useState(false);
  const [savingCur, setSavingCur] = useState(false);

  const load = useCallback(async () => {
    if (!activeSpace) return;
    try {
      const m = await api.get<User[]>(`/spaces/${activeSpace.space_id}/members`);
      setMembers(m);
    } catch (e) { console.warn(e); }
  }, [activeSpace]);

  useFocusEffect(useCallback(() => { load(); }, [load]));

  const copyCode = async () => {
    if (!activeSpace) return;
    try {
      if (Platform.OS === 'web' && typeof navigator !== 'undefined' && navigator.clipboard) {
        await navigator.clipboard.writeText(activeSpace.invite_code);
      } else {
        await Clipboard.setStringAsync(activeSpace.invite_code);
      }
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {}
  };

  const doLogout = async () => {
    await logout();
    router.replace('/welcome');
  };

  const setSpaceCurrency = async (code: string) => {
    if (!activeSpace) return;
    setSavingCur(true);
    try {
      await api.patch(`/spaces/${activeSpace.space_id}`, { currency: code });
      await refreshSpaces?.();
      setShowCurrency(false);
    } catch (e: any) {
      Alert.alert('Error', e?.message || 'Failed to update');
    } finally { setSavingCur(false); }
  };

  const [showSpaceType, setShowSpaceType] = useState(false);
  const setSpaceType = async (next: 'roommates' | 'household') => {
    if (!activeSpace || activeSpace.space_type === next) { setShowSpaceType(false); return; }
    try {
      await api.patch(`/spaces/${activeSpace.space_id}`, { space_type: next });
      await refreshSpaces?.();
      setShowSpaceType(false);
    } catch (e: any) { Alert.alert('Error', e?.message || ''); }
  };

  const currentCur = getCurrency(activeSpace?.currency);

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <ScrollView contentContainerStyle={styles.scroll} showsVerticalScrollIndicator={false}>
        <Text style={styles.title}>Profile</Text>

        <View style={styles.profileCard}>
          <View style={styles.avatar}>
            <Text style={styles.avatarTxt}>{user?.name?.[0]?.toUpperCase() || '?'}</Text>
          </View>
          <View style={{ flex: 1 }}>
            <Text style={styles.profileName} testID="profile-name">{user?.name || 'You'}</Text>
            <Text style={styles.profileEmail}>{user?.email}</Text>
          </View>
        </View>

        {activeSpace && (
          <>
            <Text style={styles.sectionTitle}>Current space</Text>
            <View style={styles.card}>
              <Text style={styles.spaceName}>{activeSpace.name}</Text>
              <Text style={styles.spaceSub}>{members.length} {members.length === 1 ? 'member' : 'members'}</Text>

              <TouchableOpacity style={styles.inviteBox} onPress={copyCode} activeOpacity={0.8} testID="profile-copy-invite">
                <View style={{ flex: 1 }}>
                  <Text style={styles.inviteLbl}>Invite code</Text>
                  <Text style={styles.inviteCode} testID="profile-invite-code">{activeSpace.invite_code}</Text>
                </View>
                <View style={styles.copyBtn}>
                  <Icon name={copied ? 'Check' : 'Copy'} size={16} color={colors.textMain} />
                  <Text style={styles.copyTxt}>{copied ? 'Copied' : 'Copy'}</Text>
                </View>
              </TouchableOpacity>

              <Text style={styles.membersTitle}>Members</Text>
              {members.map((m) => (
                <View key={m.user_id} style={styles.memberRow}>
                  <View style={[styles.memberAvatar, { backgroundColor: m.user_id === activeSpace.owner_id ? colors.peach : colors.lavender }]}>
                    <Text style={styles.memberAvatarTxt}>{m.name?.[0]?.toUpperCase()}</Text>
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.memberName}>{m.name}{m.user_id === user?.user_id ? ' (You)' : ''}</Text>
                    <Text style={styles.memberEmail}>{m.email}</Text>
                  </View>
                  {m.user_id === activeSpace.owner_id && (
                    <View style={styles.ownerBadge}><Text style={styles.ownerTxt}>Owner</Text></View>
                  )}
                </View>
              ))}
            </View>
          </>
        )}

        {spaces.length > 1 && (
          <>
            <Text style={styles.sectionTitle}>Switch space</Text>
            <View style={styles.card}>
              {spaces.map((s) => (
                <TouchableOpacity
                  key={s.space_id}
                  style={styles.memberRow}
                  onPress={() => setActiveSpaceId(s.space_id)}
                >
                  <Icon name="Home" size={18} color={colors.textMain} />
                  <Text style={[styles.memberName, { flex: 1, marginLeft: 10 }]}>{s.name}</Text>
                  {activeSpace?.space_id === s.space_id && <Icon name="Check" size={18} color={colors.primary} />}
                </TouchableOpacity>
              ))}
            </View>
          </>
        )}

        <TouchableOpacity
          style={[styles.card, styles.rowBtn]}
          onPress={() => setShowSpaceType(true)}
          testID="profile-space-type"
        >
          <Icon name={activeSpace?.space_type === 'household' ? 'Home' : 'Users'} size={20} color={colors.textMain} />
          <Text style={styles.rowBtnTxt}>Space type</Text>
          <Text style={{ color: colors.textMuted, fontWeight: '700', fontSize: 13 }}>
            {activeSpace?.space_type === 'household' ? 'Household' : 'Roommates'}
          </Text>
          <Icon name="ChevronRight" size={18} color={colors.textMuted} />
        </TouchableOpacity>

        <TouchableOpacity
          style={[styles.card, styles.rowBtn]}
          onPress={() => setShowCurrency(true)}
          testID="profile-currency"
        >
          <Icon name="DollarSign" size={20} color={colors.textMain} />
          <Text style={styles.rowBtnTxt}>Currency</Text>
          <Text style={{ color: colors.textMuted, fontWeight: '700', fontSize: 13 }}>
            {currentCur.code} · {currentCur.symbol}
          </Text>
          <Icon name="ChevronRight" size={18} color={colors.textMuted} />
        </TouchableOpacity>

        <TouchableOpacity
          style={[styles.card, styles.rowBtn]}
          onPress={() => router.push('/report')}
          testID="profile-report"
        >
          <Icon name="FileText" size={20} color={colors.textMain} />
          <Text style={styles.rowBtnTxt}>Finance report & export</Text>
          <Icon name="ChevronRight" size={18} color={colors.textMuted} />
        </TouchableOpacity>

        <TouchableOpacity
          style={[styles.card, styles.rowBtn]}
          onPress={() => router.push('/splits')}
          testID="profile-splits"
        >
          <Icon name="Users" size={20} color={colors.textMain} />
          <Text style={styles.rowBtnTxt}>Money splits</Text>
          <Icon name="ChevronRight" size={18} color={colors.textMuted} />
        </TouchableOpacity>

        <TouchableOpacity
          style={[styles.card, styles.rowBtn]}
          onPress={() => router.push('/bills')}
          testID="profile-bills"
        >
          <Icon name="Receipt" size={20} color={colors.textMain} />
          <Text style={styles.rowBtnTxt}>Recurring bills</Text>
          <Icon name="ChevronRight" size={18} color={colors.textMuted} />
        </TouchableOpacity>

        <TouchableOpacity
          style={[styles.card, styles.rowBtn]}
          onPress={() => router.push('/agreement')}
          testID="profile-agreement"
        >
          <Icon name="FileText" size={20} color={colors.textMain} />
          <Text style={styles.rowBtnTxt}>Roommate agreement</Text>
          <Icon name="ChevronRight" size={18} color={colors.textMuted} />
        </TouchableOpacity>

        <TouchableOpacity
          style={[styles.card, styles.rowBtn]}
          onPress={() => router.push('/space-setup')}
          testID="profile-add-space"
        >
          <Icon name="Plus" size={20} color={colors.textMain} />
          <Text style={styles.rowBtnTxt}>Create or join another space</Text>
          <Icon name="ChevronRight" size={18} color={colors.textMuted} />
        </TouchableOpacity>

        <TouchableOpacity
          style={[styles.card, styles.rowBtn, { marginTop: spacing.lg }]}
          onPress={doLogout}
          testID="profile-logout"
        >
          <Icon name="LogOut" size={20} color={colors.dangerText} />
          <Text style={[styles.rowBtnTxt, { color: colors.dangerText }]}>Log out</Text>
          <View />
        </TouchableOpacity>
      </ScrollView>

      {/* Currency picker */}
      <Modal visible={showCurrency} animationType="slide" transparent onRequestClose={() => setShowCurrency(false)}>
        <View style={profileExtra.modalOverlay}>
          <TouchableOpacity style={{ flex: 1 }} activeOpacity={1} onPress={() => setShowCurrency(false)} />
          <View style={profileExtra.sheet}>
            <View style={profileExtra.sheetHandle} />
            <Text style={profileExtra.sheetTitle}>Pick currency for {activeSpace?.name}</Text>
            <Text style={profileExtra.sheetSub}>Reports, splits and bills will display in this currency. Existing item prices stay as-is — they were entered in the original currency.</Text>
            <ScrollView style={{ maxHeight: 420 }}>
              {CURRENCIES.map((c) => {
                const active = (activeSpace?.currency || 'USD').toUpperCase() === c.code;
                return (
                  <TouchableOpacity
                    key={c.code}
                    style={[profileExtra.curRow, active && profileExtra.curRowActive]}
                    onPress={() => setSpaceCurrency(c.code)}
                    disabled={savingCur}
                    testID={`currency-${c.code}`}
                  >
                    <View style={profileExtra.curSym}>
                      <Text style={profileExtra.curSymTxt}>{c.symbol}</Text>
                    </View>
                    <View style={{ flex: 1 }}>
                      <Text style={profileExtra.curName}>{c.name}</Text>
                      <Text style={profileExtra.curCode}>{c.code}</Text>
                    </View>
                    {active && <Icon name="Check" size={18} color={colors.primary} />}
                  </TouchableOpacity>
                );
              })}
            </ScrollView>
          </View>
        </View>
      </Modal>

      {/* Space type picker */}
      <Modal visible={showSpaceType} animationType="slide" transparent onRequestClose={() => setShowSpaceType(false)}>
        <View style={profileExtra.modalOverlay}>
          <TouchableOpacity style={{ flex: 1 }} activeOpacity={1} onPress={() => setShowSpaceType(false)} />
          <View style={profileExtra.sheet}>
            <View style={profileExtra.sheetHandle} />
            <Text style={profileExtra.sheetTitle}>Space type</Text>
            <Text style={profileExtra.sheetSub}>Pick how this space should feel. You can switch any time — no data is lost.</Text>

            <TouchableOpacity
              style={[profileExtra.typeOption, activeSpace?.space_type === 'roommates' && profileExtra.typeOptionActive]}
              onPress={() => setSpaceType('roommates')}
              testID="space-type-roommates"
            >
              <View style={[profileExtra.typeIcon, { backgroundColor: '#FFE4DC' }]}>
                <Icon name="Users" color="#D45B43" size={26} />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={profileExtra.typeTitle}>Roommates</Text>
                <Text style={profileExtra.typeSub}>Shared rent + groceries. Focus on splits and shared inventory.</Text>
              </View>
              {activeSpace?.space_type === 'roommates' && <Icon name="Check" size={18} color={colors.primary} />}
            </TouchableOpacity>

            <TouchableOpacity
              style={[profileExtra.typeOption, activeSpace?.space_type === 'household' && profileExtra.typeOptionActive]}
              onPress={() => setSpaceType('household')}
              testID="space-type-household"
            >
              <View style={[profileExtra.typeIcon, { backgroundColor: '#E8F0FA' }]}>
                <Icon name="Home" color="#5079A8" size={26} />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={profileExtra.typeTitle}>Household</Text>
                <Text style={profileExtra.typeSub}>Family + staff (maids, drivers, nannies). Adds a Household tab with directory, roles & handbook.</Text>
              </View>
              {activeSpace?.space_type === 'household' && <Icon name="Check" size={18} color={colors.primary} />}
            </TouchableOpacity>
          </View>
        </View>
      </Modal>
    </SafeAreaView>
  );
}

const profileExtra = StyleSheet.create({
  modalOverlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.4)', justifyContent: 'flex-end' },
  sheet: {
    backgroundColor: colors.surface,
    borderTopLeftRadius: 32, borderTopRightRadius: 32,
    padding: spacing.lg, paddingBottom: 32, maxHeight: '80%',
  },
  sheetHandle: { width: 40, height: 4, borderRadius: 2, backgroundColor: colors.border, alignSelf: 'center', marginBottom: 16 },
  sheetTitle: { fontSize: 18, fontWeight: '800', color: colors.textMain, marginBottom: 4 },
  sheetSub: { fontSize: 12, color: colors.textMuted, marginBottom: spacing.md, lineHeight: 18 },
  curRow: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: colors.border },
  curRowActive: { backgroundColor: colors.surfaceAlt, borderRadius: radius.md, paddingHorizontal: 12 },
  curSym: { width: 40, height: 40, borderRadius: 12, backgroundColor: colors.surfaceAlt, alignItems: 'center', justifyContent: 'center' },
  curSymTxt: { fontSize: 16, fontWeight: '800', color: colors.textMain },
  curName: { fontSize: 14, fontWeight: '700', color: colors.textMain },
  curCode: { fontSize: 11, color: colors.textMuted, marginTop: 2 },
  typeOption: {
    flexDirection: 'row', alignItems: 'center', gap: 14,
    backgroundColor: colors.surfaceAlt, borderRadius: radius.lg,
    padding: spacing.md, marginBottom: 10,
    borderWidth: 2, borderColor: 'transparent',
  },
  typeOptionActive: { borderColor: colors.primary },
  typeIcon: { width: 52, height: 52, borderRadius: 16, alignItems: 'center', justifyContent: 'center' },
  typeTitle: { fontSize: 15, fontWeight: '800', color: colors.textMain },
  typeSub: { fontSize: 12, color: colors.textMuted, marginTop: 4, lineHeight: 17 },
});

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background },
  scroll: { padding: spacing.lg, paddingBottom: 140 },
  title: { fontSize: 30, fontWeight: '900', color: colors.textMain, letterSpacing: -0.5, marginBottom: spacing.md },
  profileCard: {
    flexDirection: 'row', alignItems: 'center', gap: 14,
    backgroundColor: colors.surface,
    padding: spacing.md,
    borderRadius: radius.lg,
    marginBottom: spacing.lg,
    ...shadows.card,
  },
  avatar: {
    width: 56, height: 56, borderRadius: 28,
    backgroundColor: colors.primary,
    alignItems: 'center', justifyContent: 'center',
  },
  avatarTxt: { color: '#fff', fontWeight: '900', fontSize: 22 },
  profileName: { fontSize: 18, fontWeight: '800', color: colors.textMain },
  profileEmail: { fontSize: 13, color: colors.textMuted, marginTop: 2 },
  sectionTitle: { fontSize: 14, fontWeight: '700', color: colors.textMuted, marginBottom: 8, marginTop: spacing.sm, textTransform: 'uppercase', letterSpacing: 0.5 },
  card: {
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    padding: spacing.md,
    ...shadows.card,
  },
  spaceName: { fontSize: 20, fontWeight: '800', color: colors.textMain },
  spaceSub: { fontSize: 13, color: colors.textMuted, marginTop: 2 },
  inviteBox: {
    flexDirection: 'row', alignItems: 'center',
    backgroundColor: colors.surfaceAlt,
    borderRadius: radius.md,
    padding: spacing.md,
    marginTop: spacing.md,
  },
  inviteLbl: { fontSize: 11, color: colors.textMuted, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 0.5 },
  inviteCode: { fontSize: 22, fontWeight: '900', color: colors.textMain, letterSpacing: 4, marginTop: 4 },
  copyBtn: {
    flexDirection: 'row', alignItems: 'center', gap: 6,
    backgroundColor: colors.surface,
    paddingHorizontal: 14, paddingVertical: 10,
    borderRadius: radius.full,
  },
  copyTxt: { fontSize: 13, fontWeight: '700', color: colors.textMain },
  membersTitle: {
    marginTop: spacing.md, marginBottom: 8,
    fontSize: 12, fontWeight: '700', color: colors.textMuted,
    textTransform: 'uppercase', letterSpacing: 0.5,
  },
  memberRow: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 10 },
  memberAvatar: {
    width: 36, height: 36, borderRadius: 18,
    alignItems: 'center', justifyContent: 'center',
  },
  memberAvatarTxt: { fontWeight: '800', color: colors.textMain },
  memberName: { fontSize: 14, fontWeight: '700', color: colors.textMain },
  memberEmail: { fontSize: 12, color: colors.textMuted, marginTop: 2 },
  ownerBadge: { backgroundColor: colors.peach, paddingHorizontal: 10, paddingVertical: 4, borderRadius: radius.full },
  ownerTxt: { fontSize: 11, fontWeight: '800', color: '#9B5A3F' },
  rowBtn: {
    flexDirection: 'row', alignItems: 'center', gap: 12,
    padding: spacing.md,
    marginTop: spacing.sm,
  },
  rowBtnTxt: { flex: 1, fontSize: 14, fontWeight: '700', color: colors.textMain },
});
