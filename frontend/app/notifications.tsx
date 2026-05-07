import React, { useCallback, useEffect, useState } from 'react';
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity, Switch, Alert, ActivityIndicator, Platform,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { api } from '../src/api';
import { colors, radius, spacing } from '../src/theme';
import { Icon } from '../src/Icon';
import { registerForPushAsync } from '../src/pushNotifications';

type Prefs = { daily_digest: boolean; important_alerts: boolean };

const DEFAULT_PREFS: Prefs = { daily_digest: true, important_alerts: true };

export default function NotificationsScreen() {
  const router = useRouter();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [prefs, setPrefs] = useState<Prefs>(DEFAULT_PREFS);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await api.get<Prefs>('/users/notification-prefs');
      setPrefs({ ...DEFAULT_PREFS, ...(r || {}) });
    } catch (e: any) {
      console.warn('load prefs failed', e?.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const update = async (next: Partial<Prefs>) => {
    const merged = { ...prefs, ...next } as Prefs;
    setPrefs(merged); // optimistic
    setSaving(true);
    try {
      const r = await api.put<Prefs>('/users/notification-prefs', next);
      setPrefs({ ...DEFAULT_PREFS, ...(r || {}) });
    } catch (e: any) {
      Alert.alert('Could not save', e?.message || 'Please try again.');
      // revert
      load();
    } finally {
      setSaving(false);
    }
  };

  const sendTest = async () => {
    setTesting(true);
    try {
      // Make sure we have a token first
      await registerForPushAsync().catch(() => null);
      const r = await api.post<{ sent: boolean }>('/users/push-test');
      if (r?.sent) {
        Alert.alert('Test sent', 'You should see the notification arrive shortly. If you don\'t, check that this device has notifications enabled in system settings.');
      } else {
        Alert.alert(
          'Nothing sent',
          Platform.OS === 'web'
            ? 'Push notifications are mobile-only. Open the app on your phone to test.'
            : 'No push token registered yet. Try logging out and back in, or grant notification permission in system settings.',
        );
      }
    } catch (e: any) {
      Alert.alert('Test failed', e?.message || 'Could not reach the server.');
    } finally { setTesting(false); }
  };

  if (loading) {
    return (
      <SafeAreaView style={styles.container} edges={['top']}>
        <View style={styles.loadingWrap}>
          <ActivityIndicator color={colors.primary} />
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.headerBtn} testID="notifications-back">
          <Icon name="ChevronLeft" size={22} color={colors.textMain} />
        </TouchableOpacity>
        <Text style={styles.title}>Notifications</Text>
        <View style={styles.headerBtn} />
      </View>

      <ScrollView contentContainerStyle={styles.scroll} showsVerticalScrollIndicator={false}>
        <Text style={styles.lede}>
          Choose what Cozii sends to your phone. We never send marketing — only the things you ask for.
        </Text>

        <View style={styles.card}>
          <View style={styles.row}>
            <View style={[styles.iconCircle, { backgroundColor: '#FFE4DC' }]}>
              <Icon name="Bell" size={20} color="#D45B43" />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={styles.rowTitle}>Important alerts</Text>
              <Text style={styles.rowSub}>
                Task assignments, payroll, contracts, payments, shopping requests, low-stock alerts.
              </Text>
            </View>
            <Switch
              value={prefs.important_alerts}
              onValueChange={(v) => update({ important_alerts: v })}
              disabled={saving}
              trackColor={{ false: '#D9D2CB', true: colors.primary }}
              thumbColor={'#fff'}
              testID="toggle-important-alerts"
            />
          </View>

          <View style={styles.divider} />

          <View style={styles.row}>
            <View style={[styles.iconCircle, { backgroundColor: '#E8F0FA' }]}>
              <Icon name="Sun" size={20} color="#5079A8" />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={styles.rowTitle}>Daily morning digest</Text>
              <Text style={styles.rowSub}>
                One short summary each morning if any items are low, finished or expiring. Tap it to jump straight to your shopping list.
              </Text>
            </View>
            <Switch
              value={prefs.daily_digest}
              onValueChange={(v) => update({ daily_digest: v })}
              disabled={saving}
              trackColor={{ false: '#D9D2CB', true: colors.primary }}
              thumbColor={'#fff'}
              testID="toggle-daily-digest"
            />
          </View>
        </View>

        <TouchableOpacity
          style={[styles.testBtn, testing && { opacity: 0.6 }]}
          onPress={sendTest}
          disabled={testing}
          testID="send-test-notification"
        >
          {testing ? <ActivityIndicator color="#fff" /> : <Icon name="Send" size={16} color="#fff" />}
          <Text style={styles.testBtnTxt}>{testing ? 'Sending…' : 'Send a test notification'}</Text>
        </TouchableOpacity>

        <Text style={styles.helper}>
          {`Push notifications work on iOS and Android. On web we use in-app updates instead. If nothing arrives, check that Cozii has notification permission in your phone's system settings.`}
        </Text>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background },
  loadingWrap: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  header: {
    flexDirection: 'row', alignItems: 'center',
    paddingHorizontal: spacing.md, paddingVertical: spacing.sm,
    borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.border,
    backgroundColor: colors.background,
  },
  headerBtn: { width: 40, height: 40, alignItems: 'center', justifyContent: 'center' },
  title: { flex: 1, textAlign: 'center', fontSize: 17, fontWeight: '800', color: colors.textMain },
  scroll: { padding: spacing.lg, paddingBottom: 48 },
  lede: { fontSize: 13, color: colors.textMuted, lineHeight: 19, marginBottom: spacing.lg },
  card: {
    backgroundColor: colors.surface, borderRadius: radius.lg,
    paddingHorizontal: spacing.md, paddingVertical: 4,
    borderWidth: 1, borderColor: colors.border,
  },
  row: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: spacing.md },
  iconCircle: { width: 40, height: 40, borderRadius: 20, alignItems: 'center', justifyContent: 'center' },
  rowTitle: { fontSize: 15, fontWeight: '700', color: colors.textMain, marginBottom: 2 },
  rowSub: { fontSize: 12, color: colors.textMuted, lineHeight: 17 },
  divider: { height: 1, backgroundColor: colors.border, marginLeft: 52 },
  testBtn: {
    marginTop: spacing.lg,
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8,
    backgroundColor: colors.primary, borderRadius: radius.md, paddingVertical: 14,
  },
  testBtnTxt: { color: '#fff', fontWeight: '800', fontSize: 14 },
  helper: { fontSize: 11, color: colors.textMuted, marginTop: spacing.md, lineHeight: 16, textAlign: 'center' },
});
