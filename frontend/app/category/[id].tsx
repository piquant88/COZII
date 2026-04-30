import React, { useState, useCallback } from 'react';
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity, RefreshControl, Image, Alert, Platform,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useLocalSearchParams, useRouter, useFocusEffect } from 'expo-router';
import { useAuth } from '../../src/AuthContext';
import { colors, radius, spacing, shadows, tints, STATUS_LABELS } from '../../src/theme';
import { Icon } from '../../src/Icon';
import { api } from '../../src/api';
import type { Item, Category } from '../../src/types';
import { format } from 'date-fns';

export default function CategoryDetail() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const { activeSpace } = useAuth();
  const [category, setCategory] = useState<Category | null>(null);
  const [items, setItems] = useState<Item[]>([]);
  const [refreshing, setRefreshing] = useState(false);
  const [filter, setFilter] = useState<'all' | 'available' | 'low' | 'finished'>('all');
  const [showAddSheet, setShowAddSheet] = useState(false);

  const load = useCallback(async () => {
    if (!activeSpace || !id) return;
    try {
      const [cats, its] = await Promise.all([
        api.get<Category[]>(`/categories?space_id=${activeSpace.space_id}`),
        api.get<Item[]>(`/items?space_id=${activeSpace.space_id}&category_id=${id}`),
      ]);
      setCategory(cats.find((c) => c.category_id === id) || null);
      setItems(its);
    } catch (e) { console.warn(e); }
  }, [activeSpace, id]);

  useFocusEffect(useCallback(() => {
    load();
    const iv = setInterval(load, 10000);
    return () => clearInterval(iv);
  }, [load]));

  const onRefresh = async () => { setRefreshing(true); await load(); setRefreshing(false); };

  const filtered = items.filter((it) => filter === 'all' ? true : it.status === filter);
  const tint = tints[category?.tint || 'mint'] || tints.mint;

  const toggleStatus = async (item: Item, newStatus: 'available' | 'low' | 'finished') => {
    try {
      await api.patch(`/items/${item.item_id}`, { status: newStatus });
      load();
    } catch (e) { console.warn(e); }
  };

  const confirmDeleteCategory = () => {
    const doIt = async () => {
      try {
        await api.delete(`/categories/${id}`);
        router.back();
      } catch (e) { console.warn(e); }
    };
    if (Platform.OS === 'web') {
      // eslint-disable-next-line no-alert
      if (typeof window !== 'undefined' && window.confirm('Delete this category and all its items? This cannot be undone.')) {
        doIt();
      }
    } else {
      Alert.alert('Delete category?', 'This will also remove all its items.', [
        { text: 'Cancel', style: 'cancel' },
        { text: 'Delete', style: 'destructive', onPress: doIt },
      ]);
    }
  };

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <View style={[styles.banner, { backgroundColor: tint.bg }]}>
        <TouchableOpacity style={styles.iconBtn} onPress={() => router.back()} testID="category-back">
          <Icon name="ArrowLeft" color={colors.textMain} />
        </TouchableOpacity>
        <View style={[styles.bannerIconWrap, { backgroundColor: '#fff' }]}>
          <Icon name={category?.icon || 'Box'} color={tint.icon} size={22} />
        </View>
        <Text style={styles.bannerTitle} numberOfLines={1}>{category?.name || 'Category'}</Text>
        <TouchableOpacity style={styles.iconBtn} onPress={confirmDeleteCategory} testID="category-delete">
          <Icon name="Trash2" color={colors.textMain} size={20} />
        </TouchableOpacity>
      </View>

      <View style={styles.filterRow}>
        {(['all', 'available', 'low', 'finished'] as const).map((f) => (
          <TouchableOpacity
            key={f}
            style={[styles.chip, filter === f && styles.chipActive]}
            onPress={() => setFilter(f)}
            testID={`filter-${f}`}
          >
            <Text style={[styles.chipTxt, filter === f && styles.chipTxtActive]}>
              {f === 'all' ? 'All' : STATUS_LABELS[f].label}
            </Text>
          </TouchableOpacity>
        ))}
      </View>

      <ScrollView
        contentContainerStyle={styles.scroll}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.primary} />}
        showsVerticalScrollIndicator={false}
      >
        {filtered.length === 0 ? (
          <View style={[styles.card, { alignItems: 'center', paddingVertical: 40 }]}>
            <Icon name="Package" color={colors.textMuted} size={28} />
            <Text style={{ color: colors.textMuted, marginTop: 10 }}>No items here yet.</Text>
            <TouchableOpacity
              style={styles.addBtn}
              onPress={() => setShowAddSheet(true)}
              testID="category-add-first"
            >
              <Text style={styles.addBtnTxt}>Add items</Text>
            </TouchableOpacity>
          </View>
        ) : (
          filtered.map((it) => {
            const sL = STATUS_LABELS[it.status] || STATUS_LABELS.available;
            return (
              <TouchableOpacity
                key={it.item_id}
                style={[styles.itemRow, it.status === 'finished' && { opacity: 0.6 }]}
                activeOpacity={0.8}
                onPress={() => router.push(`/item/${it.item_id}`)}
                testID={`item-${it.item_id}`}
              >
                <View style={styles.itemImg}>
                  {it.photo_base64 ? (
                    <Image source={{ uri: it.photo_base64 }} style={styles.itemImgInner} />
                  ) : (
                    <Icon name="Package" size={22} color={colors.textMuted} />
                  )}
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={[styles.itemName, it.status === 'finished' && { textDecorationLine: 'line-through' }]}>
                    {it.name}
                  </Text>
                  <View style={styles.metaRow}>
                    <View style={[styles.pill, { backgroundColor: sL.bg }]}>
                      <Text style={[styles.pillTxt, { color: sL.color }]}>{sL.label}</Text>
                    </View>
                    {it.expiry_date && (
                      <Text style={styles.metaTxt}>
                        Expires {format(new Date(it.expiry_date), 'MMM d')}
                      </Text>
                    )}
                    {typeof it.price === 'number' && it.price > 0 && (
                      <Text style={styles.metaTxt}>${it.price.toFixed(2)}</Text>
                    )}
                  </View>
                </View>
                <TouchableOpacity
                  style={styles.finishBtn}
                  onPress={() => toggleStatus(it, it.status === 'finished' ? 'available' : 'finished')}
                  testID={`item-${it.item_id}-toggle-finish`}
                >
                  <Icon
                    name={it.status === 'finished' ? 'PlusCircle' : 'MinusCircle'}
                    size={24}
                    color={it.status === 'finished' ? colors.primary : colors.textMuted}
                  />
                </TouchableOpacity>
              </TouchableOpacity>
            );
          })
        )}
      </ScrollView>

      <TouchableOpacity
        style={styles.fab}
        onPress={() => setShowAddSheet(true)}
        testID="category-fab-add"
      >
        <Icon name="Plus" color="#fff" size={24} />
      </TouchableOpacity>

      {showAddSheet && (
        <TouchableOpacity
          style={styles.sheetOverlay}
          activeOpacity={1}
          onPress={() => setShowAddSheet(false)}
        >
          <View style={styles.sheet} onStartShouldSetResponder={() => true}>
            <View style={styles.sheetHandle} />
            <Text style={styles.sheetTitle}>Add to {category?.name || 'this category'}</Text>

            <TouchableOpacity
              style={styles.sheetBtn}
              onPress={() => {
                setShowAddSheet(false);
                router.push(`/scan-receipt?category_id=${id}`);
              }}
              testID="category-add-scan"
            >
              <View style={[styles.sheetIcon, { backgroundColor: tints.pink.bg }]}>
                <Icon name="Camera" color={tints.pink.icon} size={22} />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={styles.sheetBtnTitle}>Scan a receipt</Text>
                <Text style={styles.sheetBtnSub}>Upload a whole receipt — AI adds every item at once</Text>
              </View>
              <Icon name="ChevronRight" color={colors.textMuted} size={18} />
            </TouchableOpacity>

            <TouchableOpacity
              style={styles.sheetBtn}
              onPress={() => {
                setShowAddSheet(false);
                router.push(`/item/new?category_id=${id}`);
              }}
              testID="category-add-manual"
            >
              <View style={[styles.sheetIcon, { backgroundColor: tints.mint.bg }]}>
                <Icon name="Plus" color={tints.mint.icon} size={22} />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={styles.sheetBtnTitle}>Add one item</Text>
                <Text style={styles.sheetBtnSub}>Type it in manually with a photo</Text>
              </View>
              <Icon name="ChevronRight" color={colors.textMuted} size={18} />
            </TouchableOpacity>

            <TouchableOpacity
              style={styles.sheetCancel}
              onPress={() => setShowAddSheet(false)}
            >
              <Text style={styles.sheetCancelTxt}>Cancel</Text>
            </TouchableOpacity>
          </View>
        </TouchableOpacity>
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background },
  banner: {
    flexDirection: 'row', alignItems: 'center',
    paddingHorizontal: spacing.md, paddingVertical: spacing.md,
    gap: 10,
    borderBottomLeftRadius: 24, borderBottomRightRadius: 24,
  },
  iconBtn: {
    width: 40, height: 40, borderRadius: 20,
    backgroundColor: '#fff',
    alignItems: 'center', justifyContent: 'center',
  },
  bannerIconWrap: { width: 44, height: 44, borderRadius: 22, alignItems: 'center', justifyContent: 'center' },
  bannerTitle: { flex: 1, fontSize: 22, fontWeight: '900', color: colors.textMain },
  filterRow: { flexDirection: 'row', padding: spacing.md, gap: 8, flexWrap: 'wrap' },
  chip: {
    paddingHorizontal: 14, paddingVertical: 8,
    borderRadius: radius.full,
    backgroundColor: colors.surface,
    ...shadows.card,
  },
  chipActive: { backgroundColor: colors.textMain },
  chipTxt: { fontSize: 12, fontWeight: '700', color: colors.textMuted },
  chipTxtActive: { color: '#fff' },
  scroll: { padding: spacing.md, paddingBottom: 140 },
  card: { backgroundColor: colors.surface, borderRadius: radius.lg, padding: spacing.md, ...shadows.card },
  addBtn: { marginTop: 16, backgroundColor: colors.primary, paddingHorizontal: 20, paddingVertical: 12, borderRadius: radius.full },
  addBtnTxt: { color: '#fff', fontWeight: '700' },
  itemRow: {
    flexDirection: 'row', alignItems: 'center', gap: 12,
    backgroundColor: colors.surface,
    padding: spacing.md,
    borderRadius: radius.md,
    marginBottom: 8,
    ...shadows.card,
  },
  itemImg: {
    width: 52, height: 52, borderRadius: radius.md,
    backgroundColor: colors.surfaceAlt,
    alignItems: 'center', justifyContent: 'center', overflow: 'hidden',
  },
  itemImgInner: { width: '100%', height: '100%' },
  itemName: { fontSize: 15, fontWeight: '700', color: colors.textMain },
  metaRow: { flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 4, flexWrap: 'wrap' },
  pill: { paddingHorizontal: 8, paddingVertical: 3, borderRadius: radius.full },
  pillTxt: { fontSize: 10, fontWeight: '800' },
  metaTxt: { fontSize: 12, color: colors.textMuted },
  finishBtn: { padding: 4 },
  fab: {
    position: 'absolute',
    right: 20, bottom: 110,
    width: 56, height: 56, borderRadius: 28,
    backgroundColor: colors.primary,
    alignItems: 'center', justifyContent: 'center',
    ...shadows.button,
  },
  sheetOverlay: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: 'rgba(0,0,0,0.4)',
    justifyContent: 'flex-end',
  },
  sheet: {
    backgroundColor: colors.surface,
    borderTopLeftRadius: 32, borderTopRightRadius: 32,
    paddingHorizontal: spacing.lg,
    paddingTop: 12,
    paddingBottom: 32,
  },
  sheetHandle: {
    width: 40, height: 4, borderRadius: 2,
    backgroundColor: colors.border,
    alignSelf: 'center',
    marginBottom: 16,
  },
  sheetTitle: {
    fontSize: 18, fontWeight: '800', color: colors.textMain,
    marginBottom: spacing.md,
  },
  sheetBtn: {
    flexDirection: 'row', alignItems: 'center', gap: 14,
    backgroundColor: colors.surfaceAlt,
    padding: spacing.md,
    borderRadius: radius.md,
    marginBottom: 10,
  },
  sheetIcon: {
    width: 44, height: 44, borderRadius: 22,
    alignItems: 'center', justifyContent: 'center',
  },
  sheetBtnTitle: { fontSize: 15, fontWeight: '800', color: colors.textMain },
  sheetBtnSub: { fontSize: 12, color: colors.textMuted, marginTop: 2 },
  sheetCancel: {
    paddingVertical: 14,
    alignItems: 'center',
    marginTop: 8,
  },
  sheetCancelTxt: { color: colors.textMuted, fontWeight: '700' },
});
