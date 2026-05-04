import React, { useState, useCallback } from 'react';
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity, RefreshControl,
  ActivityIndicator, Image,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useFocusEffect, useRouter } from 'expo-router';
import { useAuth } from '../src/AuthContext';
import { api, BASE_URL, tokenStorage } from '../src/api';
import { colors, radius, spacing, shadows, tints } from '../src/theme';
import { Icon } from '../src/Icon';
import { formatMoney } from '../src/currency';
import { Alert } from 'react-native';

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

async function downloadFile(url: string, fileName: string, token: string | null) {
  try {
    const FS: any = await import('expo-file-system');
    const Sharing: any = await import('expo-sharing');
    const { Alert } = await import('react-native');
    // Use FileSystem.legacy if available (SDK 54+) with proper Auth header
    const dir = FS.documentDirectory || FS.cacheDirectory || (FS.Paths?.cache?.uri ?? '');
    const dest = `${dir}${fileName}`;
    let resultUri: string | null = null;
    if (FS.createDownloadResumable) {
      const dl = FS.createDownloadResumable(url, dest, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      const r = await dl.downloadAsync();
      resultUri = r?.uri || null;
    } else {
      // Fallback: fetch and write
      const res = await fetch(url, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const blob = await res.blob();
      const reader = new FileReader();
      const b64 = await new Promise<string>((resolve, reject) => {
        reader.onerror = () => reject(reader.error);
        reader.onload = () => resolve((reader.result as string).split(',')[1]);
        reader.readAsDataURL(blob);
      });
      if (FS.writeAsStringAsync) {
        await FS.writeAsStringAsync(dest, b64, { encoding: FS.EncodingType?.Base64 || 'base64' });
        resultUri = dest;
      } else {
        // Web fallback: trigger browser download
        const link = document.createElement('a');
        link.href = URL.createObjectURL(blob);
        link.download = fileName;
        link.click();
        return;
      }
    }
    if (!resultUri) { Alert.alert('Download failed'); return; }
    const can = await Sharing.isAvailableAsync();
    if (can) {
      await Sharing.shareAsync(resultUri, {
        dialogTitle: 'Save report',
        mimeType: fileName.endsWith('.pdf') ? 'application/pdf' : 'text/csv',
        UTI: fileName.endsWith('.pdf') ? 'com.adobe.pdf' : 'public.comma-separated-values-text',
      });
    } else {
      Alert.alert('Saved', `Report saved to ${resultUri}`);
    }
  } catch (e: any) {
    const { Alert } = await import('react-native');
    Alert.alert('Download failed', e?.message || 'Try again with a stable network.');
  }
}

type Report = any;

export default function HouseholdReportScreen() {
  const router = useRouter();
  const { activeSpace } = useAuth();
  const today = new Date();
  const [year, setYear] = useState(today.getFullYear());
  const [month, setMonth] = useState(today.getMonth() + 1);
  const [report, setReport] = useState<Report | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    if (!activeSpace) return;
    setLoading(true);
    try {
      const r = await api.get<Report>(`/reports/household?space_id=${activeSpace.space_id}&year=${year}&month=${month}`);
      setReport(r);
    } catch (e) { console.warn(e); }
    finally { setLoading(false); }
  }, [activeSpace, year, month]);

  useFocusEffect(useCallback(() => { load(); }, [load]));
  const onRefresh = async () => { setRefreshing(true); await load(); setRefreshing(false); };

  const shiftMonth = (delta: number) => {
    let nm = month + delta;
    let ny = year;
    if (nm < 1) { nm = 12; ny = year - 1; }
    if (nm > 12) { nm = 1; ny = year + 1; }
    setMonth(nm); setYear(ny);
  };

  const currency = report?.currency || activeSpace?.currency || 'USD';
  const totalStaffWages = report?.total_wages || 0;
  const totalSpent = report?.total_spent || 0;
  const householdOther = Math.max(totalSpent - totalStaffWages, 0);

  return (
    <SafeAreaView style={styles.container} edges={['top', 'bottom']}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.backBtn} testID="hh-report-back">
          <Icon name="ChevronRight" size={18} color={colors.textMain} />
        </TouchableOpacity>
        <View style={{ flex: 1 }}>
          <Text style={styles.kicker}>{activeSpace?.name}</Text>
          <Text style={styles.title}>Monthly Report</Text>
        </View>
        <TouchableOpacity
          style={styles.downloadBtn}
          onPress={async () => {
            try {
              const Linking = await import('expo-linking');
              const base = process.env.EXPO_PUBLIC_BACKEND_URL || '';
              const { tokenStorage } = await import('../src/api');
              const token = await tokenStorage.get();
              // CSV
              const csvUrl = `${base}/api/reports/household/export?space_id=${activeSpace?.space_id}&year=${year}&month=${month}&format=csv&t=${token}`;
              const pdfUrl = `${base}/api/reports/household/export?space_id=${activeSpace?.space_id}&year=${year}&month=${month}&format=pdf&t=${token}`;
              const { Alert } = await import('react-native');
              Alert.alert('Download report', `Choose format for ${MONTHS[month - 1]} ${year}.`, [
                { text: 'PDF', onPress: () => downloadFile(pdfUrl, `household-${year}-${String(month).padStart(2,'0')}.pdf`, token) },
                { text: 'CSV (Excel)', onPress: () => downloadFile(csvUrl, `household-${year}-${String(month).padStart(2,'0')}.csv`, token) },
                { text: 'Cancel', style: 'cancel' },
              ]);
            } catch (e: any) {
              const { Alert } = await import('react-native');
              Alert.alert('Error', e?.message || '');
            }
          }}
          testID="hh-download"
        >
          <Icon name="Download" size={16} color="#fff" />
        </TouchableOpacity>
      </View>

      {/* Month selector */}
      <View style={styles.monthBar}>
        <TouchableOpacity onPress={() => shiftMonth(-1)} style={styles.navBtn} testID="hh-prev-month">
          <Icon name="ChevronRight" size={16} color={colors.textMain} />
        </TouchableOpacity>
        <View style={{ alignItems: 'center' }}>
          <Text style={styles.monthTxt}>{MONTHS[month - 1]} {year}</Text>
        </View>
        <TouchableOpacity onPress={() => shiftMonth(1)} style={styles.navBtn} testID="hh-next-month">
          <Icon name="ChevronRight" size={16} color={colors.textMain} />
        </TouchableOpacity>
      </View>

      <ScrollView
        contentContainerStyle={styles.scroll}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.primary} />}
      >
        {loading ? (
          <ActivityIndicator style={{ marginTop: 60 }} color={colors.primary} />
        ) : !report ? (
          <Text style={styles.empty}>No data yet for this month.</Text>
        ) : (
          <>
            {/* Hero — total spending */}
            <View style={[styles.heroCard, { backgroundColor: tints.peach.bg }]}>
              <Text style={styles.heroLabel}>This month, the house spent</Text>
              <Text style={styles.heroAmt}>{formatMoney(totalSpent, currency)}</Text>
              <Text style={styles.heroSub}>
                {formatMoney(householdOther, currency)} on home · {formatMoney(totalStaffWages, currency)} on staff
              </Text>
            </View>

            {/* Top categories */}
            {(report.top_categories || []).length > 0 && (
              <View style={{ marginTop: spacing.md }}>
                <Text style={styles.sectionTitle}>Where the money went</Text>
                {report.top_categories.map((c: any) => {
                  const t = tints[(c.tint as keyof typeof tints) || 'mint'] || tints.mint;
                  const pct = totalSpent ? Math.max(4, Math.round((c.total / totalSpent) * 100)) : 0;
                  return (
                    <View key={c.category_id || c.name} style={styles.catRow}>
                      <View style={[styles.catIcon, { backgroundColor: t.bg }]}>
                        <Icon name={c.icon} size={18} color={t.icon} />
                      </View>
                      <View style={{ flex: 1 }}>
                        <View style={{ flexDirection: 'row', alignItems: 'baseline', justifyContent: 'space-between' }}>
                          <Text style={styles.catName}>{c.name}</Text>
                          <Text style={styles.catAmt}>{formatMoney(c.total, currency)}</Text>
                        </View>
                        <View style={styles.barBg}>
                          <View style={[styles.barFill, { width: `${pct}%`, backgroundColor: t.icon }]} />
                        </View>
                        <Text style={styles.catSub}>{c.count} {c.count === 1 ? 'item' : 'items'} · {pct}% of spending</Text>
                      </View>
                    </View>
                  );
                })}
              </View>
            )}

            {/* Staff summary */}
            {(report.staff || []).length > 0 && (
              <View style={{ marginTop: spacing.md }}>
                <Text style={styles.sectionTitle}>Your helpers this month</Text>
                {report.staff.map((s: any) => (
                  <View key={s.staff_id} style={styles.staffCard}>
                    <View style={[styles.avatar, { backgroundColor: tints.blue.icon }]}>
                      {s.photo_base64 ? (
                        <Image source={{ uri: s.photo_base64 }} style={styles.avatarImg} />
                      ) : (
                        <Text style={styles.avatarTxt}>{(s.name || '?')[0]?.toUpperCase()}</Text>
                      )}
                    </View>
                    <View style={{ flex: 1 }}>
                      <Text style={styles.staffName}>{s.name}</Text>
                      <View style={styles.badgeRow}>
                        <View style={[styles.miniBadge, { backgroundColor: tints.sage.bg }]}>
                          <Text style={[styles.miniTxt, { color: tints.sage.icon }]}>{s.days_present}d present</Text>
                        </View>
                        {s.days_sick > 0 && (
                          <View style={[styles.miniBadge, { backgroundColor: tints.pink.bg }]}>
                            <Text style={[styles.miniTxt, { color: tints.pink.icon }]}>{s.days_sick}d sick</Text>
                          </View>
                        )}
                        {s.days_off > 0 && (
                          <View style={[styles.miniBadge, { backgroundColor: tints.lavender.bg }]}>
                            <Text style={[styles.miniTxt, { color: tints.lavender.icon }]}>{s.days_off}d off</Text>
                          </View>
                        )}
                        {s.tasks_done > 0 && (
                          <View style={[styles.miniBadge, { backgroundColor: tints.mint.bg }]}>
                            <Text style={[styles.miniTxt, { color: tints.mint.icon }]}>{s.tasks_done} tasks done</Text>
                          </View>
                        )}
                      </View>
                      {s.paid > 0 ? (
                        <Text style={styles.staffSub}>Paid {formatMoney(s.paid, currency)} this month</Text>
                      ) : s.salary ? (
                        <Text style={[styles.staffSub, { color: tints.yellow.icon }]}>Not paid yet — {formatMoney(s.salary, currency)} / {s.pay_cycle}</Text>
                      ) : (
                        <Text style={styles.staffSub}>No salary set</Text>
                      )}
                    </View>
                  </View>
                ))}
              </View>
            )}

            {/* Shopping summary */}
            {report.shopping && report.shopping.total > 0 && (
              <View style={{ marginTop: spacing.md }}>
                <Text style={styles.sectionTitle}>Shopping requests</Text>
                <View style={[styles.shopCard, { backgroundColor: tints.pink.bg }]}>
                  <View style={styles.shopStat}>
                    <Text style={styles.shopNum}>{report.shopping.total}</Text>
                    <Text style={styles.shopLbl}>total</Text>
                  </View>
                  <View style={styles.shopStat}>
                    <Text style={styles.shopNum}>{report.shopping.purchased}</Text>
                    <Text style={styles.shopLbl}>bought</Text>
                  </View>
                  <View style={styles.shopStat}>
                    <Text style={styles.shopNum}>{report.shopping.approved}</Text>
                    <Text style={styles.shopLbl}>to buy</Text>
                  </View>
                  <View style={styles.shopStat}>
                    <Text style={styles.shopNum}>{report.shopping.pending}</Text>
                    <Text style={styles.shopLbl}>pending</Text>
                  </View>
                </View>
              </View>
            )}

            {/* Tasks done */}
            {report.tasks_done > 0 && (
              <View style={[styles.bottomNote, { backgroundColor: tints.mint.bg }]}>
                <Icon name="Check" size={18} color={tints.mint.icon} />
                <Text style={styles.bottomTxt}>
                  <Text style={{ fontWeight: '800', color: tints.mint.icon }}>{report.tasks_done}</Text> household tasks completed this month.
                </Text>
              </View>
            )}

            {/* Empty state */}
            {(!report.staff || report.staff.length === 0) && (!report.top_categories || report.top_categories.length === 0) && (
              <Text style={styles.empty}>No activity in {MONTHS[month - 1]} {year} yet. Add staff, log attendance, or record expenses to see your report.</Text>
            )}
          </>
        )}

        <View style={{ height: 80 }} />
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background },
  header: { flexDirection: 'row', alignItems: 'center', gap: 12, padding: spacing.md, paddingBottom: 0 },
  backBtn: {
    width: 40, height: 40, borderRadius: 20,
    backgroundColor: colors.surface,
    alignItems: 'center', justifyContent: 'center',
    transform: [{ rotate: '180deg' }],
    ...shadows.card,
  },
  downloadBtn: {
    width: 40, height: 40, borderRadius: 20,
    backgroundColor: colors.primary,
    alignItems: 'center', justifyContent: 'center',
    ...shadows.button,
  },
  kicker: { fontSize: 11, color: colors.textMuted, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 0.5 },
  title: { fontSize: 24, fontWeight: '900', color: colors.textMain, letterSpacing: -0.5 },
  monthBar: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    padding: spacing.md, paddingTop: spacing.sm,
  },
  navBtn: {
    width: 40, height: 40, borderRadius: 20,
    backgroundColor: colors.surface,
    alignItems: 'center', justifyContent: 'center',
    ...shadows.card,
  },
  monthTxt: { fontSize: 16, fontWeight: '800', color: colors.textMain },
  scroll: { padding: spacing.md, paddingTop: 0 },
  heroCard: {
    padding: spacing.lg, borderRadius: radius.lg,
    ...shadows.card,
  },
  heroLabel: { fontSize: 12, color: colors.textMuted, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 0.5 },
  heroAmt: { fontSize: 32, fontWeight: '900', color: colors.textMain, marginTop: 6, letterSpacing: -0.8 },
  heroSub: { fontSize: 13, color: colors.textMuted, marginTop: 6, lineHeight: 18 },
  sectionTitle: { fontSize: 12, fontWeight: '800', color: colors.textMuted, textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: spacing.sm },
  catRow: {
    flexDirection: 'row', alignItems: 'flex-start', gap: 12,
    backgroundColor: colors.surface,
    padding: spacing.md, borderRadius: radius.md,
    marginBottom: 8,
    ...shadows.card,
  },
  catIcon: { width: 40, height: 40, borderRadius: 14, alignItems: 'center', justifyContent: 'center' },
  catName: { fontSize: 14, fontWeight: '700', color: colors.textMain },
  catAmt: { fontSize: 14, fontWeight: '800', color: colors.textMain },
  catSub: { fontSize: 11, color: colors.textMuted, marginTop: 4 },
  barBg: { height: 6, borderRadius: 3, backgroundColor: '#EEE7E2', marginTop: 6, overflow: 'hidden' },
  barFill: { height: '100%', borderRadius: 3 },
  staffCard: {
    flexDirection: 'row', alignItems: 'center', gap: 12,
    backgroundColor: colors.surface,
    padding: spacing.md, borderRadius: radius.md,
    marginBottom: 8,
    ...shadows.card,
  },
  avatar: { width: 44, height: 44, borderRadius: 16, alignItems: 'center', justifyContent: 'center', overflow: 'hidden' },
  avatarImg: { width: '100%', height: '100%' },
  avatarTxt: { color: '#fff', fontWeight: '800' },
  staffName: { fontSize: 15, fontWeight: '800', color: colors.textMain },
  staffSub: { fontSize: 12, color: colors.textMuted, marginTop: 6 },
  badgeRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 4, marginTop: 6 },
  miniBadge: { paddingHorizontal: 8, paddingVertical: 4, borderRadius: 10 },
  miniTxt: { fontSize: 10, fontWeight: '800' },
  shopCard: {
    flexDirection: 'row', justifyContent: 'space-around',
    padding: spacing.md, borderRadius: radius.md,
    ...shadows.card,
  },
  shopStat: { alignItems: 'center' },
  shopNum: { fontSize: 22, fontWeight: '900', color: colors.textMain },
  shopLbl: { fontSize: 11, color: colors.textMuted, fontWeight: '700', marginTop: 4 },
  bottomNote: {
    flexDirection: 'row', alignItems: 'center', gap: 8,
    padding: spacing.md, borderRadius: radius.md, marginTop: spacing.md,
  },
  bottomTxt: { flex: 1, fontSize: 13, color: colors.textMain },
  empty: { textAlign: 'center', color: colors.textMuted, padding: spacing.xl, fontStyle: 'italic' },
});
