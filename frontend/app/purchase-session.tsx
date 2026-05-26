import React, { useCallback, useEffect, useState } from 'react';
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity, RefreshControl, Alert, ActivityIndicator,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter, useLocalSearchParams, useFocusEffect } from 'expo-router';
import { api } from '../src/api';
import { useAuth } from '../src/AuthContext';
import { colors, radius, spacing, shadows } from '../src/theme';
import { Icon } from '../src/Icon';
import { formatMoney } from '../src/currency';

type PurchaseSessionItem = {
  line_id?: string;
  item_id?: string | null;
  category_id?: string | null;
  name: string;
  quantity: number;
  unit?: string | null;
  unit_price?: number | null;
  total_price?: number | null;
  shopping_request_id?: string | null;
  inventory_applied?: boolean | null;
};

type PurchaseSession = {
  session_id: string;
  space_id: string;
  merchant: string;
  purchase_date: string;
  total: number;
  currency: string;
  source: string;
  source_request_ids: string[];
  items: PurchaseSessionItem[];
  paid_by: string;
  notes?: string | null;
  created_by: string;
  created_at: string;
  receipt_image_base64?: string | null;
};

function fmtDate(d: string) {
  try { return new Date(d).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' }); }
  catch { return d; }
}

export default function PurchaseSessionScreen() {
  const router = useRouter();
  const { id } = useLocalSearchParams<{ id?: string }>();
  const { activeSpace } = useAuth() as any;

  const [list, setList] = useState<PurchaseSession[]>([]);
  const [active, setActive] = useState<PurchaseSession | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});

  const load = useCallback(async () => {
    if (!activeSpace?.space_id) { setLoading(false); return; }
    try {
      if (id) {
        const detail = await api.get<PurchaseSession>(`/purchase-sessions/${id}`);
        setActive(detail);
      } else {
        const rows = await api.get<PurchaseSession[]>(`/purchase-sessions?space_id=${activeSpace.space_id}`);
        setList(rows || []);
      }
    } catch (e: any) {
      console.warn('load purchase sessions failed', e?.message);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [activeSpace?.space_id, id]);

  useFocusEffect(useCallback(() => { load(); }, [load]));

  const onRefresh = () => { setRefreshing(true); load(); };

  const deleteSession = async (sid: string) => {
    Alert.alert(
      'Delete purchase session?',
      'This will undo the inventory updates and reopen any linked shopping requests.',
      [
        { text: 'Cancel', style: 'cancel' },
        { text: 'Delete', style: 'destructive', onPress: async () => {
          try {
            await api.delete(`/purchase-sessions/${sid}`);
            if (id) router.back();
            else load();
          } catch (e: any) {
            Alert.alert('Could not delete', e?.message || 'Try again.');
          }
        }},
      ],
    );
  };

  if (loading) {
    return (
      <SafeAreaView style={styles.container} edges={['top']}>
        <Header onBack={() => router.back()} title={id ? 'Purchase' : 'Purchase Sessions'} />
        <View style={styles.loadingWrap}><ActivityIndicator color={colors.primary} /></View>
      </SafeAreaView>
    );
  }

  // ----- DETAIL VIEW -----
  if (id && active) {
    return (
      <SafeAreaView style={styles.container} edges={['top']}>
        <Header
          onBack={() => router.back()}
          title={active.merchant}
          rightIcon="Trash2"
          onRight={() => deleteSession(active.session_id)}
        />
        <ScrollView contentContainerStyle={styles.scroll}>
          <View style={styles.hero}>
            <Text style={styles.heroMerchant}>{active.merchant}</Text>
            <Text style={styles.heroDate}>{fmtDate(active.purchase_date)}</Text>
            <Text style={styles.heroTotal}>{formatMoney(active.total, active.currency)}</Text>
            <Text style={styles.heroMeta}>
              {active.items.length} item{active.items.length !== 1 ? 's' : ''}
              {' · '}{active.source === 'receipt_scan' ? 'From receipt' : active.source === 'shopping_request' ? 'From request' : 'Manual'}
            </Text>
          </View>

          <Text style={styles.sectionLabel}>Items</Text>
          {active.items.map((it, i) => (
            <View key={it.line_id || i} style={styles.itemRow}>
              <View style={{ flex: 1 }}>
                <Text style={styles.itemName}>{it.name}</Text>
                <Text style={styles.itemSub}>
                  {it.quantity}{it.unit ? ` ${it.unit}` : ''}
                  {it.unit_price ? ` · ${formatMoney(it.unit_price, active.currency)} each` : ''}
                  {!it.inventory_applied ? ' · not added to inventory' : ''}
                </Text>
              </View>
              <Text style={styles.itemPrice}>
                {it.total_price != null
                  ? formatMoney(it.total_price, active.currency)
                  : it.unit_price != null
                    ? formatMoney(it.unit_price * it.quantity, active.currency)
                    : '—'}
              </Text>
            </View>
          ))}

          {active.notes ? (
            <View style={styles.notesCard}>
              <Text style={styles.notesLabel}>Notes</Text>
              <Text style={styles.notesTxt}>{active.notes}</Text>
            </View>
          ) : null}

          {active.receipt_image_base64 ? (
            <Text style={[styles.sectionLabel, { marginTop: spacing.lg }]}>Receipt photo on file</Text>
          ) : null}
        </ScrollView>
      </SafeAreaView>
    );
  }

  // ----- LIST VIEW -----
  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <Header onBack={() => router.back()} title="Purchase Sessions" />
      <ScrollView
        contentContainerStyle={styles.scroll}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} />}
      >
        {list.length === 0 ? (
          <View style={styles.emptyWrap}>
            <Icon name="ShoppingBag" size={32} color={colors.textMuted} />
            <Text style={styles.emptyTitle}>No purchases yet</Text>
            <Text style={styles.emptySub}>
              Scan a receipt or mark a shopping request as purchased — it will create a
              session here that updates your inventory and finance at the same time.
            </Text>
            <TouchableOpacity style={styles.cta} onPress={() => router.push('/scan-receipt')}>
              <Icon name="Camera" size={16} color="#fff" />
              <Text style={styles.ctaTxt}>Scan a receipt</Text>
            </TouchableOpacity>
          </View>
        ) : (
          list.map((s) => {
            const isOpen = !!expanded[s.session_id];
            return (
              <View key={s.session_id} style={styles.sessionCard}>
                <TouchableOpacity
                  style={styles.sessionHeader}
                  onPress={() => setExpanded((p) => ({ ...p, [s.session_id]: !p[s.session_id] }))}
                  onLongPress={() => router.push(`/purchase-session?id=${s.session_id}`)}
                  testID={`session-${s.session_id}`}
                >
                  <View style={{ flex: 1 }}>
                    <Text style={styles.sessionMerchant}>{s.merchant}</Text>
                    <Text style={styles.sessionMeta}>
                      {fmtDate(s.purchase_date)} · {s.items.length} item{s.items.length !== 1 ? 's' : ''}
                    </Text>
                  </View>
                  <Text style={styles.sessionTotal}>{formatMoney(s.total, s.currency)}</Text>
                  <Icon name={isOpen ? 'ChevronUp' : 'ChevronDown'} size={18} color={colors.textMuted} />
                </TouchableOpacity>
                {isOpen && (
                  <View style={styles.sessionItems}>
                    {s.items.map((it, i) => (
                      <View key={it.line_id || i} style={styles.expandRow}>
                        <View style={[styles.dot, { backgroundColor: it.inventory_applied ? '#5FA06A' : colors.textMuted }]} />
                        <Text style={styles.expandName}>{it.name}</Text>
                        <Text style={styles.expandQty}>{it.quantity}{it.unit ? ` ${it.unit}` : ''}</Text>
                      </View>
                    ))}
                    <TouchableOpacity
                      style={styles.openDetail}
                      onPress={() => router.push(`/purchase-session?id=${s.session_id}`)}
                    >
                      <Text style={styles.openDetailTxt}>Open full session</Text>
                      <Icon name="ChevronRight" size={14} color={colors.primary} />
                    </TouchableOpacity>
                  </View>
                )}
              </View>
            );
          })
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

function Header({ onBack, title, rightIcon, onRight }: any) {
  return (
    <View style={styles.header}>
      <TouchableOpacity onPress={onBack} style={styles.headerBtn} testID="purchase-back">
        <Icon name="ChevronLeft" size={22} color={colors.textMain} />
      </TouchableOpacity>
      <Text style={styles.headerTitle} numberOfLines={1}>{title}</Text>
      <TouchableOpacity style={styles.headerBtn} onPress={onRight}>
        {rightIcon ? <Icon name={rightIcon} size={18} color={colors.textMain} /> : null}
      </TouchableOpacity>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background },
  loadingWrap: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  header: {
    flexDirection: 'row', alignItems: 'center', paddingHorizontal: spacing.md, paddingVertical: spacing.sm,
    borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.border, backgroundColor: colors.background,
  },
  headerBtn: { width: 40, height: 40, alignItems: 'center', justifyContent: 'center' },
  headerTitle: { flex: 1, textAlign: 'center', fontSize: 17, fontWeight: '800', color: colors.textMain },
  scroll: { padding: spacing.md, paddingBottom: 48 },
  emptyWrap: { alignItems: 'center', paddingVertical: 60, paddingHorizontal: spacing.lg, gap: 10 },
  emptyTitle: { fontSize: 16, fontWeight: '800', color: colors.textMain },
  emptySub: { fontSize: 12, color: colors.textMuted, textAlign: 'center', lineHeight: 17 },
  cta: { marginTop: spacing.md, flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: colors.primary, paddingHorizontal: 18, paddingVertical: 12, borderRadius: radius.md },
  ctaTxt: { color: '#fff', fontWeight: '800' },
  sessionCard: { backgroundColor: colors.surface, borderRadius: radius.lg, marginBottom: spacing.sm, borderWidth: 1, borderColor: colors.border },
  sessionHeader: { flexDirection: 'row', alignItems: 'center', gap: 8, padding: spacing.md },
  sessionMerchant: { fontSize: 15, fontWeight: '800', color: colors.textMain },
  sessionMeta: { fontSize: 11, color: colors.textMuted, marginTop: 2 },
  sessionTotal: { fontSize: 14, fontWeight: '800', color: colors.textMain },
  sessionItems: { paddingHorizontal: spacing.md, paddingBottom: spacing.md, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.border, paddingTop: spacing.sm },
  expandRow: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingVertical: 6 },
  dot: { width: 8, height: 8, borderRadius: 4 },
  expandName: { flex: 1, fontSize: 13, color: colors.textMain },
  expandQty: { fontSize: 12, color: colors.textMuted, fontWeight: '700' },
  openDetail: { flexDirection: 'row', alignItems: 'center', justifyContent: 'flex-end', marginTop: spacing.sm, gap: 4 },
  openDetailTxt: { color: colors.primary, fontSize: 12, fontWeight: '800' },
  hero: { alignItems: 'center', paddingVertical: spacing.lg, gap: 4 },
  heroMerchant: { fontSize: 22, fontWeight: '900', color: colors.textMain },
  heroDate: { fontSize: 13, color: colors.textMuted },
  heroTotal: { fontSize: 32, fontWeight: '900', color: colors.primary, marginTop: spacing.sm },
  heroMeta: { fontSize: 11, color: colors.textMuted, marginTop: 4 },
  sectionLabel: { fontSize: 12, fontWeight: '800', color: colors.textMuted, textTransform: 'uppercase', letterSpacing: 0.5, marginTop: spacing.md, marginBottom: spacing.sm },
  itemRow: { flexDirection: 'row', alignItems: 'center', backgroundColor: colors.surface, padding: spacing.md, borderRadius: radius.md, marginBottom: 6, borderWidth: 1, borderColor: colors.border },
  itemName: { fontSize: 14, fontWeight: '700', color: colors.textMain },
  itemSub: { fontSize: 11, color: colors.textMuted, marginTop: 2 },
  itemPrice: { fontSize: 13, fontWeight: '800', color: colors.textMain },
  notesCard: { marginTop: spacing.md, backgroundColor: colors.surfaceAlt, borderRadius: radius.md, padding: spacing.md, borderWidth: 1, borderColor: colors.border },
  notesLabel: { fontSize: 11, fontWeight: '800', color: colors.textMuted, marginBottom: 4 },
  notesTxt: { fontSize: 13, color: colors.textMain, lineHeight: 18 },
});
