import React, { useState } from 'react';
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity, TextInput,
  KeyboardAvoidingView, Platform,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { useAuth } from '../../src/AuthContext';
import { colors, radius, spacing, shadows, tints, tintKeys } from '../../src/theme';
import { Icon, CATEGORY_ICON_OPTIONS } from '../../src/Icon';
import { api } from '../../src/api';

type FieldDraft = { key: string; label: string; type: 'text' | 'number' | 'date' | 'price' };

export default function NewCategory() {
  const router = useRouter();
  const { activeSpace } = useAuth();
  const [name, setName] = useState('');
  const [icon, setIcon] = useState('Box');
  const [tint, setTint] = useState('mint');
  const [fields, setFields] = useState<FieldDraft[]>([
    { key: 'expiry_date', label: 'Expiry date', type: 'date' },
    { key: 'quantity', label: 'Quantity', type: 'number' },
  ]);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const addField = () => setFields((p) => [...p, { key: `field_${p.length + 1}`, label: '', type: 'text' }]);
  const updateField = (i: number, key: keyof FieldDraft, value: string) => {
    setFields((p) => p.map((f, idx) => idx === i ? { ...f, [key]: value, key: key === 'label' ? value.toLowerCase().replace(/[^a-z0-9]+/g, '_') || f.key : f.key } : f));
  };
  const removeField = (i: number) => setFields((p) => p.filter((_, idx) => idx !== i));

  const submit = async () => {
    if (!activeSpace) return;
    if (!name.trim()) { setErr('Please name this category'); return; }
    setErr(null);
    setLoading(true);
    try {
      await api.post('/categories', {
        space_id: activeSpace.space_id,
        name: name.trim(),
        icon,
        tint,
        fields: fields.filter((f) => f.label.trim()),
      });
      router.back();
    } catch (e: any) {
      setErr(e?.message || 'Failed to create');
    } finally { setLoading(false); }
  };

  return (
    <SafeAreaView style={styles.container} edges={['top', 'bottom']}>
      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={{ flex: 1 }}>
        <View style={styles.header}>
          <TouchableOpacity style={styles.iconBtn} onPress={() => router.back()} testID="new-category-back">
            <Icon name="X" color={colors.textMain} />
          </TouchableOpacity>
          <Text style={styles.title}>New category</Text>
          <View style={{ width: 40 }} />
        </View>

        <ScrollView contentContainerStyle={styles.scroll} keyboardShouldPersistTaps="handled">
          <View style={styles.field}>
            <Text style={styles.label}>Name</Text>
            <TextInput
              style={styles.input}
              placeholder="Ex. Pantry, Medications, Makeup"
              placeholderTextColor="#95A5A6"
              value={name}
              onChangeText={setName}
              testID="new-category-name"
            />
          </View>

          <View style={styles.field}>
            <Text style={styles.label}>Color</Text>
            <View style={styles.colorRow}>
              {tintKeys.map((t) => {
                const cfg = tints[t];
                const active = tint === t;
                return (
                  <TouchableOpacity
                    key={t}
                    style={[styles.colorDot, { backgroundColor: cfg.bg, borderColor: active ? cfg.icon : 'transparent' }]}
                    onPress={() => setTint(t)}
                    testID={`new-category-tint-${t}`}
                  >
                    <View style={[styles.colorDotInner, { backgroundColor: cfg.icon }]} />
                  </TouchableOpacity>
                );
              })}
            </View>
          </View>

          <View style={styles.field}>
            <Text style={styles.label}>Icon</Text>
            <View style={styles.iconRow}>
              {CATEGORY_ICON_OPTIONS.map((i) => (
                <TouchableOpacity
                  key={i}
                  style={[styles.iconPick, icon === i && { backgroundColor: tints[tint].bg, borderColor: tints[tint].icon, borderWidth: 2 }]}
                  onPress={() => setIcon(i)}
                  testID={`new-category-icon-${i}`}
                >
                  <Icon name={i} size={22} color={icon === i ? tints[tint].icon : colors.textMuted} />
                </TouchableOpacity>
              ))}
            </View>
          </View>

          <View style={styles.field}>
            <Text style={styles.label}>Custom fields</Text>
            <Text style={styles.hint}>Define what extra info each item in this category should have (e.g. expiry, brand, size).</Text>
            {fields.map((f, i) => (
              <View key={i} style={styles.fieldRow}>
                <TextInput
                  style={[styles.input, { flex: 1 }]}
                  placeholder="Field name"
                  placeholderTextColor="#95A5A6"
                  value={f.label}
                  onChangeText={(v) => updateField(i, 'label', v)}
                />
                <View style={styles.typePicker}>
                  {(['text', 'number', 'date', 'price'] as const).map((t) => (
                    <TouchableOpacity
                      key={t}
                      style={[styles.typeChip, f.type === t && { backgroundColor: colors.textMain }]}
                      onPress={() => updateField(i, 'type', t)}
                    >
                      <Text style={[styles.typeChipTxt, f.type === t && { color: '#fff' }]}>{t}</Text>
                    </TouchableOpacity>
                  ))}
                </View>
                <TouchableOpacity onPress={() => removeField(i)} style={{ paddingHorizontal: 4 }}>
                  <Icon name="X" size={16} color={colors.textMuted} />
                </TouchableOpacity>
              </View>
            ))}
            <TouchableOpacity style={styles.addFieldBtn} onPress={addField} testID="new-category-add-field">
              <Icon name="Plus" size={16} color={colors.primary} />
              <Text style={styles.addFieldTxt}>Add field</Text>
            </TouchableOpacity>
          </View>

          {err && <Text style={styles.error}>{err}</Text>}

          <TouchableOpacity
            style={[styles.primary, loading && { opacity: 0.6 }]}
            onPress={submit}
            disabled={loading}
            testID="new-category-save"
          >
            <Text style={styles.primaryTxt}>{loading ? 'Saving...' : 'Create category'}</Text>
          </TouchableOpacity>
        </ScrollView>
      </KeyboardAvoidingView>
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
  scroll: { padding: spacing.md, paddingBottom: 80 },
  field: { marginBottom: spacing.lg },
  label: { fontSize: 12, fontWeight: '800', color: colors.textMuted, textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 8 },
  hint: { fontSize: 12, color: colors.textMuted, marginBottom: 10 },
  input: {
    backgroundColor: colors.surfaceAlt, borderRadius: radius.md,
    paddingHorizontal: spacing.md, paddingVertical: 12,
    fontSize: 15, color: colors.textMain,
  },
  colorRow: { flexDirection: 'row', gap: 10, flexWrap: 'wrap' },
  colorDot: {
    width: 44, height: 44, borderRadius: 22, borderWidth: 3,
    alignItems: 'center', justifyContent: 'center',
  },
  colorDotInner: { width: 16, height: 16, borderRadius: 8 },
  iconRow: { flexDirection: 'row', gap: 10, flexWrap: 'wrap' },
  iconPick: {
    width: 48, height: 48, borderRadius: radius.md,
    backgroundColor: colors.surface,
    alignItems: 'center', justifyContent: 'center',
    borderWidth: 2, borderColor: 'transparent',
    ...shadows.card,
  },
  fieldRow: {
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    padding: 10,
    marginBottom: 10,
    gap: 8,
    ...shadows.card,
  },
  typePicker: { flexDirection: 'row', gap: 6, flexWrap: 'wrap' },
  typeChip: {
    paddingHorizontal: 10, paddingVertical: 5,
    borderRadius: radius.full,
    backgroundColor: colors.surfaceAlt,
  },
  typeChipTxt: { fontSize: 11, fontWeight: '700', color: colors.textMuted, textTransform: 'capitalize' },
  addFieldBtn: {
    flexDirection: 'row', alignItems: 'center', gap: 6,
    alignSelf: 'flex-start',
    backgroundColor: tints.pink.bg,
    paddingHorizontal: 14, paddingVertical: 8,
    borderRadius: radius.full,
  },
  addFieldTxt: { color: colors.primary, fontWeight: '700', fontSize: 13 },
  error: { color: colors.dangerText, marginBottom: 10 },
  primary: {
    backgroundColor: colors.primary,
    paddingVertical: 16,
    borderRadius: radius.full,
    alignItems: 'center',
    marginTop: 10,
    ...shadows.button,
  },
  primaryTxt: { color: '#fff', fontWeight: '800' },
});
