import React, { useState, useEffect, useCallback } from 'react';
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity, RefreshControl,
  ActivityIndicator, Image, Alert,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useFocusEffect, useRouter } from 'expo-router';
import { useAuth } from '../src/AuthContext';
import { api } from '../src/api';
import { realtime } from '../src/realtime';
import { colors, radius, spacing, shadows, tints } from '../src/theme';
import { Icon } from '../src/Icon';
import { formatMoney } from '../src/currency';

type AlertItem = {
  item_id: string;
  name: string;
  status?: string;
  quantity?: string;
  unit?: string;
  price?: number;
  expiry_date?: string;
  category_id?: string;
  category_name?: string;
  category_icon?: string;
  category_tint?: string;
  photo_base64?: string;
  image_url?: string;
};

type AlertsResponse = {
  totals: { low: number; finished: number; expiring: number; expired: number; all: number };
  low_stock: AlertItem[];
  finished: AlertItem[];
  expiring: AlertItem[];
  expired: AlertItem[];
};

type Bucket = 'all' | 'low_stock' | 'finished' | 'expiring' | 'expired';

const BUCKET_META: Record<Bucket, { label: string; tint: keyof typeof tints; icon: string }> = {
  all:       { label: 'All',        tint: 'mint',     icon: 'Bell'      },
  low_stock: { label: 'Low stock',  tint: 'yellow',   icon: 'MinusCircle' },
  finished:  { label: 'Finished',   tint: 'pink',     icon: 'X'         },
  expiring:  { label: 'Expiring',   tint: 'peach',    icon: 'Clock'     },
  expired:   { label: 'Expired',    tint: 'pink',     icon: 'Trash2'    },
};

function daysFromNow(iso?: string): number | null {
  if (!iso) return null;
  try {
    const d = new Date(iso);
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    return Math.round((d.getTime() - today.getTime()) / 86400000);
  } catch { return null; }
}

export default function ShoppingListScreen() {
  const router = useRouter();
  const { activeSpace } = useAuth();
  const [data, setData] = useState<AlertsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [bucket, setBucket] = useState<Bucket>('all');
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [submitting, setSubmitting] = useState(false);

  const load = useCallback(async () => {
    if (!activeSpace) return;
    setLoading(true);
    try {
      const r = await api.get<AlertsResponse>(`/inventory/alerts?space_id=${activeSpace.space_id}&days_threshold=7`);
      setData(r);
    } catch (e) { console.warn(e); }
    finally { setLoading(false); }
  }, [activeSpace]);

  useFocusEffect(useCallback(() => { load(); }, [load]));

  // Realtime: refresh on item/shopping events
  useEffect(() => {
    if (!activeSpace) return;
    const off = realtime.onSpaceEvent((e) => {
      if (e.space_id !== activeSpace.space_id) return;
      if (e.kind === 'item' || e.kind === 'shopping') load();
    });
    return off;
  }, [activeSpace, load]);

  const onRefresh = async () => { setRefreshing(true); await load(); setRefreshing(false); };

  // Build a unified item list per bucket selection.
  const allItems: Array<AlertItem & { _bucket: Bucket }> = (() => {
    if (!data) return [];
    const out: Array<AlertItem & { _bucket: Bucket }> = [];
    if (bucket === 'all' || bucket === 'low_stock')   data.low_stock.forEach((it) => out.push({ ...it, _bucket: 'low_stock' }));
    if (bucket === 'all' || bucket === 'finished')    data.finished.forEach((it) => out.push({ ...it, _bucket: 'finished' }));
    if (bucket === 'all' || bucket === 'expired')     data.expired.forEach((it) => out.push({ ...it, _bucket: 'expired' }));
    if (bucket === 'all' || bucket === 'expiring')    data.expiring.forEach((it) => out.push({ ...it, _bucket: 'expiring' }));
    // Dedupe by item_id (an item can be both low and expiring)
    const seen = new Set<string>();
    return out.filter((it) => {
      if (seen.has(it.item_id)) return false;
      seen.add(it.item_id);
      return true;
    });
  })();

  const toggle = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  const selectAll = () => setSelected(new Set(allItems.map((it) => it.item_id)));
  const clearSel = () => setSelected(new Set());

  const addToShopping = async () => {
    if (!activeSpace || selected.size === 0) return;
    setSubmitting(true);
    try {
      const res = await api.post<{ created: number; skipped: number }>(`/inventory/alerts/to-shopping`, {
        space_id: activeSpace.space_id,
        item_ids: Array.from(selected),
      });
      Alert.alert(
        'Added to shopping',
        `${res.created} item${res.created === 1 ? '' : 's'} sent to the shopping list${res.skipped ? `. ${res.skipped} skipped (already requested).` : '.'}`,
      );
      setSelected(new Set());
      await load();
    } catch (e: any) {
      Alert.alert('Could not add', e?.message || 'Try again.');
    } finally { setSubmitting(false); }
  };

  return (
    <SafeAreaView style={styles.container} edges={['top', 'bottom']}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.backBtn}>
          <Icon name="ChevronRight" size={18} color={colors.textMain} />
        </TouchableOpacity>
        <View style={{ flex: 1 }}>
          <Text style={styles.kicker}>{activeSpace?.name}</Text>
          <Text style={styles.title}>Shopping list</Text>
        </View>
        {data && data.totals.all > 0 && (
          <View style={[styles.totalPill, { backgroundColor: tints.mint.bg }]}>
            <Text style={[styles.totalTxt, { color: tints.mint.icon }]}>{data.totals.all} alerts</Text>
          </View>
        )}
      </View>

      {/* Bucket tabs */}
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.tabRow}>
        {(['all', 'low_stock', 'finished', 'expiring', 'expired'] as Bucket[]).map((b) => {
          const meta = BUCKET_META[b];
          const count = b === 'all' ? data?.totals.all || 0 :
            b === 'low_stock' ? data?.totals.low || 0 :
            b === 'finished' ? data?.totals.finished || 0 :
            b === 'expiring' ? data?.totals.expiring || 0 :
            data?.totals.expired || 0;
          const active = bucket === b;
          return (
            <TouchableOpacity
              key={b}
              style={[styles.tab, active && styles.tabActive]}
              onPress={() => { setBucket(b); setSelected(new Set()); }}
              testID={`bucket-${b}`}
            >
              <Icon name={meta.icon} size={12} color={active ? '#fff' : tints[meta.tint].icon} />
              <Text style={[styles.tabTxt, active && { color: '#fff' }]}>{meta.label}</Text>
              {count > 0 && (
                <View style={[styles.tabCount, active && { backgroundColor: 'rgba(255,255,255,0.3)' }]}>
                  <Text style={[styles.tabCountTxt, active && { color: '#fff' }]}>{count}</Text>
                </View>
              )}
            </TouchableOpacity>
          );
        })}
      </ScrollView>

      <ScrollView
        contentContainerStyle={styles.scroll}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.primary} />}
      >
        {loading ? (
          <ActivityIndicator color={colors.primary} style={{ marginTop: 30 }} />
        ) : allItems.length === 0 ? (
          <View style={styles.empty}>
            <View style={[styles.heroIcon, { backgroundColor: tints.sage.bg }]}>
              <Icon name="CheckCircle2" size={28} color={tints.sage.icon} />
            </View>
            <Text style={styles.emptyTitle}>All caught up!</Text>
            <Text style={styles.emptySub}>
              No low-stock, finished or expiring items right now. Mark items "Low" or "Finished" in the inventory to see them here.
            </Text>
          </View>
        ) : (
          <>
            {/* Select all row */}
            <View style={styles.selectAllRow}>
              <TouchableOpacity
                style={styles.selectAllBtn}
                onPress={selected.size === allItems.length ? clearSel : selectAll}
                testID="select-all"
              >
                <Icon name={selected.size === allItems.length ? 'Check' : 'PlusCircle'} size={14} color={colors.textMain} />
                <Text style={styles.selectAllTxt}>{selected.size === allItems.length ? 'Clear' : 'Select all'}</Text>
              </TouchableOpacity>
              {selected.size > 0 && <Text style={styles.selCount}>{selected.size} selected</Text>}
            </View>

            {allItems.map((it) => {
              const meta = BUCKET_META[it._bucket];
              const isSel = selected.has(it.item_id);
              const days = daysFromNow(it.expiry_date);
              return (
                <TouchableOpacity
                  key={it.item_id}
                  style={[styles.row, isSel && { borderColor: colors.primary, borderWidth: 1.5 }]}
                  onPress={() => toggle(it.item_id)}
                  testID={`alert-${it.item_id}`}
                >
                  <View style={[styles.checkBox, isSel && styles.checkBoxOn]}>
                    {isSel && <Icon name="Check" size={14} color="#fff" />}
                  </View>
                  {(it.photo_base64 || it.image_url) ? (
                    <Image source={{ uri: it.photo_base64 || it.image_url }} style={styles.thumb} />
                  ) : (
                    <View style={[styles.thumb, { backgroundColor: tints[(it.category_tint as any) || 'mint'].icon, alignItems: 'center', justifyContent: 'center' }]}>
                      <Icon name={it.category_icon || 'Box'} size={16} color="#fff" />
                    </View>
                  )}
                  <View style={{ flex: 1 }}>
                    <Text style={styles.rowName} numberOfLines={1}>{it.name}</Text>
                    <View style={styles.rowMetaRow}>
                      <View style={[styles.miniBadge, { backgroundColor: tints[meta.tint].bg }]}>
                        <Text style={[styles.miniTxt, { color: tints[meta.tint].icon }]}>{meta.label}</Text>
                      </View>
                      {it.category_name && (
                        <Text style={styles.rowSub}>{it.category_name}</Text>
                      )}
                      {it._bucket === 'expiring' && days != null && (
                        <Text style={styles.rowSub}>· {days} day{days === 1 ? '' : 's'} left</Text>
                      )}
                      {it._bucket === 'expired' && days != null && (
                        <Text style={[styles.rowSub, { color: tints.pink.icon, fontWeight: '700' }]}>· {Math.abs(days)} day{Math.abs(days) === 1 ? '' : 's'} ago</Text>
                      )}
                      {it.quantity && <Text style={styles.rowSub}>· {it.quantity}{it.unit ? ` ${it.unit}` : ''}</Text>}
                    </View>
                  </View>
                  {it.price && activeSpace ? (
                    <Text style={styles.rowPrice}>{formatMoney(it.price, activeSpace.currency || 'USD')}</Text>
                  ) : null}
                </TouchableOpacity>
              );
            })}
          </>
        )}
        <View style={{ height: 80 }} />
      </ScrollView>

      {/* Floating action: add to shopping */}
      {selected.size > 0 && (
        <View style={styles.fabBar}>
          <TouchableOpacity
            style={[styles.fab, submitting && { opacity: 0.6 }]}
            onPress={addToShopping}
            disabled={submitting}
            testID="alerts-to-shopping"
          >
            {submitting ? <ActivityIndicator color="#fff" /> : (
              <>
                <Icon name="ShoppingBag" size={16} color="#fff" />
                <Text style={styles.fabTxt}>Add {selected.size} to shopping list</Text>
              </>
            )}
          </TouchableOpacity>
        </View>
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background },
  header: { flexDirection: 'row', alignItems: 'center', gap: 12, padding: spacing.md },
  backBtn: { width: 40, height: 40, borderRadius: 20, backgroundColor: colors.surface, alignItems: 'center', justifyContent: 'center', transform: [{ rotate: '180deg' }], ...shadows.card },
  kicker: { fontSize: 11, color: colors.textMuted, fontWeight: '700', textTransform: 'uppercase' },
  title: { fontSize: 24, fontWeight: '900', color: colors.textMain, letterSpacing: -0.5 },
  totalPill: { paddingHorizontal: 12, paddingVertical: 6, borderRadius: radius.full },
  totalTxt: { fontSize: 12, fontWeight: '800' },
  tabRow: { paddingHorizontal: spacing.md, gap: 6, paddingBottom: spacing.sm },
  tab: { flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 12, paddingVertical: 8, borderRadius: radius.full, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, marginRight: 6 },
  tabActive: { backgroundColor: colors.textMain, borderColor: colors.textMain },
  tabTxt: { fontSize: 12, fontWeight: '700', color: colors.textMain },
  tabCount: { backgroundColor: colors.background, borderRadius: 10, paddingHorizontal: 6, paddingVertical: 1, minWidth: 18, alignItems: 'center' },
  tabCountTxt: { fontSize: 10, fontWeight: '900', color: colors.textMain },
  scroll: { padding: spacing.md, paddingTop: 0 },
  selectAllRow: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 8 },
  selectAllBtn: { flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 10, paddingVertical: 6, backgroundColor: colors.surface, borderRadius: radius.full, borderWidth: 1, borderColor: colors.border },
  selectAllTxt: { fontSize: 12, fontWeight: '700', color: colors.textMain },
  selCount: { fontSize: 12, color: colors.textMuted, fontWeight: '700' },
  row: {
    flexDirection: 'row', alignItems: 'center', gap: 10,
    backgroundColor: colors.surface,
    padding: spacing.md, borderRadius: radius.md,
    marginBottom: 6, ...shadows.card,
  },
  checkBox: { width: 22, height: 22, borderRadius: 11, borderWidth: 2, borderColor: colors.border, alignItems: 'center', justifyContent: 'center' },
  checkBoxOn: { backgroundColor: colors.primary, borderColor: colors.primary },
  thumb: { width: 40, height: 40, borderRadius: radius.sm },
  rowName: { fontSize: 14, fontWeight: '800', color: colors.textMain },
  rowMetaRow: { flexDirection: 'row', alignItems: 'center', gap: 4, marginTop: 4, flexWrap: 'wrap' },
  miniBadge: { paddingHorizontal: 8, paddingVertical: 2, borderRadius: 8 },
  miniTxt: { fontSize: 10, fontWeight: '800' },
  rowSub: { fontSize: 11, color: colors.textMuted },
  rowPrice: { fontSize: 13, fontWeight: '800', color: colors.textMain },
  fabBar: { position: 'absolute', bottom: spacing.md, left: spacing.md, right: spacing.md },
  fab: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, backgroundColor: colors.primary, paddingVertical: 14, borderRadius: radius.full, ...shadows.button },
  fabTxt: { color: '#fff', fontWeight: '800', fontSize: 14 },
  empty: { alignItems: 'center', padding: spacing.xl, gap: 12 },
  heroIcon: { width: 64, height: 64, borderRadius: 22, alignItems: 'center', justifyContent: 'center' },
  emptyTitle: { fontSize: 18, fontWeight: '800', color: colors.textMain },
  emptySub: { fontSize: 13, color: colors.textMuted, textAlign: 'center', lineHeight: 19 },
});
