import React, { useState, useCallback, useMemo } from 'react';
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity, RefreshControl,
  TextInput, KeyboardAvoidingView, Platform, ActivityIndicator, Alert, Modal,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useFocusEffect, useRouter } from 'expo-router';
import { useAuth } from '../src/AuthContext';
import { api } from '../src/api';
import { colors, radius, spacing, shadows, tints } from '../src/theme';
import { Icon, BILL_ICON_OPTIONS } from '../src/Icon';
import { formatMoney, getCurrency } from '../src/currency';
import type { Bill, Category, User } from '../src/types';

const FREQUENCIES: Array<{ key: Bill['frequency']; label: string }> = [
  { key: 'monthly', label: 'Monthly' },
  { key: 'weekly', label: 'Weekly' },
  { key: 'yearly', label: 'Yearly' },
  { key: 'once', label: 'One time' },
];

const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

function humanFreq(b: Bill): string {
  if (b.frequency === 'monthly') return `Monthly · day ${b.due_day}`;
  if (b.frequency === 'weekly') return `Weekly · ${WEEKDAYS[b.due_day] || 'Mon'}`;
  if (b.frequency === 'yearly') return `Yearly · day ${b.due_day}`;
  return 'One time';
}

function daysUntil(iso?: string | null): number | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (isNaN(d.getTime())) return null;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const target = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  return Math.round((target.getTime() - today.getTime()) / 86400000);
}

export default function Bills() {
  const router = useRouter();
  const { activeSpace, user } = useAuth();
  const [bills, setBills] = useState<Bill[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [members, setMembers] = useState<User[]>([]);
  const [refreshing, setRefreshing] = useState(false);
  const [loading, setLoading] = useState(true);

  const [editing, setEditing] = useState<Bill | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [saving, setSaving] = useState(false);

  // form state
  const [fName, setFName] = useState('');
  const [fAmount, setFAmount] = useState('');
  const [fFreq, setFFreq] = useState<Bill['frequency']>('monthly');
  const [fDueDay, setFDueDay] = useState(1);
  const [fIcon, setFIcon] = useState('Receipt');
  const [fCategoryId, setFCategoryId] = useState<string | null>(null);
  const [fShared, setFShared] = useState<string[]>([]);
  const [fNotes, setFNotes] = useState('');

  // pay confirmation
  const [payTarget, setPayTarget] = useState<Bill | null>(null);
  // inline new category
  const [newCatName, setNewCatName] = useState('');
  const [showNewCat, setShowNewCat] = useState(false);
  const [creatingCat, setCreatingCat] = useState(false);

  const load = useCallback(async () => {
    if (!activeSpace) return;
    try {
      const [b, c, m] = await Promise.all([
        api.get<Bill[]>(`/bills?space_id=${activeSpace.space_id}`),
        api.get<Category[]>(`/categories?space_id=${activeSpace.space_id}`),
        api.get<User[]>(`/spaces/${activeSpace.space_id}/members`),
      ]);
      setBills(b);
      setCategories(c);
      setMembers(m);
    } catch (e) { console.warn(e); }
    finally { setLoading(false); }
  }, [activeSpace]);

  useFocusEffect(useCallback(() => { load(); }, [load]));

  const onRefresh = async () => { setRefreshing(true); await load(); setRefreshing(false); };
  const cur = activeSpace?.currency || 'USD';

  const openForm = (b?: Bill) => {
    if (b) {
      setEditing(b);
      setFName(b.name); setFAmount(String(b.amount));
      setFFreq(b.frequency); setFDueDay(b.due_day);
      setFIcon(b.icon || 'Receipt');
      setFCategoryId(b.category_id || null);
      setFShared(b.shared_with || []);
      setFNotes(b.notes || '');
    } else {
      setEditing(null);
      setFName(''); setFAmount(''); setFFreq('monthly'); setFDueDay(1);
      setFIcon('Receipt'); setFCategoryId(null); setFShared([]); setFNotes('');
    }
    setShowForm(true);
  };

  const saveBill = async () => {
    if (!activeSpace) return;
    const amt = parseFloat(fAmount);
    if (!fName.trim() || !(amt > 0)) { Alert.alert('Missing info', 'Please add a name and positive amount'); return; }
    setSaving(true);
    try {
      const payload = {
        name: fName.trim(), amount: amt, frequency: fFreq, due_day: fDueDay,
        icon: fIcon, category_id: fCategoryId, shared_with: fShared, notes: fNotes || null,
      };
      if (editing) {
        await api.patch(`/bills/${editing.bill_id}`, payload);
      } else {
        await api.post('/bills', { space_id: activeSpace.space_id, ...payload });
      }
      setShowForm(false);
      await load();
    } catch (e: any) {
      Alert.alert('Error', e?.message || 'Failed to save');
    } finally { setSaving(false); }
  };

  const deleteBill = async (id: string) => {
    Alert.alert('Delete bill?', 'This will remove the recurring reminder. Past payments stay.', [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Delete', style: 'destructive', onPress: async () => {
          try { await api.delete(`/bills/${id}`); await load(); }
          catch (e: any) { Alert.alert('Error', e?.message || 'Failed'); }
        }
      },
    ]);
  };

  const confirmPay = async () => {
    if (!payTarget) return;
    try {
      await api.post(`/bills/${payTarget.bill_id}/pay`);
      setPayTarget(null);
      await load();
    } catch (e: any) { Alert.alert('Error', e?.message || 'Failed to mark paid'); }
  };

  const createInlineCategory = async () => {
    if (!activeSpace || !newCatName.trim()) return;
    setCreatingCat(true);
    try {
      const c = await api.post<Category>('/categories', {
        space_id: activeSpace.space_id,
        name: newCatName.trim(),
        icon: 'Box',
        tint: 'mint',
        fields: [],
      });
      setCategories((cur) => [...cur, c]);
      setFCategoryId(c.category_id);
      setNewCatName('');
      setShowNewCat(false);
    } catch (e: any) { Alert.alert('Error', e?.message || 'Failed to create category'); }
    finally { setCreatingCat(false); }
  };

  const { due, upcoming, paid } = useMemo(() => {
    const due: Bill[] = []; const upcoming: Bill[] = []; const paid: Bill[] = [];
    bills.forEach((b) => {
      if (b.is_paid_current_period) paid.push(b);
      else {
        const d = daysUntil(b.next_due_date);
        if (d !== null && d <= 3) due.push(b);
        else upcoming.push(b);
      }
    });
    return { due, upcoming, paid };
  }, [bills]);

  const catName = (id: string | null | undefined) => categories.find((c) => c.category_id === id)?.name;

  const renderBillCard = (b: Bill) => {
    const d = daysUntil(b.next_due_date);
    const urgent = !b.is_paid_current_period && d !== null && d <= 3;
    return (
      <View key={b.bill_id} style={[styles.billCard, urgent && styles.billCardUrgent]}>
        <View style={[styles.billIcon, { backgroundColor: urgent ? tints.pink.bg : tints.blue.bg }]}>
          <Icon name={b.icon || 'Receipt'} size={22} color={urgent ? tints.pink.icon : tints.blue.icon} />
        </View>
        <View style={{ flex: 1, minWidth: 0 }}>
          <Text style={styles.billName} numberOfLines={1}>{b.name}</Text>
          <Text style={styles.billMeta}>{humanFreq(b)}{b.category_id ? ` · ${catName(b.category_id) || ''}` : ''}</Text>
          {b.is_paid_current_period ? (
            <View style={[styles.badge, { backgroundColor: tints.sage.bg }]}>
              <Icon name="Check" size={12} color={tints.sage.icon} />
              <Text style={[styles.badgeTxt, { color: tints.sage.icon }]}>Paid this period</Text>
            </View>
          ) : (
            <View style={[styles.badge, { backgroundColor: urgent ? tints.pink.bg : tints.yellow.bg }]}>
              <Icon name="Clock" size={12} color={urgent ? tints.pink.icon : tints.yellow.icon} />
              <Text style={[styles.badgeTxt, { color: urgent ? tints.pink.icon : tints.yellow.icon }]}>
                {d === null ? 'Upcoming' : d === 0 ? 'Due today' : d < 0 ? `${-d}d overdue` : `Due in ${d}d`}
              </Text>
            </View>
          )}
        </View>
        <View style={styles.billRight}>
          <Text style={styles.billAmt}>{formatMoney(b.amount, cur)}</Text>
          {!b.is_paid_current_period && (
            <TouchableOpacity
              style={styles.payBtn}
              onPress={() => setPayTarget(b)}
              testID={`bill-pay-${b.bill_id}`}
            >
              <Text style={styles.payTxt}>Mark paid</Text>
            </TouchableOpacity>
          )}
          <View style={styles.actions}>
            <TouchableOpacity onPress={() => openForm(b)} style={styles.iconAction}><Icon name="Edit3" size={14} color={colors.textMuted} /></TouchableOpacity>
            <TouchableOpacity onPress={() => deleteBill(b.bill_id)} style={styles.iconAction}><Icon name="Trash2" size={14} color={colors.dangerText} /></TouchableOpacity>
          </View>
        </View>
      </View>
    );
  };

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <View style={styles.header}>
        <TouchableOpacity style={styles.iconBtn} onPress={() => router.back()} testID="bills-back">
          <Icon name="ArrowLeft" color={colors.textMain} />
        </TouchableOpacity>
        <Text style={styles.title}>Recurring bills</Text>
        <TouchableOpacity style={styles.iconBtn} onPress={() => openForm()} testID="bills-add">
          <Icon name="Plus" color={colors.textMain} />
        </TouchableOpacity>
      </View>

      <ScrollView
        contentContainerStyle={styles.scroll}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.primary} />}
      >
        {loading ? (
          <ActivityIndicator color={colors.primary} style={{ marginTop: 40 }} />
        ) : bills.length === 0 ? (
          <View style={styles.emptyHero}>
            <View style={[styles.heroIcon, { backgroundColor: tints.blue.bg }]}>
              <Icon name="Receipt" color={tints.blue.icon} size={32} />
            </View>
            <Text style={styles.emptyTitle}>No recurring bills yet</Text>
            <Text style={styles.emptySub}>
              Add rent, wifi, electricity or any subscription. Cozii will remind you and — on confirm — split the cost with your roommates.
            </Text>
            <TouchableOpacity style={styles.ctaBtn} onPress={() => openForm()} testID="bills-cta-add">
              <Icon name="Plus" color="#fff" size={16} />
              <Text style={styles.ctaTxt}>Add your first bill</Text>
            </TouchableOpacity>
          </View>
        ) : (
          <>
            {due.length > 0 && (
              <>
                <Text style={styles.sectionTitle}>Due soon</Text>
                {due.map(renderBillCard)}
              </>
            )}
            {upcoming.length > 0 && (
              <>
                <Text style={[styles.sectionTitle, { marginTop: spacing.md }]}>Upcoming</Text>
                {upcoming.map(renderBillCard)}
              </>
            )}
            {paid.length > 0 && (
              <>
                <Text style={[styles.sectionTitle, { marginTop: spacing.md }]}>Paid this period</Text>
                {paid.map(renderBillCard)}
              </>
            )}
          </>
        )}
      </ScrollView>

      {/* Add / Edit form */}
      <Modal visible={showForm} animationType="slide" transparent onRequestClose={() => setShowForm(false)}>
        <KeyboardAvoidingView
          behavior={Platform.OS === 'ios' ? 'padding' : undefined}
          style={styles.modalOverlay}
        >
          <TouchableOpacity style={{ flex: 1 }} activeOpacity={1} onPress={() => setShowForm(false)} />
          <View style={styles.sheet}>
            <View style={styles.sheetHandle} />
            <ScrollView showsVerticalScrollIndicator={false} keyboardShouldPersistTaps="handled">
              <Text style={styles.sheetTitle}>{editing ? 'Edit bill' : 'New recurring bill'}</Text>

              <Text style={styles.label}>Name</Text>
              <TextInput style={styles.input} value={fName} onChangeText={setFName}
                placeholder="e.g. Rent, Wifi" placeholderTextColor={colors.textMuted} testID="bill-form-name" />

              <Text style={styles.label}>Amount ({getCurrency(cur).symbol} {cur})</Text>
              <TextInput style={styles.input} value={fAmount} onChangeText={setFAmount}
                keyboardType="decimal-pad"
                placeholder={cur === 'IDR' || cur === 'JPY' ? '0' : '0.00'}
                placeholderTextColor={colors.textMuted} testID="bill-form-amount" />

              <Text style={styles.label}>Icon</Text>
              <View style={styles.iconRow}>
                {BILL_ICON_OPTIONS.map((ic) => (
                  <TouchableOpacity
                    key={ic}
                    style={[styles.iconChip, fIcon === ic && styles.iconChipActive]}
                    onPress={() => setFIcon(ic)}
                  >
                    <Icon name={ic} size={18} color={fIcon === ic ? '#fff' : colors.textMain} />
                  </TouchableOpacity>
                ))}
              </View>

              <Text style={styles.label}>Frequency</Text>
              <View style={styles.freqRow}>
                {FREQUENCIES.map((f) => (
                  <TouchableOpacity
                    key={f.key}
                    style={[styles.freqChip, fFreq === f.key && styles.freqChipActive]}
                    onPress={() => setFFreq(f.key)}
                  >
                    <Text style={[styles.freqTxt, fFreq === f.key && styles.freqTxtActive]}>{f.label}</Text>
                  </TouchableOpacity>
                ))}
              </View>

              {fFreq === 'monthly' && (
                <>
                  <Text style={styles.label}>Due day of month</Text>
                  <View style={styles.dayRow}>
                    {[1, 5, 10, 15, 20, 25, 28].map((d) => (
                      <TouchableOpacity
                        key={d}
                        style={[styles.dayChip, fDueDay === d && styles.dayChipActive]}
                        onPress={() => setFDueDay(d)}
                      >
                        <Text style={[styles.dayTxt, fDueDay === d && styles.dayTxtActive]}>{d}</Text>
                      </TouchableOpacity>
                    ))}
                    <TextInput
                      style={styles.dayCustom}
                      keyboardType="number-pad"
                      maxLength={2}
                      value={String(fDueDay)}
                      onChangeText={(t) => {
                        const n = Math.max(1, Math.min(31, parseInt(t || '0', 10) || 0));
                        if (n) setFDueDay(n);
                      }}
                      placeholder="Any"
                      placeholderTextColor={colors.textMuted}
                      testID="bill-form-day-custom"
                    />
                  </View>
                  <Text style={styles.helper}>Tap a chip or type any day from 1 to 31.</Text>
                </>
              )}
              {fFreq === 'weekly' && (
                <>
                  <Text style={styles.label}>Day of week</Text>
                  <View style={styles.dayRow}>
                    {WEEKDAYS.map((w, i) => (
                      <TouchableOpacity
                        key={w}
                        style={[styles.dayChip, fDueDay === i && styles.dayChipActive]}
                        onPress={() => setFDueDay(i)}
                      >
                        <Text style={[styles.dayTxt, fDueDay === i && styles.dayTxtActive]}>{w}</Text>
                      </TouchableOpacity>
                    ))}
                  </View>
                </>
              )}

              <Text style={styles.label}>Log into category (optional)</Text>
              <Text style={styles.helper}>When you confirm payment, Cozii creates an item here so it splits automatically.</Text>
              <View style={styles.chipWrap}>
                <TouchableOpacity
                  style={[styles.chip, !fCategoryId && styles.chipActive]}
                  onPress={() => setFCategoryId(null)}
                >
                  <Text style={[styles.chipTxt, !fCategoryId && styles.chipTxtActive]}>None</Text>
                </TouchableOpacity>
                {categories.map((c) => (
                  <TouchableOpacity
                    key={c.category_id}
                    style={[styles.chip, fCategoryId === c.category_id && styles.chipActive]}
                    onPress={() => setFCategoryId(c.category_id)}
                  >
                    <Text style={[styles.chipTxt, fCategoryId === c.category_id && styles.chipTxtActive]}>{c.name}</Text>
                  </TouchableOpacity>
                ))}
                <TouchableOpacity
                  style={[styles.chip, { backgroundColor: tints.sage.bg, flexDirection: 'row', alignItems: 'center', gap: 4 }]}
                  onPress={() => setShowNewCat((v) => !v)}
                  testID="bill-form-newcat-toggle"
                >
                  <Icon name="Plus" size={12} color={tints.sage.icon} />
                  <Text style={[styles.chipTxt, { color: tints.sage.icon }]}>New</Text>
                </TouchableOpacity>
              </View>
              {showNewCat && (
                <View style={styles.newCatRow}>
                  <TextInput
                    style={[styles.input, { flex: 1 }]}
                    value={newCatName}
                    onChangeText={setNewCatName}
                    placeholder="e.g. Utilities, Gym"
                    placeholderTextColor={colors.textMuted}
                    autoFocus
                    testID="bill-form-newcat-input"
                  />
                  <TouchableOpacity
                    style={[styles.smallAddBtn, (creatingCat || !newCatName.trim()) && { opacity: 0.5 }]}
                    onPress={createInlineCategory}
                    disabled={creatingCat || !newCatName.trim()}
                    testID="bill-form-newcat-save"
                  >
                    <Text style={styles.smallAddTxt}>{creatingCat ? '...' : 'Add'}</Text>
                  </TouchableOpacity>
                </View>
              )}

              {members.length > 1 && (
                <>
                  <Text style={styles.label}>Split with</Text>
                  <Text style={styles.helper}>Pick everyone sharing this bill (including you).</Text>
                  <View style={styles.chipWrap}>
                    {members.map((m) => {
                      const active = fShared.includes(m.user_id);
                      return (
                        <TouchableOpacity
                          key={m.user_id}
                          style={[styles.chip, active && styles.chipActive]}
                          onPress={() => setFShared((cur) => active ? cur.filter((x) => x !== m.user_id) : [...cur, m.user_id])}
                        >
                          <Text style={[styles.chipTxt, active && styles.chipTxtActive]}>
                            {m.name}{m.user_id === user?.user_id ? ' (You)' : ''}
                          </Text>
                        </TouchableOpacity>
                      );
                    })}
                  </View>
                </>
              )}

              <Text style={styles.label}>Notes (optional)</Text>
              <TextInput style={[styles.input, { minHeight: 60 }]} value={fNotes} onChangeText={setFNotes}
                multiline placeholder="e.g. Autopay from joint account" placeholderTextColor={colors.textMuted} />

              <View style={styles.actionRow}>
                <TouchableOpacity style={styles.cancelBtn} onPress={() => setShowForm(false)}>
                  <Text style={styles.cancelTxt}>Cancel</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  style={[styles.confirmBtn, saving && { opacity: 0.6 }]}
                  onPress={saveBill}
                  disabled={saving}
                  testID="bill-form-save"
                >
                  <Text style={styles.confirmTxt}>{saving ? 'Saving...' : editing ? 'Update bill' : 'Add bill'}</Text>
                </TouchableOpacity>
              </View>
            </ScrollView>
          </View>
        </KeyboardAvoidingView>
      </Modal>

      {/* Pay confirmation */}
      <Modal visible={!!payTarget} animationType="fade" transparent onRequestClose={() => setPayTarget(null)}>
        <View style={styles.confirmOverlay}>
          <View style={styles.confirmCard}>
            <View style={styles.confirmHero}>
              <View style={[styles.heroIcon, { backgroundColor: tints.sage.bg, marginBottom: 12 }]}>
                <Icon name="Check" color={tints.sage.icon} size={28} />
              </View>
            </View>
            <Text style={styles.confirmTitle}>Mark {payTarget?.name} as paid?</Text>
            <Text style={styles.confirmSub}>
              This logs <Text style={{ fontWeight: '800', color: colors.textMain }}>{payTarget ? formatMoney(payTarget.amount, cur) : ''}</Text>
              {payTarget?.category_id ? ` into ${catName(payTarget.category_id)}` : ''}
              {(payTarget?.shared_with.length || 0) > 1 ? ` and splits it with ${payTarget?.shared_with.length} people.` : '.'}
            </Text>
            <View style={styles.actionRow}>
              <TouchableOpacity style={styles.cancelBtn} onPress={() => setPayTarget(null)}>
                <Text style={styles.cancelTxt}>Not yet</Text>
              </TouchableOpacity>
              <TouchableOpacity style={styles.confirmBtn} onPress={confirmPay} testID="bill-pay-confirm">
                <Text style={styles.confirmTxt}>Yes, mark paid</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>
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
  ctaBtn: {
    flexDirection: 'row', alignItems: 'center', gap: 8,
    backgroundColor: colors.primary, paddingHorizontal: 20, paddingVertical: 12,
    borderRadius: radius.full, marginTop: 20,
    ...shadows.button,
  },
  ctaTxt: { color: '#fff', fontWeight: '800' },
  sectionTitle: { fontSize: 13, fontWeight: '800', color: colors.textMuted, textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 8 },
  billCard: {
    flexDirection: 'row', alignItems: 'center', gap: 12,
    backgroundColor: colors.surface, padding: spacing.md, borderRadius: radius.md,
    marginBottom: 8, ...shadows.card,
  },
  billCardUrgent: { borderWidth: 1, borderColor: tints.pink.icon },
  billIcon: { width: 44, height: 44, borderRadius: 14, alignItems: 'center', justifyContent: 'center' },
  billName: { fontSize: 15, fontWeight: '700', color: colors.textMain },
  billMeta: { fontSize: 11, color: colors.textMuted, marginTop: 2 },
  badge: {
    flexDirection: 'row', alignItems: 'center', gap: 4, alignSelf: 'flex-start',
    paddingHorizontal: 8, paddingVertical: 3, borderRadius: radius.full, marginTop: 6,
  },
  badgeTxt: { fontSize: 10, fontWeight: '800', textTransform: 'uppercase', letterSpacing: 0.4 },
  billRight: { alignItems: 'flex-end', gap: 6 },
  billAmt: { fontSize: 16, fontWeight: '800', color: colors.textMain },
  payBtn: {
    backgroundColor: colors.primary,
    paddingHorizontal: 12, paddingVertical: 6, borderRadius: radius.full,
  },
  payTxt: { color: '#fff', fontWeight: '800', fontSize: 11 },
  actions: { flexDirection: 'row', gap: 6, marginTop: 2 },
  iconAction: { padding: 4 },

  modalOverlay: {
    flex: 1, backgroundColor: 'rgba(0,0,0,0.4)',
    justifyContent: 'flex-end',
  },
  sheet: {
    backgroundColor: colors.surface,
    borderTopLeftRadius: 32, borderTopRightRadius: 32,
    padding: spacing.lg, paddingBottom: 32, maxHeight: '90%',
  },
  sheetHandle: {
    width: 40, height: 4, borderRadius: 2,
    backgroundColor: colors.border, alignSelf: 'center', marginBottom: 16,
  },
  sheetTitle: { fontSize: 18, fontWeight: '800', color: colors.textMain, marginBottom: spacing.md },
  label: { fontSize: 11, fontWeight: '800', color: colors.textMuted, textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 6, marginTop: 10 },
  helper: { fontSize: 11, color: colors.textMuted, marginBottom: 6 },
  input: {
    backgroundColor: colors.surfaceAlt,
    borderRadius: radius.md, paddingHorizontal: spacing.md, paddingVertical: 12,
    fontSize: 15, color: colors.textMain,
  },
  iconRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 4 },
  iconChip: {
    width: 40, height: 40, borderRadius: 12,
    alignItems: 'center', justifyContent: 'center',
    backgroundColor: colors.surfaceAlt,
  },
  iconChipActive: { backgroundColor: colors.primary },
  freqRow: { flexDirection: 'row', gap: 6, flexWrap: 'wrap' },
  freqChip: {
    paddingHorizontal: 14, paddingVertical: 8, borderRadius: radius.full,
    backgroundColor: colors.surfaceAlt,
  },
  freqChipActive: { backgroundColor: colors.primary },
  freqTxt: { fontSize: 12, color: colors.textMain, fontWeight: '700' },
  freqTxtActive: { color: '#fff' },
  dayRow: { flexDirection: 'row', gap: 6, flexWrap: 'wrap' },
  dayChip: {
    minWidth: 44, paddingHorizontal: 10, paddingVertical: 8, borderRadius: radius.full,
    alignItems: 'center', backgroundColor: colors.surfaceAlt,
  },
  dayChipActive: { backgroundColor: colors.primary },
  dayTxt: { fontSize: 12, color: colors.textMain, fontWeight: '700' },
  dayTxtActive: { color: '#fff' },
  dayCustom: {
    minWidth: 60, paddingHorizontal: 10, paddingVertical: 6,
    borderRadius: radius.full,
    backgroundColor: colors.surfaceAlt,
    borderWidth: 1, borderColor: colors.border,
    fontSize: 12, fontWeight: '700', color: colors.textMain,
    textAlign: 'center',
  },
  newCatRow: { flexDirection: 'row', gap: 8, marginTop: 8, alignItems: 'center' },
  smallAddBtn: {
    paddingHorizontal: 16, paddingVertical: 12,
    borderRadius: radius.full, backgroundColor: colors.primary,
    ...shadows.button,
  },
  smallAddTxt: { color: '#fff', fontWeight: '800', fontSize: 13 },
  chipWrap: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginTop: 4 },
  chip: {
    paddingHorizontal: 12, paddingVertical: 7, borderRadius: radius.full,
    backgroundColor: colors.surfaceAlt,
  },
  chipActive: { backgroundColor: colors.primary },
  chipTxt: { fontSize: 12, color: colors.textMain, fontWeight: '600' },
  chipTxtActive: { color: '#fff', fontWeight: '700' },

  actionRow: { flexDirection: 'row', gap: 10, marginTop: spacing.lg },
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

  confirmOverlay: {
    flex: 1, backgroundColor: 'rgba(0,0,0,0.5)',
    alignItems: 'center', justifyContent: 'center', padding: 24,
  },
  confirmCard: {
    backgroundColor: colors.surface,
    borderRadius: radius.lg, padding: spacing.lg,
    width: '100%', maxWidth: 360,
    ...shadows.card,
  },
  confirmHero: { alignItems: 'center', marginBottom: 4 },
  confirmTitle: { fontSize: 18, fontWeight: '800', color: colors.textMain, textAlign: 'center' },
  confirmSub: { fontSize: 13, color: colors.textMuted, textAlign: 'center', marginTop: 8, lineHeight: 20 },
});
