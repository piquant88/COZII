import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { colors } from '../../src/theme';

// Placeholder; tab bar pushes /item/new on press.
export default function ScanTab() {
  return (
    <SafeAreaView style={styles.container}>
      <Text style={{ color: colors.textMuted }}>Scan</Text>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background, alignItems: 'center', justifyContent: 'center' },
});
