import React, { useState, useCallback, useEffect } from 'react';
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity, RefreshControl,
  ActivityIndicator,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useFocusEffect, useRouter } from 'expo-router';
import { useAuth } from '../src/AuthContext';
import { api } from '../src/api';
import { realtime } from '../src/realtime';
import { colors, radius, spacing, shadows, tints } from '../src/theme';
import { Icon } from '../src/Icon';

const KIND_META: Record<string, { label: string; icon: string; tint: keyof typeof tints }> = {
  nda: { label: 'NDA', icon: 'Shield', tint: 'sage' },
  employment: { label: 'Employment', icon: 'FileText', tint: 'blue' },
  confidentiality: { label: 'Confidentiality', icon: 'Lock', tint: 'lavender' },
  blank: { label: 'Custom', icon: 'Edit3', tint: 'peach' },
  custom: { label: 'Custom', icon: 'Edit3', tint: 'peach' },
};

const STATUS_META: Record<string, { label: string; tint: keyof typeof tints }> = {
  pending: { label: 'Pending signatures', tint: 'yellow' },
  signed: { label: 'Fully signed', tint: 'sage' },
  void: { label: 'Voided', tint: 'pink' },
};

export default function ContractsScreen() {
  const router = useRouter();
  const { activeSpace, spaceRole } = useAuth();
  const [contracts, setContracts] = useState<any[]>([]);
  const [staffList, setStaffList] = useState<any[]>([]);
  const [staffFilter, setStaffFilter] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const isOwner = spaceRole?.role !== 'staff';

  const load = useCallback(async () => {
    if (!activeSpace) return;
    setLoading(true);
    try {
      const q = staffFilter ? `&staff_id=${staffFilter}` : '';
      const list = await api.get<any[]>(`/contracts?space_id=${activeSpace.space_id}${q}`);
      setContracts(list || []);
      if (isOwner) {
        const s = await api.get<any[]>(`/household/staff?space_id=${activeSpace.space_id}`);
        setStaffList(s || []);
      }
    } catch (e) { console.warn(e); }
    finally { setLoading(false); }
  }, [activeSpace, staffFilter, isOwner]);

  useFocusEffect(useCallback(() => { load(); }, [load]));
  // Realtime: refresh contract list on contract events for this space
  useEffect(() => {
    if (!activeSpace) return;
    const off = realtime.onSpaceEvent((e) => {
      if (e.space_id === activeSpace.space_id && e.kind === 'contract') {
        load();
      }
    });
    return off;
  }, [activeSpace, load]);
  const onRefresh = async () => { setRefreshing(true); await load(); setRefreshing(false); };

  return (
    <SafeAreaView style={styles.container} edges={['top', 'bottom']}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.backBtn}>
          <Icon name="ChevronRight" size={18} color={colors.textMain} />
        </TouchableOpacity>
        <View style={{ flex: 1 }}>
          <Text style={styles.kicker}>{activeSpace?.name}</Text>
          <Text style={styles.title}>Agreements</Text>
        </View>
        {isOwner && (
          <TouchableOpacity style={styles.addBtn} onPress={() => router.push('/contract-new')} testID="contracts-new">
            <Icon name="Plus" size={18} color="#fff" />
          </TouchableOpacity>
        )}
      </View>

      {/* Staff filter chips */}
      {isOwner && staffList.length > 0 && (
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.filterRow}>
          <TouchableOpacity
            style={[styles.chip, !staffFilter && styles.chipActive]}
            onPress={() => setStaffFilter(null)}
          >
            <Text style={[styles.chipTxt, !staffFilter && { color: '#fff' }]}>All</Text>
          </TouchableOpacity>
          {staffList.map((s) => (
            <TouchableOpacity
              key={s.staff_id}
              style={[styles.chip, staffFilter === s.staff_id && styles.chipActive]}
              onPress={() => setStaffFilter(staffFilter === s.staff_id ? null : s.staff_id)}
            >
              <Text style={[styles.chipTxt, staffFilter === s.staff_id && { color: '#fff' }]}>{s.name}</Text>
            </TouchableOpacity>
          ))}
        </ScrollView>
      )}

      <ScrollView
        contentContainerStyle={styles.scroll}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.primary} />}
      >
        {loading ? (
          <ActivityIndicator color={colors.primary} style={{ marginTop: 30 }} />
        ) : contracts.length === 0 ? (
          <View style={styles.empty}>
            <View style={[styles.heroIcon, { backgroundColor: tints.sage.bg }]}>
              <Icon name="FileText" size={28} color={tints.sage.icon} />
            </View>
            <Text style={styles.emptyTitle}>No agreements yet</Text>
            <Text style={styles.emptySub}>
              {isOwner
                ? 'Create an NDA, employment contract or confidentiality pledge — staff can review and sign right inside the app.'
                : 'When the household owner sends you an agreement to sign, it will appear here.'}
            </Text>
            {isOwner && (
              <TouchableOpacity style={styles.ctaBtn} onPress={() => router.push('/contract-new')}>
                <Icon name="Plus" color="#fff" size={16} />
                <Text style={styles.ctaTxt}>Create first agreement</Text>
              </TouchableOpacity>
            )}
          </View>
        ) : (
          contracts.map((c) => {
            const meta = KIND_META[c.template_kind] || KIND_META.custom;
            const sm = STATUS_META[c.status] || STATUS_META.pending;
            const ownerSigned = !!c.owner_signature;
            const staffSigned = !!c.staff_signature;
            const assignedStaff = c.assigned_staff_id ? staffList.find((s) => s.staff_id === c.assigned_staff_id) : null;
            const staffNotJoined = isOwner && assignedStaff && !assignedStaff.user_id && c.status !== 'void';
            return (
              <TouchableOpacity
                key={c.contract_id}
                style={styles.row}
                onPress={() => router.push({ pathname: '/contract-view', params: { id: c.contract_id } })}
                testID={`contract-${c.contract_id}`}
              >
                <View style={[styles.kindIcon, { backgroundColor: tints[meta.tint].bg }]}>
                  <Icon name={meta.icon} size={18} color={tints[meta.tint].icon} />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={styles.rowName} numberOfLines={1}>{c.title}</Text>
                  <Text style={styles.rowSub}>
                    {meta.label}
                    {c.assigned_staff_name ? ` · ${c.assigned_staff_name}` : ' · Not assigned'}
                    {' · '}
                    {new Date(c.created_at).toLocaleDateString()}
                  </Text>
                  <View style={styles.badgeRow}>
                    <View style={[styles.miniBadge, { backgroundColor: tints[sm.tint].bg }]}>
                      <Text style={[styles.miniTxt, { color: tints[sm.tint].icon }]}>{sm.label}</Text>
                    </View>
                    {staffNotJoined && (
                      <View style={[styles.miniBadge, { backgroundColor: tints.peach.bg }]}>
                        <Text style={[styles.miniTxt, { color: tints.peach.icon }]}>Staff hasn't joined yet · share invite code</Text>
                      </View>
                    )}
                    {c.status !== 'void' && (
                      <View style={[styles.miniBadge, { backgroundColor: ownerSigned ? tints.sage.bg : tints.yellow.bg }]}>
                        <Text style={[styles.miniTxt, { color: ownerSigned ? tints.sage.icon : tints.yellow.icon }]}>
                          {ownerSigned ? 'Owner ✓' : 'Owner pending'}
                        </Text>
                      </View>
                    )}
                    {c.status !== 'void' && (
                      <View style={[styles.miniBadge, { backgroundColor: staffSigned ? tints.sage.bg : tints.yellow.bg }]}>
                        <Text style={[styles.miniTxt, { color: staffSigned ? tints.sage.icon : tints.yellow.icon }]}>
                          {staffSigned ? 'Staff ✓' : 'Staff pending'}
                        </Text>
                      </View>
                    )}
                  </View>
                </View>
                <Icon name="ChevronRight" size={16} color={colors.textMuted} />
              </TouchableOpacity>
            );
          })
        )}
        <View style={{ height: 60 }} />
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background },
  header: { flexDirection: 'row', alignItems: 'center', gap: 12, padding: spacing.md },
  backBtn: { width: 40, height: 40, borderRadius: 20, backgroundColor: colors.surface, alignItems: 'center', justifyContent: 'center', transform: [{ rotate: '180deg' }], ...shadows.card },
  addBtn: { width: 40, height: 40, borderRadius: 20, backgroundColor: colors.primary, alignItems: 'center', justifyContent: 'center', ...shadows.button },
  kicker: { fontSize: 11, color: colors.textMuted, fontWeight: '700', textTransform: 'uppercase' },
  title: { fontSize: 24, fontWeight: '900', color: colors.textMain, letterSpacing: -0.5 },
  filterRow: { paddingHorizontal: spacing.md, gap: 6, paddingBottom: spacing.sm },
  chip: { paddingHorizontal: 12, paddingVertical: 6, borderRadius: radius.full, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, marginRight: 6 },
  chipActive: { backgroundColor: colors.textMain, borderColor: colors.textMain },
  chipTxt: { fontSize: 12, fontWeight: '700', color: colors.textMain },
  scroll: { padding: spacing.md, paddingTop: 0 },
  row: {
    flexDirection: 'row', alignItems: 'center', gap: 12,
    backgroundColor: colors.surface,
    padding: spacing.md, borderRadius: radius.md,
    marginBottom: 8, ...shadows.card,
  },
  kindIcon: { width: 44, height: 44, borderRadius: 14, alignItems: 'center', justifyContent: 'center' },
  rowName: { fontSize: 15, fontWeight: '800', color: colors.textMain },
  rowSub: { fontSize: 11, color: colors.textMuted, marginTop: 2 },
  badgeRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 4, marginTop: 6 },
  miniBadge: { paddingHorizontal: 8, paddingVertical: 3, borderRadius: 10 },
  miniTxt: { fontSize: 10, fontWeight: '800' },
  empty: { alignItems: 'center', padding: spacing.xl, gap: 12 },
  heroIcon: { width: 64, height: 64, borderRadius: 22, alignItems: 'center', justifyContent: 'center' },
  emptyTitle: { fontSize: 18, fontWeight: '800', color: colors.textMain },
  emptySub: { fontSize: 13, color: colors.textMuted, textAlign: 'center', lineHeight: 19 },
  ctaBtn: { flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: colors.primary, paddingHorizontal: 18, paddingVertical: 12, borderRadius: radius.full, ...shadows.button },
  ctaTxt: { color: '#fff', fontWeight: '800' },
});
