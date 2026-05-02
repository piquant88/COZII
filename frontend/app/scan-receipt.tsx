import React, { useState, useEffect } from 'react';
import {
  View, Text, StyleSheet, TouchableOpacity, ScrollView, Image,
  TextInput, ActivityIndicator, KeyboardAvoidingView, Platform,
} from 'react-native';
import * as ImagePicker from 'expo-image-picker';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { useAuth } from '../src/AuthContext';
import { api } from '../src/api';
import { colors, radius, spacing, shadows, tints } from '../src/theme';
import { Icon } from '../src/Icon';
import type { Category } from '../src/types';

type Scanned = {
  name: string;
  quantity: number;
  price: number | null;
  category_hint: string | null;
  category_id: string;
  fields: Record<string, any>;
};

// Map AI category hints to category tint to help auto-assign
function autoMatchCategory(hint: string | null, categories: Category[]): string | null {
  if (!hint || categories.length === 0) return null;
  const h = hint.toLowerCase();
  const byTint = (t: string) => categories.find((c) => c.tint === t)?.category_id;
  const byName = (kw: string) => categories.find((c) => c.name.toLowerCase().includes(kw))?.category_id;
  if (h.includes('food') || h.includes('grocery') || h.includes('pantry')) return byName('food') || byName('pantry') || byTint('mint') || categories[0].category_id;
  if (h.includes('skin') || h.includes('cosmetic') || h.includes('makeup')) return byName('skin') || byTint('lavender') || categories[0].category_id;
  if (h.includes('toilet') || h.includes('hygien') || h.includes('bath')) return byName('toilet') || byTint('yellow') || categories[0].category_id;
  if (h.includes('clothe') || h.includes('closet') || h.includes('apparel')) return byName('closet') || byName('cloth') || byTint('peach') || categories[0].category_id;
  if (h.includes('clean')) return byName('clean') || byTint('sage') || categories[0].category_id;
  return categories[0].category_id;
}

export default function ScanReceipt() {
  const router = useRouter();
  const { activeSpace } = useAuth();
  const { category_id: preselectCategoryId } = useLocalSearchParams<{ category_id?: string }>();
  const [categories, setCategories] = useState<Category[]>([]);
  const [defaultCategoryId, setDefaultCategoryId] = useState<string>('');
  const [photo, setPhoto] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [saving, setSaving] = useState(false);
  const [items, setItems] = useState<Scanned[]>([]);
  const [showCategoryPicker, setShowCategoryPicker] = useState(false);
  const [pickerForIndex, setPickerForIndex] = useState<number | null>(null);
  const [eventTag, setEventTag] = useState<string>('');
  const [error, setError] = useState<string | null>(null);
  const [lockCategory, setLockCategory] = useState<boolean>(!!preselectCategoryId);

  useEffect(() => {
    (async () => {
      if (!activeSpace) return;
      try {
        const cats = await api.get<Category[]>(`/categories?space_id=${activeSpace.space_id}`);
        setCategories(cats);
        if (preselectCategoryId && cats.find((c) => c.category_id === preselectCategoryId)) {
          setDefaultCategoryId(preselectCategoryId);
        } else if (cats[0]) {
          setDefaultCategoryId(cats[0].category_id);
        }
      } catch (e) { console.warn(e); }
    })();
  }, [activeSpace, preselectCategoryId]);

  const pickImage = async (fromCamera: boolean) => {
    setError(null);
    try {
      const options = {
        mediaTypes: ImagePicker.MediaTypeOptions.Images,
        allowsEditing: false,
        quality: 0.5,
        base64: true,
      } as any;
      const result = fromCamera
        ? await ImagePicker.launchCameraAsync(options)
        : await ImagePicker.launchImageLibraryAsync(options);
      if (!result.canceled && result.assets?.[0]) {
        const a = result.assets[0];
        let base64 = a.base64 ? `data:image/jpeg;base64,${a.base64}` : a.uri;
        // Downscale on web to save AI tokens
        if (Platform.OS === 'web' && base64.startsWith('data:')) {
          try { base64 = await downscaleBase64(base64, 1024); } catch {}
        }
        setPhoto(base64);
        setItems([]);
      }
    } catch (e) { console.warn(e); }
  };

  async function downscaleBase64(src: string, maxSide: number): Promise<string> {
    return new Promise((resolve, reject) => {
      try {
        const img = new (window as any).Image();
        img.onload = () => {
          const ratio = Math.min(1, maxSide / Math.max(img.width, img.height));
          const w = Math.round(img.width * ratio);
          const h = Math.round(img.height * ratio);
          const canvas = (window as any).document.createElement('canvas');
          canvas.width = w; canvas.height = h;
          const ctx = canvas.getContext('2d');
          ctx.drawImage(img, 0, 0, w, h);
          resolve(canvas.toDataURL('image/jpeg', 0.7));
        };
        img.onerror = () => resolve(src);
        img.src = src;
      } catch (e) { reject(e); }
    });
  }

  const scan = async () => {
    if (!photo) return;
    setError(null);
    setScanning(true);
    try {
      // When locked to a category, send its custom fields to AI for richer extraction
      const lockedCat = categories.find((c) => c.category_id === defaultCategoryId);
      const target_fields = (lockCategory && lockedCat) ? lockedCat.fields : [];
      const res = await api.post<{ items: any[] }>('/ai/scan-receipt', {
        image_base64: photo,
        target_fields,
      });
      const mapped: Scanned[] = (res.items || []).map((it) => ({
        name: it.name,
        quantity: it.quantity || 1,
        price: it.price ?? null,
        category_hint: it.category_hint || null,
        category_id: lockCategory
          ? defaultCategoryId
          : (autoMatchCategory(it.category_hint, categories) || defaultCategoryId),
        fields: (it.fields && typeof it.fields === 'object') ? it.fields : {},
      }));
      if (mapped.length === 0) {
        setError("No items detected. Try a clearer photo or add items manually.");
      } else {
        setItems(mapped);
      }
    } catch (e: any) {
      setError(e?.message || 'Scan failed');
    } finally {
      setScanning(false);
    }
  };

  const updateItem = (i: number, key: keyof Scanned, value: any) => {
    setItems((p) => p.map((it, idx) => idx === i ? { ...it, [key]: value } : it));
  };

  const removeItem = (i: number) => setItems((p) => p.filter((_, idx) => idx !== i));

  const addManual = () => {
    setItems((p) => [...p, { name: '', quantity: 1, price: null, category_hint: null, category_id: defaultCategoryId, fields: {} }]);
  };

  const save = async () => {
    if (!activeSpace || !defaultCategoryId) return;
    const valid = items.filter((it) => it.name.trim());
    if (valid.length === 0) { setError('Add at least one item'); return; }
    setSaving(true);
    setError(null);
    try {
      const perItem: Record<string, string> = {};
      items.forEach((it, idx) => {
        if (it.category_id && it.category_id !== defaultCategoryId) perItem[String(idx)] = it.category_id;
      });
      await api.post('/items/bulk', {
        space_id: activeSpace.space_id,
        category_id: defaultCategoryId,
        per_item_category: perItem,
        items: valid.map((it) => ({
          name: it.name.trim(),
          quantity: it.quantity,
          price: it.price,
          category_hint: it.category_hint,
          fields: it.fields || {},
        })),
        purchase_date: new Date().toISOString().slice(0, 10),
        receipt_photo_base64: photo,
        event_tag: eventTag.trim() || null,
        auto_fetch_images: true,
      });
      router.replace('/(tabs)/inventory');
    } catch (e: any) {
      setError(e?.message || 'Failed to save');
    } finally {
      setSaving(false);
    }
  };

  const defaultCategory = categories.find((c) => c.category_id === defaultCategoryId);

  return (
    <SafeAreaView style={styles.container} edges={['top', 'bottom']}>
      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={{ flex: 1 }}>
        <View style={styles.header}>
          <TouchableOpacity style={styles.iconBtn} onPress={() => router.back()} testID="scan-back">
            <Icon name="X" color={colors.textMain} />
          </TouchableOpacity>
          <Text style={styles.title}>Scan receipt</Text>
          <View style={{ width: 40 }} />
        </View>

        <ScrollView contentContainerStyle={styles.scroll} keyboardShouldPersistTaps="handled">
          {!photo ? (
            <View style={styles.emptyHero}>
              <View style={styles.heroIcon}>
                <Icon name="Camera" color={colors.primary} size={32} />
              </View>
              <Text style={styles.heroTitle}>
                {lockCategory && defaultCategory
                  ? `Scan a receipt into ${defaultCategory.name}`
                  : 'Add a whole receipt at once'}
              </Text>
              <Text style={styles.heroSub}>
                {lockCategory
                  ? 'Snap or upload a receipt and AI will add every item to this category. You can move individual items later.'
                  : 'Snap or upload a receipt photo and Cozii AI will extract items, prices, and quantities. Edit anything, pick categories, and save all at once.'}
              </Text>
              <View style={styles.heroActions}>
                <TouchableOpacity style={styles.primaryBtn} onPress={() => pickImage(true)} testID="scan-take-photo">
                  <Icon name="Camera" color="#fff" size={18} />
                  <Text style={styles.primaryTxt}>Take photo</Text>
                </TouchableOpacity>
                <TouchableOpacity style={styles.secondaryBtn} onPress={() => pickImage(false)} testID="scan-upload">
                  <Icon name="ImageIcon" color={colors.textMain} size={18} />
                  <Text style={styles.secondaryTxt}>Upload from library</Text>
                </TouchableOpacity>
              </View>
            </View>
          ) : (
            <>
              <View style={styles.photoCard}>
                <Image source={{ uri: photo }} style={styles.photoImg} />
                <TouchableOpacity style={styles.photoRemove} onPress={() => { setPhoto(null); setItems([]); }} testID="scan-change-photo">
                  <Icon name="X" color="#fff" size={16} />
                </TouchableOpacity>
              </View>

              {items.length === 0 && !scanning && (
                <TouchableOpacity style={[styles.primaryBtn, { marginTop: spacing.md }]} onPress={scan} testID="scan-analyze">
                  <Icon name="Sparkles" color="#fff" size={18} />
                  <Text style={styles.primaryTxt}>Analyze with AI</Text>
                </TouchableOpacity>
              )}

              {scanning && (
                <View style={styles.scanning}>
                  <ActivityIndicator color={colors.primary} size="large" />
                  <Text style={styles.scanningTxt}>Reading your receipt...</Text>
                  <Text style={styles.scanningSub}>This usually takes 10–20 seconds</Text>
                </View>
              )}

              {items.length > 0 && (
                <>
                  <View style={styles.defaultCatBox}>
                    <View style={{ flex: 1 }}>
                      <Text style={styles.label}>Default category for these items</Text>
                      <TouchableOpacity
                        style={styles.catSelect}
                        onPress={() => { setShowCategoryPicker(true); setPickerForIndex(null); }}
                        testID="scan-default-category"
                      >
                        {defaultCategory && <View style={[styles.catDot, { backgroundColor: tints[defaultCategory.tint]?.icon || colors.primary }]} />}
                        <Text style={styles.catSelectTxt}>{defaultCategory?.name || 'Pick category'}</Text>
                        <Icon name="ChevronRight" size={16} color={colors.textMuted} />
                      </TouchableOpacity>
                    </View>
                  </View>

                  <View style={styles.defaultCatBox}>
                    <View style={{ flex: 1 }}>
                      <Text style={styles.label}>Event tag (optional)</Text>
                      <TextInput
                        style={styles.eventInput}
                        value={eventTag}
                        onChangeText={setEventTag}
                        placeholder='e.g. "Birthday June 8" or "Diwali 2026"'
                        placeholderTextColor={colors.textMuted}
                        testID="scan-event-tag"
                      />
                      <Text style={styles.eventHint}>Stamps every item with this tag so you can group all event expenses together.</Text>
                    </View>
                  </View>

                  <Text style={[styles.sectionTitle, { marginTop: spacing.md }]}>Detected items</Text>
                  <Text style={styles.sectionSub}>Tap any item to edit. Each can go in a different category.</Text>

                  {items.map((it, idx) => {
                    const cat = categories.find((c) => c.category_id === it.category_id);
                    return (
                      <View key={idx} style={styles.itemCard}>
                        <View style={{ flex: 1 }}>
                          <TextInput
                            style={styles.itemName}
                            value={it.name}
                            onChangeText={(v) => updateItem(idx, 'name', v)}
                            placeholder="Item name"
                            placeholderTextColor="#95A5A6"
                            testID={`scan-item-${idx}-name`}
                          />
                          <View style={styles.itemMeta}>
                            <View style={styles.metaField}>
                              <Text style={styles.metaLbl}>Qty</Text>
                              <TextInput
                                style={styles.metaInput}
                                value={String(it.quantity)}
                                onChangeText={(v) => updateItem(idx, 'quantity', parseFloat(v) || 1)}
                                keyboardType="decimal-pad"
                                testID={`scan-item-${idx}-qty`}
                              />
                            </View>
                            <View style={[styles.metaField, { flex: 1 }]}>
                              <Text style={styles.metaLbl}>Price</Text>
                              <TextInput
                                style={styles.metaInput}
                                value={it.price != null ? String(it.price) : ''}
                                onChangeText={(v) => updateItem(idx, 'price', v ? parseFloat(v) : null)}
                                placeholder="0.00"
                                placeholderTextColor="#95A5A6"
                                keyboardType="decimal-pad"
                                testID={`scan-item-${idx}-price`}
                              />
                            </View>
                          </View>
                          <TouchableOpacity
                            style={styles.itemCat}
                            onPress={() => { setShowCategoryPicker(true); setPickerForIndex(idx); }}
                            testID={`scan-item-${idx}-category`}
                          >
                            {cat && <View style={[styles.catDot, { backgroundColor: tints[cat.tint]?.icon || colors.primary }]} />}
                            <Text style={styles.itemCatTxt}>{cat?.name || 'Pick category'}</Text>
                          </TouchableOpacity>
                        </View>
                        <TouchableOpacity onPress={() => removeItem(idx)} style={styles.removeBtn}>
                          <Icon name="X" size={16} color={colors.textMuted} />
                        </TouchableOpacity>
                      </View>
                    );
                  })}

                  <TouchableOpacity style={styles.addBtn} onPress={addManual} testID="scan-add-manual">
                    <Icon name="Plus" color={colors.primary} size={16} />
                    <Text style={styles.addBtnTxt}>Add item manually</Text>
                  </TouchableOpacity>

                  {error && <Text style={styles.error}>{error}</Text>}

                  <TouchableOpacity
                    style={[styles.primaryBtn, saving && { opacity: 0.6 }, { marginTop: spacing.lg }]}
                    onPress={save}
                    disabled={saving}
                    testID="scan-save-all"
                  >
                    <Text style={styles.primaryTxt}>{saving ? 'Saving...' : `Save ${items.filter(i => i.name.trim()).length} item${items.length > 1 ? 's' : ''}`}</Text>
                  </TouchableOpacity>
                </>
              )}

              {error && items.length === 0 && !scanning && (
                <Text style={styles.error}>{error}</Text>
              )}
            </>
          )}
        </ScrollView>
      </KeyboardAvoidingView>

      {/* Category picker modal */}
      {showCategoryPicker && (
        <TouchableOpacity
          style={styles.modalOverlay}
          activeOpacity={1}
          onPress={() => setShowCategoryPicker(false)}
        >
          <View style={styles.modalSheet} onStartShouldSetResponder={() => true}>
            <Text style={styles.modalTitle}>
              {pickerForIndex === null ? 'Default category' : 'Change category'}
            </Text>
            <ScrollView style={{ maxHeight: 360 }}>
              {categories.map((c) => (
                <TouchableOpacity
                  key={c.category_id}
                  style={styles.modalRow}
                  onPress={() => {
                    if (pickerForIndex === null) setDefaultCategoryId(c.category_id);
                    else updateItem(pickerForIndex, 'category_id', c.category_id);
                    setShowCategoryPicker(false);
                  }}
                >
                  <View style={[styles.catDot, { backgroundColor: tints[c.tint]?.icon || colors.primary }]} />
                  <Text style={styles.modalRowTxt}>{c.name}</Text>
                  {((pickerForIndex === null && defaultCategoryId === c.category_id) ||
                    (pickerForIndex !== null && items[pickerForIndex]?.category_id === c.category_id)) && (
                    <Icon name="Check" size={16} color={colors.primary} />
                  )}
                </TouchableOpacity>
              ))}
            </ScrollView>
          </View>
        </TouchableOpacity>
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
  scroll: { padding: spacing.md, paddingBottom: 80 },
  emptyHero: { alignItems: 'center', paddingVertical: 40 },
  heroIcon: {
    width: 80, height: 80, borderRadius: 40,
    backgroundColor: tints.pink.bg,
    alignItems: 'center', justifyContent: 'center',
    marginBottom: spacing.md,
  },
  heroTitle: { fontSize: 22, fontWeight: '900', color: colors.textMain, textAlign: 'center', letterSpacing: -0.5 },
  heroSub: {
    fontSize: 14, color: colors.textMuted,
    textAlign: 'center', marginTop: 8,
    lineHeight: 20, paddingHorizontal: 10,
    marginBottom: spacing.lg,
  },
  heroActions: { width: '100%', gap: 10 },
  primaryBtn: {
    backgroundColor: colors.primary,
    paddingVertical: 16,
    borderRadius: radius.full,
    alignItems: 'center', justifyContent: 'center',
    flexDirection: 'row',
    gap: 8,
    ...shadows.button,
  },
  primaryTxt: { color: '#fff', fontWeight: '800', fontSize: 15 },
  secondaryBtn: {
    backgroundColor: colors.surface,
    paddingVertical: 16,
    borderRadius: radius.full,
    alignItems: 'center', justifyContent: 'center',
    flexDirection: 'row', gap: 8,
    ...shadows.card,
  },
  secondaryTxt: { color: colors.textMain, fontWeight: '700', fontSize: 15 },
  photoCard: {
    borderRadius: radius.lg, overflow: 'hidden',
    backgroundColor: colors.surface,
    ...shadows.card,
  },
  photoImg: { width: '100%', height: 260, resizeMode: 'cover' },
  photoRemove: {
    position: 'absolute', top: 10, right: 10,
    width: 30, height: 30, borderRadius: 15,
    backgroundColor: 'rgba(0,0,0,0.6)',
    alignItems: 'center', justifyContent: 'center',
  },
  scanning: { alignItems: 'center', paddingVertical: 40 },
  scanningTxt: { fontSize: 15, fontWeight: '700', color: colors.textMain, marginTop: 12 },
  scanningSub: { fontSize: 13, color: colors.textMuted, marginTop: 4 },
  defaultCatBox: {
    marginTop: spacing.md,
    backgroundColor: colors.surface,
    padding: spacing.md,
    borderRadius: radius.lg,
    ...shadows.card,
  },
  label: { fontSize: 11, fontWeight: '800', color: colors.textMuted, textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 8 },
  catSelect: {
    flexDirection: 'row', alignItems: 'center', gap: 8,
    backgroundColor: colors.surfaceAlt,
    paddingHorizontal: spacing.md, paddingVertical: 12,
    borderRadius: radius.md,
  },
  catSelectTxt: { flex: 1, fontSize: 14, fontWeight: '700', color: colors.textMain },
  eventInput: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, paddingHorizontal: 12, paddingVertical: 10, fontSize: 14, color: colors.textMain, marginTop: 6 },
  eventHint: { fontSize: 11, color: colors.textMuted, marginTop: 4, lineHeight: 15, fontStyle: 'italic' },
  catDot: { width: 10, height: 10, borderRadius: 5 },
  sectionTitle: { fontSize: 18, fontWeight: '800', color: colors.textMain, marginBottom: 2 },
  sectionSub: { fontSize: 12, color: colors.textMuted, marginBottom: spacing.md },
  itemCard: {
    flexDirection: 'row',
    backgroundColor: colors.surface,
    padding: spacing.md,
    borderRadius: radius.md,
    marginBottom: 10,
    gap: 8,
    ...shadows.card,
  },
  itemName: { fontSize: 15, fontWeight: '700', color: colors.textMain, paddingVertical: 4 },
  itemMeta: { flexDirection: 'row', gap: 10, marginTop: 8 },
  metaField: { backgroundColor: colors.surfaceAlt, borderRadius: radius.sm, paddingHorizontal: 10, paddingVertical: 6, minWidth: 72 },
  metaLbl: { fontSize: 10, color: colors.textMuted, fontWeight: '700', textTransform: 'uppercase' },
  metaInput: { fontSize: 14, fontWeight: '700', color: colors.textMain, paddingVertical: 2, minWidth: 60 },
  itemCat: {
    flexDirection: 'row', alignItems: 'center', gap: 8,
    marginTop: 10, paddingVertical: 6, paddingHorizontal: 10,
    backgroundColor: colors.surfaceAlt, borderRadius: radius.full,
    alignSelf: 'flex-start',
  },
  itemCatTxt: { fontSize: 12, fontWeight: '700', color: colors.textMain },
  removeBtn: { padding: 4, alignSelf: 'flex-start' },
  addBtn: {
    flexDirection: 'row', alignItems: 'center', gap: 6,
    alignSelf: 'center',
    backgroundColor: tints.pink.bg,
    paddingHorizontal: 16, paddingVertical: 10,
    borderRadius: radius.full,
    marginTop: 4,
  },
  addBtnTxt: { color: colors.primary, fontWeight: '700', fontSize: 13 },
  error: { color: colors.dangerText, marginTop: 10, fontSize: 13, textAlign: 'center' },
  modalOverlay: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: 'rgba(0,0,0,0.4)',
    justifyContent: 'flex-end',
  },
  modalSheet: {
    backgroundColor: colors.surface,
    borderTopLeftRadius: 32, borderTopRightRadius: 32,
    padding: spacing.lg,
    paddingBottom: 40,
  },
  modalTitle: { fontSize: 18, fontWeight: '800', color: colors.textMain, marginBottom: spacing.md, textAlign: 'center' },
  modalRow: {
    flexDirection: 'row', alignItems: 'center', gap: 10,
    paddingVertical: 14, borderBottomWidth: 1, borderBottomColor: colors.border,
  },
  modalRowTxt: { flex: 1, fontSize: 15, fontWeight: '600', color: colors.textMain },
});
