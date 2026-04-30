import React, { useEffect, useState, useCallback } from 'react';
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity, RefreshControl, Image,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter, useFocusEffect } from 'expo-router';
import { useAuth } from '../../src/AuthContext';
import { colors, radius, spacing, shadows, tints } from '../../src/theme';
import { Icon } from '../../src/Icon';
import { api } from '../../src/api';
import type { Stats, Activity } from '../../src/types';
import { formatDistanceToNow } from 'date-fns';

export default function Home() {
  const { user, activeSpace, spaces, setActiveSpaceId } = useAuth();
  const router = useRouter();
  const [stats, setStats] = useState<Stats | null>(null);
  const [activity, setActivity] = useState<Activity[]>([]);
  const [refreshing, setRefreshing] = useState(false);
  const [showSpacePicker, setShowSpacePicker] = useState(false);

  const load = useCallback(async () => {
    if (!activeSpace) return;
    try {
      const [s, a] = await Promise.all([
        api.get<Stats>(`/stats?space_id=${activeSpace.space_id}`),
        api.get<Activity[]>(`/activity?space_id=${activeSpace.space_id}`),
      ]);
      setStats(s);
      setActivity(a);
    } catch (e) {
      console.warn(e);
    }
  }, [activeSpace]);

  useFocusEffect(useCallback(() => {
    load();
    const id = setInterval(load, 10000);
    return () => clearInterval(id);
  }, [load]));

  const onRefresh = async () => {
    setRefreshing(true);
    await load();
    setRefreshing(false);
  };

  const greeting = () => {
    const h = new Date().getHours();
    if (h < 12) return 'Good morning';
    if (h < 18) return 'Good afternoon';
    return 'Good evening';
  };

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <ScrollView
        contentContainerStyle={styles.scroll}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.primary} />}
        showsVerticalScrollIndicator={false}
      >
        {/* Header */}
        <View style={styles.header}>
          <View style={{ flex: 1 }}>
            <Text style={styles.greet}>{greeting()},</Text>
            <Text style={styles.name} testID="home-user-name">{user?.name?.split(' ')[0] || 'Friend'}</Text>
          </View>
          <TouchableOpacity
            style={styles.spacePill}
            onPress={() => setShowSpacePicker((v) => !v)}
            testID="home-space-switch"
          >
            <Icon name="Home" size={16} color={colors.textMain} />
            <Text style={styles.spaceTxt} numberOfLines={1}>{activeSpace?.name || 'No space'}</Text>
            <Icon name="ChevronRight" size={14} color={colors.textMuted} />
          </TouchableOpacity>
        </View>

        {showSpacePicker && (
          <View style={styles.spaceMenu}>
            {spaces.map((s) => (
              <TouchableOpacity
                key={s.space_id}
                style={styles.spaceMenuItem}
                onPress={() => { setActiveSpaceId(s.space_id); setShowSpacePicker(false); }}
              >
                <Text style={styles.spaceMenuTxt}>{s.name}</Text>
                {activeSpace?.space_id === s.space_id && <Icon name="Check" size={16} color={colors.primary} />}
              </TouchableOpacity>
            ))}
            <TouchableOpacity
              style={[styles.spaceMenuItem, { borderTopWidth: 1, borderTopColor: colors.border }]}
              onPress={() => { setShowSpacePicker(false); router.push('/space-setup'); }}
            >
              <Icon name="Plus" size={16} color={colors.primary} />
              <Text style={[styles.spaceMenuTxt, { color: colors.primary, fontWeight: '700' }]}>Create or join a space</Text>
            </TouchableOpacity>
          </View>
        )}

        {/* Stats Grid */}
        <View style={styles.statsGrid}>
          <View style={[styles.statCard, { backgroundColor: tints.mint.bg }]} testID="home-stat-total">
            <Icon name="Package" color={tints.mint.icon} size={20} />
            <Text style={styles.statNum}>{stats?.total_items ?? 0}</Text>
            <Text style={styles.statLbl}>In stock</Text>
          </View>
          <View style={[styles.statCard, { backgroundColor: tints.yellow.bg }]} testID="home-stat-expiring">
            <Icon name="Calendar" color={tints.yellow.icon} size={20} />
            <Text style={styles.statNum}>{stats?.expiring_soon ?? 0}</Text>
            <Text style={styles.statLbl}>Expiring soon</Text>
          </View>
          <View style={[styles.statCard, { backgroundColor: tints.pink.bg }]} testID="home-stat-low">
            <Icon name="CircleDot" color={tints.pink.icon} size={20} />
            <Text style={styles.statNum}>{stats?.low_items ?? 0}</Text>
            <Text style={styles.statLbl}>Running low</Text>
          </View>
          <View style={[styles.statCard, { backgroundColor: tints.lavender.bg }]} testID="home-stat-spent">
            <Icon name="Wallet" color={tints.lavender.icon} size={20} />
            <Text style={styles.statNum}>${(stats?.spent_this_month ?? 0).toFixed(0)}</Text>
            <Text style={styles.statLbl}>This month</Text>
          </View>
        </View>

        {/* Quick Actions */}
        <View style={styles.quickRow}>
          <TouchableOpacity
            style={[styles.quick, { backgroundColor: colors.primary }]}
            onPress={() => router.push('/item/new')}
            testID="home-quick-add"
          >
            <Icon name="Plus" color="#fff" size={22} />
            <Text style={[styles.quickTxt, { color: '#fff' }]}>Add item</Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={[styles.quick, { backgroundColor: colors.surface }]}
            onPress={() => router.push('/(tabs)/inventory')}
            testID="home-quick-browse"
          >
            <Icon name="Package" color={colors.textMain} size={22} />
            <Text style={styles.quickTxt}>Browse</Text>
          </TouchableOpacity>
        </View>

        {/* Activity */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Recent activity</Text>
          {activity.length === 0 ? (
            <View style={[styles.card, { alignItems: 'center', paddingVertical: 32 }]}>
              <Icon name="Home" color={colors.textMuted} size={28} />
              <Text style={{ color: colors.textMuted, marginTop: 8, textAlign: 'center' }}>
                No activity yet. Start by adding your first item!
              </Text>
            </View>
          ) : (
            activity.map((a) => (
              <View key={a.activity_id} style={styles.activityRow}>
                <View style={styles.avatar}>
                  <Text style={styles.avatarTxt}>{a.user_name?.[0]?.toUpperCase() || '?'}</Text>
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={styles.activityText}>
                    <Text style={{ fontWeight: '700' }}>{a.user_name}</Text>
                    <Text style={{ color: colors.textMuted }}> {a.action} </Text>
                    <Text style={{ fontWeight: '700' }}>{a.entity_name}</Text>
                  </Text>
                  <Text style={styles.activityTime}>
                    {formatDistanceToNow(new Date(a.timestamp), { addSuffix: true })}
                  </Text>
                </View>
              </View>
            ))
          )}
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background },
  scroll: { padding: spacing.lg, paddingBottom: 140 },
  header: { flexDirection: 'row', alignItems: 'center', marginBottom: spacing.lg },
  greet: { fontSize: 14, color: colors.textMuted, fontWeight: '500' },
  name: { fontSize: 28, fontWeight: '900', color: colors.textMain, letterSpacing: -0.5 },
  spacePill: {
    flexDirection: 'row', alignItems: 'center', gap: 8,
    backgroundColor: colors.surface,
    paddingHorizontal: 14, paddingVertical: 10,
    borderRadius: radius.full,
    maxWidth: 170,
    ...shadows.card,
  },
  spaceTxt: { fontSize: 13, fontWeight: '700', color: colors.textMain, maxWidth: 90 },
  spaceMenu: {
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    marginBottom: spacing.md,
    overflow: 'hidden',
    ...shadows.card,
  },
  spaceMenuItem: {
    flexDirection: 'row', alignItems: 'center', gap: 10,
    paddingHorizontal: spacing.md, paddingVertical: 14,
  },
  spaceMenuTxt: { flex: 1, fontSize: 14, fontWeight: '600', color: colors.textMain },
  statsGrid: {
    flexDirection: 'row', flexWrap: 'wrap',
    gap: spacing.sm,
    marginBottom: spacing.md,
  },
  statCard: {
    flexBasis: '48%',
    flexGrow: 1,
    padding: spacing.md,
    borderRadius: radius.lg,
    gap: 4,
  },
  statNum: { fontSize: 26, fontWeight: '900', color: colors.textMain, marginTop: 4, letterSpacing: -0.5 },
  statLbl: { fontSize: 12, color: colors.textMuted, fontWeight: '600' },
  quickRow: { flexDirection: 'row', gap: spacing.sm, marginBottom: spacing.lg },
  quick: {
    flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
    paddingVertical: 16, borderRadius: radius.full, gap: 8,
    ...shadows.card,
  },
  quickTxt: { fontWeight: '700', fontSize: 14, color: colors.textMain },
  section: { marginBottom: spacing.lg },
  sectionTitle: { fontSize: 18, fontWeight: '800', color: colors.textMain, marginBottom: spacing.sm },
  card: {
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    padding: spacing.md,
    ...shadows.card,
  },
  activityRow: {
    flexDirection: 'row', alignItems: 'center', gap: 12,
    backgroundColor: colors.surface,
    padding: spacing.md,
    borderRadius: radius.md,
    marginBottom: 8,
    ...shadows.card,
  },
  avatar: {
    width: 36, height: 36, borderRadius: 18,
    backgroundColor: colors.peach,
    alignItems: 'center', justifyContent: 'center',
  },
  avatarTxt: { fontWeight: '800', color: colors.textMain },
  activityText: { fontSize: 14, color: colors.textMain },
  activityTime: { fontSize: 12, color: colors.textMuted, marginTop: 2 },
});
