import React, { useState, useEffect } from 'react';
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity, TextInput,
  KeyboardAvoidingView, Platform,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { useAuth } from '../../src/AuthContext';
import { colors, radius, spacing, shadows, tints, tintKeys } from '../../src/theme';
import { Icon, CATEGORY_ICON_OPTIONS } from '../../src/Icon';
import { api } from '../../src/api';
import type { Category } from '../../src/types';

type FieldType = 'text' | 'number' | 'date' | 'price' | 'select';
type FieldDraft = { key: string; label: string; type: FieldType; options: string[]; optionInput: string };

export default function CategoryEditor() {
  const router = useRouter();
  const { activeSpace } = useAuth();
  const { edit: editId } = useLocalSearchParams<{ edit?: string }>();
  const isEdit = !!editId;

  const [name, setName] = useState('');
  const [icon, setIcon] = useState('Box');
  const [tint, setTint] = useState('mint');
  const [fields, setFields] = useState<FieldDraft[]>([
    { key: 'expiry_date', label: 'Expiry date', type: 'date', options: [], optionInput: '' },
    { key: 'quantity', label: 'Quantity', type: 'number', options: [], optionInput: '' },
  ]);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [bootLoading, setBootLoading] = useState(isEdit);

  useEffect(() => {
    if (!isEdit || !activeSpace) return;
    (async () => {
      try {
        const cats = await api.get<Category[]>(`/categories?space_id=${activeSpace.space_id}`);
        const cat = cats.find((c) => c.category_id === editId);
        if (!cat) { router.back(); return; }
        setName(cat.name);
        setIcon(cat.icon);
        setTint(cat.tint);
        setFields(cat.fields.map((f) => ({
          key: f.key,
          label: f.label,
          type: (f.type as FieldType),
          options: f.options || [],
          optionInput: '',
        })));
      } catch (e) { console.warn(e); }
      finally { setBootLoading(false); }
    })();
  }, [isEdit, editId, activeSpace]);

  const addField = () => setFields((p) => [...p, { key: `field_${p.length + 1}`, label: '', type: 'text', options: [], optionInput: '' }]);
  const updateField = (i: number, key: keyof FieldDraft, value: any) => {
    setFields((p) => p.map((f, idx) => {
      if (idx !== i) return f;
      const next: FieldDraft = { ...f, [key]: value } as FieldDraft;
      if (key === 'label') {
        next.key = (value as string).toLowerCase().replace(/[^a-z0-9]+/g, '_') || f.key;
      }
      return next;
    }));
  };
  const removeField = (i: number) => setFields((p) => p.filter((_, idx) => idx !== i));
  const addOption = (i: number) => {
    setFields((p) => p.map((f, idx) => {
      if (idx !== i) return f;
      const v = f.optionInput.trim();
      if (!v) return f;
      if (f.options.includes(v)) return { ...f, optionInput: '' };
      return { ...f, options: [...f.options, v], optionInput: '' };
    }));
  };
  const removeOption = (i: number, o: string) => {
    setFields((p) => p.map((f, idx) => idx === i ? { ...f, options: f.options.filter((x) => x !== o) } : f));
  };

  const submit = async () => {
    if (!activeSpace) return;
    if (!name.trim()) { setErr('Please name this category'); return; }
    setErr(null);
    setLoading(true);
    const fieldsPayload = fields
      .filter((f) => f.label.trim())
      .map((f) => ({
        key: f.key,
        label: f.label,
        type: f.type,
        options: f.type === 'select' ? f.options : [],
      }));
    try {
      if (isEdit) {
        await api.patch(`/categories/${editId}`, {
          name: name.trim(), icon, tint, fields: fieldsPayload,
        });
      } else {
        await api.post('/categories', {
          space_id: activeSpace.space_id,
          name: name.trim(), icon, tint, fields: fieldsPayload,
        });
      }
      router.back();
    } catch (e: any) {
      setErr(e?.message || 'Failed to save');
    } finally { setLoading(false); }
  };

  if (bootLoading) {
    return (
      <SafeAreaView style={styles.container}>
        <Text style={{ padding: 20, color: colors.textMuted }}>Loading...</Text>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.container} edges={['top', 'bottom']}>
      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={{ flex: 1 }}>
        <View style={styles.header}>
          <TouchableOpacity style={styles.iconBtn} onPress={() => router.back()} testID="cat-edit-back">
            <Icon name="X" color={colors.textMain} />
          </TouchableOpacity>
          <Text style={styles.title}>{isEdit ? 'Edit category' : 'New category'}</Text>
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
              testID="cat-edit-name"
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
                    testID={`cat-edit-tint-${t}`}
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
                  testID={`cat-edit-icon-${i}`}
                >
                  <Icon name={i} size={22} color={icon === i ? tints[tint].icon : colors.textMuted} />
                </TouchableOpacity>
              ))}
            </View>
          </View>

          <View style={styles.field}>
            <Text style={styles.label}>Custom fields</Text>
            <Text style={styles.hint}>
              Define extra info each item should have. Use "Choices" for fixed lists like Type → Dairy, Meat, Veggies.
            </Text>
            {fields.map((f, i) => (
              <View key={i} style={styles.fieldRow}>
                <View style={styles.fieldHeader}>
                  <TextInput
                    style={[styles.input, { flex: 1, paddingVertical: 10 }]}
                    placeholder="Field name (e.g. Type)"
                    placeholderTextColor="#95A5A6"
                    value={f.label}
                    onChangeText={(v) => updateField(i, 'label', v)}
                  />
                  <TouchableOpacity onPress={() => removeField(i)} style={{ paddingHorizontal: 8 }}>
                    <Icon name="X" size={16} color={colors.textMuted} />
                  </TouchableOpacity>
                </View>
                <View style={styles.typePicker}>
                  {([
                    { v: 'text', l: 'Text' },
                    { v: 'number', l: 'Number' },
                    { v: 'date', l: 'Date' },
                    { v: 'price', l: 'Price' },
                    { v: 'select', l: 'Choices' },
                  ] as const).map((opt) => (
                    <TouchableOpacity
                      key={opt.v}
                      style={[styles.typeChip, f.type === opt.v && { backgroundColor: colors.textMain }]}
                      onPress={() => updateField(i, 'type', opt.v)}
                    >
                      <Text style={[styles.typeChipTxt, f.type === opt.v && { color: '#fff' }]}>{opt.l}</Text>
                    </TouchableOpacity>
                  ))}
                </View>
                {f.type === 'select' && (
                  <View style={styles.optionsBox}>
                    <View style={styles.optionsList}>
                      {f.options.map((o) => (
                        <View key={o} style={styles.optChip}>
                          <Text style={styles.optChipTxt}>{o}</Text>
                          <TouchableOpacity onPress={() => removeOption(i, o)} style={{ marginLeft: 6 }}>
                            <Icon name="X" size={12} color={colors.textMuted} />
                          </TouchableOpacity>
                        </View>
                      ))}
                      {f.options.length === 0 && (
                        <Text style={{ color: colors.textMuted, fontSize: 12 }}>No choices yet</Text>
                      )}
                    </View>
                    <View style={styles.optionAddRow}>
                      <TextInput
                        style={[styles.input, { flex: 1, paddingVertical: 10 }]}
                        placeholder="e.g. Dairy"
                        placeholderTextColor="#95A5A6"
                        value={f.optionInput}
                        onChangeText={(v) => updateField(i, 'optionInput', v)}
                        onSubmitEditing={() => addOption(i)}
                        returnKeyType="done"
                      />
                      <TouchableOpacity style={styles.optAddBtn} onPress={() => addOption(i)}>
                        <Icon name="Plus" color={colors.primary} size={16} />
                        <Text style={styles.optAddTxt}>Add</Text>
                      </TouchableOpacity>
                    </View>
                  </View>
                )}
              </View>
            ))}
            <TouchableOpacity style={styles.addFieldBtn} onPress={addField} testID="cat-edit-add-field">
              <Icon name="Plus" size={16} color={colors.primary} />
              <Text style={styles.addFieldTxt}>Add field</Text>
            </TouchableOpacity>
          </View>

          {err && <Text style={styles.error}>{err}</Text>}

          <TouchableOpacity
            style={[styles.primary, loading && { opacity: 0.6 }]}
            onPress={submit}
            disabled={loading}
            testID="cat-edit-save"
          >
            <Text style={styles.primaryTxt}>{loading ? 'Saving...' : isEdit ? 'Save changes' : 'Create category'}</Text>
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
  fieldHeader: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  typePicker: { flexDirection: 'row', gap: 6, flexWrap: 'wrap' },
  typeChip: {
    paddingHorizontal: 10, paddingVertical: 5,
    borderRadius: radius.full,
    backgroundColor: colors.surfaceAlt,
  },
  typeChipTxt: { fontSize: 11, fontWeight: '700', color: colors.textMuted },
  optionsBox: {
    backgroundColor: colors.surfaceAlt,
    borderRadius: radius.md,
    padding: 10,
    gap: 10,
  },
  optionsList: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  optChip: {
    flexDirection: 'row', alignItems: 'center',
    backgroundColor: colors.surface,
    borderRadius: radius.full,
    paddingHorizontal: 10, paddingVertical: 6,
  },
  optChipTxt: { fontSize: 12, fontWeight: '700', color: colors.textMain },
  optionAddRow: { flexDirection: 'row', gap: 8, alignItems: 'center' },
  optAddBtn: {
    flexDirection: 'row', alignItems: 'center', gap: 4,
    backgroundColor: tints.pink.bg,
    paddingHorizontal: 12, paddingVertical: 10,
    borderRadius: radius.full,
  },
  optAddTxt: { color: colors.primary, fontWeight: '700', fontSize: 12 },
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
