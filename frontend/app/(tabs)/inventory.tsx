import React, { useState, useCallback } from 'react';
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity, RefreshControl, TextInput,
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
  const [itemCounts, setItemCounts] = useState<Record<string, number>>({});
  const [refreshing, setRefreshing] = useState(false);
  const [search, setSearch] = useState('');

  const load = useCallback(async () => {
    if (!activeSpace) return;
    try {
      const [cats, items] = await Promise.all([
        api.get<Category[]>(`/categories?space_id=${activeSpace.space_id}`),
        api.get<Item[]>(`/items?space_id=${activeSpace.space_id}`),
      ]);
      setCategories(cats);
      const counts: Record<string, number> = {};
      items.forEach((it) => {
        if (it.status === 'finished') return;
        counts[it.category_id] = (counts[it.category_id] || 0) + 1;
      });
      setItemCounts(counts);
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

  const filtered = categories.filter((c) => c.name.toLowerCase().includes(search.toLowerCase()));

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
            placeholder="Search categories"
            placeholderTextColor={colors.textMuted}
            value={search}
            onChangeText={setSearch}
            testID="inventory-search"
          />
        </View>

        {filtered.length === 0 ? (
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
        ) : (
          <View style={styles.grid}>
            {filtered.map((c) => {
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
  card: { backgroundColor: colors.surface, borderRadius: radius.lg, padding: spacing.md, ...shadows.card },
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
