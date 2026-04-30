import React from 'react';
import { View, Text, TouchableOpacity, StyleSheet, Platform } from 'react-native';
import { Tabs } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { colors, radius, shadows } from '../../src/theme';
import { Icon } from '../../src/Icon';

function CustomTabBar({ state, navigation }: any) {
  const insets = useSafeAreaInsets();
  const router = useRouter();

  const tabs = [
    { name: 'home', label: 'Home', icon: 'Home' },
    { name: 'inventory', label: 'Inventory', icon: 'Package' },
    { name: 'scan', label: 'Scan', icon: 'Camera', center: true },
    { name: 'finance', label: 'Finance', icon: 'PieChart' },
    { name: 'profile', label: 'Profile', icon: 'User' },
  ];

  return (
    <View
      style={[
        styles.wrap,
        { paddingBottom: Math.max(insets.bottom, 8) },
      ]}
      testID="tab-bar"
    >
      <View style={styles.bar}>
        {tabs.map((t, idx) => {
          const isFocused = state.routes[state.index]?.name === t.name;
          const onPress = () => {
            if (t.name === 'scan') {
              router.push('/item/new');
              return;
            }
            const event = navigation.emit({ type: 'tabPress', target: state.routes.find((r: any) => r.name === t.name)?.key, canPreventDefault: true });
            if (!isFocused && !event.defaultPrevented) {
              navigation.navigate(t.name);
            }
          };
          if (t.center) {
            return (
              <TouchableOpacity
                key={t.name}
                style={styles.centerBtn}
                onPress={onPress}
                activeOpacity={0.85}
                testID={`tab-${t.name}`}
              >
                <Icon name={t.icon} color="#fff" size={24} />
              </TouchableOpacity>
            );
          }
          return (
            <TouchableOpacity
              key={t.name}
              style={styles.tabBtn}
              onPress={onPress}
              activeOpacity={0.7}
              testID={`tab-${t.name}`}
            >
              <Icon name={t.icon} color={isFocused ? colors.textMain : colors.textMuted} size={22} />
              <Text style={[styles.tabLbl, isFocused && { color: colors.textMain, fontWeight: '700' }]}>
                {t.label}
              </Text>
            </TouchableOpacity>
          );
        })}
      </View>
    </View>
  );
}

export default function TabsLayout() {
  return (
    <Tabs
      screenOptions={{ headerShown: false }}
      tabBar={(props) => <CustomTabBar {...props} />}
    >
      <Tabs.Screen name="home" options={{ title: 'Home' }} />
      <Tabs.Screen name="inventory" options={{ title: 'Inventory' }} />
      <Tabs.Screen name="scan" options={{ title: 'Scan' }} />
      <Tabs.Screen name="finance" options={{ title: 'Finance' }} />
      <Tabs.Screen name="profile" options={{ title: 'Profile' }} />
    </Tabs>
  );
}

const styles = StyleSheet.create({
  wrap: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: 0,
    alignItems: 'center',
    paddingHorizontal: 16,
  },
  bar: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-around',
    backgroundColor: 'rgba(255,255,255,0.97)',
    borderRadius: 32,
    paddingVertical: 10,
    paddingHorizontal: 10,
    width: '100%',
    maxWidth: 480,
    borderWidth: 1,
    borderColor: colors.border,
    ...shadows.card,
  },
  tabBtn: { flex: 1, alignItems: 'center', paddingVertical: 6, gap: 2 },
  tabLbl: { fontSize: 10, color: colors.textMuted, fontWeight: '600' },
  centerBtn: {
    width: 56, height: 56, borderRadius: 28,
    backgroundColor: colors.primary,
    alignItems: 'center', justifyContent: 'center',
    marginTop: -22,
    ...shadows.button,
  },
});
