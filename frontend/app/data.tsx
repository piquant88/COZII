import React, { useState, useCallback, useMemo } from 'react';
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity, ActivityIndicator, Alert,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useFocusEffect, useRouter, useLocalSearchParams } from 'expo-router';
import * as Clipboard from 'expo-clipboard';
import { useAuth } from '../src/AuthContext';
import { api } from '../src/api';
import { colors, radius, spacing, shadows, tints } from '../src/theme';
import { Icon } from '../src/Icon';
import { formatMoney } from '../src/currency';
import { toCSV, exportText } from '../src/csv';

const TABS = [
  { key: 'summary', label: 'Summary' },
  { key: 'items', label: 'Items' },
  { key: 'categories', label: 'Categories' },
  { key: 'members', label: 'Members' },
  { key: 'bills', label: 'Bills' },
  { key: 'settlements', label: 'Settlements' },
];

const PERIODS: Record<string, string> = {
  this_month: 'This month',
  last_month: 'Last month',
  last_3_months: 'Last 3 months',
  ytd: 'Year-to-date',
  all: 'All time',
};

export default function DataSheet() {
  const router = useRouter();
  const { activeSpace } = useAuth();
  const params = useLocalSearchParams<{ period?: string }>();
  const initialPeriod = (params?.period as string) || 'this_month';

  const [period, setPeriod] = useState(initialPeriod);
  const [tab, setTab] = useState('summary');
  const [report, setReport] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    if (!activeSpace) return;
    setLoading(true);
    try {
      const r = await api.get<any>(`/reports/finance?space_id=${activeSpace.space_id}&period=${period}`);
      setReport(r);
    } catch (e) { console.warn(e); }
    finally { setLoading(false); }
  }, [activeSpace, period]);

  useFocusEffect(useCallback(() => { load(); }, [load]));

  const currency = report?.currency || activeSpace?.currency || 'USD';

  const sections = useMemo(() => {
    if (!report) return {} as Record<string, { title: string; rows: any[]; columns: { key: string; label: string; w?: number; numeric?: boolean }[] }>;
    return {
      summary: {
        title: 'Summary',
        rows: [
          { metric: 'Period', value: report.period_label },
          { metric: 'Currency', value: report.currency },
          { metric: 'Items logged', value: report.totals.count },
          { metric: 'Total spent', value: formatMoney(report.totals.total, currency) },
          { metric: 'Average / item', value: formatMoney(report.totals.avg_per_item, currency) },
          { metric: 'Largest', value: formatMoney(report.totals.largest, currency) },
          { metric: 'Smallest', value: formatMoney(report.totals.smallest, currency) },
          { metric: 'Categories tracked', value: report.by_category.length },
          { metric: 'Members contributing', value: report.by_member.length },
          { metric: 'Recurring bills', value: report.bills.length },
          { metric: 'Settlements in window', value: report.settlements.length },
        ],
        columns: [
          { key: 'metric', label: 'Metric', w: 200 },
          { key: 'value', label: 'Value', w: 200 },
        ],
      },
      items: {
        title: 'Items',
        rows: report.all_items || [],
        columns: [
          { key: 'name', label: 'Item', w: 180 },
          { key: 'category_name', label: 'Category', w: 130 },
          { key: 'price', label: `Price (${currency})`, w: 100, numeric: true },
          { key: 'quantity', label: 'Qty', w: 60, numeric: true },
          { key: 'purchased_by', label: 'Bought by', w: 130 },
          { key: 'purchase_date', label: 'Purchased', w: 100 },
          { key: 'expiry_date', label: 'Expiry', w: 100 },
          { key: 'status', label: 'Status', w: 90 },
          { key: 'created_at', label: 'Logged at', w: 180 },
        ],
      },
      categories: {
        title: 'Categories',
        rows: report.by_category || [],
        columns: [
          { key: 'name', label: 'Category', w: 180 },
          { key: 'total', label: `Total (${currency})`, w: 120, numeric: true },
          { key: 'count', label: 'Items', w: 70, numeric: true },
          { key: 'pct', label: '% of spend', w: 100, numeric: true },
        ],
      },
      members: {
        title: 'Members',
        rows: report.by_member || [],
        columns: [
          { key: 'name', label: 'Member', w: 160 },
          { key: 'total', label: `Total (${currency})`, w: 120, numeric: true },
          { key: 'count', label: 'Items', w: 70, numeric: true },
          { key: 'pct', label: '% of spend', w: 100, numeric: true },
        ],
      },
      bills: {
        title: 'Bills',
        rows: report.bills || [],
        columns: [
          { key: 'name', label: 'Bill', w: 160 },
          { key: 'amount', label: `Amount (${currency})`, w: 110, numeric: true },
          { key: 'frequency', label: 'Freq', w: 90 },
          { key: 'due_day', label: 'Due day', w: 80, numeric: true },
          { key: 'is_paid_current_period', label: 'Paid?', w: 70 },
          { key: 'next_due_date', label: 'Next due', w: 110 },
          { key: 'last_paid_date', label: 'Last paid', w: 110 },
          { key: 'category_name', label: 'Category', w: 130 },
        ],
      },
      settlements: {
        title: 'Settlements',
        rows: report.settlements || [],
        columns: [
          { key: 'from_name', label: 'From', w: 130 },
          { key: 'to_name', label: 'To', w: 130 },
          { key: 'amount', label: `Amount (${currency})`, w: 110, numeric: true },
          { key: 'note', label: 'Note', w: 200 },
          { key: 'created_at', label: 'When', w: 180 },
        ],
      },
    };
  }, [report, currency]);

  const current = sections[tab as keyof typeof sections];

  const copyCSV = async () => {
    if (!current) return;
    const csv = toCSV(current.rows, current.columns.map((c) => ({ key: c.key, label: c.label })));
    try {
      await Clipboard.setStringAsync(csv);
      Alert.alert('Copied', `${current.title} CSV copied to clipboard.`);
    } catch (e: any) { Alert.alert('Copy failed', e?.message || ''); }
  };

  const shareCSV = async () => {
    if (!current) return;
    const csv = toCSV(current.rows, current.columns.map((c) => ({ key: c.key, label: c.label })));
    const fname = `cozii-${tab}-${period}-${new Date().toISOString().slice(0, 10)}.csv`;
    await exportText(fname, csv);
  };

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <View style={styles.header}>
        <TouchableOpacity style={styles.iconBtn} onPress={() => router.back()} testID="data-back">
          <Icon name="ArrowLeft" color={colors.textMain} />
        </TouchableOpacity>
        <Text style={styles.title}>Raw data</Text>
        <View style={{ width: 40 }} />
      </View>

      {/* Period selector */}
      <View style={{ height: 44 }}>
        <ScrollView
          horizontal
          showsHorizontalScrollIndicator={false}
          contentContainerStyle={styles.periodRow}
        >
          {Object.entries(PERIODS).map(([k, l]) => (
            <TouchableOpacity
              key={k}
              style={[styles.periodChip, period === k && styles.periodChipActive]}
              onPress={() => setPeriod(k)}
            >
              <Text style={[styles.periodTxt, period === k && styles.periodTxtActive]}>{l}</Text>
            </TouchableOpacity>
          ))}
        </ScrollView>
      </View>

      {/* Section tabs */}
      <View style={{ height: 44 }}>
        <ScrollView
          horizontal
          showsHorizontalScrollIndicator={false}
          contentContainerStyle={styles.tabRow}
        >
          {TABS.map((t) => (
            <TouchableOpacity
              key={t.key}
              style={[styles.tabChip, tab === t.key && styles.tabChipActive]}
              onPress={() => setTab(t.key)}
              testID={`tab-${t.key}`}
            >
              <Text style={[styles.tabTxt, tab === t.key && styles.tabTxtActive]}>{t.label}</Text>
            </TouchableOpacity>
          ))}
        </ScrollView>
      </View>

      {/* Action row */}
      <View style={styles.actionRow}>
        <Text style={styles.actionLbl}>
          {current ? `${current.rows.length} ${current.rows.length === 1 ? 'row' : 'rows'}` : ''}
        </Text>
        <TouchableOpacity style={styles.smallBtn} onPress={copyCSV} testID="data-copy">
          <Icon name="Copy" size={14} color={colors.textMain} />
          <Text style={styles.smallBtnTxt}>Copy CSV</Text>
        </TouchableOpacity>
        <TouchableOpacity style={[styles.smallBtn, { backgroundColor: colors.primary }]} onPress={shareCSV} testID="data-share">
          <Icon name="ArrowRight" size={14} color="#fff" />
          <Text style={[styles.smallBtnTxt, { color: '#fff' }]}>Export</Text>
        </TouchableOpacity>
      </View>

      {loading || !current ? (
        <ActivityIndicator color={colors.primary} style={{ marginTop: 60 }} />
      ) : current.rows.length === 0 ? (
        <View style={styles.emptyBox}>
          <Icon name="Box" size={28} color={colors.textMuted} />
          <Text style={styles.emptyTxt}>No rows in this section.</Text>
        </View>
      ) : (
        <ScrollView horizontal showsHorizontalScrollIndicator>
          <View>
            <View style={styles.headerRow}>
              {current.columns.map((c) => (
                <View key={c.key} style={[styles.cell, styles.cellHeader, { width: c.w || 120 }]}>
                  <Text style={styles.cellHeaderTxt} numberOfLines={1}>{c.label}</Text>
                </View>
              ))}
            </View>
            <ScrollView style={{ maxHeight: 460 }}>
              {current.rows.map((row, idx) => (
                <View key={idx} style={[styles.dataRow, idx % 2 === 0 && styles.dataRowAlt]}>
                  {current.columns.map((c) => {
                    let val: any = (row as any)[c.key];
                    if (typeof val === 'boolean') val = val ? 'Yes' : 'No';
                    if (val === null || val === undefined) val = '';
                    if (c.numeric && typeof val === 'number' && c.label.includes(currency)) {
                      val = formatMoney(val, currency);
                    } else if (c.numeric && typeof val === 'number') {
                      val = String(val);
                    }
                    return (
                      <View key={c.key} style={[styles.cell, { width: c.w || 120 }]}>
                        <Text style={[styles.cellTxt, c.numeric && { textAlign: 'right' }]} numberOfLines={2}>{String(val)}</Text>
                      </View>
                    );
                  })}
                </View>
              ))}
            </ScrollView>
          </View>
        </ScrollView>
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background },
  header: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingHorizontal: spacing.md, paddingVertical: spacing.sm,
  },
  iconBtn: {
    width: 40, height: 40, borderRadius: 20,
    backgroundColor: colors.surface,
    alignItems: 'center', justifyContent: 'center',
    ...shadows.card,
  },
  title: { fontSize: 18, fontWeight: '800', color: colors.textMain },
  periodRow: { paddingHorizontal: spacing.md, gap: 8, paddingBottom: 8 },
  periodChip: {
    paddingHorizontal: 12, paddingVertical: 6, borderRadius: radius.full,
    backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border,
  },
  periodChipActive: { backgroundColor: colors.primary, borderColor: colors.primary },
  periodTxt: { fontSize: 11, fontWeight: '700', color: colors.textMain },
  periodTxtActive: { color: '#fff' },

  tabRow: { paddingHorizontal: spacing.md, gap: 6, paddingBottom: 8 },
  tabChip: {
    paddingHorizontal: 12, paddingVertical: 8, borderRadius: radius.sm,
    backgroundColor: colors.surfaceAlt,
  },
  tabChipActive: { backgroundColor: colors.surface, ...shadows.card },
  tabTxt: { fontSize: 12, fontWeight: '700', color: colors.textMuted },
  tabTxtActive: { color: colors.textMain },

  actionRow: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: spacing.md, paddingVertical: 8, gap: 8 },
  actionLbl: { flex: 1, fontSize: 12, color: colors.textMuted, fontWeight: '700' },
  smallBtn: {
    flexDirection: 'row', alignItems: 'center', gap: 6,
    paddingHorizontal: 12, paddingVertical: 8,
    backgroundColor: colors.surface, borderRadius: radius.full,
    ...shadows.card,
  },
  smallBtnTxt: { fontSize: 12, fontWeight: '800', color: colors.textMain },

  emptyBox: { alignItems: 'center', paddingVertical: 60, gap: 8 },
  emptyTxt: { color: colors.textMuted },

  headerRow: { flexDirection: 'row', backgroundColor: colors.surfaceAlt, borderTopWidth: 1, borderTopColor: colors.border, borderBottomWidth: 1, borderBottomColor: colors.border },
  cell: { paddingVertical: 10, paddingHorizontal: 8, borderRightWidth: 1, borderRightColor: colors.border, justifyContent: 'center' },
  cellHeader: { backgroundColor: colors.surfaceAlt },
  cellHeaderTxt: { fontSize: 11, fontWeight: '800', color: colors.textMain, textTransform: 'uppercase', letterSpacing: 0.4 },
  dataRow: { flexDirection: 'row', borderBottomWidth: 1, borderBottomColor: colors.border, backgroundColor: colors.surface },
  dataRowAlt: { backgroundColor: '#FBFBFC' },
  cellTxt: { fontSize: 12, color: colors.textMain },
});
