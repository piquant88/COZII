import React, { useState, useCallback } from 'react';
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity, RefreshControl,
  ActivityIndicator, TextInput, Alert, Image,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useFocusEffect, useRouter, useLocalSearchParams } from 'expo-router';
import { useAuth } from '../src/AuthContext';
import { api } from '../src/api';
import { colors, radius, spacing, shadows, tints } from '../src/theme';
import { Icon } from '../src/Icon';
import { formatMoney } from '../src/currency';

const SECTIONS: Array<{ key: 'today' | 'attendance' | 'shopping' | 'wages' | 'handbook' | 'inventory' | 'finance'; label: string; icon: string; tint: keyof typeof tints }> = [
  { key: 'today', label: 'Today', icon: 'Check', tint: 'mint' },
  { key: 'attendance', label: 'Attendance', icon: 'Calendar', tint: 'yellow' },
  { key: 'shopping', label: 'Shopping', icon: 'ShoppingBag', tint: 'pink' },
  { key: 'handbook', label: 'Handbook', icon: 'BookOpen', tint: 'sage' },
  { key: 'wages', label: 'Wages', icon: 'Wallet', tint: 'peach' },
  { key: 'inventory', label: 'Inventory', icon: 'Package', tint: 'lavender' },
  { key: 'finance', label: 'Finance', icon: 'PieChart', tint: 'blue' },
];

const ATT_LABELS: Record<string, string> = { present: 'Present', off: 'Off', sick: 'Sick', leave: 'Leave', late: 'Late' };

export default function StaffHome() {
  const { activeSpace, user, logout } = useAuth();
  const router = useRouter();
  const params = useLocalSearchParams<{ preview?: string }>();
  const previewStaffId = params?.preview || null;
  const isPreview = !!previewStaffId;
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [tab, setTab] = useState<typeof SECTIONS[number]['key']>('today');
  const [newReq, setNewReq] = useState('');
  const [newQty, setNewQty] = useState('');
  const [newPrice, setNewPrice] = useState('');
  const [newPhoto, setNewPhoto] = useState<string | null>(null);
  const [taskPhoto, setTaskPhoto] = useState<{ [taskId: string]: string }>({});
  const [taskNote, setTaskNote] = useState<{ [taskId: string]: string }>({});
  const [notifs, setNotifs] = useState<any[]>([]);
  const [showNotifs, setShowNotifs] = useState(false);
  const [myShop, setMyShop] = useState<any[]>([]);
  const [shopKind, setShopKind] = useState<'request' | 'reimbursement'>('request');
  const [handbook, setHandbook] = useState<any[]>([]);
  const [openHb, setOpenHb] = useState<string | null>(null);
  const [invCats, setInvCats] = useState<any[]>([]);
  const [invItems, setInvItems] = useState<any[]>([]);
  const [openCat, setOpenCat] = useState<string | null>(null);
  const [finReport, setFinReport] = useState<any>(null);

  const load = useCallback(async () => {
    if (!activeSpace) return;
    try {
      if (isPreview) {
        const d = await api.get<any>(`/household/staff/${previewStaffId}/view`);
        setData(d);
        setNotifs([]);
      } else {
        const [d, n] = await Promise.all([
          api.get<any>(`/household/staff/me?space_id=${activeSpace.space_id}`),
          api.get<any[]>(`/notifications?space_id=${activeSpace.space_id}`).catch(() => []),
        ]);
        setData(d);
        setNotifs(n || []);
      }
    } catch (e: any) {
      if (e?.status === 404) {
        Alert.alert(isPreview ? 'Staff not found' : 'Not linked', isPreview ? 'This staff member no longer exists.' : 'You are not registered as staff in this space.');
        router.back();
      }
    } finally { setLoading(false); }
  }, [activeSpace, router, isPreview, previewStaffId]);

  useFocusEffect(useCallback(() => { load(); }, [load]));
  const onRefresh = async () => { setRefreshing(true); await load(); setRefreshing(false); };

  // Lazy fetch when staff opens handbook/inventory/finance tabs (only if permission granted)
  const perms = data?.permissions || {};
  const sid = activeSpace?.space_id;
  React.useEffect(() => {
    if (!sid) return;
    if (tab === 'handbook' && perms.view_handbook && handbook.length === 0) {
      api.get<any[]>(`/household/handbook?space_id=${sid}`).then(setHandbook).catch(() => {});
    }
    if (tab === 'inventory' && perms.view_inventory && invCats.length === 0) {
      Promise.all([
        api.get<any[]>(`/categories?space_id=${sid}`),
        api.get<any[]>(`/items?space_id=${sid}`),
      ]).then(([c, it]) => { setInvCats(c); setInvItems(it); }).catch(() => {});
    }
    if (tab === 'finance' && perms.view_finance && !finReport) {
      const today = new Date();
      api.get<any>(`/reports/household?space_id=${sid}&year=${today.getFullYear()}&month=${today.getMonth() + 1}`).then(setFinReport).catch(() => {});
    }
  }, [tab, sid, perms.view_handbook, perms.view_inventory, perms.view_finance]);

  const toggleTask = async (taskId: string) => {
    if (isPreview) { Alert.alert('Preview mode', 'Actions are disabled. This is how the staff sees it.'); return; }
    const t = (data?.today_tasks || []).find((x: any) => x.task_id === taskId);
    const photo = taskPhoto[taskId];
    const note = taskNote[taskId];
    // If task already done → toggle off is allowed
    if (!t?.completed_today && t?.requires_photo && !photo) {
      Alert.alert('Photo required', 'This task needs a photo as proof. Tap the camera icon below the task first.');
      return;
    }
    try {
      await api.post(`/household/tasks/${taskId}/complete`, {
        date: new Date().toISOString().slice(0, 10),
        photo_base64: photo || null,
        notes: note || null,
      });
      // clear local input for that task
      setTaskPhoto((p) => { const n = { ...p }; delete n[taskId]; return n; });
      setTaskNote((p) => { const n = { ...p }; delete n[taskId]; return n; });
      await load();
    } catch (e: any) { Alert.alert('Error', e?.message || ''); }
  };

  const setMyAttendance = async (status: string) => {
    if (isPreview) { Alert.alert('Preview mode', 'Actions are disabled. This is how the staff sees it.'); return; }
    if (!activeSpace || !data?.staff) return;
    try {
      await api.post('/household/attendance', { space_id: activeSpace.space_id, staff_id: data.staff.staff_id, date: new Date().toISOString().slice(0, 10), status });
      await load();
    } catch (e: any) { Alert.alert('Error', e?.message || ''); }
  };

  const submitRequest = async () => {
    if (isPreview) { Alert.alert('Preview mode', 'Actions are disabled. This is how the staff sees it.'); return; }
    if (!activeSpace || !newReq.trim() || !data?.staff) return;
    try {
      const priceNum = parseFloat(newPrice.replace(/[^0-9.]/g, '')) || null;
      const isReimb = shopKind === 'reimbursement';
      if (isReimb && !priceNum) { Alert.alert('Add the amount', 'For reimbursements please enter what you actually paid.'); return; }
      await api.post('/household/shopping', {
        space_id: activeSpace.space_id,
        item_name: newReq.trim(),
        quantity: newQty || null,
        requested_by_staff_id: data.staff.staff_id,
        urgency: 'normal',
        kind: shopKind,
        estimated_price: !isReimb ? priceNum : null,
        actual_price: isReimb ? priceNum : null,
        photo_base64: newPhoto,
      });
      setNewReq(''); setNewQty(''); setNewPrice(''); setNewPhoto(null);
      Alert.alert(isReimb ? 'Reimbursement requested' : 'Sent', isReimb ? 'Your reimbursement is waiting for owner to mark paid.' : 'Your request is waiting for approval.');
      await load();
    } catch (e: any) { Alert.alert('Error', e?.message || ''); }
  };

  const pickShoppingPhoto = async () => {
    if (isPreview) return;
    try {
      const { launchImageLibraryAsync, MediaTypeOptions } = await import('expo-image-picker');
      const res = await launchImageLibraryAsync({ mediaTypes: MediaTypeOptions.Images, base64: true, quality: 0.5, allowsEditing: false });
      if (!res.canceled && res.assets?.[0]?.base64) {
        setNewPhoto(`data:image/jpeg;base64,${res.assets[0].base64}`);
      }
    } catch (e: any) { Alert.alert('Error', e?.message || 'Could not pick image'); }
  };

  const pickTaskPhoto = async (taskId: string) => {
    if (isPreview) return;
    try {
      const { launchImageLibraryAsync, MediaTypeOptions } = await import('expo-image-picker');
      const res = await launchImageLibraryAsync({ mediaTypes: MediaTypeOptions.Images, base64: true, quality: 0.5, allowsEditing: false });
      if (!res.canceled && res.assets?.[0]?.base64) {
        setTaskPhoto((p) => ({ ...p, [taskId]: `data:image/jpeg;base64,${res.assets[0].base64}` }));
      }
    } catch (e: any) { Alert.alert('Error', e?.message || ''); }
  };

  if (!activeSpace || loading || !data) {
    return (
      <SafeAreaView style={styles.container} edges={['top']}>
        <ActivityIndicator style={{ marginTop: 80 }} color={colors.primary} />
      </SafeAreaView>
    );
  }

  const staff = data.staff;
  const cur = staff.salary_currency || activeSpace.currency || 'USD';
  const today = new Date().toISOString().slice(0, 10);
  const todayAtt = (data.attendance || []).find((a: any) => a.date === today);
  const doneCount = (data.today_tasks || []).filter((t: any) => t.completed_today).length;
  const totalTasks = (data.today_tasks || []).length;
  const totalPaidThisYear = (data.payments || [])
    .filter((p: any) => new Date(p.paid_at).getFullYear() === new Date().getFullYear())
    .reduce((s: number, p: any) => s + p.net, 0);

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <ScrollView
        contentContainerStyle={styles.scroll}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.primary} />}
      >
        {isPreview && (
          <View style={styles.previewBanner} testID="preview-banner">
            <Icon name="User" size={14} color={tints.blue.icon} />
            <Text style={styles.previewTxt}>Previewing as {data.staff.name} · read-only</Text>
            <TouchableOpacity onPress={() => router.back()} style={styles.previewExit} testID="preview-exit">
              <Text style={styles.previewExitTxt}>Exit</Text>
            </TouchableOpacity>
          </View>
        )}
        {/* Greeting header */}
        <View style={styles.greeting}>
          <View style={[styles.avatarBig, { backgroundColor: tints.blue.icon }]}>
            {staff.photo_base64 ? <Image source={{ uri: staff.photo_base64 }} style={styles.avatarImg} /> : <Text style={styles.avatarBigTxt}>{staff.name?.[0]?.toUpperCase()}</Text>}
          </View>
          <View style={{ flex: 1 }}>
            <Text style={styles.hi}>Hi, {staff.name?.split(' ')[0] || 'there'}!</Text>
            <Text style={styles.greetSub}>{staff.role_name || 'Staff'} · {activeSpace.name}</Text>
          </View>
          <TouchableOpacity onPress={() => setShowNotifs((v) => !v)} style={styles.iconBtn} testID="staff-notifs-btn" disabled={isPreview}>
            <Icon name="Heart" size={18} color={isPreview ? colors.textMuted : colors.textMain} />
            {!isPreview && notifs.filter((n) => !n.read).length > 0 && (
              <View style={styles.notifDot}><Text style={styles.notifDotTxt}>{notifs.filter((n) => !n.read).length}</Text></View>
            )}
          </TouchableOpacity>
        </View>

        {/* Notifications */}
        {showNotifs && (
          <View style={styles.notifPanel}>
            <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
              <Text style={styles.sectionTitle}>Notifications</Text>
              {notifs.some((n) => !n.read) && (
                <TouchableOpacity onPress={async () => {
                  try {
                    await api.post(`/notifications/read_all?space_id=${activeSpace.space_id}`, {});
                    await load();
                  } catch {}
                }}>
                  <Text style={styles.readAllTxt}>Mark all read</Text>
                </TouchableOpacity>
              )}
            </View>
            {notifs.length === 0 ? (
              <Text style={styles.emptyTxt}>Nothing new.</Text>
            ) : (
              notifs.slice(0, 8).map((n) => (
                <TouchableOpacity key={n.notification_id} style={[styles.notifRow, !n.read && { backgroundColor: tints.mint.bg }]} onPress={async () => {
                  if (!n.read) {
                    try { await api.post(`/notifications/${n.notification_id}/read`, {}); await load(); } catch {}
                  }
                }}>
                  <View style={[styles.notifIcon, { backgroundColor: tints.peach.icon }]}>
                    <Icon name={n.kind === 'wage_paid' ? 'Wallet' : 'Heart'} size={14} color="#fff" />
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.notifTitle}>{n.title}</Text>
                    {n.body ? <Text style={styles.notifBody} numberOfLines={2}>{n.body}</Text> : null}
                    <Text style={styles.notifTime}>{new Date(n.created_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}</Text>
                  </View>
                  {!n.read && <View style={styles.unreadDot} />}
                </TouchableOpacity>
              ))
            )}
          </View>
        )}

        {/* Section tabs */}
        <View style={{ height: 56 }}>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.tabRow}>
            {SECTIONS.filter((s) => {
              if (s.key === 'shopping' && !perms.request_shopping) return false;
              if (s.key === 'wages' && !perms.view_wage_amount) return false;
              if (s.key === 'attendance' && !perms.log_attendance) return false;
              if (s.key === 'handbook' && !perms.view_handbook) return false;
              if (s.key === 'finance' && !perms.view_finance) return false;
              if (s.key === 'inventory' && !perms.view_inventory) return false;
              return true;
            }).map((s) => {
              const active = tab === s.key;
              const t = tints[s.tint];
              return (
                <TouchableOpacity
                  key={s.key}
                  style={[styles.tabChip, active && { backgroundColor: t.bg, borderColor: t.icon }]}
                  onPress={() => setTab(s.key)}
                  testID={`staff-tab-${s.key}`}
                >
                  <Icon name={s.icon} size={16} color={active ? t.icon : colors.textMuted} />
                  <Text style={[styles.tabTxt, active && { color: t.icon, fontWeight: '800' }]}>{s.label}</Text>
                </TouchableOpacity>
              );
            })}
          </ScrollView>
        </View>

        {tab === 'today' && (
          <View style={{ gap: 8 }}>
            <View style={[styles.hero, { backgroundColor: tints.mint.bg }]}>
              <View>
                <Text style={styles.heroLabel}>Today</Text>
                <Text style={styles.heroAmt}>{doneCount}/{totalTasks} done</Text>
                <Text style={styles.heroSub}>{new Date().toLocaleDateString(undefined, { weekday: 'long', month: 'long', day: 'numeric' })}</Text>
              </View>
              <Icon name="Check" size={40} color={tints.mint.icon} />
            </View>
            {totalTasks === 0 ? (
              <Text style={styles.emptyTxt}>No tasks for today. Enjoy your day!</Text>
            ) : (
              (data.today_tasks || []).map((t: any) => {
                const compAt = t.completion?.completed_at ? new Date(t.completion.completed_at) : null;
                const needsPhoto = !!t.requires_photo;
                const stagedPhoto = taskPhoto[t.task_id];
                const stagedNote = taskNote[t.task_id];
                return (
                <View key={t.task_id} style={[styles.row, { flexDirection: 'column', alignItems: 'stretch', gap: 6 }, t.completed_today && { opacity: 0.85 }]}>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12 }}>
                    <TouchableOpacity style={[styles.checkBox, t.completed_today && styles.checkBoxDone]} onPress={() => toggleTask(t.task_id)} testID={`task-${t.task_id}`}>
                      {t.completed_today && <Icon name="Check" size={14} color="#fff" />}
                    </TouchableOpacity>
                    <View style={{ flex: 1 }}>
                      <Text style={[styles.rowName, t.completed_today && { textDecorationLine: 'line-through' }]} numberOfLines={2}>{t.title}</Text>
                      {t.description ? <Text style={styles.rowSub} numberOfLines={2}>{t.description}</Text> : null}
                      <View style={{ flexDirection: 'row', gap: 6, flexWrap: 'wrap', marginTop: 2 }}>
                        {t.due_time ? <Text style={[styles.rowSub, { fontWeight: '800' }]}>Due {t.due_time}</Text> : null}
                        {needsPhoto && !t.completed_today ? (
                          <Text style={[styles.rowSub, { color: tints.pink.icon, fontWeight: '800' }]}>📷 photo required</Text>
                        ) : null}
                        {compAt ? (
                          <Text style={[styles.rowSub, { color: tints.sage.icon }]}>Done {compAt.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</Text>
                        ) : null}
                      </View>
                    </View>
                  </View>
                  {!t.completed_today && (
                    <View style={{ gap: 6 }}>
                      <View style={{ flexDirection: 'row', gap: 6 }}>
                        <TouchableOpacity style={[styles.miniPhoto, stagedPhoto && { padding: 0, overflow: 'hidden' }]} onPress={() => pickTaskPhoto(t.task_id)} testID={`task-photo-${t.task_id}`}>
                          {stagedPhoto ? (
                            <Image source={{ uri: stagedPhoto }} style={{ width: '100%', height: '100%' }} />
                          ) : (
                            <Icon name="Camera" size={16} color={needsPhoto ? tints.pink.icon : colors.textMuted} />
                          )}
                        </TouchableOpacity>
                        <TextInput
                          style={[styles.input, { flex: 1, minHeight: 40 }]}
                          value={stagedNote || ''}
                          onChangeText={(v) => setTaskNote((p) => ({ ...p, [t.task_id]: v }))}
                          placeholder="Add a note (optional)"
                          placeholderTextColor={colors.textMuted}
                          testID={`task-note-${t.task_id}`}
                        />
                      </View>
                    </View>
                  )}
                  {t.completed_today && t.completion?.photo_base64 && (
                    <Image source={{ uri: t.completion.photo_base64 }} style={styles.doneThumb} />
                  )}
                  {t.completed_today && t.completion?.notes && (
                    <Text style={[styles.rowSub, { fontStyle: 'italic' }]}>"{t.completion.notes}"</Text>
                  )}
                  {t.completed_today && t.completion?.owner_note && (
                    <View style={styles.ownerNote}>
                      <Icon name="MessageSquare" size={12} color={tints.blue.icon} />
                      <Text style={styles.ownerNoteTxt}>{t.completion.owner_note}</Text>
                    </View>
                  )}
                </View>
                );
              })
            )}
          </View>
        )}

        {tab === 'attendance' && (
          <View style={{ gap: 8 }}>
            <View style={[styles.hero, { backgroundColor: tints.yellow.bg }]}>
              <View>
                <Text style={styles.heroLabel}>Today's status</Text>
                <Text style={styles.heroAmt}>{todayAtt ? ATT_LABELS[todayAtt.status] : 'Not set'}</Text>
                <Text style={styles.heroSub}>{new Date().toLocaleDateString()}</Text>
              </View>
              <Icon name="Calendar" size={40} color={tints.yellow.icon} />
            </View>
            <View style={styles.row}>
              <Text style={[styles.rowName, { flex: 1 }]}>Mark today as:</Text>
            </View>
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
              {Object.keys(ATT_LABELS).map((st) => (
                <TouchableOpacity key={st} style={[styles.attBtn, todayAtt?.status === st && styles.attBtnActive]} onPress={() => setMyAttendance(st)} testID={`my-att-${st}`}>
                  <Text style={[styles.attBtnTxt, todayAtt?.status === st && { color: '#fff' }]}>{ATT_LABELS[st]}</Text>
                </TouchableOpacity>
              ))}
            </View>
            <Text style={[styles.sectionTitle, { marginTop: spacing.md }]}>Recent</Text>
            {(data.attendance || []).slice(0, 14).map((a: any) => (
              <View key={a.attendance_id} style={styles.row}>
                <Text style={[styles.rowName, { flex: 1 }]}>{new Date(a.date).toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' })}</Text>
                <Text style={[styles.attTagTxt, { color: a.status === 'present' ? tints.sage.icon : a.status === 'sick' ? tints.pink.icon : tints.lavender.icon }]}>{ATT_LABELS[a.status]}</Text>
              </View>
            ))}
          </View>
        )}

        {tab === 'shopping' && (
          <View style={{ gap: 8 }}>
            <View style={[styles.hero, { backgroundColor: tints.pink.bg }]}>
              <View>
                <Text style={styles.heroLabel}>{shopKind === 'reimbursement' ? 'Already paid out of pocket?' : 'Need something?'}</Text>
                <Text style={styles.heroAmt}>{shopKind === 'reimbursement' ? 'Ask for reimbursement' : 'Send a request'}</Text>
                <Text style={styles.heroSub}>{shopKind === 'reimbursement' ? 'Add the receipt photo + how much you spent.' : 'Add a rough price + photo if you can.'}</Text>
              </View>
              <Icon name="ShoppingBag" size={40} color={tints.pink.icon} />
            </View>
            <View style={{ flexDirection: 'row', gap: 6, marginBottom: 4 }}>
              <TouchableOpacity style={[styles.kindChip, shopKind === 'request' && styles.kindChipActive]} onPress={() => setShopKind('request')} testID="staff-kind-request">
                <Text style={[styles.kindTxt, shopKind === 'request' && styles.kindTxtActive]}>Need to buy</Text>
              </TouchableOpacity>
              <TouchableOpacity style={[styles.kindChip, shopKind === 'reimbursement' && styles.kindChipActive]} onPress={() => setShopKind('reimbursement')} testID="staff-kind-reimb">
                <Text style={[styles.kindTxt, shopKind === 'reimbursement' && styles.kindTxtActive]}>Already bought (reimburse me)</Text>
              </TouchableOpacity>
            </View>
            <Text style={styles.label}>{shopKind === 'reimbursement' ? 'What did you buy?' : "What's running low?"}</Text>
            <TextInput style={styles.input} value={newReq} onChangeText={setNewReq} placeholder="e.g. Rice" placeholderTextColor={colors.textMuted} testID="staff-shop-name" />
            <View style={{ flexDirection: 'row', gap: 8 }}>
              <View style={{ flex: 1 }}>
                <Text style={styles.label}>Quantity</Text>
                <TextInput style={styles.input} value={newQty} onChangeText={setNewQty} placeholder="e.g. 5 kg" placeholderTextColor={colors.textMuted} />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={styles.label}>{shopKind === 'reimbursement' ? `Actual price (${cur})` : `Estimated price (${cur})`}</Text>
                <TextInput style={styles.input} value={newPrice} onChangeText={setNewPrice} placeholder="e.g. 50000" placeholderTextColor={colors.textMuted} keyboardType="numeric" testID="staff-shop-price" />
              </View>
            </View>
            <TouchableOpacity style={styles.photoPick} onPress={pickShoppingPhoto} activeOpacity={0.8} testID="staff-shop-photo">
              {newPhoto ? (
                <Image source={{ uri: newPhoto }} style={styles.photoImg} />
              ) : (
                <View style={{ alignItems: 'center', gap: 4 }}>
                  <Icon name="Camera" size={18} color={colors.primary} />
                  <Text style={styles.photoTxt}>{shopKind === 'reimbursement' ? 'Add receipt photo (optional but recommended)' : 'Add photo (optional)'}</Text>
                </View>
              )}
            </TouchableOpacity>
            {newPhoto && (
              <TouchableOpacity onPress={() => setNewPhoto(null)} style={{ alignSelf: 'center' }}>
                <Text style={{ color: colors.textMuted, fontSize: 11 }}>Remove photo</Text>
              </TouchableOpacity>
            )}
            <TouchableOpacity style={[styles.sendBtn, !newReq.trim() && { opacity: 0.5 }]} onPress={submitRequest} disabled={!newReq.trim()} testID="staff-shop-send">
              <Icon name="ArrowRight" size={16} color="#fff" />
              <Text style={styles.sendTxt}>{shopKind === 'reimbursement' ? 'Submit reimbursement' : 'Send request'}</Text>
            </TouchableOpacity>
          </View>
        )}

        {tab === 'wages' && perms.view_wage_amount && (
          <View style={{ gap: 8 }}>
            <View style={[styles.hero, { backgroundColor: tints.peach.bg }]}>
              <View>
                <Text style={styles.heroLabel}>Salary</Text>
                <Text style={styles.heroAmt}>{staff.salary ? formatMoney(staff.salary, cur) : '—'}</Text>
                <Text style={styles.heroSub}>per {staff.pay_cycle || 'month'}</Text>
              </View>
              <Icon name="Wallet" size={40} color={tints.peach.icon} />
            </View>
            {totalPaidThisYear > 0 && (
              <Text style={styles.sectionTitle}>{formatMoney(totalPaidThisYear, cur)} paid this year</Text>
            )}
            <Text style={[styles.sectionTitle, { marginTop: spacing.md }]}>Payment history</Text>
            {(data.payments || []).length === 0 ? (
              <Text style={styles.emptyTxt}>No payments yet.</Text>
            ) : (
              (data.payments || []).map((p: any) => (
                <View key={p.payment_id} style={[styles.row, { flexDirection: 'column', alignItems: 'stretch' }]}>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12 }}>
                    <View style={{ flex: 1 }}>
                      <Text style={styles.rowName}>{p.period}</Text>
                      <Text style={styles.rowSub}>Paid {new Date(p.paid_at).toLocaleDateString()}</Text>
                    </View>
                    <Text style={styles.rowAmt}>{formatMoney(p.net, p.currency)}</Text>
                  </View>
                  {p.requires_confirmation && !p.confirmed_at && !isPreview && (
                    <TouchableOpacity
                      style={styles.confirmPill}
                      onPress={async () => {
                        try {
                          await api.post(`/household/payroll/${p.payment_id}/confirm`, {});
                          await load();
                        } catch (e: any) { Alert.alert('Error', e?.message || ''); }
                      }}
                      testID={`confirm-pay-${p.payment_id}`}
                    >
                      <Icon name="Check" size={12} color="#fff" />
                      <Text style={styles.confirmPillTxt}>Confirm I received this</Text>
                    </TouchableOpacity>
                  )}
                  {p.confirmed_at && (
                    <View style={styles.pendingPill}>
                      <Icon name="Check" size={12} color={tints.sage.icon} />
                      <Text style={[styles.pendingPillTxt, { color: tints.sage.icon }]}>Confirmed {new Date(p.confirmed_at).toLocaleDateString()}</Text>
                    </View>
                  )}
                  {p.requires_confirmation && !p.confirmed_at && isPreview && (
                    <View style={styles.pendingPill}>
                      <Icon name="X" size={12} color={tints.yellow.icon} />
                      <Text style={styles.pendingPillTxt}>Awaiting staff confirmation</Text>
                    </View>
                  )}
                </View>
              ))
            )}
          </View>
        )}

        {tab === 'handbook' && perms.view_handbook && (
          <View style={{ gap: 8 }}>
            <View style={[styles.hero, { backgroundColor: tints.sage.bg }]}>
              <View>
                <Text style={styles.heroLabel}>How things work here</Text>
                <Text style={styles.heroAmt}>Handbook</Text>
                <Text style={styles.heroSub}>Wifi, emergency contacts, machines & more.</Text>
              </View>
              <Icon name="BookOpen" size={40} color={tints.sage.icon} />
            </View>
            {handbook.length === 0 ? (
              <Text style={styles.emptyTxt}>The owner hasn't added any handbook entries yet.</Text>
            ) : (
              handbook.map((h: any) => {
                const open = openHb === h.entry_id;
                const t = tints[(h.tint as keyof typeof tints) || 'sage'] || tints.sage;
                return (
                  <View key={h.entry_id} style={[styles.row, { flexDirection: 'column', alignItems: 'stretch', padding: 0 }]}>
                    <TouchableOpacity onPress={() => setOpenHb(open ? null : h.entry_id)} activeOpacity={0.8} style={{ flexDirection: 'row', alignItems: 'center', gap: 12, padding: spacing.md }} testID={`hb-${h.entry_id}`}>
                      <View style={[styles.avatar, { backgroundColor: t.icon }]}>
                        <Icon name={h.icon || 'BookOpen'} size={18} color="#fff" />
                      </View>
                      <View style={{ flex: 1 }}>
                        <Text style={styles.rowName}>{h.title}</Text>
                        {h.body ? <Text style={styles.rowSub} numberOfLines={open ? undefined : 1}>{h.body}</Text> : null}
                      </View>
                      <Icon name="ChevronRight" size={16} color={colors.textMuted} />
                    </TouchableOpacity>
                    {open && h.photo_base64 && (
                      <Image source={{ uri: h.photo_base64 }} style={{ width: '100%', height: 220, borderBottomLeftRadius: radius.md, borderBottomRightRadius: radius.md }} resizeMode="cover" />
                    )}
                  </View>
                );
              })
            )}
          </View>
        )}

        {tab === 'inventory' && perms.view_inventory && (
          <View style={{ gap: 8 }}>
            <View style={[styles.hero, { backgroundColor: tints.lavender.bg }]}>
              <View>
                <Text style={styles.heroLabel}>What's in the house</Text>
                <Text style={styles.heroAmt}>{invItems.length} items</Text>
                <Text style={styles.heroSub}>Read-only · {invCats.length} categories</Text>
              </View>
              <Icon name="Package" size={40} color={tints.lavender.icon} />
            </View>
            {invCats.length === 0 ? (
              <Text style={styles.emptyTxt}>No categories yet.</Text>
            ) : (
              invCats.map((c: any) => {
                const t = tints[(c.tint as keyof typeof tints) || 'mint'] || tints.mint;
                const items = invItems.filter((it: any) => it.category_id === c.category_id);
                const open = openCat === c.category_id;
                return (
                  <View key={c.category_id} style={[styles.row, { flexDirection: 'column', alignItems: 'stretch', padding: 0 }]}>
                    <TouchableOpacity onPress={() => setOpenCat(open ? null : c.category_id)} activeOpacity={0.8} style={{ flexDirection: 'row', alignItems: 'center', gap: 12, padding: spacing.md }} testID={`inv-cat-${c.category_id}`}>
                      <View style={[styles.avatar, { backgroundColor: t.icon }]}>
                        <Icon name={c.icon || 'Package'} size={18} color="#fff" />
                      </View>
                      <View style={{ flex: 1 }}>
                        <Text style={styles.rowName}>{c.name}</Text>
                        <Text style={styles.rowSub}>{items.length} items</Text>
                      </View>
                      <Icon name={open ? 'X' : 'ChevronRight'} size={16} color={colors.textMuted} />
                    </TouchableOpacity>
                    {open && (
                      <View style={{ paddingHorizontal: spacing.md, paddingBottom: spacing.md, gap: 6 }}>
                        {items.length === 0 ? (
                          <Text style={styles.emptyTxt}>No items in this category.</Text>
                        ) : (
                          items.map((it: any) => (
                            <View key={it.item_id} style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                              {it.photo_base64 ? (
                                <Image source={{ uri: it.photo_base64 }} style={{ width: 36, height: 36, borderRadius: radius.sm }} />
                              ) : (
                                <View style={[styles.avatar, { backgroundColor: t.icon, width: 36, height: 36 }]}>
                                  <Icon name="Box" size={14} color="#fff" />
                                </View>
                              )}
                              <View style={{ flex: 1 }}>
                                <Text style={[styles.rowName, { fontSize: 13 }]}>{it.name}</Text>
                                <Text style={styles.rowSub}>{[it.quantity && `Qty: ${it.quantity}`, it.location && it.location].filter(Boolean).join(' · ')}</Text>
                              </View>
                              {it.price && perms.view_inventory_prices !== false ? <Text style={styles.rowAmt}>{formatMoney(it.price, activeSpace.currency || 'USD')}</Text> : null}
                            </View>
                          ))
                        )}
                      </View>
                    )}
                  </View>
                );
              })
            )}
          </View>
        )}

        {tab === 'finance' && perms.view_finance && (
          <View style={{ gap: 8 }}>
            <View style={[styles.hero, { backgroundColor: tints.blue.bg }]}>
              <View>
                <Text style={styles.heroLabel}>This month</Text>
                <Text style={styles.heroAmt}>{finReport ? formatMoney(finReport.total_spent || 0, finReport.currency || cur) : '—'}</Text>
                <Text style={styles.heroSub}>{finReport?.month || ''}</Text>
              </View>
              <Icon name="PieChart" size={40} color={tints.blue.icon} />
            </View>
            {!finReport ? (
              <ActivityIndicator color={colors.primary} />
            ) : (finReport.top_categories || []).length === 0 ? (
              <Text style={styles.emptyTxt}>No spending recorded this month.</Text>
            ) : (
              <>
                <Text style={styles.sectionTitle}>Top categories</Text>
                {finReport.top_categories.map((c: any) => {
                  const t = tints[(c.tint as keyof typeof tints) || 'mint'] || tints.mint;
                  const pct = finReport.total_spent ? Math.max(4, Math.round((c.total / finReport.total_spent) * 100)) : 0;
                  return (
                    <View key={c.category_id || c.name} style={styles.row}>
                      <View style={[styles.avatar, { backgroundColor: t.bg, width: 36, height: 36 }]}>
                        <Icon name={c.icon || 'Package'} size={14} color={t.icon} />
                      </View>
                      <View style={{ flex: 1 }}>
                        <View style={{ flexDirection: 'row', alignItems: 'baseline', justifyContent: 'space-between' }}>
                          <Text style={styles.rowName}>{c.name}</Text>
                          <Text style={styles.rowAmt}>{formatMoney(c.total, finReport.currency || cur)}</Text>
                        </View>
                        <View style={{ height: 5, borderRadius: 3, backgroundColor: '#EEE7E2', marginTop: 4, overflow: 'hidden' }}>
                          <View style={{ height: '100%', width: `${pct}%`, backgroundColor: t.icon }} />
                        </View>
                        <Text style={styles.rowSub}>{c.count} {c.count === 1 ? 'item' : 'items'} · {pct}%</Text>
                      </View>
                    </View>
                  );
                })}
              </>
            )}
            <Text style={styles.helperSm}>Read-only view. Owner can edit numbers from their full app.</Text>
          </View>
        )}

        {isPreview ? (
          <TouchableOpacity style={styles.logoutBtn} onPress={() => router.back()} testID="preview-exit-bottom">
            <Icon name="ChevronRight" size={16} color={colors.textMain} />
            <Text style={[styles.logoutTxt, { color: colors.textMain }]}>Exit preview</Text>
          </TouchableOpacity>
        ) : (
          <TouchableOpacity style={styles.logoutBtn} onPress={async () => { await logout(); router.replace('/welcome'); }} testID="staff-logout">
            <Icon name="LogOut" size={16} color={colors.dangerText} />
            <Text style={styles.logoutTxt}>Log out</Text>
          </TouchableOpacity>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background },
  scroll: { padding: spacing.md, paddingBottom: 60 },
  greeting: { flexDirection: 'row', alignItems: 'center', gap: 12, marginBottom: spacing.md },
  avatarBig: { width: 56, height: 56, borderRadius: 20, alignItems: 'center', justifyContent: 'center', overflow: 'hidden' },
  avatarImg: { width: '100%', height: '100%' },
  avatarBigTxt: { color: '#fff', fontSize: 22, fontWeight: '900' },
  hi: { fontSize: 22, fontWeight: '900', color: colors.textMain },
  greetSub: { fontSize: 12, color: colors.textMuted, marginTop: 2 },
  iconBtn: { width: 40, height: 40, borderRadius: 20, backgroundColor: colors.surface, alignItems: 'center', justifyContent: 'center', ...shadows.card },
  notifDot: { position: 'absolute', top: -2, right: -2, minWidth: 18, height: 18, paddingHorizontal: 4, borderRadius: 9, backgroundColor: colors.primary, alignItems: 'center', justifyContent: 'center' },
  notifDotTxt: { fontSize: 10, fontWeight: '900', color: '#fff' },
  notifPanel: { backgroundColor: colors.surface, borderRadius: radius.md, padding: spacing.md, marginBottom: spacing.sm, ...shadows.card },
  readAllTxt: { fontSize: 12, fontWeight: '700', color: colors.primary },
  notifRow: { flexDirection: 'row', alignItems: 'center', gap: 10, padding: 10, borderRadius: radius.sm, marginBottom: 4 },
  notifIcon: { width: 30, height: 30, borderRadius: 10, alignItems: 'center', justifyContent: 'center' },
  notifTitle: { fontSize: 13, fontWeight: '800', color: colors.textMain },
  notifBody: { fontSize: 11, color: colors.textMuted, marginTop: 2 },
  notifTime: { fontSize: 10, color: colors.textMuted, marginTop: 4 },
  unreadDot: { width: 8, height: 8, borderRadius: 4, backgroundColor: colors.primary },
  previewBanner: { flexDirection: 'row', alignItems: 'center', gap: 8, padding: 10, backgroundColor: tints.blue.bg, borderRadius: radius.md, marginBottom: spacing.sm, borderWidth: 1, borderColor: tints.blue.icon },
  previewTxt: { flex: 1, fontSize: 12, fontWeight: '800', color: tints.blue.icon },
  previewExit: { paddingHorizontal: 10, paddingVertical: 4, borderRadius: radius.full, backgroundColor: '#fff' },
  previewExitTxt: { fontSize: 11, fontWeight: '800', color: tints.blue.icon },
  photoPick: { height: 80, borderWidth: 1, borderStyle: 'dashed', borderColor: colors.border, borderRadius: radius.md, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.surfaceAlt, overflow: 'hidden' },
  photoImg: { width: '100%', height: '100%' },
  photoTxt: { fontSize: 12, color: colors.primary, fontWeight: '700' },
  miniPhoto: { width: 40, height: 40, borderRadius: radius.sm, backgroundColor: colors.surfaceAlt, alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: colors.border },
  doneThumb: { width: 120, height: 80, borderRadius: radius.sm, marginTop: 6 },
  ownerNote: { flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: tints.blue.bg, padding: 8, borderRadius: radius.sm, marginTop: 4 },
  ownerNoteTxt: { flex: 1, fontSize: 12, color: tints.blue.icon, fontWeight: '600' },
  helperSm: { fontSize: 11, color: colors.textMuted, fontStyle: 'italic', textAlign: 'center', marginTop: spacing.sm },
  kindChip: { flex: 1, paddingHorizontal: 10, paddingVertical: 8, borderRadius: radius.full, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, alignItems: 'center' },
  kindChipActive: { backgroundColor: colors.textMain, borderColor: colors.textMain },
  kindTxt: { fontSize: 11, fontWeight: '700', color: colors.textMain },
  kindTxtActive: { color: '#fff' },
  confirmPill: { flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 12, paddingVertical: 8, borderRadius: radius.full, backgroundColor: tints.sage.icon, alignSelf: 'flex-start', marginTop: 6 },
  confirmPillTxt: { color: '#fff', fontSize: 11, fontWeight: '800' },
  pendingPill: { flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 12, paddingVertical: 8, borderRadius: radius.full, backgroundColor: tints.yellow.bg, alignSelf: 'flex-start', marginTop: 6 },
  pendingPillTxt: { color: tints.yellow.icon, fontSize: 11, fontWeight: '800' },
  tabRow: { gap: 8, paddingVertical: 8 },
  tabChip: { flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 14, paddingVertical: 8, borderRadius: radius.full, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border },
  tabTxt: { fontSize: 12, fontWeight: '700', color: colors.textMuted },
  hero: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', padding: spacing.lg, borderRadius: radius.lg, marginBottom: spacing.sm },
  heroLabel: { fontSize: 12, color: colors.textMuted, fontWeight: '700' },
  heroAmt: { fontSize: 26, fontWeight: '900', color: colors.textMain, marginTop: 4, letterSpacing: -0.5 },
  heroSub: { fontSize: 12, color: colors.textMuted, marginTop: 4 },
  row: { flexDirection: 'row', alignItems: 'center', gap: 12, backgroundColor: colors.surface, padding: spacing.md, borderRadius: radius.md, ...shadows.card },
  rowName: { fontSize: 14, fontWeight: '700', color: colors.textMain },
  rowSub: { fontSize: 11, color: colors.textMuted, marginTop: 2 },
  rowAmt: { fontSize: 14, fontWeight: '800', color: colors.textMain },
  sectionTitle: { fontSize: 12, fontWeight: '800', color: colors.textMuted, textTransform: 'uppercase', letterSpacing: 0.5 },
  emptyTxt: { fontSize: 13, color: colors.textMuted, fontStyle: 'italic', textAlign: 'center', padding: spacing.md },
  checkBox: { width: 28, height: 28, borderRadius: 8, borderWidth: 2, borderColor: colors.border, alignItems: 'center', justifyContent: 'center' },
  checkBoxDone: { backgroundColor: colors.primary, borderColor: colors.primary },
  attBtn: { flex: 1, minWidth: 80, paddingVertical: 12, borderRadius: radius.md, alignItems: 'center', backgroundColor: colors.surfaceAlt },
  attBtnActive: { backgroundColor: colors.primary },
  attBtnTxt: { fontSize: 12, fontWeight: '800', color: colors.textMain },
  attTagTxt: { fontSize: 12, fontWeight: '800' },
  label: { fontSize: 11, fontWeight: '800', color: colors.textMuted, textTransform: 'uppercase', letterSpacing: 0.5, marginTop: 4 },
  input: { backgroundColor: colors.surface, borderRadius: radius.md, paddingHorizontal: spacing.md, paddingVertical: 12, fontSize: 15, color: colors.textMain, ...shadows.card },
  sendBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, backgroundColor: colors.primary, paddingVertical: 14, borderRadius: radius.full, marginTop: spacing.sm, ...shadows.button },
  sendTxt: { color: '#fff', fontWeight: '800', fontSize: 14 },
  logoutBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, padding: spacing.md, marginTop: spacing.xl, backgroundColor: colors.surface, borderRadius: radius.full, ...shadows.card },
  logoutTxt: { color: colors.dangerText, fontWeight: '700' },
});
