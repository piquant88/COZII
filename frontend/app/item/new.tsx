import React from 'react';
import { useLocalSearchParams } from 'expo-router';
import ItemEditor from '../../src/ItemEditor';

export default function NewItem() {
  const { category_id } = useLocalSearchParams<{ category_id?: string }>();
  return <ItemEditor mode="create" preselectCategoryId={category_id} />;
}
