import React, { useState, useCallback, useMemo } from 'react';
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity, RefreshControl, Image,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useFocusEffect } from 'expo-router';
import { useAuth } from '../../src/AuthContext';
import { colors, radius, spacing, shadows, tints } from '../../src/theme';
import { Icon } from '../../src/Icon';
import { api } from '../../src/api';
import type { Item, Category } from '../../src/types';

export default function Finance() {
  const { activeSpace } = useAuth();
  const [items, setItems] = useState<Item[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [refreshing, setRefreshing] = useState(false);

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

  const { totalMonth, byCategory, lastMonth, monthItems } = useMemo(() => {
    const now = new Date();
    const firstOfMonth = new Date(now.getFullYear(), now.getMonth(), 1);
    const firstOfLast = new Date(now.getFullYear(), now.getMonth() - 1, 1);
    const firstOfThis = firstOfMonth;

    let total = 0;
    let last = 0;
    const byCat: Record<string, number> = {};
    const mi: Item[] = [];

    items.forEach((it) => {
      const price = typeof it.price === 'number' ? it.price : 0;
      if (!price) return;
      const d = new Date(it.created_at);
      if (d >= firstOfMonth) {
        total += price;
        byCat[it.category_id] = (byCat[it.category_id] || 0) + price;
        mi.push(it);
      } else if (d >= firstOfLast && d < firstOfThis) {
        last += price;
      }
    });
    return { totalMonth: total, byCategory: byCat, lastMonth: last, monthItems: mi };
  }, [items]);

  const diff = totalMonth - lastMonth;
  const diffPct = lastMonth > 0 ? (diff / lastMonth) * 100 : 0;

  const catName = (id: string) => categories.find((c) => c.category_id === id)?.name || 'Uncategorized';
  const catTint = (id: string) => categories.find((c) => c.category_id === id)?.tint || 'mint';

  const monthLabel = new Date().toLocaleString('default', { month: 'long', year: 'numeric' });

  const topCats = Object.entries(byCategory)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 6);

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <ScrollView
        contentContainerStyle={styles.scroll}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.primary} />}
        showsVerticalScrollIndicator={false}
      >
        <Text style={styles.title}>Finance</Text>
        <Text style={styles.subtitle}>{monthLabel}</Text>

        <View style={styles.heroCard}>
          <Text style={styles.heroLabel}>Spent this month</Text>
          <Text style={styles.heroAmount} testID="finance-total">${totalMonth.toFixed(2)}</Text>
          <View style={styles.diffRow}>
            {lastMonth > 0 ? (
              <>
                <View style={[styles.diffBadge, { backgroundColor: diff <= 0 ? tints.sage.bg : tints.pink.bg }]}>
                  <Text style={[styles.diffTxt, { color: diff <= 0 ? tints.sage.icon : tints.pink.icon }]}>
                    {diff > 0 ? '+' : ''}{diffPct.toFixed(0)}%
                  </Text>
                </View>
                <Text style={styles.diffLabel}>vs last month (${lastMonth.toFixed(2)})</Text>
              </>
            ) : (
              <Text style={styles.diffLabel}>Log items with a price to track spending</Text>
            )}
          </View>
        </View>

        <Text style={styles.sectionTitle}>By category</Text>
        {topCats.length === 0 ? (
          <View style={[styles.card, { alignItems: 'center', paddingVertical: 32 }]}>
            <Icon name="PieChart" size={28} color={colors.textMuted} />
            <Text style={{ color: colors.textMuted, marginTop: 8 }}>No spending logged yet.</Text>
          </View>
        ) : (
          topCats.map(([cid, amount]) => {
            const tint = tints[catTint(cid)] || tints.mint;
            const pct = totalMonth > 0 ? (amount / totalMonth) * 100 : 0;
            return (
              <View key={cid} style={styles.catRow}>
                <View style={styles.catTopRow}>
                  <View style={[styles.catDot, { backgroundColor: tint.icon }]} />
                  <Text style={styles.catName}>{catName(cid)}</Text>
                  <Text style={styles.catAmt}>${amount.toFixed(2)}</Text>
                </View>
                <View style={styles.bar}>
                  <View style={[styles.barFill, { width: `${pct}%`, backgroundColor: tint.icon }]} />
                </View>
              </View>
            );
          })
        )}

        <Text style={[styles.sectionTitle, { marginTop: spacing.lg }]}>This month's purchases</Text>
        {monthItems.length === 0 ? (
          <View style={[styles.card, { alignItems: 'center', paddingVertical: 24 }]}>
            <Text style={{ color: colors.textMuted }}>Add items with prices to see them here.</Text>
          </View>
        ) : (
          monthItems
            .sort((a, b) => +new Date(b.created_at) - +new Date(a.created_at))
            .slice(0, 20)
            .map((it) => (
              <View key={it.item_id} style={styles.txnRow}>
                <View style={styles.txnImg}>
                  {it.photo_base64 ? (
                    <Image source={{ uri: it.photo_base64 }} style={styles.txnImgInner} />
                  ) : (
                    <Icon name="Package" color={colors.textMuted} size={18} />
                  )}
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={styles.txnName}>{it.name}</Text>
                  <Text style={styles.txnCat}>{catName(it.category_id)}</Text>
                </View>
                <Text style={styles.txnAmt}>${(it.price || 0).toFixed(2)}</Text>
              </View>
            ))
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background },
  scroll: { padding: spacing.lg, paddingBottom: 140 },
  title: { fontSize: 30, fontWeight: '900', color: colors.textMain, letterSpacing: -0.5 },
  subtitle: { fontSize: 14, color: colors.textMuted, marginBottom: spacing.md, marginTop: 2 },
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
  catRow: {
    backgroundColor: colors.surface,
    padding: spacing.md,
    borderRadius: radius.md,
    marginBottom: 8,
    ...shadows.card,
  },
  catTopRow: { flexDirection: 'row', alignItems: 'center', marginBottom: 8 },
  catDot: { width: 10, height: 10, borderRadius: 5, marginRight: 8 },
  catName: { flex: 1, fontSize: 14, fontWeight: '700', color: colors.textMain },
  catAmt: { fontSize: 14, fontWeight: '800', color: colors.textMain },
  bar: {
    height: 6, backgroundColor: colors.surfaceAlt, borderRadius: 3, overflow: 'hidden',
  },
  barFill: { height: '100%', borderRadius: 3 },
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
    backgroundColor: colors.surfaceAlt,
    alignItems: 'center', justifyContent: 'center',
    overflow: 'hidden',
  },
  txnImgInner: { width: '100%', height: '100%' },
  txnName: { fontSize: 14, fontWeight: '700', color: colors.textMain },
  txnCat: { fontSize: 12, color: colors.textMuted, marginTop: 2 },
  txnAmt: { fontSize: 14, fontWeight: '800', color: colors.textMain },
});
