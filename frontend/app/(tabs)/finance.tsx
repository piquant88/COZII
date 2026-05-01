import React, { useState, useCallback, useMemo } from 'react';
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity, RefreshControl, Image, Dimensions,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useFocusEffect, useRouter } from 'expo-router';
import { useAuth } from '../../src/AuthContext';
import { colors, radius, spacing, shadows, tints } from '../../src/theme';
import { Icon } from '../../src/Icon';
import { api } from '../../src/api';
import { formatMoney } from '../../src/currency';
import type { Item, Category } from '../../src/types';
import { PieChart, PieLegend, BarChart } from '../../src/Charts';

const TINT_COLORS = ['#3CB4A0', '#9B6FB0', '#E8936F', '#C9A227', '#5FA06A', '#E08B7A', '#6A94B8'];

export default function Finance() {
  const { activeSpace } = useAuth();
  const router = useRouter();
  const [items, setItems] = useState<Item[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [refreshing, setRefreshing] = useState(false);
  const [view, setView] = useState<'month' | 'trend'>('month');

  const load = useCallback(async () => {
    if (!activeSpace) return;
    try {
      const [it, cats] = await Promise.all([
        api.get<Item[]>(`/items?space_id=${activeSpace.space_id}`),
        api.get<Category[]>(`/categories?space_id=${activeSpace.space_id}`),
      ]);
      setItems(it);
      setCategories(cats);
    } catch (e) { console.warn(e); }
  }, [activeSpace]);

  useFocusEffect(useCallback(() => { load(); }, [load]));

  const onRefresh = async () => { setRefreshing(true); await load(); setRefreshing(false); };

  const catName = (id: string) => categories.find((c) => c.category_id === id)?.name || 'Uncategorized';
  const catTint = (id: string) => categories.find((c) => c.category_id === id)?.tint || 'mint';

  // Current-month spend, by category, transactions
  const monthAgg = useMemo(() => {
    const now = new Date();
    const firstOfMonth = new Date(now.getFullYear(), now.getMonth(), 1);
    const firstOfLast = new Date(now.getFullYear(), now.getMonth() - 1, 1);
    let total = 0, last = 0;
    const byCat: Record<string, number> = {};
    const monthItems: Item[] = [];
    items.forEach((it) => {
      const p = typeof it.price === 'number' ? it.price : 0;
      if (!p) return;
      const d = new Date(it.created_at);
      if (d >= firstOfMonth) {
        total += p;
        byCat[it.category_id] = (byCat[it.category_id] || 0) + p;
        monthItems.push(it);
      } else if (d >= firstOfLast && d < firstOfMonth) {
        last += p;
      }
    });
    return { total, last, byCat, monthItems };
  }, [items]);

  const diff = monthAgg.total - monthAgg.last;
  const diffPct = monthAgg.last > 0 ? (diff / monthAgg.last) * 100 : 0;

  // Pie slices for current month spend by category
  const pieSlices = useMemo(() => {
    const entries = Object.entries(monthAgg.byCat).sort((a, b) => b[1] - a[1]);
    return entries.map(([cid, val], i) => ({
      label: catName(cid),
      value: val,
      color: tints[catTint(cid)]?.icon || TINT_COLORS[i % TINT_COLORS.length],
    }));
  }, [monthAgg, categories]);

  // Last 6 months trend
  const sixMonths = useMemo(() => {
    const now = new Date();
    const buckets: { label: string; value: number; key: string }[] = [];
    for (let i = 5; i >= 0; i--) {
      const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
      buckets.push({
        label: d.toLocaleString('default', { month: 'short' }),
        key: `${d.getFullYear()}-${d.getMonth()}`,
        value: 0,
      });
    }
    items.forEach((it) => {
      const p = typeof it.price === 'number' ? it.price : 0;
      if (!p) return;
      const d = new Date(it.created_at);
      const key = `${d.getFullYear()}-${d.getMonth()}`;
      const b = buckets.find((x) => x.key === key);
      if (b) b.value += p;
    });
    return buckets;
  }, [items]);

  const sixMonthTotal = sixMonths.reduce((s, x) => s + x.value, 0);
  const sixMonthAvg = sixMonthTotal / 6;
  const screenW = Dimensions.get('window').width;
  const chartW = Math.min(screenW - 64, 360);

  const monthLabel = new Date().toLocaleString('default', { month: 'long', year: 'numeric' });
  const cur = activeSpace?.currency || 'USD';

  // Top items this month
  const topPurchases = monthAgg.monthItems
    .slice()
    .sort((a, b) => (b.price || 0) - (a.price || 0))
    .slice(0, 8);

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <ScrollView
        contentContainerStyle={styles.scroll}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.primary} />}
        showsVerticalScrollIndicator={false}
      >
        <Text style={styles.title}>Finance</Text>

        <View style={styles.quickRow}>
          <TouchableOpacity
            style={[styles.quickCard, { backgroundColor: tints.lavender.bg }]}
            onPress={() => router.push('/report')}
            testID="finance-report-link"
          >
            <Icon name="FileText" size={22} color={tints.lavender.icon} />
            <Text style={styles.quickTxt}>Report & export</Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={[styles.quickCard, { backgroundColor: tints.blue.bg }]}
            onPress={() => router.push('/bills')}
            testID="finance-bills-link"
          >
            <Icon name="Receipt" size={22} color={tints.blue.icon} />
            <Text style={styles.quickTxt}>Bills</Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={[styles.quickCard, { backgroundColor: tints.peach.bg }]}
            onPress={() => router.push('/splits')}
            testID="finance-splits-link"
          >
            <Icon name="Users" size={22} color={tints.peach.icon} />
            <Text style={styles.quickTxt}>Splits</Text>
          </TouchableOpacity>
        </View>

        <View style={styles.tabs}>
          <TouchableOpacity
            style={[styles.tab, view === 'month' && styles.tabActive]}
            onPress={() => setView('month')}
            testID="finance-tab-month"
          >
            <Text style={[styles.tabTxt, view === 'month' && styles.tabTxtActive]}>This month</Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={[styles.tab, view === 'trend' && styles.tabActive]}
            onPress={() => setView('trend')}
            testID="finance-tab-trend"
          >
            <Text style={[styles.tabTxt, view === 'trend' && styles.tabTxtActive]}>6-month trend</Text>
          </TouchableOpacity>
        </View>

        {view === 'month' ? (
          <>
            <View style={styles.heroCard}>
              <Text style={styles.heroLabel}>{monthLabel}</Text>
              <Text style={styles.heroAmount} testID="finance-total">{formatMoney(monthAgg.total, cur)}</Text>
              <View style={styles.diffRow}>
                {monthAgg.last > 0 ? (
                  <>
                    <View style={[styles.diffBadge, { backgroundColor: diff <= 0 ? tints.sage.bg : tints.pink.bg }]}>
                      <Text style={[styles.diffTxt, { color: diff <= 0 ? tints.sage.icon : tints.pink.icon }]}>
                        {diff > 0 ? '+' : ''}{diffPct.toFixed(0)}%
                      </Text>
                    </View>
                    <Text style={styles.diffLabel}>vs last month ({formatMoney(monthAgg.last, cur)})</Text>
                  </>
                ) : (
                  <Text style={styles.diffLabel}>Log items with a price to track spending</Text>
                )}
              </View>
            </View>

            <Text style={styles.sectionTitle}>Where it went</Text>
            <View style={styles.pieCard}>
              {pieSlices.length === 0 ? (
                <View style={{ alignItems: 'center', paddingVertical: 24 }}>
                  <Icon name="PieChart" size={28} color={colors.textMuted} />
                  <Text style={{ color: colors.textMuted, marginTop: 8 }}>No spending logged yet.</Text>
                </View>
              ) : (
                <>
                  <View style={styles.pieWrap}>
                    <PieChart slices={pieSlices} size={200} hole={70} />
                    <View style={styles.pieCenter} pointerEvents="none">
                      <Text style={styles.pieCenterAmount}>{formatMoney(monthAgg.total, cur)}</Text>
                      <Text style={styles.pieCenterLbl}>spent</Text>
                    </View>
                  </View>
                  <PieLegend slices={pieSlices} />
                </>
              )}
            </View>

            <Text style={[styles.sectionTitle, { marginTop: spacing.lg }]}>Biggest purchases this month</Text>
            {topPurchases.length === 0 ? (
              <View style={[styles.card, { alignItems: 'center', paddingVertical: 24 }]}>
                <Text style={{ color: colors.textMuted }}>Add items with prices to see them here.</Text>
              </View>
            ) : (
              topPurchases.map((it) => (
                <View key={it.item_id} style={styles.txnRow}>
                  <View style={[styles.txnImg, { backgroundColor: tints[catTint(it.category_id)]?.bg || colors.surfaceAlt }]}>
                    {it.photo_base64 ? (
                      <Image source={{ uri: it.photo_base64 }} style={styles.txnImgInner} />
                    ) : (
                      <Icon name="Package" color={colors.textMuted} size={16} />
                    )}
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.txnName} numberOfLines={1}>{it.name}</Text>
                    <Text style={styles.txnCat}>{catName(it.category_id)}</Text>
                  </View>
                  <Text style={styles.txnAmt}>{formatMoney(it.price || 0, cur)}</Text>
                </View>
              ))
            )}
          </>
        ) : (
          <>
            <View style={styles.heroCard}>
              <Text style={styles.heroLabel}>Last 6 months</Text>
              <Text style={styles.heroAmount}>{formatMoney(sixMonthTotal, cur)}</Text>
              <Text style={styles.diffLabel}>Average {formatMoney(sixMonthAvg, cur)} per month</Text>
            </View>

            <Text style={styles.sectionTitle}>Monthly trend</Text>
            <View style={styles.chartCard}>
              <BarChart data={sixMonths} width={chartW} height={180} color={colors.primary} />
              <View style={styles.barLabels}>
                {sixMonths.map((m, i) => (
                  <View key={i} style={styles.barLabelCol}>
                    <Text style={styles.barAmt}>{m.value > 999 ? `${(m.value / 1000).toFixed(1)}k` : Math.round(m.value)}</Text>
                    <Text style={styles.barLbl}>{m.label}</Text>
                  </View>
                ))}
              </View>
            </View>

            <Text style={[styles.sectionTitle, { marginTop: spacing.lg }]}>Insights</Text>
            <View style={styles.insightCard}>
              {(() => {
                const max = Math.max(...sixMonths.map((m) => m.value));
                const min = Math.min(...sixMonths.map((m) => m.value));
                const peak = sixMonths.find((m) => m.value === max);
                const low = sixMonths.find((m) => m.value === min && m.value > 0);
                const lines = [];
                if (peak && max > 0) lines.push(`📈 Highest spend was in ${peak.label} (${formatMoney(peak.value, cur)})`);
                if (low && low !== peak) lines.push(`📉 Lightest month: ${low.label} (${formatMoney(low.value, cur)})`);
                if (sixMonthAvg > 0) lines.push(`💡 You typically spend around ${formatMoney(sixMonthAvg, cur)}/month`);
                if (sixMonths[5].value > sixMonthAvg * 1.2) lines.push(`⚠️ This month is trending higher than usual`);
                else if (sixMonths[5].value < sixMonthAvg * 0.8 && sixMonths[5].value > 0) lines.push(`✨ This month is trending lower than usual`);
                if (lines.length === 0) lines.push('Keep adding items with prices to unlock insights.');
                return lines.map((l, i) => (
                  <Text key={i} style={styles.insightLine}>{l}</Text>
                ));
              })()}
            </View>
          </>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background },
  scroll: { padding: spacing.lg, paddingBottom: 140 },
  title: { fontSize: 30, fontWeight: '900', color: colors.textMain, letterSpacing: -0.5, marginBottom: spacing.md },
  quickRow: { flexDirection: 'row', gap: spacing.sm, marginBottom: spacing.md },
  quickCard: {
    flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8,
    paddingHorizontal: spacing.sm, paddingVertical: 14, borderRadius: radius.md,
  },
  quickTxt: { fontSize: 12, fontWeight: '800', color: colors.textMain, textAlign: 'center' },
  tabs: {
    flexDirection: 'row',
    backgroundColor: colors.surfaceAlt,
    borderRadius: radius.full,
    padding: 4,
    marginBottom: spacing.md,
  },
  tab: { flex: 1, alignItems: 'center', paddingVertical: 10, borderRadius: radius.full },
  tabActive: { backgroundColor: colors.surface, ...shadows.card },
  tabTxt: { fontSize: 13, fontWeight: '700', color: colors.textMuted },
  tabTxtActive: { color: colors.textMain },
  heroCard: {
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    padding: spacing.lg,
    marginBottom: spacing.lg,
    ...shadows.card,
  },
  heroLabel: { fontSize: 13, color: colors.textMuted, fontWeight: '600' },
  heroAmount: { fontSize: 40, fontWeight: '900', color: colors.textMain, letterSpacing: -1, marginTop: 4 },
  diffRow: { flexDirection: 'row', alignItems: 'center', gap: 10, marginTop: 8 },
  diffBadge: { borderRadius: radius.full, paddingHorizontal: 10, paddingVertical: 4 },
  diffTxt: { fontWeight: '800', fontSize: 12 },
  diffLabel: { fontSize: 12, color: colors.textMuted },
  sectionTitle: { fontSize: 18, fontWeight: '800', color: colors.textMain, marginBottom: spacing.sm },
  pieCard: {
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    padding: spacing.lg,
    alignItems: 'center',
    ...shadows.card,
  },
  pieWrap: { width: 200, height: 200, alignItems: 'center', justifyContent: 'center' },
  pieCenter: {
    position: 'absolute',
    alignItems: 'center', justifyContent: 'center',
  },
  pieCenterAmount: { fontSize: 20, fontWeight: '900', color: colors.textMain, letterSpacing: -0.5 },
  pieCenterLbl: { fontSize: 11, color: colors.textMuted, fontWeight: '600', marginTop: 2 },
  chartCard: {
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    padding: spacing.md,
    alignItems: 'center',
    ...shadows.card,
  },
  barLabels: { flexDirection: 'row', justifyContent: 'space-around', width: '100%', marginTop: 4 },
  barLabelCol: { flex: 1, alignItems: 'center' },
  barLbl: { fontSize: 11, color: colors.textMuted, marginTop: 2 },
  barAmt: { fontSize: 11, color: colors.textMain, fontWeight: '700' },
  insightCard: {
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    padding: spacing.md,
    gap: 10,
    ...shadows.card,
  },
  insightLine: { fontSize: 14, color: colors.textMain, lineHeight: 20 },
  card: { backgroundColor: colors.surface, borderRadius: radius.lg, padding: spacing.md, ...shadows.card },
  txnRow: {
    flexDirection: 'row', alignItems: 'center', gap: 12,
    backgroundColor: colors.surface,
    padding: spacing.md,
    borderRadius: radius.md,
    marginBottom: 8,
    ...shadows.card,
  },
  txnImg: {
    width: 40, height: 40, borderRadius: 12,
    alignItems: 'center', justifyContent: 'center',
    overflow: 'hidden',
  },
  txnImgInner: { width: '100%', height: '100%' },
  txnName: { fontSize: 14, fontWeight: '700', color: colors.textMain },
  txnCat: { fontSize: 12, color: colors.textMuted, marginTop: 2 },
  txnAmt: { fontSize: 14, fontWeight: '800', color: colors.textMain },
});
