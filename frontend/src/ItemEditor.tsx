import React, { useEffect, useState } from 'react';
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity, TextInput,
  KeyboardAvoidingView, Platform, Image, Alert,
} from 'react-native';
import * as ImagePicker from 'expo-image-picker';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { useAuth } from './AuthContext';
import { colors, radius, spacing, shadows, tints, STATUS_LABELS } from './theme';
import { Icon } from './Icon';
import { api } from './api';
import type { Category, Item } from './types';

type Props = {
  mode: 'create' | 'edit';
  itemId?: string;
  preselectCategoryId?: string;
};

export default function ItemEditor({ mode, itemId, preselectCategoryId }: Props) {
  const router = useRouter();
  const { activeSpace } = useAuth();
  const [categories, setCategories] = useState<Category[]>([]);
  const [categoryId, setCategoryId] = useState<string>(preselectCategoryId || '');
  const [showCatPicker, setShowCatPicker] = useState(false);

  const [name, setName] = useState('');
  const [status, setStatus] = useState<'available' | 'low' | 'finished'>('available');
  const [quantity, setQuantity] = useState('1');
  const [price, setPrice] = useState('');
  const [purchaseDate, setPurchaseDate] = useState('');
  const [expiryDate, setExpiryDate] = useState('');
  const [notes, setNotes] = useState('');
  const [photo, setPhoto] = useState<string | null>(null);
  const [fields, setFields] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [bootLoading, setBootLoading] = useState(mode === 'edit');

  useEffect(() => {
    const run = async () => {
      if (!activeSpace) return;
      try {
        const cats = await api.get<Category[]>(`/categories?space_id=${activeSpace.space_id}`);
        setCategories(cats);
        if (mode === 'edit' && itemId) {
          const it = await api.get<Item>(`/items/${itemId}`);
          setCategoryId(it.category_id);
          setName(it.name);
          setStatus(it.status);
          setQuantity(String(it.quantity ?? 1));
          setPrice(it.price != null ? String(it.price) : '');
          setPurchaseDate(it.purchase_date || '');
          setExpiryDate(it.expiry_date || '');
          setNotes(it.notes || '');
          setPhoto(it.photo_base64 || null);
          setFields(it.fields || {});
        } else if (!categoryId && cats.length > 0) {
          setCategoryId(cats[0].category_id);
        }
      } catch (e) {
        console.warn(e);
      } finally {
        setBootLoading(false);
      }
    };
    run();
  }, [activeSpace, itemId, mode]);

  const activeCategory = categories.find((c) => c.category_id === categoryId);

  const pickImage = async () => {
    try {
      const result = await ImagePicker.launchImageLibraryAsync({
        mediaTypes: ImagePicker.MediaTypeOptions.Images,
        allowsEditing: true,
        aspect: [1, 1],
        quality: 0.6,
        base64: true,
      });
      if (!result.canceled && result.assets[0]) {
        const a = result.assets[0];
        const base64 = a.base64 ? `data:image/jpeg;base64,${a.base64}` : a.uri;
        setPhoto(base64);
      }
    } catch (e) { console.warn(e); }
  };

  const save = async () => {
    if (!activeSpace) return;
    if (!name.trim()) { setErr('Give this item a name'); return; }
    if (!categoryId) { setErr('Pick a category'); return; }
    setErr(null);
    setLoading(true);
    const payload: any = {
      category_id: categoryId,
      name: name.trim(),
      photo_base64: photo,
      status,
      quantity: parseFloat(quantity) || 1,
      price: price ? parseFloat(price) : null,
      purchase_date: purchaseDate || null,
      expiry_date: expiryDate || null,
      notes: notes || null,
      fields,
    };
    try {
      if (mode === 'create') {
        await api.post('/items', { ...payload, space_id: activeSpace.space_id });
      } else if (itemId) {
        await api.patch(`/items/${itemId}`, payload);
      }
      router.back();
    } catch (e: any) {
      setErr(e?.message || 'Failed to save');
    } finally { setLoading(false); }
  };

  const deleteItem = () => {
    const doIt = async () => {
      try {
        if (itemId) await api.delete(`/items/${itemId}`);
        router.back();
      } catch (e) { console.warn(e); }
    };
    if (Platform.OS === 'web') {
      if (typeof window !== 'undefined' && window.confirm('Delete this item? This cannot be undone.')) doIt();
    } else {
      Alert.alert('Delete item?', 'This cannot be undone.', [
        { text: 'Cancel', style: 'cancel' },
        { text: 'Delete', style: 'destructive', onPress: doIt },
      ]);
    }
  };

  if (bootLoading) return <SafeAreaView style={styles.container}><Text style={{ padding: 20 }}>Loading...</Text></SafeAreaView>;

  return (
    <SafeAreaView style={styles.container} edges={['top', 'bottom']}>
      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={{ flex: 1 }}>
        <View style={styles.header}>
          <TouchableOpacity style={styles.iconBtn} onPress={() => router.back()} testID="item-editor-back">
            <Icon name="X" color={colors.textMain} />
          </TouchableOpacity>
          <Text style={styles.title}>{mode === 'create' ? 'Add item' : 'Edit item'}</Text>
          {mode === 'edit' ? (
            <TouchableOpacity style={styles.iconBtn} onPress={deleteItem} testID="item-editor-delete">
              <Icon name="Trash2" color={colors.dangerText} size={20} />
            </TouchableOpacity>
          ) : <View style={{ width: 40 }} />}
        </View>

        <ScrollView contentContainerStyle={styles.scroll} keyboardShouldPersistTaps="handled">
          <TouchableOpacity style={styles.photoBox} onPress={pickImage} testID="item-editor-photo">
            {photo ? (
              <Image source={{ uri: photo }} style={styles.photoImg} />
            ) : (
              <>
                <View style={[styles.photoPlaceholder, { backgroundColor: tints.pink.bg }]}>
                  <Icon name="ImageIcon" color={tints.pink.icon} size={24} />
                </View>
                <Text style={styles.photoTxt}>Add photo</Text>
              </>
            )}
          </TouchableOpacity>

          <View style={styles.field}>
            <Text style={styles.label}>Name</Text>
            <TextInput
              style={styles.input}
              placeholder="Ex. Oat milk, Vitamin C serum"
              placeholderTextColor="#95A5A6"
              value={name}
              onChangeText={setName}
              testID="item-editor-name"
            />
          </View>

          <View style={styles.field}>
            <Text style={styles.label}>Category</Text>
            <TouchableOpacity
              style={styles.input}
              onPress={() => setShowCatPicker((v) => !v)}
              testID="item-editor-category"
            >
              <Text style={{ color: activeCategory ? colors.textMain : colors.textMuted, fontSize: 15 }}>
                {activeCategory ? activeCategory.name : 'Pick a category'}
              </Text>
            </TouchableOpacity>
            {showCatPicker && (
              <View style={styles.catMenu}>
                {categories.map((c) => (
                  <TouchableOpacity
                    key={c.category_id}
                    style={styles.catMenuItem}
                    onPress={() => { setCategoryId(c.category_id); setShowCatPicker(false); }}
                  >
                    <View style={[styles.catDot, { backgroundColor: tints[c.tint]?.icon || colors.primary }]} />
                    <Text style={styles.catMenuTxt}>{c.name}</Text>
                    {categoryId === c.category_id && <Icon name="Check" color={colors.primary} size={16} />}
                  </TouchableOpacity>
                ))}
              </View>
            )}
          </View>

          <View style={styles.field}>
            <Text style={styles.label}>Status</Text>
            <View style={styles.statusRow}>
              {(['available', 'low', 'finished'] as const).map((s) => {
                const sl = STATUS_LABELS[s];
                const active = status === s;
                return (
                  <TouchableOpacity
                    key={s}
                    style={[styles.statusChip, active && { backgroundColor: sl.bg, borderColor: sl.color, borderWidth: 2 }]}
                    onPress={() => setStatus(s)}
                    testID={`item-editor-status-${s}`}
                  >
                    <Text style={[styles.statusTxt, active && { color: sl.color, fontWeight: '800' }]}>{sl.label}</Text>
                  </TouchableOpacity>
                );
              })}
            </View>
          </View>

          <View style={[styles.fieldRow, { gap: 10 }]}>
            <View style={{ flex: 1 }}>
              <Text style={styles.label}>Quantity</Text>
              <TextInput
                style={styles.input}
                keyboardType="numeric"
                value={quantity}
                onChangeText={setQuantity}
                testID="item-editor-quantity"
              />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={styles.label}>Price</Text>
              <TextInput
                style={styles.input}
                placeholder="0.00"
                placeholderTextColor="#95A5A6"
                keyboardType="decimal-pad"
                value={price}
                onChangeText={setPrice}
                testID="item-editor-price"
              />
            </View>
          </View>

          <View style={[styles.fieldRow, { gap: 10 }]}>
            <View style={{ flex: 1 }}>
              <Text style={styles.label}>Purchase date</Text>
              <TextInput
                style={styles.input}
                placeholder="YYYY-MM-DD"
                placeholderTextColor="#95A5A6"
                value={purchaseDate}
                onChangeText={setPurchaseDate}
                testID="item-editor-purchase"
              />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={styles.label}>Expiry date</Text>
              <TextInput
                style={styles.input}
                placeholder="YYYY-MM-DD"
                placeholderTextColor="#95A5A6"
                value={expiryDate}
                onChangeText={setExpiryDate}
                testID="item-editor-expiry"
              />
            </View>
          </View>

          {activeCategory && activeCategory.fields.length > 0 && (
            <View style={styles.field}>
              <Text style={styles.label}>{activeCategory.name} details</Text>
              {activeCategory.fields.map((f) => (
                <View key={f.key} style={{ marginBottom: 10 }}>
                  <Text style={[styles.label, { marginBottom: 4, textTransform: 'none' }]}>{f.label}</Text>
                  <TextInput
                    style={styles.input}
                    placeholder={f.type === 'date' ? 'YYYY-MM-DD' : f.type === 'number' || f.type === 'price' ? '0' : ''}
                    placeholderTextColor="#95A5A6"
                    keyboardType={f.type === 'number' || f.type === 'price' ? 'decimal-pad' : 'default'}
                    value={String(fields[f.key] ?? '')}
                    onChangeText={(v) => setFields((p) => ({ ...p, [f.key]: v }))}
                  />
                </View>
              ))}
            </View>
          )}

          <View style={styles.field}>
            <Text style={styles.label}>Notes</Text>
            <TextInput
              style={[styles.input, { height: 80, textAlignVertical: 'top' }]}
              multiline
              placeholder="Optional notes"
              placeholderTextColor="#95A5A6"
              value={notes}
              onChangeText={setNotes}
            />
          </View>

          {err && <Text style={styles.error}>{err}</Text>}

          <TouchableOpacity
            style={[styles.primary, loading && { opacity: 0.6 }]}
            onPress={save}
            disabled={loading}
            testID="item-editor-save"
          >
            <Text style={styles.primaryTxt}>{loading ? 'Saving...' : (mode === 'create' ? 'Save item' : 'Save changes')}</Text>
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
  photoBox: {
    height: 180,
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    alignItems: 'center', justifyContent: 'center',
    marginBottom: spacing.md,
    overflow: 'hidden',
    ...shadows.card,
  },
  photoImg: { width: '100%', height: '100%' },
  photoPlaceholder: {
    width: 56, height: 56, borderRadius: 28,
    alignItems: 'center', justifyContent: 'center',
    marginBottom: 8,
  },
  photoTxt: { color: colors.textMuted, fontWeight: '600', fontSize: 14 },
  field: { marginBottom: spacing.md },
  fieldRow: { flexDirection: 'row', marginBottom: spacing.md },
  label: { fontSize: 11, fontWeight: '800', color: colors.textMuted, textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 6 },
  input: {
    backgroundColor: colors.surfaceAlt,
    borderRadius: radius.md,
    paddingHorizontal: spacing.md, paddingVertical: 12,
    fontSize: 15, color: colors.textMain,
  },
  catMenu: {
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    marginTop: 8,
    overflow: 'hidden',
    ...shadows.card,
  },
  catMenuItem: {
    flexDirection: 'row', alignItems: 'center', gap: 10,
    paddingHorizontal: spacing.md, paddingVertical: 12,
  },
  catDot: { width: 10, height: 10, borderRadius: 5 },
  catMenuTxt: { flex: 1, fontSize: 14, fontWeight: '600', color: colors.textMain },
  statusRow: { flexDirection: 'row', gap: 8 },
  statusChip: {
    flex: 1,
    paddingVertical: 12,
    alignItems: 'center',
    borderRadius: radius.md,
    backgroundColor: colors.surface,
    borderWidth: 2, borderColor: 'transparent',
  },
  statusTxt: { fontSize: 13, fontWeight: '600', color: colors.textMuted },
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
