import React from 'react';
import { useLocalSearchParams } from 'expo-router';
import ItemEditor from '../../src/ItemEditor';

export default function EditItem() {
  const { id } = useLocalSearchParams<{ id: string }>();
  return <ItemEditor mode="edit" itemId={id} />;
}
