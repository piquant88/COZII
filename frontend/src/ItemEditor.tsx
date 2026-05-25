import React, { useEffect, useState } from 'react';
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity, TextInput,
  KeyboardAvoidingView, Platform, Image, Alert,
} from 'react-native';
import * as ImagePicker from 'expo-image-picker';
import { pickImageWithChoice } from './imagePicker';
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
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [searchingImg, setSearchingImg] = useState(false);
  const [fields, setFields] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [bootLoading, setBootLoading] = useState(mode === 'edit');
  const [auditRows, setAuditRows] = useState<any[]>([]);
  const [auditLoading, setAuditLoading] = useState(false);

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
          setImageUrl(it.image_url || null);
          setFields(it.fields || {});
          // Load audit history in parallel — never block the editor on this
          setAuditLoading(true);
          api.get<any[]>(`/items/${itemId}/audit?limit=30`)
            .then((rows) => setAuditRows(Array.isArray(rows) ? rows : []))
            .catch(() => setAuditRows([]))
            .finally(() => setAuditLoading(false));
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
    const picked = await pickImageWithChoice({ allowsEditing: true, aspect: [1, 1], quality: 0.6, base64: true });
    if (!picked) return; // cancelled or denied (helper showed Alert)
    setPhoto(picked.dataUri);
    setImageUrl(null); // user-uploaded photo overrides web image
  };

  const findImage = async () => {
    if (!name.trim()) { Alert.alert('Add a name first', 'Type the product name (e.g. "Dior Joy Bag") then tap Find image.'); return; }
    setSearchingImg(true);
    try {
      const r = await api.get<{ image_url: string | null }>(`/products/image-search?q=${encodeURIComponent(name.trim())}`);
      if (r.image_url) {
        setImageUrl(r.image_url);
        setPhoto(null);
      } else {
        Alert.alert('No image found', 'Try a more specific name, or tap the photo box to upload one yourself.');
      }
    } catch (e: any) {
      Alert.alert('Search failed', e?.message || 'Try again, or upload a photo manually.');
    } finally {
      setSearchingImg(false);
    }
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
      image_url: imageUrl,
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
          <View style={{ gap: 6 }}>
            <TouchableOpacity style={styles.photoBox} onPress={pickImage} testID="item-editor-photo">
              {(photo || imageUrl) ? (
                <Image source={{ uri: photo || imageUrl! }} style={styles.photoImg} />
              ) : (
                <>
                  <View style={[styles.photoPlaceholder, { backgroundColor: tints.pink.bg }]}>
                    <Icon name="ImageIcon" color={tints.pink.icon} size={24} />
                  </View>
                  <Text style={styles.photoTxt}>Add photo</Text>
                </>
              )}
            </TouchableOpacity>
            <View style={{ flexDirection: 'row', gap: 6 }}>
              <TouchableOpacity
                style={styles.findImgBtn}
                onPress={findImage}
                disabled={searchingImg || !name.trim()}
                testID="item-editor-find-image"
              >
                <Icon name="Sparkles" size={14} color={searchingImg ? colors.textMuted : colors.primary} />
                <Text style={[styles.findImgTxt, (searchingImg || !name.trim()) && { color: colors.textMuted }]}>
                  {searchingImg ? 'Searching…' : 'Find image online'}
                </Text>
              </TouchableOpacity>
              {(photo || imageUrl) && (
                <TouchableOpacity
                  style={styles.findImgBtn}
                  onPress={() => { setPhoto(null); setImageUrl(null); }}
                  testID="item-editor-clear-image"
                >
                  <Icon name="X" size={14} color={colors.dangerText} />
                  <Text style={[styles.findImgTxt, { color: colors.dangerText }]}>Clear</Text>
                </TouchableOpacity>
              )}
            </View>
          </View>

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
                  {f.type === 'select' && f.options && f.options.length > 0 ? (
                    <View style={styles.selectChipRow}>
                      {f.options.map((opt) => {
                        const active = String(fields[f.key] ?? '') === opt;
                        return (
                          <TouchableOpacity
                            key={opt}
                            style={[styles.selectChip, active && styles.selectChipActive]}
                            onPress={() => setFields((p) => ({ ...p, [f.key]: active ? '' : opt }))}
                          >
                            <Text style={[styles.selectChipTxt, active && styles.selectChipTxtActive]}>{opt}</Text>
                          </TouchableOpacity>
                        );
                      })}
                    </View>
                  ) : (
                    <TextInput
                      style={styles.input}
                      placeholder={f.type === 'date' ? 'YYYY-MM-DD' : f.type === 'number' || f.type === 'price' ? '0' : ''}
                      placeholderTextColor="#95A5A6"
                      keyboardType={f.type === 'number' || f.type === 'price' ? 'decimal-pad' : 'default'}
                      value={String(fields[f.key] ?? '')}
                      onChangeText={(v) => setFields((p) => ({ ...p, [f.key]: v }))}
                    />
                  )}
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

          {/* Activity / history — only on edit mode */}
          {mode === 'edit' && (
            <View style={styles.activityCard}>
              <View style={styles.activityHeader}>
                <Icon name="Clock" size={16} color={colors.textMain} />
                <Text style={styles.activityTitle}>Activity</Text>
                {auditRows.length > 0 && <Text style={styles.activityCount}>{auditRows.length}</Text>}
              </View>
              {auditLoading ? (
                <Text style={styles.activityEmpty}>Loading…</Text>
              ) : auditRows.length === 0 ? (
                <Text style={styles.activityEmpty}>No changes yet. Use the +/- buttons in inventory to start tracking.</Text>
              ) : (
                auditRows.map((row, i) => {
                  const isInc = (row.delta || 0) > 0;
                  const deltaTxt = `${isInc ? '+' : ''}${row.delta}${row.unit ? ' ' + row.unit : ''}`;
                  const when = (() => {
                    try {
                      const d = new Date(row.created_at);
                      return d.toLocaleString();
                    } catch { return row.created_at; }
                  })();
                  return (
                    <View key={row.audit_id || i} style={styles.auditRow}>
                      <View style={[styles.auditBadge, { backgroundColor: isInc ? '#E6F5E8' : '#FFE4E1' }]}>
                        <Icon
                          name={isInc ? 'PlusCircle' : 'MinusCircle'}
                          size={14}
                          color={isInc ? '#5FA06A' : '#C0392B'}
                        />
                      </View>
                      <View style={{ flex: 1 }}>
                        <Text style={styles.auditLine}>
                          <Text style={styles.auditUser}>{row.user_name}</Text>
                          <Text> {row.action} </Text>
                          <Text style={styles.auditDelta}>{deltaTxt}</Text>
                          <Text style={styles.auditTail}>{`  (${row.prev_qty} → ${row.new_qty})`}</Text>
                        </Text>
                        <Text style={styles.auditTime}>{when}{row.note ? ` • ${row.note}` : ''}</Text>
                      </View>
                    </View>
                  );
                })
              )}
            </View>
          )}
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
  findImgBtn: { flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, paddingVertical: 10, borderRadius: radius.full, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border },
  findImgTxt: { fontSize: 12, fontWeight: '800', color: colors.primary },
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
  activityCard: {
    marginTop: spacing.lg,
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    padding: spacing.md,
    borderWidth: 1, borderColor: colors.border,
  },
  activityHeader: {
    flexDirection: 'row', alignItems: 'center', gap: 8,
    marginBottom: spacing.sm,
  },
  activityTitle: { flex: 1, fontWeight: '800', fontSize: 14, color: colors.textMain },
  activityCount: {
    fontSize: 11, fontWeight: '700', color: colors.textMuted,
    backgroundColor: colors.surfaceAlt, paddingHorizontal: 8, paddingVertical: 2, borderRadius: radius.full,
  },
  activityEmpty: { color: colors.textMuted, fontSize: 12, paddingVertical: 8, lineHeight: 17 },
  auditRow: {
    flexDirection: 'row', alignItems: 'flex-start', gap: 10,
    paddingVertical: 8,
    borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.border,
  },
  auditBadge: {
    width: 26, height: 26, borderRadius: 13,
    alignItems: 'center', justifyContent: 'center',
  },
  auditLine: { fontSize: 13, color: colors.textMain, lineHeight: 18 },
  auditUser: { fontWeight: '800' },
  auditDelta: { fontWeight: '800', color: colors.textMain },
  auditTail: { color: colors.textMuted, fontWeight: '500' },
  auditTime: { fontSize: 11, color: colors.textMuted, marginTop: 2 },
  selectChipRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  selectChip: {
    paddingHorizontal: 14, paddingVertical: 8,
    borderRadius: radius.full,
    backgroundColor: colors.surfaceAlt,
    borderWidth: 2, borderColor: 'transparent',
  },
  selectChipActive: { backgroundColor: colors.primary, borderColor: colors.primary },
  selectChipTxt: { fontSize: 13, fontWeight: '700', color: colors.textMuted },
  selectChipTxtActive: { color: '#fff' },
});
