import React, { useState, useCallback } from 'react';
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity, RefreshControl, TextInput, Image,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter, useFocusEffect } from 'expo-router';
import { useAuth } from '../../src/AuthContext';
import { colors, radius, spacing, shadows, tints } from '../../src/theme';
import { Icon } from '../../src/Icon';
import { api } from '../../src/api';
import type { Category, Item } from '../../src/types';

export default function Inventory() {
  const { activeSpace } = useAuth();
  const router = useRouter();
  const [categories, setCategories] = useState<Category[]>([]);
  const [items, setItems] = useState<Item[]>([]);
  const [refreshing, setRefreshing] = useState(false);
  const [search, setSearch] = useState('');

  const load = useCallback(async () => {
    if (!activeSpace) return;
    try {
      const [cats, its] = await Promise.all([
        api.get<Category[]>(`/categories?space_id=${activeSpace.space_id}`),
        api.get<Item[]>(`/items?space_id=${activeSpace.space_id}`),
      ]);
      setCategories(cats);
      setItems(its);
    } catch (e) { console.warn(e); }
  }, [activeSpace]);

  useFocusEffect(useCallback(() => {
    load();
    const id = setInterval(load, 10000);
    return () => clearInterval(id);
  }, [load]));

  const onRefresh = async () => {
    setRefreshing(true);
    await load();
    setRefreshing(false);
  };

  const itemCounts: Record<string, number> = {};
  items.forEach((it) => {
    if (it.status === 'finished') return;
    itemCounts[it.category_id] = (itemCounts[it.category_id] || 0) + 1;
  });

  const q = search.trim().toLowerCase();
  const filteredCategories = q
    ? categories.filter((c) => c.name.toLowerCase().includes(q))
    : categories;

  const matchedItems = q
    ? items
        .filter((it) => {
          const inName = it.name.toLowerCase().includes(q);
          const inFields = Object.values(it.fields || {}).some((v) => String(v).toLowerCase().includes(q));
          const inNotes = (it.notes || '').toLowerCase().includes(q);
          return inName || inFields || inNotes;
        })
        .slice(0, 30)
    : [];

  const catName = (id: string) => categories.find((c) => c.category_id === id)?.name || 'Uncategorized';
  const catTint = (id: string) => categories.find((c) => c.category_id === id)?.tint || 'mint';
  const catIcon = (id: string) => categories.find((c) => c.category_id === id)?.icon || 'Box';

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <ScrollView
        contentContainerStyle={styles.scroll}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.primary} />}
        showsVerticalScrollIndicator={false}
      >
        <View style={styles.headerRow}>
          <Text style={styles.title}>Inventory</Text>
          <TouchableOpacity
            style={styles.addBtn}
            onPress={() => router.push('/category/new')}
            testID="inventory-add-category"
          >
            <Icon name="Plus" color="#fff" size={18} />
          </TouchableOpacity>
        </View>

        <View style={styles.searchBox}>
          <Icon name="Search" size={18} color={colors.textMuted} />
          <TextInput
            style={styles.searchInput}
            placeholder="Search items or categories"
            placeholderTextColor={colors.textMuted}
            value={search}
            onChangeText={setSearch}
            testID="inventory-search"
          />
          {!!q && (
            <TouchableOpacity onPress={() => setSearch('')}>
              <Icon name="X" size={16} color={colors.textMuted} />
            </TouchableOpacity>
          )}
        </View>

        {/* Item search results */}
        {q !== '' && (
          <>
            <Text style={styles.sectionTitle}>
              Items ({matchedItems.length})
            </Text>
            {matchedItems.length === 0 ? (
              <View style={[styles.emptyCard]}>
                <Text style={{ color: colors.textMuted, fontSize: 13 }}>No items match "{q}"</Text>
              </View>
            ) : (
              matchedItems.map((it) => {
                const tint = tints[catTint(it.category_id)] || tints.mint;
                return (
                  <TouchableOpacity
                    key={it.item_id}
                    style={styles.itemRow}
                    onPress={() => router.push(`/item/${it.item_id}`)}
                    activeOpacity={0.8}
                    testID={`search-item-${it.item_id}`}
                  >
                    <View style={[styles.itemThumb, { backgroundColor: tint.bg }]}>
                      {(it.image_url || it.photo_base64) ? (
                        <Image source={{ uri: it.image_url || it.photo_base64 }} style={styles.itemThumbImg} />
                      ) : (
                        <Icon name={catIcon(it.category_id)} color={tint.icon} size={20} />
                      )}
                    </View>
                    <View style={{ flex: 1 }}>
                      <Text style={[styles.itemName, it.status === 'finished' && { textDecorationLine: 'line-through', color: colors.textMuted }]}>
                        {it.name}
                      </Text>
                      <Text style={styles.itemSub}>
                        {catName(it.category_id)}
                        {it.status === 'low' ? '  •  Low' : it.status === 'finished' ? '  •  Finished' : ''}
                        {typeof it.price === 'number' && it.price > 0 ? `  •  $${it.price.toFixed(2)}` : ''}
                      </Text>
                    </View>
                    <Icon name="ChevronRight" size={16} color={colors.textMuted} />
                  </TouchableOpacity>
                );
              })
            )}
            <Text style={[styles.sectionTitle, { marginTop: spacing.md }]}>
              Categories ({filteredCategories.length})
            </Text>
          </>
        )}

        {filteredCategories.length === 0 && q === '' ? (
          <View style={[styles.card, { alignItems: 'center', paddingVertical: 40 }]}>
            <Icon name="Package" color={colors.textMuted} size={32} />
            <Text style={{ color: colors.textMuted, marginTop: 12, textAlign: 'center' }}>
              No categories found.
            </Text>
            <TouchableOpacity
              style={styles.emptyBtn}
              onPress={() => router.push('/category/new')}
            >
              <Text style={styles.emptyBtnTxt}>Create your first category</Text>
            </TouchableOpacity>
          </View>
        ) : filteredCategories.length === 0 ? (
          <View style={[styles.emptyCard]}>
            <Text style={{ color: colors.textMuted, fontSize: 13 }}>No categories match "{q}"</Text>
          </View>
        ) : (
          <View style={styles.grid}>
            {filteredCategories.map((c) => {
              const tint = tints[c.tint] || tints.mint;
              return (
                <TouchableOpacity
                  key={c.category_id}
                  style={[styles.categoryCard, { backgroundColor: tint.bg }]}
                  activeOpacity={0.85}
                  onPress={() => router.push(`/category/${c.category_id}`)}
                  testID={`category-${c.category_id}`}
                >
                  <View style={[styles.iconWrap, { backgroundColor: '#fff' }]}>
                    <Icon name={c.icon} color={tint.icon} size={22} />
                  </View>
                  <Text style={styles.categoryName} numberOfLines={1}>{c.name}</Text>
                  <Text style={styles.categoryCount}>
                    {itemCounts[c.category_id] || 0} {(itemCounts[c.category_id] || 0) === 1 ? 'item' : 'items'}
                  </Text>
                </TouchableOpacity>
              );
            })}
          </View>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background },
  scroll: { padding: spacing.lg, paddingBottom: 140 },
  headerRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: spacing.lg },
  title: { fontSize: 30, fontWeight: '900', color: colors.textMain, letterSpacing: -0.5 },
  addBtn: {
    width: 44, height: 44, borderRadius: 22,
    backgroundColor: colors.primary,
    alignItems: 'center', justifyContent: 'center',
    ...shadows.button,
  },
  searchBox: {
    flexDirection: 'row', alignItems: 'center', gap: 10,
    backgroundColor: colors.surface,
    borderRadius: radius.full,
    paddingHorizontal: spacing.md,
    paddingVertical: 12,
    marginBottom: spacing.md,
    ...shadows.card,
  },
  searchInput: { flex: 1, fontSize: 14, color: colors.textMain },
  sectionTitle: { fontSize: 13, fontWeight: '800', color: colors.textMuted, marginBottom: 8, textTransform: 'uppercase', letterSpacing: 0.5 },
  itemRow: {
    flexDirection: 'row', alignItems: 'center', gap: 12,
    backgroundColor: colors.surface,
    padding: spacing.md,
    borderRadius: radius.md,
    marginBottom: 8,
    ...shadows.card,
  },
  itemThumb: {
    width: 44, height: 44, borderRadius: radius.md,
    alignItems: 'center', justifyContent: 'center', overflow: 'hidden',
  },
  itemThumbImg: { width: '100%', height: '100%' },
  itemName: { fontSize: 14, fontWeight: '700', color: colors.textMain },
  itemSub: { fontSize: 12, color: colors.textMuted, marginTop: 2 },
  card: { backgroundColor: colors.surface, borderRadius: radius.lg, padding: spacing.md, ...shadows.card },
  emptyCard: {
    backgroundColor: colors.surface,
    padding: spacing.md,
    borderRadius: radius.md,
    alignItems: 'center',
    marginBottom: spacing.md,
    ...shadows.card,
  },
  emptyBtn: {
    marginTop: 16,
    backgroundColor: colors.primary,
    paddingHorizontal: 20, paddingVertical: 12,
    borderRadius: radius.full,
  },
  emptyBtnTxt: { color: '#fff', fontWeight: '700' },
  grid: {
    flexDirection: 'row', flexWrap: 'wrap',
    gap: spacing.sm,
  },
  categoryCard: {
    flexBasis: '48%',
    flexGrow: 1,
    minHeight: 140,
    padding: spacing.md,
    borderRadius: radius.lg,
    justifyContent: 'space-between',
  },
  iconWrap: {
    width: 42, height: 42, borderRadius: 21,
    alignItems: 'center', justifyContent: 'center',
  },
  categoryName: { fontSize: 16, fontWeight: '800', color: colors.textMain, marginTop: 20 },
  categoryCount: { fontSize: 12, color: colors.textMuted, fontWeight: '600', marginTop: 2 },
});
