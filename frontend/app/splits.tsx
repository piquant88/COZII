import React, { useState, useCallback } from 'react';
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity, RefreshControl,
  TextInput, Image, KeyboardAvoidingView, Platform, ActivityIndicator,
} from 'react-native';
import * as ImagePicker from 'expo-image-picker';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useFocusEffect, useRouter } from 'expo-router';
import { useAuth } from '../src/AuthContext';
import { api } from '../src/api';
import { colors, radius, spacing, shadows, tints } from '../src/theme';
import { Icon } from '../src/Icon';
import type { Balances, Settlement, Balance, BalanceDetails, BalanceItem } from '../src/types';

export default function Splits() {
  const router = useRouter();
  const { activeSpace, user } = useAuth();
  const [balances, setBalances] = useState<Balances | null>(null);
  const [history, setHistory] = useState<Settlement[]>([]);
  const [refreshing, setRefreshing] = useState(false);

  const [paying, setPaying] = useState<Balance | null>(null);
  const [amount, setAmount] = useState('');
  const [note, setNote] = useState('');
  const [evidence, setEvidence] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  // Expanded breakdown state: key = other_user_id
  const [expanded, setExpanded] = useState<Record<string, BalanceDetails | 'loading' | 'error'>>({});

  const toggleExpand = async (otherId: string) => {
    if (!activeSpace) return;
    const cur = expanded[otherId];
    if (cur && cur !== 'loading' && cur !== 'error') {
      setExpanded((s) => { const n = { ...s }; delete n[otherId]; return n; });
      return;
    }
    setExpanded((s) => ({ ...s, [otherId]: 'loading' }));
    try {
      const d = await api.get<BalanceDetails>(`/balance-details?space_id=${activeSpace.space_id}&with_user_id=${otherId}`);
      setExpanded((s) => ({ ...s, [otherId]: d }));
    } catch (e) {
      setExpanded((s) => ({ ...s, [otherId]: 'error' }));
    }
  };

  const load = useCallback(async () => {
    if (!activeSpace) return;
    try {
      const [b, h] = await Promise.all([
        api.get<Balances>(`/balances?space_id=${activeSpace.space_id}`),
        api.get<Settlement[]>(`/settlements?space_id=${activeSpace.space_id}`),
      ]);
      setBalances(b);
      setHistory(h);
    } catch (e) { console.warn(e); }
  }, [activeSpace]);

  useFocusEffect(useCallback(() => { load(); }, [load]));

  const onRefresh = async () => { setRefreshing(true); await load(); setRefreshing(false); };

  const startPay = (b: Balance) => {
    setPaying(b);
    setAmount(b.amount.toFixed(2));
    setNote('');
    setEvidence(null);
    setErr(null);
  };

  const pickEvidence = async () => {
    try {
      const result = await ImagePicker.launchImageLibraryAsync({
        mediaTypes: ImagePicker.MediaTypeOptions.Images,
        quality: 0.5, base64: true, allowsEditing: false,
      });
      if (!result.canceled && result.assets[0]) {
        const a = result.assets[0];
        setEvidence(a.base64 ? `data:image/jpeg;base64,${a.base64}` : a.uri);
      }
    } catch (e) { console.warn(e); }
  };

  const confirmPay = async () => {
    if (!paying || !activeSpace) return;
    const amt = parseFloat(amount);
    if (!(amt > 0)) { setErr('Enter a valid amount'); return; }
    setSaving(true);
    setErr(null);
    try {
      await api.post('/settlements', {
        space_id: activeSpace.space_id,
        to_user_id: paying.to_user_id,
        amount: amt,
        note: note || null,
        evidence_photo_base64: evidence,
      });
      setPaying(null);
      setAmount(''); setNote(''); setEvidence(null);
      load();
    } catch (e: any) { setErr(e?.message || 'Failed'); }
    finally { setSaving(false); }
  };

  const removeSettlement = async (id: string) => {
    try { await api.delete(`/settlements/${id}`); load(); }
    catch (e: any) { console.warn(e); }
  };

  const cur = activeSpace?.currency || 'USD';
  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <View style={styles.header}>
        <TouchableOpacity style={styles.iconBtn} onPress={() => router.back()} testID="splits-back">
          <Icon name="ArrowLeft" color={colors.textMain} />
        </TouchableOpacity>
        <Text style={styles.title}>Money splits</Text>
        <View style={{ width: 40 }} />
      </View>

      <ScrollView
        contentContainerStyle={styles.scroll}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.primary} />}
      >
        {balances === null ? (
          <ActivityIndicator color={colors.primary} style={{ marginTop: 40 }} />
        ) : balances.shared_categories_count === 0 ? (
          <View style={styles.emptyHero}>
            <View style={[styles.heroIcon, { backgroundColor: tints.lavender.bg }]}>
              <Icon name="Users" color={tints.lavender.icon} size={32} />
            </View>
            <Text style={styles.emptyTitle}>No shared categories yet</Text>
            <Text style={styles.emptySub}>
              Open any category, tap the ✏️ pencil, and pick "Custom" sharing with 2+ people. Then any priced item is split automatically.
            </Text>
          </View>
        ) : (
          <>
            <View style={styles.summaryRow}>
              <View style={[styles.summaryCard, { backgroundColor: tints.sage.bg }]}>
                <Text style={[styles.summaryLbl, { color: tints.sage.icon }]}>You're owed</Text>
                <Text style={styles.summaryAmt} testID="splits-total-owed">{formatMoney(balances.total_owed_to_you, cur)}</Text>
              </View>
              <View style={[styles.summaryCard, { backgroundColor: tints.pink.bg }]}>
                <Text style={[styles.summaryLbl, { color: tints.pink.icon }]}>You owe</Text>
                <Text style={styles.summaryAmt} testID="splits-total-owe">{formatMoney(balances.total_you_owe, cur)}</Text>
              </View>
            </View>

            <View style={[styles.netCard, { backgroundColor: balances.net >= 0 ? tints.sage.bg : tints.pink.bg }]}>
              <Text style={[styles.netLbl, { color: balances.net >= 0 ? tints.sage.icon : tints.pink.icon }]}>
                Net balance
              </Text>
              <Text style={[styles.netAmt, { color: balances.net >= 0 ? tints.sage.icon : tints.pink.icon }]}>
                {balances.net >= 0 ? '+' : ''}{formatMoney(balances.net, cur)}
              </Text>
            </View>

            {balances.owed_to_you.length > 0 && (
              <>
                <Text style={styles.sectionTitle}>People who owe you</Text>
                {balances.owed_to_you.map((b) => {
                  const otherId = b.from_user_id;
                  const det = expanded[otherId];
                  const isOpen = !!det && det !== 'loading' && det !== 'error';
                  return (
                    <View key={`${b.from_user_id}-${b.to_user_id}`}>
                      <TouchableOpacity
                        style={styles.balanceRow}
                        onPress={() => toggleExpand(otherId)}
                        activeOpacity={0.7}
                        testID={`splits-row-owed-${otherId}`}
                      >
                        <View style={[styles.avatar, { backgroundColor: tints.peach.icon }]}>
                          <Text style={styles.avatarTxt}>{b.from_name?.[0]?.toUpperCase()}</Text>
                        </View>
                        <View style={{ flex: 1 }}>
                          <Text style={styles.balName}>{b.from_name}</Text>
                          <Text style={styles.balSub}>{isOpen ? 'hide details' : 'tap to see what for'}</Text>
                        </View>
                        <Text style={[styles.balAmt, { color: tints.sage.icon }]}>{formatMoney(b.amount, cur)}</Text>
                        <Icon name={isOpen ? 'ChevronUp' : 'ChevronDown'} size={16} color={colors.textMuted} />
                      </TouchableOpacity>
                      {det === 'loading' && (
                        <View style={styles.breakdownBox}><ActivityIndicator color={colors.primary} /></View>
                      )}
                      {isOpen && (
                        <View style={styles.breakdownBox}>
                          {(det as BalanceDetails).breakdown.filter((x) => x.direction === 'they_owe_you').map((it) => (
                            <View key={it.item_id} style={styles.breakdownRow}>
                              <View style={[styles.itemImg, { backgroundColor: tints.mint.bg }]}>
                                {it.photo_base64 ? (
                                  <Image source={{ uri: it.photo_base64 }} style={styles.itemImgInner} />
                                ) : (
                                  <Icon name="Package" size={14} color={tints.mint.icon} />
                                )}
                              </View>
                              <View style={{ flex: 1 }}>
                                <Text style={styles.itemName} numberOfLines={1}>{it.name}</Text>
                                <Text style={styles.itemSub}>
                                  {it.category_name} · {formatMoney(it.price, cur)} ÷ {it.split_count}
                                </Text>
                              </View>
                              <Text style={styles.itemAmt}>{formatMoney(it.share_each, cur)}</Text>
                            </View>
                          ))}
                          {(det as BalanceDetails).breakdown.filter((x) => x.direction === 'they_owe_you').length === 0 && (
                            <Text style={styles.emptyLine}>No items – possibly offset by their payments.</Text>
                          )}
                        </View>
                      )}
                    </View>
                  );
                })}
              </>
            )}

            {balances.you_owe.length > 0 && (
              <>
                <Text style={styles.sectionTitle}>You owe</Text>
                {balances.you_owe.map((b) => {
                  const otherId = b.to_user_id;
                  const det = expanded[otherId];
                  const isOpen = !!det && det !== 'loading' && det !== 'error';
                  return (
                    <View key={`${b.from_user_id}-${b.to_user_id}`}>
                      <View style={styles.balanceRow}>
                        <TouchableOpacity
                          style={styles.rowMain}
                          onPress={() => toggleExpand(otherId)}
                          activeOpacity={0.7}
                          testID={`splits-row-owe-${otherId}`}
                        >
                          <View style={[styles.avatar, { backgroundColor: tints.lavender.icon }]}>
                            <Text style={styles.avatarTxt}>{b.to_name?.[0]?.toUpperCase()}</Text>
                          </View>
                          <View style={{ flex: 1 }}>
                            <Text style={styles.balName}>{b.to_name}</Text>
                            <Text style={styles.balSub}>{isOpen ? 'hide details' : 'tap to see what for'}</Text>
                          </View>
                          <Text style={[styles.balAmt, { color: tints.pink.icon }]}>{formatMoney(b.amount, cur)}</Text>
                          <Icon name={isOpen ? 'ChevronUp' : 'ChevronDown'} size={16} color={colors.textMuted} />
                        </TouchableOpacity>
                        <TouchableOpacity
                          style={styles.payBtn}
                          onPress={() => startPay(b)}
                          testID={`splits-pay-${b.to_user_id}`}
                        >
                          <Text style={styles.payTxt}>Mark paid</Text>
                        </TouchableOpacity>
                      </View>
                      {det === 'loading' && (
                        <View style={styles.breakdownBox}><ActivityIndicator color={colors.primary} /></View>
                      )}
                      {isOpen && (
                        <View style={styles.breakdownBox}>
                          {(det as BalanceDetails).breakdown.filter((x) => x.direction === 'you_owe_them').map((it) => (
                            <View key={it.item_id} style={styles.breakdownRow}>
                              <View style={[styles.itemImg, { backgroundColor: tints.lavender.bg }]}>
                                {it.photo_base64 ? (
                                  <Image source={{ uri: it.photo_base64 }} style={styles.itemImgInner} />
                                ) : (
                                  <Icon name="Package" size={14} color={tints.lavender.icon} />
                                )}
                              </View>
                              <View style={{ flex: 1 }}>
                                <Text style={styles.itemName} numberOfLines={1}>{it.name}</Text>
                                <Text style={styles.itemSub}>
                                  {it.category_name} · {formatMoney(it.price, cur)} ÷ {it.split_count}
                                </Text>
                              </View>
                              <Text style={styles.itemAmt}>{formatMoney(it.share_each, cur)}</Text>
                            </View>
                          ))}
                          {(det as BalanceDetails).breakdown.filter((x) => x.direction === 'you_owe_them').length === 0 && (
                            <Text style={styles.emptyLine}>No items – possibly offset by your payments.</Text>
                          )}
                        </View>
                      )}
                    </View>
                  );
                })}
              </>
            )}

            {balances.others.length > 0 && (
              <>
                <Text style={styles.sectionTitle}>Other balances</Text>
                {balances.others.map((b) => (
                  <View key={`${b.from_user_id}-${b.to_user_id}`} style={styles.balanceRow}>
                    <Text style={[styles.balName, { flex: 1 }]}>{b.from_name} → {b.to_name}</Text>
                    <Text style={styles.balAmt}>{formatMoney(b.amount, cur)}</Text>
                  </View>
                ))}
              </>
            )}

            {history.length > 0 && (
              <>
                <Text style={[styles.sectionTitle, { marginTop: spacing.lg }]}>Payment history</Text>
                {history.slice(0, 30).map((s) => (
                  <View key={s.settlement_id} style={styles.histRow}>
                    {s.evidence_photo_base64 ? (
                      <Image source={{ uri: s.evidence_photo_base64 }} style={styles.histImg} />
                    ) : (
                      <View style={[styles.histImg, { backgroundColor: tints.mint.bg, alignItems: 'center', justifyContent: 'center' }]}>
                        <Icon name="Receipt" size={18} color={tints.mint.icon} />
                      </View>
                    )}
                    <View style={{ flex: 1 }}>
                      <Text style={styles.histName}>
                        <Text style={{ fontWeight: '800' }}>{s.from_name}</Text>
                        <Text> paid </Text>
                        <Text style={{ fontWeight: '800' }}>{s.to_name}</Text>
                      </Text>
                      {s.note ? <Text style={styles.histNote}>{s.note}</Text> : null}
                      <Text style={styles.histDate}>{new Date(s.created_at).toLocaleDateString()}</Text>
                    </View>
                    <Text style={styles.histAmt}>{formatMoney(s.amount, cur)}</Text>
                    {s.from_user_id === user?.user_id && (
                      <TouchableOpacity onPress={() => removeSettlement(s.settlement_id)} style={{ padding: 4 }}>
                        <Icon name="X" size={14} color={colors.textMuted} />
                      </TouchableOpacity>
                    )}
                  </View>
                ))}
              </>
            )}
          </>
        )}
      </ScrollView>

      {/* Pay sheet */}
      {paying && (
        <KeyboardAvoidingView
          behavior={Platform.OS === 'ios' ? 'padding' : undefined}
          style={styles.modalOverlay}
        >
          <TouchableOpacity style={{ flex: 1 }} activeOpacity={1} onPress={() => setPaying(null)} />
          <View style={styles.sheet}>
            <View style={styles.sheetHandle} />
            <Text style={styles.sheetTitle}>Mark payment to {paying.to_name}</Text>

            <Text style={styles.label}>Amount</Text>
            <TextInput
              style={styles.input}
              value={amount}
              onChangeText={setAmount}
              keyboardType="decimal-pad"
              placeholder="0.00"
              placeholderTextColor={colors.textMuted}
              testID="splits-pay-amount"
            />

            <Text style={styles.label}>Note (optional)</Text>
            <TextInput
              style={styles.input}
              value={note}
              onChangeText={setNote}
              placeholder="e.g. Venmo, cash, May groceries"
              placeholderTextColor={colors.textMuted}
            />

            <Text style={styles.label}>Evidence (optional)</Text>
            <TouchableOpacity style={styles.evidenceBox} onPress={pickEvidence}>
              {evidence ? (
                <Image source={{ uri: evidence }} style={styles.evidenceImg} />
              ) : (
                <>
                  <Icon name="ImagePlus" color={colors.textMuted} size={20} />
                  <Text style={styles.evidenceTxt}>Add screenshot or receipt</Text>
                </>
              )}
            </TouchableOpacity>

            {err && <Text style={styles.error}>{err}</Text>}

            <View style={styles.actionRow}>
              <TouchableOpacity style={styles.cancelBtn} onPress={() => setPaying(null)}>
                <Text style={styles.cancelTxt}>Cancel</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={[styles.confirmBtn, saving && { opacity: 0.6 }]}
                onPress={confirmPay}
                disabled={saving}
                testID="splits-pay-confirm"
              >
                <Text style={styles.confirmTxt}>{saving ? 'Saving...' : 'Confirm payment'}</Text>
              </TouchableOpacity>
            </View>
          </View>
        </KeyboardAvoidingView>
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
  scroll: { padding: spacing.md, paddingBottom: 100 },
  emptyHero: { alignItems: 'center', paddingVertical: 60, paddingHorizontal: spacing.lg },
  heroIcon: { width: 80, height: 80, borderRadius: 40, alignItems: 'center', justifyContent: 'center', marginBottom: spacing.md },
  emptyTitle: { fontSize: 18, fontWeight: '800', color: colors.textMain, textAlign: 'center' },
  emptySub: { fontSize: 13, color: colors.textMuted, textAlign: 'center', marginTop: 8, lineHeight: 20 },
  summaryRow: { flexDirection: 'row', gap: spacing.sm, marginBottom: spacing.sm },
  summaryCard: { flex: 1, padding: spacing.md, borderRadius: radius.lg, gap: 4 },
  summaryLbl: { fontSize: 11, fontWeight: '800', textTransform: 'uppercase', letterSpacing: 0.5 },
  summaryAmt: { fontSize: 24, fontWeight: '900', color: colors.textMain, marginTop: 4 },
  netCard: {
    padding: spacing.md, borderRadius: radius.md,
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    marginBottom: spacing.lg,
  },
  netLbl: { fontSize: 13, fontWeight: '800' },
  netAmt: { fontSize: 22, fontWeight: '900' },
  sectionTitle: { fontSize: 13, fontWeight: '800', color: colors.textMuted, textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 8, marginTop: 8 },
  balanceRow: {
    flexDirection: 'row', alignItems: 'center', gap: 12,
    backgroundColor: colors.surface, padding: spacing.md, borderRadius: radius.md,
    marginBottom: 8, ...shadows.card,
  },
  avatar: { width: 40, height: 40, borderRadius: 20, alignItems: 'center', justifyContent: 'center' },
  avatarTxt: { color: '#fff', fontWeight: '800', fontSize: 16 },
  balName: { fontSize: 15, fontWeight: '700', color: colors.textMain },
  balSub: { fontSize: 12, color: colors.textMuted, marginTop: 2 },
  balAmt: { fontSize: 16, fontWeight: '800', color: colors.textMain },
  rowMain: { flex: 1, flexDirection: 'row', alignItems: 'center', gap: 12 },
  breakdownBox: {
    backgroundColor: colors.surfaceAlt,
    borderRadius: radius.md,
    padding: 10,
    marginTop: -6, marginBottom: 10,
    gap: 6,
  },
  breakdownRow: {
    flexDirection: 'row', alignItems: 'center', gap: 10,
    backgroundColor: colors.surface,
    padding: 10, borderRadius: radius.sm,
  },
  itemImg: {
    width: 32, height: 32, borderRadius: 8,
    alignItems: 'center', justifyContent: 'center',
    overflow: 'hidden',
  },
  itemImgInner: { width: '100%', height: '100%' },
  itemName: { fontSize: 13, fontWeight: '700', color: colors.textMain },
  itemSub: { fontSize: 11, color: colors.textMuted, marginTop: 2 },
  itemAmt: { fontSize: 14, fontWeight: '800', color: colors.textMain },
  emptyLine: { fontSize: 12, color: colors.textMuted, fontStyle: 'italic', padding: 6, textAlign: 'center' },
  payBtn: {
    backgroundColor: colors.primary,
    paddingHorizontal: 12, paddingVertical: 8, borderRadius: radius.full, marginLeft: 8,
  },
  payTxt: { color: '#fff', fontWeight: '800', fontSize: 12 },
  histRow: {
    flexDirection: 'row', alignItems: 'center', gap: 10,
    backgroundColor: colors.surface, padding: 10, borderRadius: radius.md,
    marginBottom: 6, ...shadows.card,
  },
  histImg: { width: 36, height: 36, borderRadius: 8, overflow: 'hidden' },
  histName: { fontSize: 13, color: colors.textMain },
  histNote: { fontSize: 11, color: colors.textMuted, marginTop: 2 },
  histDate: { fontSize: 11, color: colors.textMuted, marginTop: 2 },
  histAmt: { fontSize: 14, fontWeight: '800', color: colors.textMain },
  modalOverlay: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: 'rgba(0,0,0,0.4)',
    justifyContent: 'flex-end',
  },
  sheet: {
    backgroundColor: colors.surface,
    borderTopLeftRadius: 32, borderTopRightRadius: 32,
    padding: spacing.lg, paddingBottom: 32,
  },
  sheetHandle: {
    width: 40, height: 4, borderRadius: 2,
    backgroundColor: colors.border, alignSelf: 'center', marginBottom: 16,
  },
  sheetTitle: { fontSize: 18, fontWeight: '800', color: colors.textMain, marginBottom: spacing.md },
  label: { fontSize: 11, fontWeight: '800', color: colors.textMuted, textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 6, marginTop: 6 },
  input: {
    backgroundColor: colors.surfaceAlt,
    borderRadius: radius.md, paddingHorizontal: spacing.md, paddingVertical: 12,
    fontSize: 15, color: colors.textMain,
  },
  evidenceBox: {
    backgroundColor: colors.surfaceAlt,
    borderRadius: radius.md,
    height: 100,
    alignItems: 'center', justifyContent: 'center',
    overflow: 'hidden',
    flexDirection: 'row', gap: 8,
  },
  evidenceImg: { width: '100%', height: '100%' },
  evidenceTxt: { color: colors.textMuted, fontSize: 13, fontWeight: '600' },
  error: { color: colors.dangerText, fontSize: 13, marginTop: 8 },
  actionRow: { flexDirection: 'row', gap: 10, marginTop: spacing.md },
  cancelBtn: {
    flex: 1, paddingVertical: 14, borderRadius: radius.full,
    alignItems: 'center', backgroundColor: colors.surfaceAlt,
  },
  cancelTxt: { color: colors.textMain, fontWeight: '700' },
  confirmBtn: {
    flex: 2, paddingVertical: 14, borderRadius: radius.full,
    alignItems: 'center', backgroundColor: colors.primary,
    ...shadows.button,
  },
  confirmTxt: { color: '#fff', fontWeight: '800' },
});
