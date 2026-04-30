import React, { useState, useCallback } from 'react';
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity, Alert, Platform,
} from 'react-native';
import * as Clipboard from 'expo-clipboard';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter, useFocusEffect } from 'expo-router';
import { useAuth } from '../../src/AuthContext';
import { colors, radius, spacing, shadows } from '../../src/theme';
import { Icon } from '../../src/Icon';
import { api } from '../../src/api';
import type { User } from '../../src/types';

export default function Profile() {
  const router = useRouter();
  const { user, logout, activeSpace, spaces, setActiveSpaceId } = useAuth();
  const [members, setMembers] = useState<User[]>([]);
  const [copied, setCopied] = useState(false);

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
    </SafeAreaView>
  );
}

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
