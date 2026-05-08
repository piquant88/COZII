import React, { useCallback, useEffect, useState } from 'react';
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity, Switch, Alert, ActivityIndicator, Platform,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter, useFocusEffect } from 'expo-router';
import { api } from '../src/api';
import { useAuth } from '../src/AuthContext';
import { colors, radius, spacing, tints } from '../src/theme';
import { Icon } from '../src/Icon';
import {
  registerForPushAsync, getPushDiagnostics, scheduleLocalTest, routeForNotification,
  type PushDiagnostics,
} from '../src/pushNotifications';

type Prefs = { daily_digest: boolean; important_alerts: boolean };
type Notif = {
  notification_id: string;
  user_id: string;
  space_id: string;
  kind: string;
  title: string;
  body?: string;
  data?: any;
  read: boolean;
  created_at: string;
};

const DEFAULT_PREFS: Prefs = { daily_digest: true, important_alerts: true };

function timeAgo(iso?: string) {
  if (!iso) return '';
  const t = new Date(iso).getTime();
  const diff = Math.max(0, Date.now() - t) / 1000;
  if (diff < 60) return 'just now';
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

function iconForKind(kind?: string): string {
  const k = (kind || '').toLowerCase();
  if (k === 'daily_digest') return 'Sun';
  if (k.startsWith('contract')) return 'FileText';
  if (k.startsWith('task')) return 'Check';
  if (k.startsWith('wage')) return 'Wallet';
  if (k.startsWith('shopping')) return 'ShoppingBag';
  return 'Bell';
}

export default function NotificationsScreen() {
  const router = useRouter();
  const { activeSpace } = useAuth() as any;
  const [tab, setTab] = useState<'feed' | 'settings'>('feed');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [prefs, setPrefs] = useState<Prefs>(DEFAULT_PREFS);
  const [notifs, setNotifs] = useState<Notif[]>([]);
  const [showDiag, setShowDiag] = useState(false);
  const [diag, setDiag] = useState<PushDiagnostics | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const tasks: Promise<any>[] = [
        api.get<Prefs>('/users/notification-prefs'),
      ];
      if (activeSpace?.space_id) {
        tasks.push(api.get<Notif[]>(`/notifications?space_id=${activeSpace.space_id}`));
      } else {
        tasks.push(Promise.resolve([]));
      }
      const [p, n] = await Promise.all(tasks);
      setPrefs({ ...DEFAULT_PREFS, ...(p || {}) });
      setNotifs(Array.isArray(n) ? n : []);
    } catch (e: any) {
      console.warn('load notifications failed', e?.message);
    } finally {
      setLoading(false);
    }
  }, [activeSpace?.space_id]);

  useFocusEffect(useCallback(() => { load(); }, [load]));

  const refreshDiag = useCallback(async () => {
    const d = await getPushDiagnostics();
    setDiag(d);
  }, []);

  useEffect(() => { if (showDiag) refreshDiag(); }, [showDiag, refreshDiag]);

  const update = async (next: Partial<Prefs>) => {
    const merged = { ...prefs, ...next } as Prefs;
    setPrefs(merged); // optimistic
    setSaving(true);
    try {
      const r = await api.put<Prefs>('/users/notification-prefs', next);
      setPrefs({ ...DEFAULT_PREFS, ...(r || {}) });
    } catch (e: any) {
      Alert.alert('Could not save', e?.message || 'Please try again.');
      load();
    } finally {
      setSaving(false);
    }
  };

  const onTapNotif = async (n: Notif) => {
    if (!n.read) {
      try {
        await api.post(`/notifications/${n.notification_id}/read`, {});
        setNotifs((prev) => prev.map((x) => x.notification_id === n.notification_id ? { ...x, read: true } : x));
      } catch {}
    }
    const route = routeForNotification(n.kind, n.data);
    if (route) {
      try { (router as any).push(route); } catch (e) { console.warn('notif tap nav failed', e); }
    }
  };

  const markAllRead = async () => {
    if (!activeSpace?.space_id) return;
    try {
      await api.post(`/notifications/read_all?space_id=${activeSpace.space_id}`, {});
      setNotifs((prev) => prev.map((x) => ({ ...x, read: true })));
    } catch (e: any) {
      Alert.alert('Could not mark all read', e?.message || '');
    }
  };

  const sendTest = async () => {
    setTesting(true);
    try {
      // Try real push first
      const reg = await registerForPushAsync({ force: true });
      let backendSent = false;
      let backendErr = '';
      if (reg.token) {
        try {
          const r = await api.post<{ sent: boolean }>('/users/push-test');
          backendSent = !!r?.sent;
        } catch (e: any) {
          backendErr = e?.message || 'backend error';
        }
      }

      if (backendSent) {
        Alert.alert(
          'Test push sent',
          'A real push went out via Expo. It should arrive in a few seconds. If it does not, check that this device has notification permission in system settings.',
        );
        return;
      }

      // Fallback to a local notification so the user can still verify the
      // foreground handler + tap-to-deep-link path.
      if (Platform.OS !== 'web') {
        try {
          await scheduleLocalTest({
            title: 'Cozii local test notification',
            body: 'Tap me — I should open the shopping list.',
            data: { kind: 'daily_digest', screen: '/shopping-list' },
          });
          const reason = reg.error || backendErr || 'no Expo push token (likely Expo Go without EAS projectId)';
          Alert.alert(
            'Used a LOCAL notification',
            `Real push isn't available (${reason}), so we fired a local one instead. The handler + deep-link should still work — tap the notification to confirm it opens /shopping-list.`,
          );
          return;
        } catch (e: any) {
          Alert.alert('Local notification failed', e?.message || 'Permission denied?');
          return;
        }
      }

      Alert.alert('Mobile only', 'Push notifications are only available on iOS / Android.');
    } catch (e: any) {
      Alert.alert('Test failed', e?.message || 'Could not run the test.');
    } finally {
      setTesting(false);
    }
  };

  if (loading) {
    return (
      <SafeAreaView style={styles.container} edges={['top']}>
        <View style={styles.header}>
          <TouchableOpacity onPress={() => router.back()} style={styles.headerBtn}>
            <Icon name="ChevronLeft" size={22} color={colors.textMain} />
          </TouchableOpacity>
          <Text style={styles.title}>Notifications</Text>
          <View style={styles.headerBtn} />
        </View>
        <View style={styles.loadingWrap}>
          <ActivityIndicator color={colors.primary} />
        </View>
      </SafeAreaView>
    );
  }

  const unread = notifs.filter((n) => !n.read).length;

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.headerBtn} testID="notifications-back">
          <Icon name="ChevronLeft" size={22} color={colors.textMain} />
        </TouchableOpacity>
        <Text style={styles.title}>Notifications</Text>
        <View style={styles.headerBtn} />
      </View>

      {/* Tab toggle */}
      <View style={styles.tabBar}>
        <TouchableOpacity
          style={[styles.tab, tab === 'feed' && styles.tabActive]}
          onPress={() => setTab('feed')}
          testID="tab-feed"
        >
          <Text style={[styles.tabTxt, tab === 'feed' && styles.tabTxtActive]}>
            Inbox{unread ? ` (${unread})` : ''}
          </Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={[styles.tab, tab === 'settings' && styles.tabActive]}
          onPress={() => setTab('settings')}
          testID="tab-settings"
        >
          <Text style={[styles.tabTxt, tab === 'settings' && styles.tabTxtActive]}>Settings</Text>
        </TouchableOpacity>
      </View>

      <ScrollView contentContainerStyle={styles.scroll} showsVerticalScrollIndicator={false}>
        {tab === 'feed' ? (
          <View>
            {notifs.length > 0 && (
              <View style={styles.feedHeader}>
                <Text style={styles.feedHeaderLeft}>{notifs.length} recent</Text>
                {unread > 0 && (
                  <TouchableOpacity onPress={markAllRead}>
                    <Text style={styles.feedHeaderRight}>Mark all read</Text>
                  </TouchableOpacity>
                )}
              </View>
            )}

            {notifs.length === 0 ? (
              <View style={styles.emptyWrap}>
                <View style={styles.emptyIcon}>
                  <Icon name="Bell" size={28} color={colors.textMuted} />
                </View>
                <Text style={styles.emptyTitle}>You{`'`}re all caught up</Text>
                <Text style={styles.emptySub}>New activity from your space will show up here. Tap any notification to jump straight to the relevant screen.</Text>
              </View>
            ) : (
              notifs.map((n) => {
                const route = routeForNotification(n.kind, n.data);
                return (
                  <TouchableOpacity
                    key={n.notification_id}
                    style={[styles.notifRow, !n.read && styles.notifRowUnread]}
                    onPress={() => onTapNotif(n)}
                    testID={`notif-${n.notification_id}`}
                  >
                    <View style={[styles.notifIcon, { backgroundColor: tints.peach.bg }]}>
                      <Icon name={iconForKind(n.kind)} size={16} color={tints.peach.icon} />
                    </View>
                    <View style={{ flex: 1 }}>
                      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                        <Text style={styles.notifTitle} numberOfLines={1}>{n.title}</Text>
                        {!n.read && <View style={styles.unreadDot} />}
                      </View>
                      {n.body ? <Text style={styles.notifBody} numberOfLines={2}>{n.body}</Text> : null}
                      <View style={styles.notifMeta}>
                        <Text style={styles.notifTime}>{timeAgo(n.created_at)}</Text>
                        {route ? <Icon name="ChevronRight" size={14} color={colors.textMuted} /> : null}
                      </View>
                    </View>
                  </TouchableOpacity>
                );
              })
            )}
          </View>
        ) : (
          <View>
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

            <TouchableOpacity onPress={() => setShowDiag((v) => !v)} style={styles.diagToggle} testID="toggle-diagnostics">
              <Icon name="Shield" size={14} color={colors.textMuted} />
              <Text style={styles.diagToggleTxt}>{showDiag ? 'Hide diagnostics' : 'Show diagnostics'}</Text>
            </TouchableOpacity>

            {showDiag && diag && (
              <View style={styles.diagCard}>
                <DiagRow k="Platform" v={diag.platform} />
                <DiagRow k="Real device" v={diag.isDevice ? 'yes' : 'no'} />
                <DiagRow k="Expo Go" v={diag.isExpoGo ? 'yes (push limited)' : 'no'} bad={diag.isExpoGo} />
                <DiagRow k="Permission" v={diag.permission} bad={diag.permission !== 'granted'} />
                <DiagRow k="EAS projectId" v={diag.projectId || '— not configured —'} bad={!diag.projectId} />
                <DiagRow k="Token" v={diag.token ? `${diag.token.slice(0, 28)}…` : '— not registered —'} bad={!diag.token} />
                <Text style={styles.diagFootnote}>
                  {diag.isExpoGo
                    ? 'Expo Go (SDK 53+) no longer supports remote push. To get a real ExpoPushToken you need a development build (`eas build --profile development`) and an EAS projectId in app.json (expo.extra.eas.projectId).'
                    : !diag.projectId
                      ? 'Run `eas init` once and add the printed projectId to app.json under expo.extra.eas.projectId.'
                      : 'All set! Real push should work via Expo Push Service.'}
                </Text>
              </View>
            )}

            <Text style={styles.helper}>
              {`Push notifications work on iOS and Android. On web we use in-app updates instead. If real push isn't available, "Send a test notification" falls back to a LOCAL notification so you can still verify deep linking.`}
            </Text>
          </View>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

function DiagRow({ k, v, bad }: { k: string; v: string; bad?: boolean }) {
  return (
    <View style={styles.diagRow}>
      <Text style={styles.diagK}>{k}</Text>
      <Text style={[styles.diagV, bad && { color: colors.dangerText }]} numberOfLines={2}>{v}</Text>
    </View>
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

  tabBar: { flexDirection: 'row', paddingHorizontal: spacing.md, paddingVertical: spacing.sm, gap: 8 },
  tab: { flex: 1, paddingVertical: 10, borderRadius: radius.md, alignItems: 'center', backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border },
  tabActive: { backgroundColor: colors.primary, borderColor: colors.primary },
  tabTxt: { fontWeight: '700', color: colors.textMain, fontSize: 13 },
  tabTxtActive: { color: '#fff' },

  scroll: { paddingHorizontal: spacing.md, paddingBottom: 48 },

  feedHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingVertical: spacing.sm },
  feedHeaderLeft: { fontSize: 12, color: colors.textMuted, fontWeight: '600' },
  feedHeaderRight: { fontSize: 13, color: colors.primary, fontWeight: '700' },

  notifRow: {
    flexDirection: 'row', gap: 12, paddingVertical: spacing.md, paddingHorizontal: spacing.md,
    backgroundColor: colors.surface, borderRadius: radius.md, marginBottom: 8,
    borderWidth: 1, borderColor: colors.border,
  },
  notifRowUnread: { borderColor: colors.primary, backgroundColor: '#FFF8F5' },
  notifIcon: { width: 36, height: 36, borderRadius: 18, alignItems: 'center', justifyContent: 'center' },
  notifTitle: { flex: 1, fontSize: 14, fontWeight: '700', color: colors.textMain },
  notifBody: { fontSize: 12, color: colors.textMuted, marginTop: 2, lineHeight: 16 },
  notifMeta: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginTop: 4 },
  notifTime: { fontSize: 11, color: colors.textMuted },
  unreadDot: { width: 8, height: 8, borderRadius: 4, backgroundColor: colors.primary },

  emptyWrap: { alignItems: 'center', paddingVertical: spacing.xl * 2 },
  emptyIcon: { width: 64, height: 64, borderRadius: 32, backgroundColor: colors.surfaceAlt, alignItems: 'center', justifyContent: 'center', marginBottom: spacing.md },
  emptyTitle: { fontSize: 16, fontWeight: '800', color: colors.textMain, marginBottom: 4 },
  emptySub: { fontSize: 12, color: colors.textMuted, textAlign: 'center', lineHeight: 17, paddingHorizontal: spacing.lg },

  lede: { fontSize: 13, color: colors.textMuted, lineHeight: 19, marginVertical: spacing.md },
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

  diagToggle: { flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: spacing.md, alignSelf: 'center' },
  diagToggleTxt: { color: colors.textMuted, fontSize: 12, fontWeight: '600' },
  diagCard: {
    backgroundColor: colors.surfaceAlt, borderRadius: radius.md, padding: spacing.md,
    marginTop: spacing.sm, borderWidth: 1, borderColor: colors.border,
  },
  diagRow: { flexDirection: 'row', alignItems: 'flex-start', paddingVertical: 4, gap: 8 },
  diagK: { width: 110, fontSize: 11, color: colors.textMuted, fontWeight: '700', textTransform: 'uppercase' },
  diagV: { flex: 1, fontSize: 12, color: colors.textMain, fontWeight: '600' },
  diagFootnote: { marginTop: spacing.sm, fontSize: 11, color: colors.textMuted, lineHeight: 16 },

  helper: { fontSize: 11, color: colors.textMuted, marginTop: spacing.md, lineHeight: 16, textAlign: 'center' },
});
