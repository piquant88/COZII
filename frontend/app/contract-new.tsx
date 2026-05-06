import React, { useState, useEffect, useCallback } from 'react';
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity, TextInput,
  ActivityIndicator, Alert, KeyboardAvoidingView, Platform, Switch,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { useAuth } from '../src/AuthContext';
import { api } from '../src/api';
import { colors, radius, spacing, shadows, tints } from '../src/theme';
import { Icon } from '../src/Icon';

type TemplateDef = {
  kind: string;
  title: string;
  icon: string;
  summary: string;
  default_variables: Record<string, any>;
  body: string;
};

// Friendly labels for placeholder variables — fall back to the raw key.
const VAR_LABELS: Record<string, string> = {
  household_name: 'Household name',
  staff_name: 'Staff name',
  start_date: 'Start date',
  city: 'City',
  role: 'Role / position',
  monthly_wage: 'Monthly wage',
  currency: 'Currency',
  pay_cycle: 'Pay cycle',
  off_day: 'Weekly off day',
  working_hours: 'Working hours',
  probation_months: 'Probation (months)',
};

export default function ContractNewScreen() {
  const router = useRouter();
  const { activeSpace, user } = useAuth();
  const [templates, setTemplates] = useState<TemplateDef[]>([]);
  const [picked, setPicked] = useState<TemplateDef | null>(null);
  const [staffList, setStaffList] = useState<any[]>([]);
  const [staffId, setStaffId] = useState<string | null>(null);
  const [title, setTitle] = useState('');
  const [body, setBody] = useState('');
  const [vars, setVars] = useState<Record<string, string>>({});
  const [requireOwner, setRequireOwner] = useState(true);
  const [requireStaff, setRequireStaff] = useState(true);
  const [drawnOwner, setDrawnOwner] = useState(false);
  const [drawnStaff, setDrawnStaff] = useState(false);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    if (!activeSpace) return;
    try {
      const [tpls, staff] = await Promise.all([
        api.get<TemplateDef[]>('/contract-templates'),
        api.get<any[]>(`/household/staff?space_id=${activeSpace.space_id}`),
      ]);
      setTemplates(tpls || []);
      setStaffList(staff || []);
      // Auto-pick first active staff by default so the contract is assigned right away.
      if (!staffId && (staff || []).length > 0) {
        const firstActive = (staff || []).find((s: any) => s.active !== false) || staff![0];
        if (firstActive) setStaffId(firstActive.staff_id);
      }
    } catch (e) { console.warn(e); }
  }, [activeSpace, staffId]);
  useEffect(() => { load(); }, [load]);

  // Pre-fill default variables from the active context (household name, currency, today's date)
  const pickTemplate = (t: TemplateDef) => {
    setPicked(t);
    setTitle(t.title);
    setBody(t.body);
    const dv: Record<string, string> = {};
    Object.keys(t.default_variables || {}).forEach((k) => {
      dv[k] = '';
    });
    // Smart defaults
    if (dv.household_name !== undefined) dv.household_name = activeSpace?.name || '';
    if (dv.currency !== undefined) dv.currency = activeSpace?.currency || 'USD';
    if (dv.start_date !== undefined) dv.start_date = new Date().toISOString().slice(0, 10);
    setVars(dv);
  };

  // When staff_id changes, autofill staff_name + role + wage
  useEffect(() => {
    if (!staffId) return;
    const s = staffList.find((x) => x.staff_id === staffId);
    if (!s) return;
    setVars((v) => ({
      ...v,
      ...(v.staff_name !== undefined ? { staff_name: s.name || v.staff_name } : {}),
      ...(v.role !== undefined ? { role: s.role_name || v.role } : {}),
      ...(v.monthly_wage !== undefined && s.salary ? { monthly_wage: String(s.salary) } : {}),
      ...(v.currency !== undefined && s.salary_currency ? { currency: s.salary_currency } : {}),
      ...(v.off_day !== undefined && s.off_day ? { off_day: s.off_day } : {}),
    }));
  }, [staffId, staffList]);

  // Live-rendered preview
  const renderedBody = (() => {
    let out = body || '';
    Object.entries(vars).forEach(([k, v]) => {
      out = out.split(`{{${k}}}`).join(v || `{{${k}}}`);
    });
    return out;
  })();

  const submit = async () => {
    if (!picked) { Alert.alert('Pick a template'); return; }
    if (!title.trim()) { Alert.alert('Title required'); return; }
    if (!body.trim()) { Alert.alert('Body cannot be empty'); return; }
    if (!staffId) { Alert.alert('Pick a staff member', 'An agreement needs to be assigned to a specific staff member so they can see and sign it.'); return; }
    setSaving(true);
    try {
      const created = await api.post('/contracts', {
        space_id: activeSpace?.space_id,
        template_kind: picked.kind,
        title: title.trim(),
        body,
        variables: vars,
        assigned_staff_id: staffId,
        require_owner_signature: requireOwner,
        require_staff_signature: requireStaff,
        require_drawn_signature_owner: drawnOwner,
        require_drawn_signature_staff: drawnStaff,
      });
      router.replace({ pathname: '/contract-view', params: { id: created.contract_id } });
    } catch (e: any) {
      Alert.alert('Could not create', e?.message || 'Try again.');
    } finally { setSaving(false); }
  };

  if (!picked) {
    return (
      <SafeAreaView style={styles.container} edges={['top', 'bottom']}>
        <View style={styles.header}>
          <TouchableOpacity onPress={() => router.back()} style={styles.backBtn}>
            <Icon name="ChevronRight" size={18} color={colors.textMain} />
          </TouchableOpacity>
          <View style={{ flex: 1 }}>
            <Text style={styles.kicker}>{activeSpace?.name}</Text>
            <Text style={styles.title}>Pick a template</Text>
          </View>
        </View>
        <ScrollView contentContainerStyle={styles.scroll}>
          {templates.length === 0 ? <ActivityIndicator color={colors.primary} style={{ marginTop: 30 }} /> : (
            templates.map((t) => (
              <TouchableOpacity key={t.kind} style={styles.tplCard} onPress={() => pickTemplate(t)} testID={`tpl-${t.kind}`}>
                <View style={[styles.tplIcon, { backgroundColor: tints.sage.bg }]}>
                  <Icon name={t.icon} size={20} color={tints.sage.icon} />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={styles.tplTitle}>{t.title}</Text>
                  <Text style={styles.tplSummary}>{t.summary}</Text>
                </View>
                <Icon name="ChevronRight" size={16} color={colors.textMuted} />
              </TouchableOpacity>
            ))
          )}
          <View style={{ height: 60 }} />
        </ScrollView>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.container} edges={['top', 'bottom']}>
      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={{ flex: 1 }}>
        <View style={styles.header}>
          <TouchableOpacity onPress={() => setPicked(null)} style={styles.backBtn}>
            <Icon name="ChevronRight" size={18} color={colors.textMain} />
          </TouchableOpacity>
          <View style={{ flex: 1 }}>
            <Text style={styles.kicker}>{picked.title}</Text>
            <Text style={styles.title}>Customize</Text>
          </View>
        </View>
        <ScrollView contentContainerStyle={styles.scroll} keyboardShouldPersistTaps="handled">
          {/* Title */}
          <Text style={styles.label}>Title</Text>
          <TextInput style={styles.input} value={title} onChangeText={setTitle} placeholder="Contract title" placeholderTextColor={colors.textMuted} />

          {/* Assign staff */}
          <Text style={styles.label}>Assign to staff</Text>
          {staffList.length === 0 ? (
            <View style={[styles.input, { padding: spacing.md }]}>
              <Text style={{ color: colors.textMuted, fontSize: 12, lineHeight: 18 }}>
                You need at least one staff member to create an agreement. Add a staff member from the Household tab first, then come back here.
              </Text>
            </View>
          ) : (
            <View style={styles.chipRow}>
              {staffList.filter((s) => s.active !== false).map((s) => (
                <TouchableOpacity key={s.staff_id} style={[styles.chip, staffId === s.staff_id && styles.chipActive]} onPress={() => setStaffId(s.staff_id)} testID={`assign-${s.staff_id}`}>
                  <Text style={[styles.chipTxt, staffId === s.staff_id && { color: '#fff' }]}>
                    {s.name}{!s.user_id ? '  (not joined)' : ''}
                  </Text>
                </TouchableOpacity>
              ))}
            </View>
          )}

          {/* Variables */}
          {Object.keys(vars).length > 0 && (
            <>
              <Text style={[styles.label, { marginTop: spacing.md }]}>Fill in details</Text>
              {Object.keys(vars).map((k) => (
                <View key={k} style={{ marginBottom: 8 }}>
                  <Text style={styles.varLabel}>{VAR_LABELS[k] || k}</Text>
                  <TextInput
                    style={styles.input}
                    value={vars[k]}
                    onChangeText={(t) => setVars((v) => ({ ...v, [k]: t }))}
                    placeholder={`Enter ${VAR_LABELS[k] || k}`}
                    placeholderTextColor={colors.textMuted}
                  />
                </View>
              ))}
            </>
          )}

          {/* Body editor */}
          <Text style={[styles.label, { marginTop: spacing.md }]}>Body (you can edit)</Text>
          <TextInput
            style={[styles.input, { minHeight: 220, textAlignVertical: 'top' }]}
            value={body}
            onChangeText={setBody}
            multiline
            placeholder="Write the agreement…"
            placeholderTextColor={colors.textMuted}
          />

          {/* Live preview */}
          <Text style={[styles.label, { marginTop: spacing.md }]}>Live preview</Text>
          <View style={styles.preview}>
            <Text style={styles.previewTxt}>{renderedBody}</Text>
          </View>

          {/* Signature settings */}
          <Text style={[styles.label, { marginTop: spacing.md }]}>Signature settings</Text>
          <View style={styles.sigCard}>
            <View style={styles.sigRow}>
              <View style={{ flex: 1 }}>
                <Text style={styles.sigName}>Owner signs (you)</Text>
                <Text style={styles.sigHint}>Recommended. Both parties signing makes the agreement bilaterally binding.</Text>
              </View>
              <Switch value={requireOwner} onValueChange={setRequireOwner} />
            </View>
            {requireOwner && (
              <View style={styles.sigRow}>
                <View style={{ flex: 1 }}>
                  <Text style={styles.sigSub}>Force hand-drawn signature for owner</Text>
                  <Text style={styles.sigHint}>If off, you can sign with your typed name.</Text>
                </View>
                <Switch value={drawnOwner} onValueChange={setDrawnOwner} />
              </View>
            )}
            <View style={[styles.sigRow, { borderTopWidth: 1, borderTopColor: colors.border, paddingTop: 10, marginTop: 6 }]}>
              <View style={{ flex: 1 }}>
                <Text style={styles.sigName}>Staff signs</Text>
                <Text style={styles.sigHint}>The staff member you assigned above.</Text>
              </View>
              <Switch value={requireStaff} onValueChange={setRequireStaff} />
            </View>
            {requireStaff && (
              <View style={styles.sigRow}>
                <View style={{ flex: 1 }}>
                  <Text style={styles.sigSub}>Force hand-drawn signature for this staff</Text>
                  <Text style={styles.sigHint}>Recommended for legal-style agreements (NDA, employment).</Text>
                </View>
                <Switch value={drawnStaff} onValueChange={setDrawnStaff} />
              </View>
            )}
          </View>

          {/* Submit */}
          <TouchableOpacity
            style={[styles.saveBtn, (saving || !title.trim()) && { opacity: 0.5 }]}
            onPress={submit}
            disabled={saving || !title.trim()}
            testID="contract-create"
          >
            {saving ? <ActivityIndicator color="#fff" /> : (
              <>
                <Icon name="Send" size={16} color="#fff" />
                <Text style={styles.saveTxt}>Create & open for signing</Text>
              </>
            )}
          </TouchableOpacity>
          <View style={{ height: 60 }} />
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background },
  header: { flexDirection: 'row', alignItems: 'center', gap: 12, padding: spacing.md },
  backBtn: { width: 40, height: 40, borderRadius: 20, backgroundColor: colors.surface, alignItems: 'center', justifyContent: 'center', transform: [{ rotate: '180deg' }], ...shadows.card },
  kicker: { fontSize: 11, color: colors.textMuted, fontWeight: '700', textTransform: 'uppercase' },
  title: { fontSize: 24, fontWeight: '900', color: colors.textMain, letterSpacing: -0.5 },
  scroll: { padding: spacing.md, paddingTop: 0 },
  tplCard: {
    flexDirection: 'row', alignItems: 'center', gap: 12,
    backgroundColor: colors.surface, padding: spacing.md, borderRadius: radius.md,
    marginBottom: 8, ...shadows.card,
  },
  tplIcon: { width: 44, height: 44, borderRadius: 14, alignItems: 'center', justifyContent: 'center' },
  tplTitle: { fontSize: 15, fontWeight: '800', color: colors.textMain },
  tplSummary: { fontSize: 12, color: colors.textMuted, marginTop: 2, lineHeight: 17 },
  label: { fontSize: 12, fontWeight: '800', color: colors.textMuted, textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 6 },
  varLabel: { fontSize: 11, fontWeight: '700', color: colors.textMain, marginBottom: 4 },
  input: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, padding: 12, fontSize: 14, color: colors.textMain, marginBottom: 4 },
  chipRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginBottom: 8 },
  chip: { paddingHorizontal: 12, paddingVertical: 6, borderRadius: radius.full, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border },
  chipActive: { backgroundColor: colors.textMain, borderColor: colors.textMain },
  chipTxt: { fontSize: 12, fontWeight: '700', color: colors.textMain },
  preview: {
    backgroundColor: '#FFFEFB',
    borderWidth: 1, borderColor: colors.border,
    borderRadius: radius.md, padding: spacing.md,
    minHeight: 120,
  },
  previewTxt: { fontSize: 13, color: colors.textMain, lineHeight: 20 },
  sigCard: { backgroundColor: colors.surface, padding: spacing.md, borderRadius: radius.md, gap: 6, ...shadows.card },
  sigRow: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  sigName: { fontSize: 14, fontWeight: '800', color: colors.textMain },
  sigSub: { fontSize: 13, fontWeight: '700', color: colors.textMain },
  sigHint: { fontSize: 11, color: colors.textMuted, marginTop: 2, lineHeight: 15 },
  saveBtn: {
    flexDirection: 'row', gap: 8,
    backgroundColor: colors.primary, padding: 14, borderRadius: radius.full,
    alignItems: 'center', justifyContent: 'center',
    marginTop: spacing.md, ...shadows.button,
  },
  saveTxt: { color: '#fff', fontWeight: '800', fontSize: 14 },
});
