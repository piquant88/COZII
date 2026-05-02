import React, { useEffect } from 'react';
import { View, ActivityIndicator, StyleSheet } from 'react-native';
import { useRouter } from 'expo-router';
import { useAuth } from '../src/AuthContext';
import { colors } from '../src/theme';

export default function Index() {
  const { user, loading, activeSpace, spaceRole } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (loading) return;
    if (!user) {
      router.replace('/welcome');
    } else if (!activeSpace) {
      router.replace('/space-setup');
    } else if (spaceRole?.role === 'staff') {
      router.replace('/staff-home');
    } else if (spaceRole) {
      router.replace('/(tabs)/home');
    }
    // if spaceRole is still null, wait for it to load (short)
  }, [user, loading, activeSpace, spaceRole]);

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
