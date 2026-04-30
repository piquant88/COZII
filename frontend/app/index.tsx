import React, { useEffect } from 'react';
import { View, ActivityIndicator, StyleSheet } from 'react-native';
import { useRouter } from 'expo-router';
import { useAuth } from '../src/AuthContext';
import { colors } from '../src/theme';

export default function Index() {
  const { user, loading, activeSpace } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (loading) return;
    if (!user) {
      router.replace('/welcome');
    } else if (!activeSpace) {
      router.replace('/space-setup');
    } else {
      router.replace('/(tabs)/home');
    }
  }, [user, loading, activeSpace]);

  return (
    <View style={styles.container} testID="splash-screen">
      <ActivityIndicator color={colors.primary} size="large" />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.background,
  },
});
