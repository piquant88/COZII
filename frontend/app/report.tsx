import React, { useState, useCallback, useMemo } from 'react';
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity, RefreshControl,
  ActivityIndicator, Modal, Platform,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useFocusEffect, useRouter } from 'expo-router';
import { useAuth } from '../src/AuthContext';
import { api } from '../src/api';
import { colors, radius, spacing, shadows, tints } from '../src/theme';
import { Icon } from '../src/Icon';
import { formatMoney, taxTips, getCurrency } from '../src/currency';
import { toCSV, combineCSV, exportText, exportPDFFromHTML } from '../src/csv';
import { PieChart, PieLegend, BarChart } from '../src/Charts';

const PERIODS = [
  { key: 'this_month', label: 'This month' },
  { key: 'last_month', label: 'Last month' },
  { key: 'last_3_months', label: 'Last 3 months' },
  { key: 'ytd', label: 'Year-to-date' },
  { key: 'all', label: 'All time' },
];

const TINT_COLORS = ['#3CB4A0', '#9B6FB0', '#E8936F', '#C9A227', '#5FA06A', '#E08B7A', '#6A94B8'];

type Report = any;

export default function ReportScreen() {
  const router = useRouter();
  const { activeSpace } = useAuth();
  const [period, setPeriod] = useState('this_month');
  const [report, setReport] = useState<Report | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [showExport, setShowExport] = useState(false);
  const [showTaxTips, setShowTaxTips] = useState(false);

  const load = useCallback(async () => {
    if (!activeSpace) return;
    setLoading(true);
    try {
      const r = await api.get<Report>(`/reports/finance?space_id=${activeSpace.space_id}&period=${period}`);
      setReport(r);
    } catch (e) { console.warn(e); }
    finally { setLoading(false); }
  }, [activeSpace, period]);

  useFocusEffect(useCallback(() => { load(); }, [load]));

  const onRefresh = async () => { setRefreshing(true); await load(); setRefreshing(false); };

  const currency = report?.currency || activeSpace?.currency || 'USD';

  const pieSlices = useMemo(() => {
    if (!report) return [];
    return (report.by_category || []).slice(0, 8).map((c: any, i: number) => ({
      label: c.name, value: c.total,
      color: tints[c.tint]?.icon || TINT_COLORS[i % TINT_COLORS.length],
    }));
  }, [report]);

  const monthlyBars = useMemo(() => {
    if (!report) return [];
    return (report.monthly || []).slice(-6).map((m: any) => ({
      label: m.month.slice(5), value: m.total, key: m.month,
    }));
  }, [report]);

  const exportCSV = async () => {
    if (!report) return;
    setShowExport(false);
    const sections = [
      { title: 'Summary', csv: toCSV([{ Period: report.period_label, Currency: report.currency, Total: report.totals.total, Items: report.totals.count, Average: report.totals.avg_per_item, Largest: report.totals.largest, Smallest: report.totals.smallest }]) },
      { title: 'By category', csv: toCSV(report.by_category || [], [
        { key: 'name', label: 'Category' }, { key: 'total', label: `Total (${currency})` }, { key: 'count', label: 'Items' }, { key: 'pct', label: '% of spend' },
      ]) },
      { title: 'By member', csv: toCSV(report.by_member || [], [
        { key: 'name', label: 'Member' }, { key: 'total', label: `Total (${currency})` }, { key: 'count', label: 'Items' }, { key: 'pct', label: '% of spend' },
      ]) },
      { title: 'Items', csv: toCSV(report.all_items || [], [
        { key: 'name', label: 'Item' }, { key: 'category_name', label: 'Category' }, { key: 'price', label: `Price (${currency})` },
        { key: 'quantity', label: 'Qty' }, { key: 'purchased_by', label: 'Purchased by' }, { key: 'purchase_date', label: 'Purchase date' },
        { key: 'expiry_date', label: 'Expiry' }, { key: 'status', label: 'Status' }, { key: 'created_at', label: 'Logged at' },
      ]) },
      { title: 'Bills', csv: toCSV(report.bills || [], [
        { key: 'name', label: 'Bill' }, { key: 'amount', label: `Amount (${currency})` }, { key: 'frequency', label: 'Frequency' },
        { key: 'due_day', label: 'Due day' }, { key: 'is_paid_current_period', label: 'Paid?' },
        { key: 'next_due_date', label: 'Next due' }, { key: 'last_paid_date', label: 'Last paid' }, { key: 'category_name', label: 'Category' },
      ]) },
      { title: 'Settlements', csv: toCSV(report.settlements || [], [
        { key: 'from_name', label: 'From' }, { key: 'to_name', label: 'To' }, { key: 'amount', label: `Amount (${currency})` },
        { key: 'note', label: 'Note' }, { key: 'created_at', label: 'When' },
      ]) },
      { title: 'Daily totals', csv: toCSV(report.daily || [], [
        { key: 'date', label: 'Date' }, { key: 'total', label: `Total (${currency})` },
      ]) },
      { title: 'Monthly totals', csv: toCSV(report.monthly || [], [
        { key: 'month', label: 'Month' }, { key: 'total', label: `Total (${currency})` },
      ]) },
    ];
    const csv = combineCSV(sections);
    const fname = `cozii-finance-${period}-${new Date().toISOString().slice(0, 10)}.csv`;
    await exportText(fname, csv, 'text/csv');
  };

  const exportPDF = async () => {
    if (!report) return;
    setShowExport(false);
    const html = buildHTML(report, currency);
    const fname = `cozii-finance-${period}-${new Date().toISOString().slice(0, 10)}.pdf`;
    await exportPDFFromHTML(fname, html);
  };

  if (!activeSpace) {
    return (
      <SafeAreaView style={styles.container} edges={['top']}>
        <Text style={{ padding: 24 }}>Pick or create a space first.</Text>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <View style={styles.header}>
        <TouchableOpacity style={styles.iconBtn} onPress={() => router.back()} testID="report-back">
          <Icon name="ArrowLeft" color={colors.textMain} />
        </TouchableOpacity>
        <Text style={styles.title}>Finance report</Text>
        <TouchableOpacity style={styles.iconBtn} onPress={() => setShowExport(true)} testID="report-export">
          <Icon name="ArrowRight" color={colors.textMain} size={18} />
        </TouchableOpacity>
      </View>

      <ScrollView
        contentContainerStyle={styles.scroll}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.primary} />}
      >
        {/* Period selector */}
        <View style={styles.periodWrap}>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8 }}>
            {PERIODS.map((p) => (
              <TouchableOpacity
                key={p.key}
                style={[styles.periodChip, period === p.key && styles.periodChipActive]}
                onPress={() => setPeriod(p.key)}
                testID={`period-${p.key}`}
              >
                <Text style={[styles.periodTxt, period === p.key && styles.periodTxtActive]}>{p.label}</Text>
              </TouchableOpacity>
            ))}
          </ScrollView>
        </View>

        {loading || !report ? (
          <ActivityIndicator color={colors.primary} style={{ marginTop: 60 }} />
        ) : (
          <>
            {/* Hero */}
            <View style={styles.heroCard}>
              <Text style={styles.heroLabel}>{report.period_label} · {getCurrency(currency).code}</Text>
              <Text style={styles.heroAmount}>{formatMoney(report.totals.total, currency)}</Text>
              <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12, marginTop: 8 }}>
                <Stat label="Items" value={String(report.totals.count)} />
                <Stat label="Avg / item" value={formatMoney(report.totals.avg_per_item, currency)} />
                <Stat label="Largest" value={formatMoney(report.totals.largest, currency)} />
              </View>
            </View>

            {/* Insights */}
            {report.insights?.length > 0 && (
              <View style={[styles.card, { gap: 8 }]}>
                <Text style={styles.sectionTitle}>What this means</Text>
                {report.insights.map((i: string, idx: number) => (
                  <Text key={idx} style={styles.insightLine}>• {i}</Text>
                ))}
              </View>
            )}

            {/* Tax tips */}
            <TouchableOpacity
              style={[styles.card, styles.taxBtn]}
              onPress={() => setShowTaxTips((v) => !v)}
              activeOpacity={0.8}
              testID="report-tax-toggle"
            >
              <Icon name="Lightbulb" size={18} color={tints.yellow.icon} />
              <Text style={styles.taxBtnTxt}>Tax & spending tips for {currency}</Text>
              <Icon name={showTaxTips ? 'ChevronUp' : 'ChevronDown'} size={16} color={colors.textMuted} />
            </TouchableOpacity>
            {showTaxTips && (
              <View style={[styles.card, { gap: 6, backgroundColor: tints.yellow.bg }]}>
                {taxTips(currency).map((t, i) => (
                  <Text key={i} style={[styles.insightLine, { color: '#7a5d12' }]}>• {t}</Text>
                ))}
                <Text style={[styles.helper, { marginTop: 6 }]}>
                  Friendly guidance only — not legal or tax advice.
                </Text>
              </View>
            )}

            {/* Where it went */}
            <Text style={styles.sectionTitle}>Where it went</Text>
            <View style={styles.pieCard}>
              {pieSlices.length === 0 ? (
                <Text style={{ color: colors.textMuted }}>No spending in this period.</Text>
              ) : (
                <>
                  <View style={styles.pieWrap}>
                    <PieChart slices={pieSlices} size={180} hole={62} />
                    <View style={styles.pieCenter} pointerEvents="none">
                      <Text style={styles.pieCenterAmount}>{formatMoney(report.totals.total, currency)}</Text>
                      <Text style={styles.pieCenterLbl}>spent</Text>
                    </View>
                  </View>
                  <PieLegend slices={pieSlices} />
                </>
              )}
            </View>

            {/* By category table */}
            {(report.by_category || []).length > 0 && (
              <View style={styles.card}>
                {(report.by_category || []).map((c: any) => (
                  <View key={c.category_id} style={styles.tblRow}>
                    <View style={[styles.tintDot, { backgroundColor: tints[c.tint]?.icon || colors.primary }]} />
                    <Text style={styles.tblName}>{c.name}</Text>
                    <Text style={styles.tblPct}>{c.pct}%</Text>
                    <Text style={styles.tblAmt}>{formatMoney(c.total, currency)}</Text>
                  </View>
                ))}
              </View>
            )}

            {/* By member */}
            {(report.by_member || []).length > 1 && (
              <>
                <Text style={[styles.sectionTitle, { marginTop: spacing.lg }]}>Who paid</Text>
                <View style={styles.card}>
                  {report.by_member.map((m: any) => (
                    <View key={m.user_id} style={styles.tblRow}>
                      <View style={[styles.avatar, { backgroundColor: tints.peach.icon }]}>
                        <Text style={styles.avatarTxt}>{m.name?.[0]?.toUpperCase()}</Text>
                      </View>
                      <Text style={styles.tblName}>{m.name}</Text>
                      <Text style={styles.tblPct}>{m.pct}%</Text>
                      <Text style={styles.tblAmt}>{formatMoney(m.total, currency)}</Text>
                    </View>
                  ))}
                </View>
              </>
            )}

            {/* Monthly trend */}
            {monthlyBars.length > 1 && (
              <>
                <Text style={[styles.sectionTitle, { marginTop: spacing.lg }]}>Monthly trend</Text>
                <View style={styles.chartCard}>
                  <BarChart data={monthlyBars} width={300} height={160} color={colors.primary} />
                  <View style={styles.barLabels}>
                    {monthlyBars.map((m: any, i: number) => (
                      <View key={i} style={{ flex: 1, alignItems: 'center' }}>
                        <Text style={styles.barAmt}>{formatMoney(m.value, currency)}</Text>
                        <Text style={styles.barLbl}>{m.label}</Text>
                      </View>
                    ))}
                  </View>
                </View>
              </>
            )}

            {/* Top items */}
            {(report.top_items || []).length > 0 && (
              <>
                <Text style={[styles.sectionTitle, { marginTop: spacing.lg }]}>Top purchases</Text>
                {report.top_items.slice(0, 10).map((it: any) => (
                  <View key={it.item_id} style={styles.itemRow}>
                    <View style={{ flex: 1 }}>
                      <Text style={styles.tblName} numberOfLines={1}>{it.name}</Text>
                      <Text style={styles.tblSub}>{it.category_name} · {it.purchased_by}</Text>
                    </View>
                    <Text style={styles.tblAmt}>{formatMoney(it.price, currency)}</Text>
                  </View>
                ))}
              </>
            )}

            {/* Open raw data */}
            <TouchableOpacity
              style={[styles.card, styles.dataBtn]}
              onPress={() => router.push(`/data?period=${period}`)}
              testID="report-open-data"
            >
              <Icon name="Box" size={18} color={tints.lavender.icon} />
              <Text style={styles.dataBtnTxt}>Open raw data sheet</Text>
              <Icon name="ChevronRight" size={16} color={colors.textMuted} />
            </TouchableOpacity>
          </>
        )}
      </ScrollView>

      {/* Export sheet */}
      <Modal visible={showExport} animationType="fade" transparent onRequestClose={() => setShowExport(false)}>
        <View style={styles.modalOverlay}>
          <View style={styles.exportCard}>
            <Text style={styles.exportTitle}>Export this report</Text>
            <Text style={styles.exportSub}>{report?.period_label || ''} · {currency}</Text>
            <TouchableOpacity style={styles.exportRow} onPress={exportPDF} testID="export-pdf">
              <View style={[styles.expIcon, { backgroundColor: tints.pink.bg }]}>
                <Icon name="FileText" size={22} color={tints.pink.icon} />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={styles.exportRowTitle}>PDF report</Text>
                <Text style={styles.exportRowSub}>Printable / share via email or messages</Text>
              </View>
              <Icon name="ChevronRight" size={16} color={colors.textMuted} />
            </TouchableOpacity>
            <TouchableOpacity style={styles.exportRow} onPress={exportCSV} testID="export-csv">
              <View style={[styles.expIcon, { backgroundColor: tints.sage.bg }]}>
                <Icon name="Box" size={22} color={tints.sage.icon} />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={styles.exportRowTitle}>CSV (spreadsheet)</Text>
                <Text style={styles.exportRowSub}>Open in Sheets / Excel — multiple sections in one file</Text>
              </View>
              <Icon name="ChevronRight" size={16} color={colors.textMuted} />
            </TouchableOpacity>
            <TouchableOpacity style={styles.exportCancel} onPress={() => setShowExport(false)}>
              <Text style={styles.exportCancelTxt}>Cancel</Text>
            </TouchableOpacity>
          </View>
        </View>
      </Modal>
    </SafeAreaView>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <View style={{ minWidth: 90 }}>
      <Text style={styles.statLbl}>{label}</Text>
      <Text style={styles.statVal}>{value}</Text>
    </View>
  );
}

function buildHTML(r: any, currency: string): string {
  const fmt = (n: number) => formatMoney(n, currency);
  const rows = (arr: any[], cells: (x: any) => string[]) =>
    arr.map((x) => `<tr>${cells(x).map((c) => `<td>${c}</td>`).join('')}</tr>`).join('');
  const insights = (r.insights || []).map((i: string) => `<li>${escapeHtml(i)}</li>`).join('');
  const tips = taxTips(currency).map((t) => `<li>${escapeHtml(t)}</li>`).join('');
  const cats = rows(r.by_category || [], (c: any) => [c.name, fmt(c.total), String(c.count), `${c.pct}%`]);
  const mems = rows(r.by_member || [], (m: any) => [m.name, fmt(m.total), String(m.count), `${m.pct}%`]);
  const items = rows((r.top_items || []).slice(0, 30), (i: any) => [escapeHtml(i.name), escapeHtml(i.category_name), escapeHtml(i.purchased_by), fmt(i.price)]);
  const bills = rows(r.bills || [], (b: any) => [escapeHtml(b.name), fmt(b.amount), b.frequency, b.is_paid_current_period ? 'Paid' : 'Due', b.next_due_date || '']);
  const settle = rows(r.settlements || [], (s: any) => [escapeHtml(s.from_name), escapeHtml(s.to_name), fmt(s.amount), escapeHtml(s.note || ''), s.created_at?.slice(0, 10) || '']);
  return `<!DOCTYPE html><html><head><meta charset="utf-8" />
    <title>Cozii finance report</title>
    <style>
      *{box-sizing:border-box;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;}
      body{padding:24px;color:#2D3436;}
      h1{font-size:28px;margin:0 0 4px;}
      h2{font-size:18px;margin:24px 0 8px;border-bottom:2px solid #FFB5A7;padding-bottom:4px;}
      .label{color:#636E72;font-size:13px;}
      .hero{background:#FEF9F8;padding:20px;border-radius:14px;margin-top:8px;}
      .amount{font-size:36px;font-weight:900;letter-spacing:-1px;}
      .grid{display:flex;gap:18px;margin-top:8px;flex-wrap:wrap;}
      .stat{min-width:120px;}
      .stat .v{font-size:18px;font-weight:800;}
      table{width:100%;border-collapse:collapse;margin-top:6px;font-size:13px;}
      th,td{padding:8px 10px;text-align:left;border-bottom:1px solid #eee;}
      th{background:#F8F9FA;font-size:11px;text-transform:uppercase;letter-spacing:0.5px;color:#636E72;}
      ul{padding-left:18px;line-height:1.5;}
      .small{color:#636E72;font-size:11px;margin-top:4px;}
      .badge{display:inline-block;background:#FFEDE0;color:#8b5a3a;padding:2px 10px;border-radius:999px;font-size:11px;font-weight:700;}
    </style></head><body>
    <h1>Cozii finance report</h1>
    <div class="label">${escapeHtml(r.period_label)} <span class="badge">${currency}</span></div>
    <div class="hero">
      <div class="label">Total spent</div>
      <div class="amount">${fmt(r.totals.total)}</div>
      <div class="grid">
        <div class="stat"><div class="label">Items</div><div class="v">${r.totals.count}</div></div>
        <div class="stat"><div class="label">Avg / item</div><div class="v">${fmt(r.totals.avg_per_item)}</div></div>
        <div class="stat"><div class="label">Largest</div><div class="v">${fmt(r.totals.largest)}</div></div>
        <div class="stat"><div class="label">Smallest</div><div class="v">${fmt(r.totals.smallest)}</div></div>
      </div>
    </div>
    ${insights ? `<h2>What this means</h2><ul>${insights}</ul>` : ''}
    <h2>Tax & spending tips for ${currency}</h2>
    <ul>${tips}</ul><div class="small">Friendly guidance only — not legal or tax advice.</div>
    ${cats ? `<h2>By category</h2><table><thead><tr><th>Category</th><th>Total</th><th>Items</th><th>%</th></tr></thead><tbody>${cats}</tbody></table>` : ''}
    ${mems ? `<h2>Who paid</h2><table><thead><tr><th>Member</th><th>Total</th><th>Items</th><th>%</th></tr></thead><tbody>${mems}</tbody></table>` : ''}
    ${items ? `<h2>Top items</h2><table><thead><tr><th>Item</th><th>Category</th><th>Paid by</th><th>Price</th></tr></thead><tbody>${items}</tbody></table>` : ''}
    ${bills ? `<h2>Recurring bills</h2><table><thead><tr><th>Name</th><th>Amount</th><th>Frequency</th><th>Status</th><th>Next due</th></tr></thead><tbody>${bills}</tbody></table>` : ''}
    ${settle ? `<h2>Settlements</h2><table><thead><tr><th>From</th><th>To</th><th>Amount</th><th>Note</th><th>Date</th></tr></thead><tbody>${settle}</tbody></table>` : ''}
    <div class="small" style="margin-top:32px;">Generated by Cozii on ${new Date().toLocaleString()}</div>
  </body></html>`;
}

function escapeHtml(s: any): string {
  return String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c] as string));
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
  scroll: { padding: spacing.md, paddingBottom: 100 },
  periodWrap: { marginBottom: spacing.md },
  periodChip: {
    paddingHorizontal: 14, paddingVertical: 8, borderRadius: radius.full,
    backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border,
  },
  periodChipActive: { backgroundColor: colors.primary, borderColor: colors.primary },
  periodTxt: { fontSize: 12, fontWeight: '700', color: colors.textMain },
  periodTxtActive: { color: '#fff' },
  heroCard: {
    backgroundColor: colors.surface, borderRadius: radius.lg,
    padding: spacing.lg, marginBottom: spacing.md,
    ...shadows.card,
  },
  heroLabel: { fontSize: 13, color: colors.textMuted, fontWeight: '700' },
  heroAmount: { fontSize: 36, fontWeight: '900', color: colors.textMain, letterSpacing: -1, marginTop: 4 },
  statLbl: { fontSize: 10, color: colors.textMuted, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 0.4 },
  statVal: { fontSize: 14, fontWeight: '800', color: colors.textMain, marginTop: 2 },
  card: { backgroundColor: colors.surface, borderRadius: radius.lg, padding: spacing.md, ...shadows.card, marginBottom: spacing.sm },
  sectionTitle: { fontSize: 15, fontWeight: '800', color: colors.textMain, marginBottom: 8, marginTop: 8 },
  insightLine: { fontSize: 13, color: colors.textMain, lineHeight: 19 },
  helper: { fontSize: 11, color: colors.textMuted, fontStyle: 'italic' },
  taxBtn: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  taxBtnTxt: { flex: 1, fontSize: 13, fontWeight: '700', color: colors.textMain },
  pieCard: {
    backgroundColor: colors.surface, borderRadius: radius.lg,
    padding: spacing.md, alignItems: 'center', marginBottom: spacing.sm,
    ...shadows.card,
  },
  pieWrap: { width: 180, height: 180, alignItems: 'center', justifyContent: 'center' },
  pieCenter: { position: 'absolute', alignItems: 'center', justifyContent: 'center' },
  pieCenterAmount: { fontSize: 16, fontWeight: '900', color: colors.textMain, letterSpacing: -0.3 },
  pieCenterLbl: { fontSize: 10, color: colors.textMuted, marginTop: 2 },
  tblRow: {
    flexDirection: 'row', alignItems: 'center', gap: 10,
    paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: colors.border,
  },
  tintDot: { width: 10, height: 10, borderRadius: 5 },
  tblName: { flex: 1, fontSize: 13, fontWeight: '700', color: colors.textMain },
  tblSub: { fontSize: 11, color: colors.textMuted, marginTop: 2 },
  tblPct: { fontSize: 11, color: colors.textMuted, fontWeight: '700', minWidth: 40, textAlign: 'right' },
  tblAmt: { fontSize: 13, fontWeight: '800', color: colors.textMain, minWidth: 70, textAlign: 'right' },
  avatar: { width: 28, height: 28, borderRadius: 14, alignItems: 'center', justifyContent: 'center' },
  avatarTxt: { color: '#fff', fontWeight: '800', fontSize: 12 },
  itemRow: {
    flexDirection: 'row', alignItems: 'center', gap: 10,
    backgroundColor: colors.surface, padding: 10, borderRadius: radius.md, marginBottom: 6,
    ...shadows.card,
  },
  chartCard: { backgroundColor: colors.surface, borderRadius: radius.lg, padding: spacing.md, ...shadows.card },
  barLabels: { flexDirection: 'row', marginTop: 4 },
  barAmt: { fontSize: 10, fontWeight: '700', color: colors.textMain },
  barLbl: { fontSize: 10, color: colors.textMuted, marginTop: 2 },
  dataBtn: { flexDirection: 'row', alignItems: 'center', gap: 10, marginTop: spacing.md },
  dataBtnTxt: { flex: 1, fontSize: 13, fontWeight: '700', color: colors.textMain },

  modalOverlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.5)', justifyContent: 'center', alignItems: 'center', padding: 24 },
  exportCard: {
    backgroundColor: colors.surface, borderRadius: radius.lg, padding: spacing.lg,
    width: '100%', maxWidth: 380, ...shadows.card,
  },
  exportTitle: { fontSize: 18, fontWeight: '800', color: colors.textMain },
  exportSub: { fontSize: 12, color: colors.textMuted, marginTop: 4, marginBottom: spacing.md },
  exportRow: {
    flexDirection: 'row', alignItems: 'center', gap: 12,
    paddingVertical: 12, borderTopWidth: 1, borderTopColor: colors.border,
  },
  expIcon: { width: 44, height: 44, borderRadius: 14, alignItems: 'center', justifyContent: 'center' },
  exportRowTitle: { fontSize: 14, fontWeight: '800', color: colors.textMain },
  exportRowSub: { fontSize: 11, color: colors.textMuted, marginTop: 2 },
  exportCancel: { paddingVertical: 14, alignItems: 'center', marginTop: 8, backgroundColor: colors.surfaceAlt, borderRadius: radius.full },
  exportCancelTxt: { color: colors.textMain, fontWeight: '700' },
});
