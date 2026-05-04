import React, { useState, useCallback, useEffect } from 'react';
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity, RefreshControl,
  ActivityIndicator, Modal, KeyboardAvoidingView, Platform, TextInput, Alert, Image,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useFocusEffect, useRouter } from 'expo-router';
import * as ImagePicker from 'expo-image-picker';
import { useAuth } from '../../src/AuthContext';
import { api } from '../../src/api';
import { colors, radius, spacing, shadows, tints } from '../../src/theme';
import { Icon } from '../../src/Icon';
import { formatMoney, getCurrency } from '../../src/currency';
import type { HouseholdRole, FamilyMember, StaffMember, HandbookEntry, TaskTemplate, AttendanceLog, ShoppingReq } from '../../src/types';

const SECTIONS = [
  { key: 'people', label: 'People', icon: 'Users', tint: 'peach' },
  { key: 'staff', label: 'Staff', icon: 'User', tint: 'blue' },
  { key: 'tasks', label: 'Tasks', icon: 'Check', tint: 'mint' },
  { key: 'attendance', label: 'Attendance', icon: 'Calendar', tint: 'yellow' },
  { key: 'shopping', label: 'Shopping', icon: 'ShoppingBag', tint: 'pink' },
  { key: 'roles', label: 'Roles', icon: 'Tag', tint: 'lavender' },
  { key: 'handbook', label: 'Handbook', icon: 'BookOpen', tint: 'sage' },
] as const;

const ROLE_ICON_OPTIONS = ['User', 'Heart', 'Star', 'Apple', 'Sparkles', 'Refrigerator', 'Droplet', 'Lock', 'BookOpen', 'ShoppingBag', 'Tag', 'Camera', 'ArrowRight'];
const TINT_OPTIONS: Array<keyof typeof tints> = ['peach', 'sage', 'lavender', 'mint', 'blue', 'pink', 'yellow'];
const HANDBOOK_TEMPLATES = [
  { title: 'Wifi', body: 'Network: \nPassword: ', icon: 'Star' },
  { title: 'Emergency contacts', body: 'Police: 911\nDoctor: \nNeighbor: ', icon: 'Heart' },
  { title: 'Doctor & medical', body: 'Family doctor: \nClinic: \nInsurance: ', icon: 'Heart' },
  { title: 'Kid pickup info', body: 'School: \nPickup time: \nAfter-school: ', icon: 'Apple' },
  { title: 'Gas & water shutoff', body: 'Gas valve location: \nWater main: ', icon: 'Droplet' },
];

export default function HouseholdHub() {
  const router = useRouter();
  const { activeSpace } = useAuth();
  const [section, setSection] = useState<typeof SECTIONS[number]['key']>('people');
  const [refreshing, setRefreshing] = useState(false);
  const [loading, setLoading] = useState(true);

  const [roles, setRoles] = useState<HouseholdRole[]>([]);
  const [people, setPeople] = useState<FamilyMember[]>([]);
  const [staff, setStaff] = useState<StaffMember[]>([]);
  const [handbook, setHandbook] = useState<HandbookEntry[]>([]);
  const [tasks, setTasks] = useState<TaskTemplate[]>([]);
  const [taskDate, setTaskDate] = useState<string>(() => new Date().toISOString().slice(0, 10));
  const [attendance, setAttendance] = useState<AttendanceLog[]>([]);
  const [attendanceDate, setAttendanceDate] = useState<string>(() => new Date().toISOString().slice(0, 10));
  const [shopping, setShopping] = useState<ShoppingReq[]>([]);
  const [categoriesList, setCategoriesList] = useState<any[]>([]);

  // modal state — generic dispatch
  const [edit, setEdit] = useState<{ kind: 'people' | 'staff' | 'role' | 'handbook' | 'task' | 'shopping'; data?: any } | null>(null);

  const load = useCallback(async () => {
    if (!activeSpace) return;
    try {
      const [r, p, s, h, tRes, att, shop, cats] = await Promise.all([
        api.get<HouseholdRole[]>(`/household/roles?space_id=${activeSpace.space_id}`),
        api.get<FamilyMember[]>(`/household/family?space_id=${activeSpace.space_id}`),
        api.get<StaffMember[]>(`/household/staff?space_id=${activeSpace.space_id}`),
        api.get<HandbookEntry[]>(`/household/handbook?space_id=${activeSpace.space_id}`),
        api.get<{ date: string; tasks: TaskTemplate[] }>(`/household/tasks?space_id=${activeSpace.space_id}&date=${taskDate}`),
        api.get<AttendanceLog[]>(`/household/attendance?space_id=${activeSpace.space_id}&date_from=${attendanceDate}&date_to=${attendanceDate}`),
        api.get<ShoppingReq[]>(`/household/shopping?space_id=${activeSpace.space_id}`),
        api.get<any[]>(`/categories?space_id=${activeSpace.space_id}`),
      ]);
      setRoles(r); setPeople(p); setStaff(s); setHandbook(h);
      setTasks(tRes.tasks || []); setAttendance(att); setShopping(shop); setCategoriesList(cats);
    } catch (e) { console.warn(e); }
    finally { setLoading(false); }
  }, [activeSpace, taskDate, attendanceDate]);

  useFocusEffect(useCallback(() => { load(); }, [load]));
  const onRefresh = async () => { setRefreshing(true); await load(); setRefreshing(false); };

  if (!activeSpace) {
    return (
      <SafeAreaView style={styles.container} edges={['top']}>
        <Text style={{ padding: 24 }}>Pick or create a space first.</Text>
      </SafeAreaView>
    );
  }
  const isHousehold = activeSpace.space_type === 'household';

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <View style={styles.header}>
        <View style={{ flex: 1 }}>
          <Text style={styles.kicker}>{activeSpace.name}</Text>
          <Text style={styles.title}>Household</Text>
        </View>
        {isHousehold && (
          <TouchableOpacity
            style={styles.iconBtn}
            onPress={() => router.push('/contracts')}
            testID="open-contracts"
          >
            <Icon name="FileText" color={colors.textMain} />
          </TouchableOpacity>
        )}
        {isHousehold && (
          <TouchableOpacity
            style={styles.iconBtn}
            onPress={() => router.push('/household-report')}
            testID="household-report"
          >
            <Icon name="PieChart" color={colors.textMain} />
          </TouchableOpacity>
        )}
        <TouchableOpacity
          style={styles.iconBtn}
          onPress={() => {
            if (section === 'people') setEdit({ kind: 'people' });
            else if (section === 'staff') setEdit({ kind: 'staff' });
            else if (section === 'roles') setEdit({ kind: 'role' });
            else if (section === 'handbook') setEdit({ kind: 'handbook' });
            else if (section === 'tasks') setEdit({ kind: 'task' });
            else if (section === 'shopping') setEdit({ kind: 'shopping' });
          }}
          testID="household-add"
        >
          <Icon name="Plus" color={colors.textMain} />
        </TouchableOpacity>
      </View>

      {!isHousehold && (
        <View style={[styles.banner, { backgroundColor: tints.yellow.bg }]}>
          <Icon name="Sparkles" size={16} color={tints.yellow.icon} />
          <Text style={styles.bannerTxt}>This space is set as Roommates. Switch to Household in Profile to enable household management.</Text>
        </View>
      )}

      {/* Section tabs */}
      <View style={{ height: 56 }}>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.tabRow}>
          {SECTIONS.map((s) => {
            const active = section === s.key;
            const t = tints[s.tint];
            let badge = 0;
            if (s.key === 'shopping') badge = (shopping || []).filter((r: any) => r.status === 'pending').length;
            if (s.key === 'tasks') {
              badge = (tasks || []).filter((x: any) => x.active !== false && !x.completed_today).length;
            }
            return (
              <TouchableOpacity
                key={s.key}
                style={[styles.tabChip, active && { backgroundColor: t.bg, borderColor: t.icon }]}
                onPress={() => setSection(s.key)}
                testID={`household-tab-${s.key}`}
              >
                <Icon name={s.icon} size={16} color={active ? t.icon : colors.textMuted} />
                <Text style={[styles.tabTxt, active && { color: t.icon, fontWeight: '800' }]}>{s.label}</Text>
                {badge > 0 && (
                  <View style={styles.chipBadge}>
                    <Text style={styles.chipBadgeTxt}>{badge > 9 ? '9+' : badge}</Text>
                  </View>
                )}
              </TouchableOpacity>
            );
          })}
        </ScrollView>
      </View>

      <ScrollView
        contentContainerStyle={styles.scroll}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.primary} />}
      >
        {loading ? (
          <ActivityIndicator color={colors.primary} style={{ marginTop: 60 }} />
        ) : section === 'people' ? (
          <PeopleSection people={people} roles={roles.filter((r) => r.category === 'family')} onEdit={(p) => setEdit({ kind: 'people', data: p })} />
        ) : section === 'staff' ? (
          <StaffSection staff={staff} roles={roles.filter((r) => r.category === 'staff')} currency={activeSpace.currency || 'USD'} spaceId={activeSpace.space_id} onEdit={(s) => setEdit({ kind: 'staff', data: s })} onRefresh={load} />
        ) : section === 'tasks' ? (
          <TasksSection
            tasks={tasks} date={taskDate} setDate={setTaskDate}
            onEdit={(t) => setEdit({ kind: 'task', data: t })}
            onToggle={async (t) => {
              try { await api.post(`/household/tasks/${t.task_id}/complete`, { date: taskDate }); await load(); }
              catch (e: any) { Alert.alert('Error', e?.message || ''); }
            }}
          />
        ) : section === 'attendance' ? (
          <AttendanceSection
            staff={staff} attendance={attendance} date={attendanceDate} setDate={setAttendanceDate}
            onSet={async (staffId, status) => {
              try {
                await api.post('/household/attendance', { space_id: activeSpace.space_id, staff_id: staffId, date: attendanceDate, status });
                await load();
              } catch (e: any) { Alert.alert('Error', e?.message || ''); }
            }}
          />
        ) : section === 'shopping' ? (
          <ShoppingSection
            requests={shopping}
            currency={activeSpace.currency || 'USD'}
            onEdit={(r) => setEdit({ kind: 'shopping', data: r })}
            onStatus={async (r, status) => {
              try {
                if (status === 'rejected') {
                  // Prompt for a reason (simple one-line via Alert prompt)
                  Alert.prompt?.('Reject reason', 'Why are you rejecting this? (optional)', async (reason?: string) => {
                    try {
                      await api.patch(`/household/shopping/${r.request_id}`, { status: 'rejected', rejected_reason: reason || '' });
                      await load();
                    } catch (e: any) { Alert.alert('Error', e?.message || ''); }
                  });
                  // Fallback (Android/web): just set rejected without reason
                  if (!Alert.prompt) {
                    await api.patch(`/household/shopping/${r.request_id}`, { status: 'rejected' });
                    await load();
                  }
                  return;
                }
                if (status === 'purchased') {
                  Alert.prompt?.('Actual price?', `How much did you pay for ${r.item_name}? (optional)`, async (priceStr?: string) => {
                    const p = parseFloat((priceStr || '').replace(/[^0-9.]/g, '')) || null;
                    try {
                      await api.post(`/household/shopping/${r.request_id}/purchase`, { actual_price: p });
                      await load();
                    } catch (e: any) { Alert.alert('Error', e?.message || ''); }
                  });
                  if (!Alert.prompt) {
                    await api.post(`/household/shopping/${r.request_id}/purchase`, {});
                    await load();
                  }
                  return;
                }
                await api.patch(`/household/shopping/${r.request_id}`, { status });
                await load();
              }
              catch (e: any) { Alert.alert('Error', e?.message || ''); }
            }}
          />
        ) : section === 'roles' ? (
          <RolesSection roles={roles} onEdit={(r) => setEdit({ kind: 'role', data: r })} onDelete={async (r) => {
            try { await api.delete(`/household/roles/${r.role_id}`); await load(); }
            catch (e: any) { Alert.alert('Cannot delete', e?.message || ''); }
          }} />
        ) : (
          <HandbookSection entries={handbook} onEdit={(e) => setEdit({ kind: 'handbook', data: e })} onTemplate={(t) => setEdit({ kind: 'handbook', data: { ...t, _template: true } })} />
        )}
      </ScrollView>

      {/* Modals */}
      {edit?.kind === 'people' && (
        <PersonForm initial={edit.data} roles={roles.filter((r) => r.category === 'family')} spaceId={activeSpace.space_id} onClose={() => setEdit(null)} onSaved={() => { setEdit(null); load(); }} />
      )}
      {edit?.kind === 'staff' && (
        <StaffForm initial={edit.data} roles={roles.filter((r) => r.category === 'staff')} spaceId={activeSpace.space_id} currency={activeSpace.currency || 'USD'} onClose={() => setEdit(null)} onSaved={() => { setEdit(null); load(); }} />
      )}
      {edit?.kind === 'role' && (
        <RoleForm initial={edit.data} spaceId={activeSpace.space_id} onClose={() => setEdit(null)} onSaved={() => { setEdit(null); load(); }} />
      )}
      {edit?.kind === 'handbook' && (
        <HandbookForm initial={edit.data} spaceId={activeSpace.space_id} onClose={() => setEdit(null)} onSaved={() => { setEdit(null); load(); }} />
      )}
      {edit?.kind === 'task' && (
        <TaskForm initial={edit.data} spaceId={activeSpace.space_id} staff={staff} roles={roles} onClose={() => setEdit(null)} onSaved={() => { setEdit(null); load(); }} />
      )}
      {edit?.kind === 'shopping' && (
        <ShoppingForm initial={edit.data} spaceId={activeSpace.space_id} categories={categoriesList} staff={staff} onClose={() => setEdit(null)} onSaved={() => { setEdit(null); load(); }} />
      )}
    </SafeAreaView>
  );
}

// ---------- Section renderers ----------
function PeopleSection({ people, roles, onEdit }: { people: FamilyMember[]; roles: HouseholdRole[]; onEdit: (p?: FamilyMember) => void }) {
  if (people.length === 0) {
    return (
      <View style={styles.empty}>
        <View style={[styles.heroIcon, { backgroundColor: tints.peach.bg }]}>
          <Icon name="Users" size={32} color={tints.peach.icon} />
        </View>
        <Text style={styles.emptyTitle}>Family directory</Text>
        <Text style={styles.emptySub}>
          Add the people who live here — kids, parents, partner. Helpful so nannies and cooks know allergies, schools, and schedules at a glance.
        </Text>
        <TouchableOpacity style={styles.ctaBtn} onPress={() => onEdit()} testID="household-people-cta">
          <Icon name="Plus" color="#fff" size={16} />
          <Text style={styles.ctaTxt}>Add a family member</Text>
        </TouchableOpacity>
      </View>
    );
  }
  return (
    <View style={{ gap: 8 }}>
      {people.map((p) => {
        const role = roles.find((r) => r.role_id === p.role_id);
        const t = tints[(role?.color as keyof typeof tints) || 'peach'];
        return (
          <TouchableOpacity key={p.member_id} style={styles.row} onPress={() => onEdit(p)} testID={`household-person-${p.member_id}`} activeOpacity={0.8}>
            <View style={[styles.avatar, { backgroundColor: t.icon }]}>
              {p.photo_base64 ? <Image source={{ uri: p.photo_base64 }} style={styles.avatarImg} /> : <Text style={styles.avatarTxt}>{p.name?.[0]?.toUpperCase()}</Text>}
            </View>
            <View style={{ flex: 1 }}>
              <Text style={styles.rowName}>{p.name}</Text>
              <Text style={styles.rowSub}>
                {role?.name || 'No role'}
                {p.age ? ` · ${p.age}y` : ''}
                {p.school ? ` · ${p.school}` : ''}
              </Text>
              {p.allergies ? (
                <View style={[styles.badge, { backgroundColor: tints.pink.bg }]}>
                  <Icon name="Heart" size={10} color={tints.pink.icon} />
                  <Text style={[styles.badgeTxt, { color: tints.pink.icon }]}>Allergies: {p.allergies}</Text>
                </View>
              ) : null}
            </View>
            <Icon name="ChevronRight" size={16} color={colors.textMuted} />
          </TouchableOpacity>
        );
      })}
    </View>
  );
}

function StaffSection({ staff, roles, currency, spaceId, onEdit, onRefresh }: { staff: StaffMember[]; roles: HouseholdRole[]; currency: string; spaceId: string; onEdit: (s?: StaffMember) => void; onRefresh: () => void }) {
  if (staff.length === 0) {
    return (
      <View style={styles.empty}>
        <View style={[styles.heroIcon, { backgroundColor: tints.blue.bg }]}>
          <Icon name="User" size={32} color={tints.blue.icon} />
        </View>
        <Text style={styles.emptyTitle}>Staff roster</Text>
        <Text style={styles.emptySub}>
          Track maids, drivers, nannies, cooks. Keep their contact, salary, off-day and emergency info in one place. Tasks & payroll come next.
        </Text>
        <TouchableOpacity style={styles.ctaBtn} onPress={() => onEdit()} testID="household-staff-cta">
          <Icon name="Plus" color="#fff" size={16} />
          <Text style={styles.ctaTxt}>Add staff</Text>
        </TouchableOpacity>
      </View>
    );
  }
  return (
    <View style={{ gap: 8 }}>
      {staff.map((s) => (
        <StaffCard
          key={s.staff_id}
          staff={s}
          roles={roles}
          currency={currency}
          spaceId={spaceId}
          onEdit={onEdit}
          onRefresh={onRefresh}
        />
      ))}
    </View>
  );
}

function StaffCard({ staff: s, roles, currency, spaceId, onEdit, onRefresh }: { staff: StaffMember; roles: HouseholdRole[]; currency: string; spaceId: string; onEdit: (s?: StaffMember) => void; onRefresh: () => void }) {
  const router = useRouter();
  const role = roles.find((r) => r.role_id === s.role_id);
  const t = tints[(role?.color as keyof typeof tints) || 'blue'];
  const [expanded, setExpanded] = useState(false);
  const [shortcuts, setShortcuts] = useState<any[]>([]);
  const [freeText, setFreeText] = useState('');
  const [saving, setSaving] = useState(false);

  const loadShortcuts = useCallback(async () => {
    try {
      const list = await api.get<any[]>(`/household/shortcuts?space_id=${spaceId}&staff_id=${s.staff_id}`);
      // filter: shown if scoped to this staff or shared (null)
      setShortcuts((list || []).filter((x) => x.staff_id === s.staff_id || !x.staff_id));
    } catch (e) {}
  }, [spaceId, s.staff_id]);

  useEffect(() => { if (expanded) loadShortcuts(); }, [expanded, loadShortcuts]);

  const fire = async (title: string, saveAsShortcut: boolean) => {
    if (!title.trim()) return;
    setSaving(true);
    try {
      await api.post('/household/tasks/quick', {
        space_id: spaceId, staff_id: s.staff_id, title: title.trim(),
        save_as_shortcut: saveAsShortcut,
      });
      Alert.alert('Sent', `"${title}" sent to ${s.name}.${saveAsShortcut ? ' Saved as shortcut.' : ''}`);
      setFreeText('');
      if (saveAsShortcut) await loadShortcuts();
      onRefresh();
    } catch (e: any) { Alert.alert('Error', e?.message || 'Could not send'); }
    finally { setSaving(false); }
  };

  const removeShortcut = async (scId: string) => {
    try {
      await api.delete(`/household/shortcuts/${scId}`);
      await loadShortcuts();
    } catch (e: any) { Alert.alert('Error', e?.message || ''); }
  };

  return (
    <View style={[styles.row, { flexDirection: 'column', alignItems: 'stretch', padding: 0 }]} testID={`household-staff-${s.staff_id}`}>
      <TouchableOpacity onPress={() => onEdit(s)} activeOpacity={0.8} style={{ flexDirection: 'row', alignItems: 'center', gap: 12, padding: spacing.md }}>
        <View style={[styles.avatar, { backgroundColor: t.icon }]}>
          {s.photo_base64 ? <Image source={{ uri: s.photo_base64 }} style={styles.avatarImg} /> : <Text style={styles.avatarTxt}>{s.name?.[0]?.toUpperCase()}</Text>}
        </View>
        <View style={{ flex: 1 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
            <Text style={styles.rowName}>{s.name}</Text>
            {(s as any).user_id ? (
              <View style={[styles.badge, { backgroundColor: tints.sage.bg, paddingVertical: 2 }]}>
                <Icon name="Check" size={9} color={tints.sage.icon} />
                <Text style={[styles.badgeTxt, { color: tints.sage.icon, fontSize: 9 }]}>linked</Text>
              </View>
            ) : null}
            {((s as any).active === false) ? (
              <View style={[styles.badge, { backgroundColor: tints.pink.bg, paddingVertical: 2 }]}>
                <Text style={[styles.badgeTxt, { color: tints.pink.icon, fontSize: 9 }]}>former</Text>
              </View>
            ) : null}
          </View>
          <Text style={styles.rowSub}>
            {role?.name || 'No role'}
            {s.phone ? ` · ${s.phone}` : ''}
            {s.off_day ? ` · off ${s.off_day}` : ''}
          </Text>
          {s.salary ? (
            <View style={[styles.badge, { backgroundColor: tints.sage.bg, marginTop: 4 }]}>
              <Icon name="DollarSign" size={10} color={tints.sage.icon} />
              <Text style={[styles.badgeTxt, { color: tints.sage.icon }]}>{formatMoney(s.salary, s.salary_currency || currency)} / {s.pay_cycle}</Text>
            </View>
          ) : null}
          {!!(s as any).invite_code && !(s as any).user_id && (
            <TouchableOpacity
              style={styles.codeChip}
              onPress={async (e) => {
                e.stopPropagation?.();
                try {
                  const Clipboard = await import('expo-clipboard');
                  await (Clipboard as any).setStringAsync((s as any).invite_code);
                  Alert.alert('Code copied', `Give ${(s as any).invite_code} to ${s.name}. They sign up with any email, tap "I'm staff" and paste this code.`);
                } catch {}
              }}
              testID={`staff-code-${s.staff_id}`}
            >
              <Icon name="Copy" size={10} color={tints.yellow.icon} />
              <Text style={styles.codeChipTxt}>CODE {(s as any).invite_code}</Text>
            </TouchableOpacity>
          )}
        </View>
        <Icon name="ChevronRight" size={16} color={colors.textMuted} />
      </TouchableOpacity>
      {/* Action row: Quick send + Preview */}
      <View style={styles.staffActions}>
        <TouchableOpacity
          style={[styles.actionBtn, expanded && { backgroundColor: tints.mint.icon }]}
          onPress={() => setExpanded((v) => !v)}
          testID={`staff-quick-${s.staff_id}`}
        >
          <Icon name="Sparkles" size={13} color={expanded ? '#fff' : tints.mint.icon} />
          <Text style={[styles.actionTxt, expanded && { color: '#fff' }]}>Quick send</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={styles.actionBtn}
          onPress={() => router.push(`/staff-home?preview=${s.staff_id}`)}
          testID={`staff-preview-${s.staff_id}`}
        >
          <Icon name="User" size={13} color={tints.blue.icon} />
          <Text style={[styles.actionTxt, { color: tints.blue.icon }]}>Preview home</Text>
        </TouchableOpacity>
      </View>
      {expanded && (
        <View style={styles.quickPanel}>
          <Text style={styles.helper}>Tap a shortcut to send it now. {(s as any).user_id ? `${s.name?.split(' ')[0]} will get a notification.` : `${s.name?.split(' ')[0]} isn't linked to the app yet — share their invite code first.`}</Text>
          {shortcuts.length > 0 && (
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginTop: 8 }}>
              {shortcuts.map((sc) => (
                <View key={sc.shortcut_id} style={styles.scChip}>
                  <TouchableOpacity onPress={() => fire(sc.title, false)} disabled={saving} testID={`sc-${sc.shortcut_id}`}>
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
                      <Icon name={sc.icon || 'Zap'} size={12} color={colors.primary} />
                      <Text style={styles.scChipTxt}>{sc.title}</Text>
                    </View>
                  </TouchableOpacity>
                  <TouchableOpacity onPress={() => removeShortcut(sc.shortcut_id)} style={{ padding: 2 }}>
                    <Icon name="X" size={10} color={colors.textMuted} />
                  </TouchableOpacity>
                </View>
              ))}
            </View>
          )}
          <TextInput
            style={[styles.input, { marginTop: 8 }]}
            value={freeText}
            onChangeText={setFreeText}
            placeholder='e.g. "Bring me water"'
            placeholderTextColor={colors.textMuted}
            testID={`quick-text-${s.staff_id}`}
          />
          <View style={{ flexDirection: 'row', gap: 6, marginTop: 6 }}>
            <TouchableOpacity
              style={[styles.sendBtn, (!freeText.trim() || saving) && { opacity: 0.5 }]}
              onPress={() => fire(freeText, false)}
              disabled={!freeText.trim() || saving}
              testID={`quick-send-${s.staff_id}`}
            >
              <Icon name="ArrowRight" size={12} color="#fff" />
              <Text style={styles.sendBtnTxt}>Send</Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={[styles.sendBtnAlt, (!freeText.trim() || saving) && { opacity: 0.5 }]}
              onPress={() => fire(freeText, true)}
              disabled={!freeText.trim() || saving}
              testID={`quick-save-${s.staff_id}`}
            >
              <Icon name="Plus" size={12} color={colors.primary} />
              <Text style={styles.sendBtnAltTxt}>Send + save</Text>
            </TouchableOpacity>
          </View>
        </View>
      )}
    </View>
  );
}

function RolesSection({ roles, onEdit, onDelete }: { roles: HouseholdRole[]; onEdit: (r?: HouseholdRole) => void; onDelete: (r: HouseholdRole) => void }) {
  const family = roles.filter((r) => r.category === 'family');
  const staff = roles.filter((r) => r.category === 'staff');
  return (
    <View style={{ gap: 8 }}>
      <Text style={styles.sectionTitle}>Family roles</Text>
      {family.map((r) => <RoleRow key={r.role_id} role={r} onEdit={onEdit} onDelete={onDelete} />)}
      <Text style={[styles.sectionTitle, { marginTop: spacing.md }]}>Staff roles</Text>
      {staff.map((r) => <RoleRow key={r.role_id} role={r} onEdit={onEdit} onDelete={onDelete} />)}
    </View>
  );
}
function RoleRow({ role, onEdit, onDelete }: any) {
  const t = tints[(role.color as keyof typeof tints) || 'mint'];
  return (
    <View style={styles.row}>
      <TouchableOpacity style={[styles.avatar, { backgroundColor: t.bg }]} onPress={() => onEdit(role)}>
        <Icon name={role.icon || 'User'} size={18} color={t.icon} />
      </TouchableOpacity>
      <TouchableOpacity style={{ flex: 1 }} onPress={() => onEdit(role)}>
        <Text style={styles.rowName}>{role.name}</Text>
        <Text style={styles.rowSub}>{role.is_default ? 'Default' : 'Custom'} · {role.category === 'family' ? 'Family' : 'Staff'}</Text>
      </TouchableOpacity>
      {!role.is_default && (
        <TouchableOpacity onPress={() => onDelete(role)} style={{ padding: 6 }}>
          <Icon name="Trash2" size={14} color={colors.dangerText} />
        </TouchableOpacity>
      )}
      <TouchableOpacity onPress={() => onEdit(role)} style={{ padding: 6 }}>
        <Icon name="Edit3" size={14} color={colors.textMuted} />
      </TouchableOpacity>
    </View>
  );
}

function HandbookSection({ entries, onEdit, onTemplate }: { entries: HandbookEntry[]; onEdit: (e?: HandbookEntry) => void; onTemplate: (t: any) => void }) {
  return (
    <View style={{ gap: spacing.sm }}>
      {entries.length === 0 && (
        <View style={[styles.empty, { paddingTop: 20 }]}>
          <View style={[styles.heroIcon, { backgroundColor: tints.sage.bg }]}>
            <Icon name="BookOpen" size={32} color={tints.sage.icon} />
          </View>
          <Text style={styles.emptyTitle}>House handbook</Text>
          <Text style={styles.emptySub}>Save the small things everyone forgets — wifi password, emergency #s, doctor info. Pick a template to start fast.</Text>
        </View>
      )}
      {entries.map((e) => {
        const t = tints[(e.color as keyof typeof tints) || 'sage'];
        return (
          <TouchableOpacity key={e.entry_id} style={[styles.handbookCard, { backgroundColor: t.bg }]} onPress={() => onEdit(e)} testID={`household-handbook-${e.entry_id}`}>
            <View style={[styles.hbIcon, { backgroundColor: t.icon }]}>
              <Icon name={e.icon || 'BookOpen'} size={18} color="#fff" />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={styles.hbTitle}>{e.title}</Text>
              {e.photo_base64 ? <Image source={{ uri: e.photo_base64 }} style={styles.hbPhoto} /> : null}
              <Text style={styles.hbBody} numberOfLines={3}>{e.body}</Text>
            </View>
            <Icon name="Edit3" size={14} color={colors.textMuted} />
          </TouchableOpacity>
        );
      })}
      <Text style={[styles.sectionTitle, { marginTop: spacing.md }]}>Quick templates</Text>
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
        {HANDBOOK_TEMPLATES.map((t) => (
          <TouchableOpacity key={t.title} style={styles.templateChip} onPress={() => onTemplate(t)}>
            <Icon name={t.icon} size={14} color={colors.textMain} />
            <Text style={styles.templateTxt}>{t.title}</Text>
          </TouchableOpacity>
        ))}
      </View>
    </View>
  );
}

// ---------- Forms ----------
async function pickPhoto(): Promise<string | null> {
  const r = await ImagePicker.requestMediaLibraryPermissionsAsync();
  if (!r.granted) return null;
  const res = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ImagePicker.MediaTypeOptions.Images, allowsEditing: true, aspect: [1, 1], quality: 0.5, base64: true });
  if (res.canceled) return null;
  const a = res.assets?.[0];
  if (!a?.base64) return null;
  return `data:image/jpeg;base64,${a.base64}`;
}

function FormSheet({ title, onClose, onSave, saving, children }: any) {
  return (
    <Modal visible animationType="slide" transparent onRequestClose={onClose}>
      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={styles.modalOverlay}>
        <TouchableOpacity style={{ flex: 1 }} activeOpacity={1} onPress={onClose} />
        <View style={styles.sheet}>
          <View style={styles.sheetHandle} />
          <ScrollView showsVerticalScrollIndicator={false} keyboardShouldPersistTaps="handled">
            <Text style={styles.sheetTitle}>{title}</Text>
            {children}
            <View style={styles.actionRow}>
              <TouchableOpacity style={styles.cancelBtn} onPress={onClose}><Text style={styles.cancelTxt}>Cancel</Text></TouchableOpacity>
              <TouchableOpacity style={[styles.saveBtn, saving && { opacity: 0.6 }]} onPress={onSave} disabled={saving}>
                <Text style={styles.saveTxt}>{saving ? 'Saving...' : 'Save'}</Text>
              </TouchableOpacity>
            </View>
          </ScrollView>
        </View>
      </KeyboardAvoidingView>
    </Modal>
  );
}

function PhotoPicker({ photo, onChange, color = tints.peach.icon }: { photo?: string | null; onChange: (b: string | null) => void; color?: string }) {
  return (
    <TouchableOpacity style={[styles.photoPicker, { borderColor: color }]} onPress={async () => { const p = await pickPhoto(); if (p) onChange(p); }}>
      {photo ? (
        <>
          <Image source={{ uri: photo }} style={styles.photoImg} />
          <TouchableOpacity onPress={() => onChange(null)} style={styles.photoRemove}>
            <Icon name="X" size={12} color="#fff" />
          </TouchableOpacity>
        </>
      ) : (
        <>
          <Icon name="ImagePlus" size={20} color={color} />
          <Text style={[styles.photoTxt, { color }]}>Add photo</Text>
        </>
      )}
    </TouchableOpacity>
  );
}

function PersonForm({ initial, roles, spaceId, onClose, onSaved }: any) {
  const [name, setName] = useState(initial?.name || '');
  const [roleId, setRoleId] = useState<string | null>(initial?.role_id || null);
  const [photo, setPhoto] = useState<string | null>(initial?.photo_base64 || null);
  const [age, setAge] = useState(initial?.age ? String(initial.age) : '');
  const [school, setSchool] = useState(initial?.school || '');
  const [allergies, setAllergies] = useState(initial?.allergies || '');
  const [notes, setNotes] = useState(initial?.notes || '');
  const [medical, setMedical] = useState(initial?.medical_notes || '');
  const [saving, setSaving] = useState(false);

  const save = async () => {
    if (!name.trim()) { Alert.alert('Name required', 'Please add a name'); return; }
    setSaving(true);
    try {
      const payload: any = {
        name: name.trim(),
        role_id: roleId,
        photo_base64: photo,
        age: age ? parseInt(age, 10) : null,
        school: school || null,
        allergies: allergies || null,
        medical_notes: medical || null,
        notes: notes || null,
      };
      if (initial?.member_id) await api.patch(`/household/family/${initial.member_id}`, payload);
      else await api.post('/household/family', { space_id: spaceId, ...payload });
      onSaved();
    } catch (e: any) { Alert.alert('Error', e?.message || ''); }
    finally { setSaving(false); }
  };

  const remove = async () => {
    if (!initial?.member_id) return;
    Alert.alert('Remove member?', `Remove ${initial.name} from the family directory.`, [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Remove', style: 'destructive', onPress: async () => {
          try { await api.delete(`/household/family/${initial.member_id}`); onSaved(); }
          catch (e: any) { Alert.alert('Error', e?.message || ''); }
        }
      },
    ]);
  };

  return (
    <FormSheet title={initial?.member_id ? 'Edit family member' : 'Add family member'} onClose={onClose} onSave={save} saving={saving}>
      <PhotoPicker photo={photo} onChange={setPhoto} color={tints.peach.icon} />
      <Text style={styles.label}>Name</Text>
      <TextInput style={styles.input} value={name} onChangeText={setName} placeholder="e.g. Maya" placeholderTextColor={colors.textMuted} testID="person-form-name" />

      <Text style={styles.label}>Role</Text>
      <View style={styles.chipWrap}>
        {roles.map((r: HouseholdRole) => (
          <TouchableOpacity key={r.role_id} style={[styles.chip, roleId === r.role_id && styles.chipActive]} onPress={() => setRoleId(r.role_id)}>
            <Text style={[styles.chipTxt, roleId === r.role_id && styles.chipTxtActive]}>{r.name}</Text>
          </TouchableOpacity>
        ))}
      </View>

      <View style={{ flexDirection: 'row', gap: 10 }}>
        <View style={{ flex: 1 }}>
          <Text style={styles.label}>Age</Text>
          <TextInput style={styles.input} value={age} onChangeText={setAge} keyboardType="number-pad" placeholder="e.g. 8" placeholderTextColor={colors.textMuted} />
        </View>
        <View style={{ flex: 2 }}>
          <Text style={styles.label}>School / workplace</Text>
          <TextInput style={styles.input} value={school} onChangeText={setSchool} placeholder="optional" placeholderTextColor={colors.textMuted} />
        </View>
      </View>
      <Text style={styles.label}>Allergies</Text>
      <TextInput style={styles.input} value={allergies} onChangeText={setAllergies} placeholder="e.g. peanuts, dust" placeholderTextColor={colors.textMuted} />
      <Text style={styles.label}>Medical notes</Text>
      <TextInput style={[styles.input, { minHeight: 60 }]} value={medical} onChangeText={setMedical} multiline placeholder="medications, conditions" placeholderTextColor={colors.textMuted} />
      <Text style={styles.label}>Notes</Text>
      <TextInput style={[styles.input, { minHeight: 60 }]} value={notes} onChangeText={setNotes} multiline placeholder="favourite foods, schedule, anything helpful" placeholderTextColor={colors.textMuted} />

      {initial?.member_id && (
        <TouchableOpacity onPress={remove} style={styles.deleteRow}><Icon name="Trash2" size={14} color={colors.dangerText} /><Text style={styles.deleteTxt}>Remove from family</Text></TouchableOpacity>
      )}
    </FormSheet>
  );
}

function StaffForm({ initial, roles, spaceId, currency, onClose, onSaved }: any) {
  const [name, setName] = useState(initial?.name || '');
  const [roleId, setRoleId] = useState<string | null>(initial?.role_id || null);
  const [photo, setPhoto] = useState<string | null>(initial?.photo_base64 || null);
  const [phone, setPhone] = useState(initial?.phone || '');
  const [emergency, setEmergency] = useState(initial?.emergency_contact || '');
  const [idNum, setIdNum] = useState(initial?.id_number || '');
  const [salary, setSalary] = useState(initial?.salary ? String(initial.salary) : '');
  const [cycle, setCycle] = useState<'monthly' | 'weekly' | 'daily'>(initial?.pay_cycle || 'monthly');
  const [offDay, setOffDay] = useState(initial?.off_day || '');
  const [startDate, setStartDate] = useState(initial?.start_date || '');
  const [endDate, setEndDate] = useState(initial?.end_date || '');
  const [active, setActive] = useState<boolean>(initial?.active !== false);
  const [requiresConfirm, setRequiresConfirm] = useState<boolean>(!!initial?.requires_wage_confirmation);
  const [notes, setNotes] = useState(initial?.notes || '');
  const [saving, setSaving] = useState(false);
  const [payNote, setPayNote] = useState('');
  const [paying, setPaying] = useState(false);

  const save = async () => {
    if (!name.trim()) { Alert.alert('Name required', ''); return; }
    setSaving(true);
    try {
      const payload: any = {
        name: name.trim(), role_id: roleId, photo_base64: photo,
        phone: phone || null, emergency_contact: emergency || null,
        id_number: idNum || null,
        salary: salary ? parseFloat(salary) : null,
        pay_cycle: cycle, salary_currency: currency,
        off_day: offDay || null, start_date: startDate || null,
        end_date: endDate || null, active: active,
        requires_wage_confirmation: requiresConfirm,
        notes: notes || null,
      };
      if (initial?.staff_id) await api.patch(`/household/staff/${initial.staff_id}`, payload);
      else await api.post('/household/staff', { space_id: spaceId, ...payload });
      onSaved();
    } catch (e: any) { Alert.alert('Error', e?.message || ''); }
    finally { setSaving(false); }
  };

  const markSalaryPaid = async () => {
    if (!initial?.staff_id || !initial?.salary) { Alert.alert('Set salary first', ''); return; }
    setPaying(true);
    try {
      await api.post('/household/payroll', { space_id: spaceId, staff_id: initial.staff_id, notes: payNote || null });
      Alert.alert('Paid', 'Salary logged in Finance as "Staff wages".');
      setPayNote('');
      onSaved();
    } catch (e: any) { Alert.alert('Error', e?.message || ''); }
    finally { setPaying(false); }
  };

  const copyCode = async () => {
    try {
      const Clipboard = await import('expo-clipboard');
      await (Clipboard as any).setStringAsync(initial.invite_code);
      Alert.alert('Copied', `Share code ${initial.invite_code} with ${initial.name}. They sign up with any email, tap "Join as staff" and paste this code.`);
    } catch (e) {}
  };

  const remove = async () => {
    if (!initial?.staff_id) return;
    Alert.alert('Remove staff?', `Remove ${initial.name}. Past records stay.`, [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Remove', style: 'destructive', onPress: async () => {
          try { await api.delete(`/household/staff/${initial.staff_id}`); onSaved(); }
          catch (e: any) { Alert.alert('Error', e?.message || ''); }
        }
      },
    ]);
  };

  return (
    <FormSheet title={initial?.staff_id ? 'Edit staff' : 'Add staff'} onClose={onClose} onSave={save} saving={saving}>
      <PhotoPicker photo={photo} onChange={setPhoto} color={tints.blue.icon} />
      <Text style={styles.label}>Name</Text>
      <TextInput style={styles.input} value={name} onChangeText={setName} placeholder="e.g. Mbak Rina" placeholderTextColor={colors.textMuted} testID="staff-form-name" />
      <Text style={styles.label}>Role</Text>
      <View style={styles.chipWrap}>
        {roles.map((r: HouseholdRole) => (
          <TouchableOpacity key={r.role_id} style={[styles.chip, roleId === r.role_id && styles.chipActive]} onPress={() => setRoleId(r.role_id)}>
            <Text style={[styles.chipTxt, roleId === r.role_id && styles.chipTxtActive]}>{r.name}</Text>
          </TouchableOpacity>
        ))}
      </View>
      <View style={{ flexDirection: 'row', gap: 10 }}>
        <View style={{ flex: 1 }}>
          <Text style={styles.label}>Phone</Text>
          <TextInput style={styles.input} value={phone} onChangeText={setPhone} keyboardType="phone-pad" placeholder="optional" placeholderTextColor={colors.textMuted} />
        </View>
        <View style={{ flex: 1 }}>
          <Text style={styles.label}>Emergency contact</Text>
          <TextInput style={styles.input} value={emergency} onChangeText={setEmergency} placeholder="family member" placeholderTextColor={colors.textMuted} />
        </View>
      </View>
      <Text style={styles.label}>ID / KTP / passport (optional)</Text>
      <TextInput style={styles.input} value={idNum} onChangeText={setIdNum} placeholder="for your records" placeholderTextColor={colors.textMuted} />
      <View style={{ flexDirection: 'row', gap: 10 }}>
        <View style={{ flex: 2 }}>
          <Text style={styles.label}>Salary ({getCurrency(currency).symbol} {currency})</Text>
          <TextInput style={styles.input} value={salary} onChangeText={setSalary} keyboardType="decimal-pad" placeholder={currency === 'IDR' || currency === 'JPY' ? '0' : '0.00'} placeholderTextColor={colors.textMuted} />
        </View>
        <View style={{ flex: 1 }}>
          <Text style={styles.label}>Cycle</Text>
          <View style={{ flexDirection: 'row', gap: 4 }}>
            {(['monthly', 'weekly', 'daily'] as const).map((c) => (
              <TouchableOpacity key={c} style={[styles.chip, cycle === c && styles.chipActive, { paddingHorizontal: 8 }]} onPress={() => setCycle(c)}>
                <Text style={[styles.chipTxt, cycle === c && styles.chipTxtActive]}>{c[0].toUpperCase()}</Text>
              </TouchableOpacity>
            ))}
          </View>
        </View>
      </View>
      <View style={{ flexDirection: 'row', gap: 10 }}>
        <View style={{ flex: 1 }}>
          <Text style={styles.label}>Off day</Text>
          <TextInput style={styles.input} value={offDay} onChangeText={setOffDay} placeholder="e.g. Sunday" placeholderTextColor={colors.textMuted} />
        </View>
        <View style={{ flex: 1 }}>
          <Text style={styles.label}>Start date</Text>
          <TextInput style={styles.input} value={startDate} onChangeText={setStartDate} placeholder="YYYY-MM-DD" placeholderTextColor={colors.textMuted} />
        </View>
      </View>
      <View style={{ flexDirection: 'row', gap: 10, alignItems: 'flex-end' }}>
        <View style={{ flex: 1 }}>
          <Text style={styles.label}>End date (if they stopped)</Text>
          <TextInput style={styles.input} value={endDate} onChangeText={setEndDate} placeholder="optional · YYYY-MM-DD" placeholderTextColor={colors.textMuted} testID="staff-end-date" />
        </View>
        <TouchableOpacity
          style={[styles.activeToggle, active && { backgroundColor: tints.sage.bg, borderColor: tints.sage.icon }]}
          onPress={() => setActive((v) => !v)}
          testID="staff-active-toggle"
        >
          <Icon name={active ? 'Check' : 'X'} size={12} color={active ? tints.sage.icon : colors.textMuted} />
          <Text style={[styles.activeToggleTxt, active && { color: tints.sage.icon }]}>{active ? 'Currently employed' : 'Former staff'}</Text>
        </TouchableOpacity>
      </View>
      <Text style={styles.helper}>Former staff won't appear in monthly reports from the current month onward — past records (wages paid, attendance) stay intact for history.</Text>

      <TouchableOpacity
        style={[styles.activeToggle, requiresConfirm && { backgroundColor: tints.lavender.bg, borderColor: tints.lavender.icon }]}
        onPress={() => setRequiresConfirm((v) => !v)}
        testID="staff-confirm-toggle"
      >
        <Icon name={requiresConfirm ? 'Check' : 'X'} size={12} color={requiresConfirm ? tints.lavender.icon : colors.textMuted} />
        <Text style={[styles.activeToggleTxt, requiresConfirm && { color: tints.lavender.icon }]}>
          {requiresConfirm ? 'Staff must confirm wage receipt' : 'Wages auto-confirmed'}
        </Text>
      </TouchableOpacity>
      <Text style={styles.helper}>When ON, paid wages stay "pending" in the report until {initial?.name?.split(' ')[0] || 'they'} taps "I received" in their app — keeps the record clean and avoids he-said-she-said.</Text>
      <Text style={styles.label}>Notes</Text>
      <TextInput style={[styles.input, { minHeight: 60 }]} value={notes} onChangeText={setNotes} multiline placeholder="responsibilities, agreement, anything important" placeholderTextColor={colors.textMuted} />
      {initial?.staff_id && initial?.invite_code && (
        <View style={styles.inviteBox}>
          <View style={{ flex: 1 }}>
            <Text style={styles.label}>Staff-only invite code</Text>
            <Text style={styles.inviteCode}>{initial.invite_code}</Text>
            <Text style={styles.helper}>Give this to {initial.name}. They sign up with any email, tap the "I'm staff" tab and paste this code — they'll land on a simplified app. This is DIFFERENT from the space invite code (which is for family/roommates).</Text>
          </View>
          <TouchableOpacity onPress={copyCode} style={styles.copyBtn}><Icon name="Copy" size={14} color={colors.textMain} /><Text style={styles.copyTxt}>Copy</Text></TouchableOpacity>
        </View>
      )}

      {initial?.staff_id && (
        <StaffPermissionsEditor staff={initial} onChanged={onSaved} />
      )}

      {initial?.staff_id && initial?.salary ? (
        <View style={styles.payBox}>
          <Text style={styles.label}>Mark salary paid</Text>
          <Text style={styles.helper}>Logs this as an expense in Finance ("Staff wages" category). Adjust amount / advances in Wages report if needed.</Text>
          <TextInput style={styles.input} value={payNote} onChangeText={setPayNote} placeholder="Optional note (e.g. advance, bonus)" placeholderTextColor={colors.textMuted} />
          <TouchableOpacity style={[styles.payNowBtn, paying && { opacity: 0.6 }]} onPress={markSalaryPaid} disabled={paying}>
            <Icon name="Wallet" size={14} color="#fff" />
            <Text style={styles.payNowTxt}>{paying ? 'Recording...' : `Pay ${formatMoney(initial.salary, currency)}`}</Text>
          </TouchableOpacity>
        </View>
      ) : null}

      {initial?.staff_id && (
        <TouchableOpacity onPress={remove} style={styles.deleteRow}><Icon name="Trash2" size={14} color={colors.dangerText} /><Text style={styles.deleteTxt}>Remove from staff</Text></TouchableOpacity>
      )}
    </FormSheet>
  );
}

function StaffPermissionsEditor({ staff, onChanged }: { staff: StaffMember; onChanged: () => void }) {
  const initialPerms: Record<string, boolean> = (staff as any).permissions || {};
  const [perms, setPerms] = useState<Record<string, boolean>>({
    view_tasks: true, log_attendance: true, request_shopping: true, view_handbook: true,
    view_wage_amount: true, view_other_staff: false, view_family: false,
    view_finance: false, view_inventory: false,
    ...initialPerms,
  });
  const [saving, setSaving] = useState(false);

  const toggle = (k: string) => {
    setPerms((p) => ({ ...p, [k]: !p[k] }));
  };

  const save = async () => {
    setSaving(true);
    try {
      await api.patch(`/household/staff/${staff.staff_id}/permissions`, { permissions: perms });
      onChanged();
    } catch (e: any) { Alert.alert('Error', e?.message || 'Could not update'); }
    finally { setSaving(false); }
  };

  const groups: Array<{ title: string; items: Array<{ key: string; label: string; hint?: string }> }> = [
    {
      title: 'Staff home (on their own app)',
      items: [
        { key: 'view_tasks', label: 'See assigned tasks' },
        { key: 'log_attendance', label: 'Log own attendance', hint: 'Mark themselves present / sick / off' },
        { key: 'request_shopping', label: 'Send shopping requests' },
        { key: 'view_handbook', label: 'Open handbook' },
        { key: 'view_wage_amount', label: 'See own wage amount', hint: 'Turn off to hide salary and history' },
      ],
    },
    {
      title: 'Extra access (into the main family app)',
      items: [
        { key: 'view_inventory', label: 'View inventory tab', hint: 'They can see household inventory (read-only for now)' },
        { key: 'view_inventory_prices', label: '↳ Show prices in inventory', hint: 'Hide for staff who shouldn\'t know item costs' },
        { key: 'view_finance', label: 'View finance tab', hint: 'They can see monthly spending' },
        { key: 'view_family', label: 'See family directory' },
        { key: 'view_other_staff', label: 'See other staff list' },
      ],
    },
  ];

  return (
    <View style={styles.payBox}>
      <Text style={styles.label}>Permissions</Text>
      <Text style={styles.helper}>Choose what {staff.name?.split(' ')[0] || 'this person'} can see and do. Off means the tab or section stays hidden.</Text>
      {groups.map((g) => (
        <View key={g.title} style={{ marginTop: spacing.sm }}>
          <Text style={styles.sectionTitle}>{g.title}</Text>
          {g.items.map((it) => (
            <TouchableOpacity
              key={it.key}
              style={styles.permRow}
              onPress={() => toggle(it.key)}
              testID={`perm-${it.key}`}
              activeOpacity={0.7}
            >
              <View style={{ flex: 1 }}>
                <Text style={styles.rowName}>{it.label}</Text>
                {it.hint ? <Text style={styles.rowSub}>{it.hint}</Text> : null}
              </View>
              <View style={[styles.switch, perms[it.key] && { backgroundColor: colors.primary }]}>
                <View style={[styles.switchDot, perms[it.key] && { left: 22, backgroundColor: '#fff' }]} />
              </View>
            </TouchableOpacity>
          ))}
        </View>
      ))}
      <TouchableOpacity style={[styles.payNowBtn, saving && { opacity: 0.6 }]} onPress={save} disabled={saving}>
        <Icon name="Check" size={14} color="#fff" />
        <Text style={styles.payNowTxt}>{saving ? 'Saving...' : 'Save permissions'}</Text>
      </TouchableOpacity>
    </View>
  );
}


function RoleForm({ initial, spaceId, onClose, onSaved }: any) {
  const [name, setName] = useState(initial?.name || '');
  const [icon, setIcon] = useState(initial?.icon || 'User');
  const [color, setColor] = useState<keyof typeof tints>((initial?.color as any) || 'mint');
  const [category, setCategory] = useState<'family' | 'staff'>(initial?.category || 'family');
  const [saving, setSaving] = useState(false);

  const save = async () => {
    if (!name.trim()) return;
    setSaving(true);
    try {
      const payload: any = { name: name.trim(), icon, color, category };
      if (initial?.role_id) await api.patch(`/household/roles/${initial.role_id}`, payload);
      else await api.post('/household/roles', { space_id: spaceId, ...payload });
      onSaved();
    } catch (e: any) { Alert.alert('Error', e?.message || ''); }
    finally { setSaving(false); }
  };

  return (
    <FormSheet title={initial?.role_id ? 'Edit role' : 'New role'} onClose={onClose} onSave={save} saving={saving}>
      <Text style={styles.label}>Name</Text>
      <TextInput style={styles.input} value={name} onChangeText={setName} placeholder="e.g. Tutor, Pet sitter" placeholderTextColor={colors.textMuted} editable={!initial?.is_default} />
      {initial?.is_default && <Text style={styles.helper}>Default role names cannot be renamed (you can change icon and color).</Text>}
      <Text style={styles.label}>Type</Text>
      <View style={styles.chipWrap}>
        {(['family', 'staff'] as const).map((c) => (
          <TouchableOpacity key={c} style={[styles.chip, category === c && styles.chipActive]} onPress={() => setCategory(c)} disabled={!!initial?.is_default}>
            <Text style={[styles.chipTxt, category === c && styles.chipTxtActive]}>{c === 'family' ? 'Family' : 'Staff'}</Text>
          </TouchableOpacity>
        ))}
      </View>
      <Text style={styles.label}>Icon</Text>
      <View style={styles.iconRow}>
        {ROLE_ICON_OPTIONS.map((ic) => (
          <TouchableOpacity key={ic} style={[styles.iconChip, icon === ic && { backgroundColor: tints[color].icon }]} onPress={() => setIcon(ic)}>
            <Icon name={ic} size={16} color={icon === ic ? '#fff' : colors.textMain} />
          </TouchableOpacity>
        ))}
      </View>
      <Text style={styles.label}>Color</Text>
      <View style={styles.iconRow}>
        {TINT_OPTIONS.map((c) => (
          <TouchableOpacity key={c} style={[styles.colorChip, { backgroundColor: tints[c].icon }, color === c && { borderWidth: 3, borderColor: colors.textMain }]} onPress={() => setColor(c)} />
        ))}
      </View>
    </FormSheet>
  );
}

function HandbookForm({ initial, spaceId, onClose, onSaved }: any) {
  const isTemplate = initial?._template === true;
  const [title, setTitle] = useState(initial?.title || '');
  const [body, setBody] = useState(initial?.body || '');
  const [icon, setIcon] = useState(initial?.icon || 'BookOpen');
  const [color, setColor] = useState<keyof typeof tints>((initial?.color as any) || 'sage');
  const [photo, setPhoto] = useState<string | null>(initial?.photo_base64 || null);
  const [saving, setSaving] = useState(false);

  const save = async () => {
    if (!title.trim()) return;
    setSaving(true);
    try {
      const payload: any = { title: title.trim(), body, icon, color, photo_base64: photo };
      if (initial?.entry_id && !isTemplate) await api.patch(`/household/handbook/${initial.entry_id}`, payload);
      else await api.post('/household/handbook', { space_id: spaceId, ...payload });
      onSaved();
    } catch (e: any) { Alert.alert('Error', e?.message || ''); }
    finally { setSaving(false); }
  };

  const remove = async () => {
    if (!initial?.entry_id || isTemplate) return;
    Alert.alert('Delete card?', '', [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Delete', style: 'destructive', onPress: async () => {
        try { await api.delete(`/household/handbook/${initial.entry_id}`); onSaved(); } catch (e: any) { Alert.alert('Error', e?.message || ''); }
      }},
    ]);
  };

  return (
    <FormSheet title={initial?.entry_id && !isTemplate ? 'Edit handbook entry' : 'New handbook entry'} onClose={onClose} onSave={save} saving={saving}>
      <PhotoPicker photo={photo} onChange={setPhoto} color={tints[color].icon} />
      <Text style={styles.label}>Title</Text>
      <TextInput style={styles.input} value={title} onChangeText={setTitle} placeholder="e.g. Wifi, Doctor info" placeholderTextColor={colors.textMuted} />
      <Text style={styles.label}>Body</Text>
      <TextInput style={[styles.input, { minHeight: 120 }]} value={body} onChangeText={setBody} multiline placeholder="Type anything helpful — passwords, instructions, contacts" placeholderTextColor={colors.textMuted} textAlignVertical="top" />
      <Text style={styles.label}>Icon</Text>
      <View style={styles.iconRow}>
        {ROLE_ICON_OPTIONS.map((ic) => (
          <TouchableOpacity key={ic} style={[styles.iconChip, icon === ic && { backgroundColor: tints[color].icon }]} onPress={() => setIcon(ic)}>
            <Icon name={ic} size={16} color={icon === ic ? '#fff' : colors.textMain} />
          </TouchableOpacity>
        ))}
      </View>
      <Text style={styles.label}>Color</Text>
      <View style={styles.iconRow}>
        {TINT_OPTIONS.map((c) => (
          <TouchableOpacity key={c} style={[styles.colorChip, { backgroundColor: tints[c].icon }, color === c && { borderWidth: 3, borderColor: colors.textMain }]} onPress={() => setColor(c)} />
        ))}
      </View>
      {initial?.entry_id && !isTemplate && (
        <TouchableOpacity onPress={remove} style={styles.deleteRow}><Icon name="Trash2" size={14} color={colors.dangerText} /><Text style={styles.deleteTxt}>Delete card</Text></TouchableOpacity>
      )}
    </FormSheet>
  );
}

// ---------- Phase 2 section renderers ----------
const WEEKDAY_NAMES = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
const ATT_STATUSES: { key: AttendanceLog['status']; label: string; tint: keyof typeof tints }[] = [
  { key: 'present', label: 'Present', tint: 'sage' },
  { key: 'off', label: 'Off', tint: 'lavender' },
  { key: 'sick', label: 'Sick', tint: 'pink' },
  { key: 'leave', label: 'Leave', tint: 'peach' },
  { key: 'late', label: 'Late', tint: 'yellow' },
];

function DateNav({ date, onChange }: { date: string; onChange: (d: string) => void }) {
  const d = new Date(date + 'T00:00:00');
  const shift = (days: number) => {
    const n = new Date(d); n.setDate(d.getDate() + days);
    onChange(n.toISOString().slice(0, 10));
  };
  const today = new Date().toISOString().slice(0, 10);
  return (
    <View style={styles.dateNav}>
      <TouchableOpacity onPress={() => shift(-1)} style={styles.navBtn}><Icon name="ChevronRight" size={16} color={colors.textMain} /></TouchableOpacity>
      <View style={{ flex: 1, alignItems: 'center' }}>
        <Text style={styles.dateTxt}>{d.toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' })}</Text>
        {date !== today && <TouchableOpacity onPress={() => onChange(today)}><Text style={styles.todayLink}>Jump to today</Text></TouchableOpacity>}
      </View>
      <TouchableOpacity onPress={() => shift(1)} style={styles.navBtn}><Icon name="ChevronRight" size={16} color={colors.textMain} /></TouchableOpacity>
    </View>
  );
}

function TasksSection({ tasks, date, setDate, onEdit, onToggle }: any) {
  const visible = tasks.filter((t: TaskTemplate) => t.due_today);
  const done = visible.filter((t: TaskTemplate) => t.completed_today).length;
  return (
    <View style={{ gap: 8 }}>
      <DateNav date={date} onChange={setDate} />
      {visible.length === 0 ? (
        <View style={styles.empty}>
          <View style={[styles.heroIcon, { backgroundColor: tints.mint.bg }]}>
            <Icon name="Check" size={28} color={tints.mint.icon} />
          </View>
          <Text style={styles.emptyTitle}>No tasks today</Text>
          <Text style={styles.emptySub}>Create recurring task templates for staff (e.g. "Dust living room — daily") and tick them off as the day goes.</Text>
          <TouchableOpacity style={styles.ctaBtn} onPress={() => onEdit()} testID="tasks-cta">
            <Icon name="Plus" color="#fff" size={16} />
            <Text style={styles.ctaTxt}>Add a task</Text>
          </TouchableOpacity>
        </View>
      ) : (
        <>
          <Text style={styles.sectionTitle}>{done} of {visible.length} done</Text>
          {visible.map((t: TaskTemplate) => (
            <View key={t.task_id} style={[styles.row, t.completed_today && { opacity: 0.55 }]}>
              <TouchableOpacity style={[styles.checkBox, t.completed_today && styles.checkBoxDone]} onPress={() => onToggle(t)} testID={`task-toggle-${t.task_id}`}>
                {t.completed_today && <Icon name="Check" size={14} color="#fff" />}
              </TouchableOpacity>
              <TouchableOpacity style={{ flex: 1 }} onPress={() => onEdit(t)}>
                <Text style={[styles.rowName, t.completed_today && { textDecorationLine: 'line-through' }]} numberOfLines={2}>{t.title}</Text>
                <Text style={styles.rowSub}>
                  {t.staff_name ? t.staff_name : t.role_name ? `Any ${t.role_name}` : 'Anyone'}
                  {t.due_time ? ` · ${t.due_time}` : ''}
                  {t.recurrence !== 'daily' ? ` · ${t.recurrence}` : ''}
                </Text>
              </TouchableOpacity>
              <TouchableOpacity onPress={() => onEdit(t)} style={{ padding: 6 }}><Icon name="Edit3" size={14} color={colors.textMuted} /></TouchableOpacity>
            </View>
          ))}
          <Text style={[styles.sectionTitle, { marginTop: spacing.md }]}>All tasks</Text>
          {tasks.filter((t: TaskTemplate) => !t.due_today).map((t: TaskTemplate) => (
            <TouchableOpacity key={t.task_id} style={[styles.row, { opacity: 0.7 }]} onPress={() => onEdit(t)}>
              <View style={[styles.checkBox, { backgroundColor: colors.surfaceAlt }]}><Icon name="Clock" size={12} color={colors.textMuted} /></View>
              <View style={{ flex: 1 }}>
                <Text style={styles.rowName}>{t.title}</Text>
                <Text style={styles.rowSub}>
                  {t.recurrence === 'weekly' ? `Weekly · ${(t.weekdays || []).map((w) => WEEKDAY_NAMES[w]).join(', ')}` :
                   t.recurrence === 'monthly' ? `Monthly · day ${t.monthly_day}` :
                   t.recurrence === 'once' ? `One time · ${t.once_date}` : 'Daily'}
                  {t.staff_name ? ` · ${t.staff_name}` : ''}
                </Text>
              </View>
              <Icon name="ChevronRight" size={14} color={colors.textMuted} />
            </TouchableOpacity>
          ))}
        </>
      )}
    </View>
  );
}

function AttendanceSection({ staff, attendance, date, setDate, onSet }: any) {
  const statusByStaff: Record<string, AttendanceLog | undefined> = {};
  (attendance || []).forEach((a: AttendanceLog) => { statusByStaff[a.staff_id] = a; });
  if (staff.length === 0) {
    return (
      <View style={styles.empty}>
        <View style={[styles.heroIcon, { backgroundColor: tints.yellow.bg }]}><Icon name="Calendar" size={28} color={tints.yellow.icon} /></View>
        <Text style={styles.emptyTitle}>Add staff first</Text>
        <Text style={styles.emptySub}>Attendance needs at least one staff member. Head to the Staff tab to add your first helper.</Text>
      </View>
    );
  }
  return (
    <View style={{ gap: 8 }}>
      <DateNav date={date} onChange={setDate} />
      {staff.map((s: StaffMember) => {
        const cur = statusByStaff[s.staff_id];
        return (
          <View key={s.staff_id} style={styles.row}>
            <View style={[styles.avatar, { backgroundColor: tints.blue.icon }]}>
              {s.photo_base64 ? <Image source={{ uri: s.photo_base64 }} style={styles.avatarImg} /> : <Text style={styles.avatarTxt}>{s.name?.[0]?.toUpperCase()}</Text>}
            </View>
            <View style={{ flex: 1 }}>
              <Text style={styles.rowName}>{s.name}</Text>
              <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 4, marginTop: 6 }}>
                {ATT_STATUSES.map((st) => {
                  const active = cur?.status === st.key;
                  const t = tints[st.tint];
                  return (
                    <TouchableOpacity
                      key={st.key}
                      style={[styles.attChip, active && { backgroundColor: t.bg, borderColor: t.icon }]}
                      onPress={() => onSet(s.staff_id, st.key)}
                      testID={`att-${s.staff_id}-${st.key}`}
                    >
                      <Text style={[styles.attTxt, active && { color: t.icon, fontWeight: '800' }]}>{st.label}</Text>
                    </TouchableOpacity>
                  );
                })}
              </View>
            </View>
          </View>
        );
      })}
    </View>
  );
}

function ShoppingSection({ requests, onEdit, onStatus, currency }: any) {
  const [filter, setFilter] = useState<'pending' | 'approved' | 'purchased' | 'rejected' | 'all'>('pending');
  const counts = {
    pending: (requests || []).filter((r: ShoppingReq) => r.status === 'pending').length,
    approved: (requests || []).filter((r: ShoppingReq) => r.status === 'approved').length,
    purchased: (requests || []).filter((r: ShoppingReq) => r.status === 'purchased').length,
    rejected: (requests || []).filter((r: ShoppingReq) => r.status === 'rejected').length,
    all: (requests || []).length,
  };
  const filtered = filter === 'all' ? (requests || []) : (requests || []).filter((r: ShoppingReq) => r.status === filter);

  if (requests.length === 0) {
    return (
      <View style={styles.empty}>
        <View style={[styles.heroIcon, { backgroundColor: tints.pink.bg }]}><Icon name="ShoppingBag" size={28} color={tints.pink.icon} /></View>
        <Text style={styles.emptyTitle}>Shopping list</Text>
        <Text style={styles.emptySub}>Your staff will drop things here as they run out — rice, tissue, oil. Approve and buy, or reject.</Text>
        <TouchableOpacity style={styles.ctaBtn} onPress={() => onEdit()} testID="shopping-cta">
          <Icon name="Plus" color="#fff" size={16} />
          <Text style={styles.ctaTxt}>Add request</Text>
        </TouchableOpacity>
      </View>
    );
  }
  const filters: Array<{ key: typeof filter; label: string; count: number }> = [
    { key: 'pending', label: 'Pending', count: counts.pending },
    { key: 'approved', label: 'Approved', count: counts.approved },
    { key: 'purchased', label: 'Purchased', count: counts.purchased },
    { key: 'rejected', label: 'Rejected', count: counts.rejected },
    { key: 'all', label: 'All', count: counts.all },
  ];

  const card = (r: any) => {
    const urgT = r.urgency === 'high' ? tints.pink : r.urgency === 'low' ? tints.sage : tints.yellow;
    const curr = r.currency || currency || 'USD';
    const price = r.actual_price ?? r.estimated_price;
    const priceLabel = r.actual_price ? 'Paid' : r.estimated_price ? 'Est.' : '';
    const created = r.created_at ? new Date(r.created_at) : null;
    const purchased = r.purchased_at ? new Date(r.purchased_at) : null;
    const approved = r.approved_at ? new Date(r.approved_at) : null;
    return (
      <View key={r.request_id} style={styles.row}>
        {r.photo_base64 ? (
          <Image source={{ uri: r.photo_base64 }} style={styles.shopThumb} />
        ) : (
          <View style={[styles.avatar, { backgroundColor: urgT.icon }]}>
            <Icon name="ShoppingBag" size={18} color="#fff" />
          </View>
        )}
        <View style={{ flex: 1 }}>
          <Text style={styles.rowName}>{r.item_name}{r.quantity ? ` · ${r.quantity}` : ''}</Text>
          <Text style={styles.rowSub}>
            {r.requested_by_name || 'Someone'}
            {r.category_name ? ` · ${r.category_name}` : ''}
            {` · ${r.urgency}`}
          </Text>
          {price ? (
            <View style={styles.priceChip}>
              <Icon name="DollarSign" size={10} color={tints.sage.icon} />
              <Text style={styles.priceChipTxt}>{priceLabel} {formatMoney(price, curr)}</Text>
            </View>
          ) : null}
          {r.note ? <Text style={[styles.rowSub, { marginTop: 4, fontStyle: 'italic' }]}>"{r.note}"</Text> : null}
          {created ? (
            <Text style={styles.metaTime}>Requested {created.toLocaleDateString()} {created.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</Text>
          ) : null}
          {approved && r.status !== 'rejected' ? (
            <Text style={styles.metaTime}>Approved {approved.toLocaleDateString()} {approved.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</Text>
          ) : null}
          {purchased ? (
            <Text style={styles.metaTime}>Purchased {purchased.toLocaleDateString()} {purchased.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</Text>
          ) : null}
          {r.rejected_reason ? (
            <Text style={[styles.metaTime, { color: tints.pink.icon }]}>Rejected: "{r.rejected_reason}"</Text>
          ) : null}

          {/* Action row */}
          <View style={{ flexDirection: 'row', gap: 6, marginTop: 8, flexWrap: 'wrap' }}>
            {r.status === 'pending' && (
              <>
                <TouchableOpacity style={[styles.miniBtn, { backgroundColor: tints.sage.icon }]} onPress={() => onStatus(r, 'approved')} testID={`shop-approve-${r.request_id}`}>
                  <Text style={styles.miniBtnTxt}>Approve</Text>
                </TouchableOpacity>
                <TouchableOpacity style={[styles.miniBtn, { backgroundColor: tints.pink.icon }]} onPress={() => onStatus(r, 'rejected')} testID={`shop-reject-${r.request_id}`}>
                  <Text style={styles.miniBtnTxt}>Reject</Text>
                </TouchableOpacity>
              </>
            )}
            {r.status === 'approved' && (
              <TouchableOpacity style={[styles.miniBtn, { backgroundColor: colors.primary }]} onPress={() => onStatus(r, 'purchased')} testID={`shop-purchase-${r.request_id}`}>
                <Text style={styles.miniBtnTxt}>Mark purchased</Text>
              </TouchableOpacity>
            )}
            {r.status === 'rejected' && (
              <TouchableOpacity style={[styles.miniBtn, { backgroundColor: tints.sage.icon }]} onPress={() => onStatus(r, 'approved')}>
                <Text style={styles.miniBtnTxt}>Re-approve</Text>
              </TouchableOpacity>
            )}
          </View>
        </View>
        <TouchableOpacity onPress={() => onEdit(r)} style={{ padding: 6 }}>
          <Icon name="Edit3" size={14} color={colors.textMuted} />
        </TouchableOpacity>
      </View>
    );
  };

  return (
    <View style={{ gap: 8 }}>
      <View style={styles.shopFilterRow}>
        {filters.map((f) => (
          <TouchableOpacity
            key={f.key}
            style={[styles.shopFilterChip, filter === f.key && styles.shopFilterActive]}
            onPress={() => setFilter(f.key)}
            testID={`shop-filter-${f.key}`}
          >
            <Text style={[styles.shopFilterTxt, filter === f.key && styles.shopFilterTxtActive]}>{f.label}</Text>
            {f.count > 0 && (
              <View style={{ minWidth: 16, height: 16, borderRadius: 8, paddingHorizontal: 4, alignItems: 'center', justifyContent: 'center', backgroundColor: filter === f.key ? '#fff' : tints.pink.icon }}>
                <Text style={{ fontSize: 9, fontWeight: '900', color: filter === f.key ? colors.textMain : '#fff' }}>{f.count}</Text>
              </View>
            )}
          </TouchableOpacity>
        ))}
      </View>
      {filtered.length === 0 ? (
        <Text style={styles.emptyTxt}>No {filter} requests.</Text>
      ) : (
        filtered.map(card)
      )}
    </View>
  );
}

function TaskForm({ initial, spaceId, staff, roles, onClose, onSaved }: any) {
  const [title, setTitle] = useState(initial?.title || '');
  const [desc, setDesc] = useState(initial?.description || '');
  const [rec, setRec] = useState<TaskTemplate['recurrence']>(initial?.recurrence || 'daily');
  const [weekdays, setWeekdays] = useState<number[]>(initial?.weekdays || []);
  const [monthlyDay, setMonthlyDay] = useState<number>(initial?.monthly_day || 1);
  const [onceDate, setOnceDate] = useState<string>(initial?.once_date || new Date().toISOString().slice(0, 10));
  const [dueTime, setDueTime] = useState(initial?.due_time || '');
  const [staffId, setStaffId] = useState<string | null>(initial?.staff_id || null);
  const [roleId, setRoleId] = useState<string | null>(initial?.role_id || null);
  const [requiresPhoto, setRequiresPhoto] = useState<boolean>(!!initial?.requires_photo);
  const [saving, setSaving] = useState(false);

  const save = async () => {
    if (!title.trim()) return;
    setSaving(true);
    try {
      const payload: any = { title: title.trim(), description: desc || null, recurrence: rec, weekdays, monthly_day: monthlyDay, once_date: onceDate, due_time: dueTime || null, staff_id: staffId, role_id: roleId, requires_photo: requiresPhoto };
      if (initial?.task_id) await api.patch(`/household/tasks/${initial.task_id}`, payload);
      else await api.post('/household/tasks', { space_id: spaceId, ...payload });
      onSaved();
    } catch (e: any) { Alert.alert('Error', e?.message || ''); }
    finally { setSaving(false); }
  };
  const remove = async () => {
    if (!initial?.task_id) return;
    Alert.alert('Delete task?', 'Past completions stay as records.', [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Delete', style: 'destructive', onPress: async () => {
        try { await api.delete(`/household/tasks/${initial.task_id}`); onSaved(); } catch (e: any) { Alert.alert('Error', e?.message || ''); }
      }},
    ]);
  };

  return (
    <FormSheet title={initial?.task_id ? 'Edit task' : 'New task'} onClose={onClose} onSave={save} saving={saving}>
      <Text style={styles.label}>What should be done?</Text>
      <TextInput style={styles.input} value={title} onChangeText={setTitle} placeholder="e.g. Mop kitchen floor" placeholderTextColor={colors.textMuted} testID="task-form-title" />
      <Text style={styles.label}>Notes (optional)</Text>
      <TextInput style={[styles.input, { minHeight: 50 }]} value={desc} onChangeText={setDesc} multiline placeholder="Any instructions" placeholderTextColor={colors.textMuted} />

      <Text style={styles.label}>Recurrence</Text>
      <View style={styles.chipWrap}>
        {(['daily', 'weekly', 'monthly', 'once'] as const).map((r) => (
          <TouchableOpacity key={r} style={[styles.chip, rec === r && styles.chipActive]} onPress={() => setRec(r)}>
            <Text style={[styles.chipTxt, rec === r && styles.chipTxtActive]}>{r[0].toUpperCase() + r.slice(1)}</Text>
          </TouchableOpacity>
        ))}
      </View>

      {rec === 'weekly' && (
        <>
          <Text style={styles.label}>Days of week</Text>
          <View style={styles.chipWrap}>
            {WEEKDAY_NAMES.map((w, i) => (
              <TouchableOpacity key={w} style={[styles.chip, weekdays.includes(i) && styles.chipActive]}
                onPress={() => setWeekdays((cur) => cur.includes(i) ? cur.filter((x) => x !== i) : [...cur, i])}
              >
                <Text style={[styles.chipTxt, weekdays.includes(i) && styles.chipTxtActive]}>{w}</Text>
              </TouchableOpacity>
            ))}
          </View>
        </>
      )}
      {rec === 'monthly' && (
        <>
          <Text style={styles.label}>Day of month (1–31)</Text>
          <TextInput style={styles.input} value={String(monthlyDay)} onChangeText={(t) => setMonthlyDay(Math.max(1, Math.min(31, parseInt(t || '1', 10) || 1)))} keyboardType="number-pad" />
        </>
      )}
      {rec === 'once' && (
        <>
          <Text style={styles.label}>Date (YYYY-MM-DD)</Text>
          <TextInput style={styles.input} value={onceDate} onChangeText={setOnceDate} placeholder="YYYY-MM-DD" placeholderTextColor={colors.textMuted} />
        </>
      )}

      <Text style={styles.label}>Due time (optional)</Text>
      <TextInput style={styles.input} value={dueTime} onChangeText={setDueTime} placeholder="e.g. 07:30" placeholderTextColor={colors.textMuted} />

      <Text style={styles.label}>Assigned to (pick one)</Text>
      <View style={styles.chipWrap}>
        <TouchableOpacity style={[styles.chip, !staffId && !roleId && styles.chipActive]} onPress={() => { setStaffId(null); setRoleId(null); }}>
          <Text style={[styles.chipTxt, !staffId && !roleId && styles.chipTxtActive]}>Anyone</Text>
        </TouchableOpacity>
        {staff.map((s: StaffMember) => (
          <TouchableOpacity key={s.staff_id} style={[styles.chip, staffId === s.staff_id && styles.chipActive]} onPress={() => { setStaffId(s.staff_id); setRoleId(null); }}>
            <Text style={[styles.chipTxt, staffId === s.staff_id && styles.chipTxtActive]}>{s.name}</Text>
          </TouchableOpacity>
        ))}
      </View>
      <Text style={styles.label}>Or any staff with role</Text>
      <View style={styles.chipWrap}>
        {roles.filter((r: HouseholdRole) => r.category === 'staff').map((r: HouseholdRole) => (
          <TouchableOpacity key={r.role_id} style={[styles.chip, roleId === r.role_id && styles.chipActive]} onPress={() => { setRoleId(r.role_id); setStaffId(null); }}>
            <Text style={[styles.chipTxt, roleId === r.role_id && styles.chipTxtActive]}>{r.name}</Text>
          </TouchableOpacity>
        ))}
      </View>

      <TouchableOpacity style={styles.photoCheckRow} onPress={() => setRequiresPhoto((v) => !v)}>
        <View style={[styles.checkBox, requiresPhoto && styles.checkBoxDone]}>
          {requiresPhoto && <Icon name="Check" size={12} color="#fff" />}
        </View>
        <Text style={{ fontSize: 13, color: colors.textMain, fontWeight: '600' }}>Require photo proof when marked done</Text>
      </TouchableOpacity>

      {initial?.task_id && (
        <TouchableOpacity onPress={remove} style={styles.deleteRow}>
          <Icon name="Trash2" size={14} color={colors.dangerText} /><Text style={styles.deleteTxt}>Delete task</Text>
        </TouchableOpacity>
      )}
    </FormSheet>
  );
}

function ShoppingForm({ initial, spaceId, categories, staff, onClose, onSaved }: any) {
  const [name, setName] = useState(initial?.item_name || '');
  const [qty, setQty] = useState(initial?.quantity || '');
  const [urgency, setUrgency] = useState<ShoppingReq['urgency']>(initial?.urgency || 'normal');
  const [categoryId, setCategoryId] = useState<string | null>(initial?.category_id || null);
  const [staffId, setStaffId] = useState<string | null>(initial?.requested_by_staff_id || null);
  const [note, setNote] = useState(initial?.note || '');
  const [saving, setSaving] = useState(false);

  const save = async () => {
    if (!name.trim()) return;
    setSaving(true);
    try {
      const payload: any = { item_name: name.trim(), quantity: qty || null, urgency, category_id: categoryId, note: note || null, requested_by_staff_id: staffId };
      if (initial?.request_id) await api.patch(`/household/shopping/${initial.request_id}`, payload);
      else await api.post('/household/shopping', { space_id: spaceId, ...payload });
      onSaved();
    } catch (e: any) { Alert.alert('Error', e?.message || ''); }
    finally { setSaving(false); }
  };
  const remove = async () => {
    if (!initial?.request_id) return;
    try { await api.delete(`/household/shopping/${initial.request_id}`); onSaved(); }
    catch (e: any) { Alert.alert('Error', e?.message || ''); }
  };

  return (
    <FormSheet title={initial?.request_id ? 'Edit shopping request' : 'New shopping request'} onClose={onClose} onSave={save} saving={saving}>
      <Text style={styles.label}>Item</Text>
      <TextInput style={styles.input} value={name} onChangeText={setName} placeholder="e.g. Rice" placeholderTextColor={colors.textMuted} testID="shop-form-name" />
      <Text style={styles.label}>Quantity (optional)</Text>
      <TextInput style={styles.input} value={qty} onChangeText={setQty} placeholder="e.g. 5 kg, 2 bottles" placeholderTextColor={colors.textMuted} />
      <Text style={styles.label}>Urgency</Text>
      <View style={styles.chipWrap}>
        {(['low', 'normal', 'high'] as const).map((u) => (
          <TouchableOpacity key={u} style={[styles.chip, urgency === u && styles.chipActive]} onPress={() => setUrgency(u)}>
            <Text style={[styles.chipTxt, urgency === u && styles.chipTxtActive]}>{u[0].toUpperCase() + u.slice(1)}</Text>
          </TouchableOpacity>
        ))}
      </View>
      {staff.length > 0 && (
        <>
          <Text style={styles.label}>Requested by (optional)</Text>
          <View style={styles.chipWrap}>
            <TouchableOpacity style={[styles.chip, !staffId && styles.chipActive]} onPress={() => setStaffId(null)}>
              <Text style={[styles.chipTxt, !staffId && styles.chipTxtActive]}>Me</Text>
            </TouchableOpacity>
            {staff.map((s: StaffMember) => (
              <TouchableOpacity key={s.staff_id} style={[styles.chip, staffId === s.staff_id && styles.chipActive]} onPress={() => setStaffId(s.staff_id)}>
                <Text style={[styles.chipTxt, staffId === s.staff_id && styles.chipTxtActive]}>{s.name}</Text>
              </TouchableOpacity>
            ))}
          </View>
        </>
      )}
      {categories.length > 0 && (
        <>
          <Text style={styles.label}>Log into category (optional)</Text>
          <View style={styles.chipWrap}>
            <TouchableOpacity style={[styles.chip, !categoryId && styles.chipActive]} onPress={() => setCategoryId(null)}>
              <Text style={[styles.chipTxt, !categoryId && styles.chipTxtActive]}>None</Text>
            </TouchableOpacity>
            {categories.map((c: any) => (
              <TouchableOpacity key={c.category_id} style={[styles.chip, categoryId === c.category_id && styles.chipActive]} onPress={() => setCategoryId(c.category_id)}>
                <Text style={[styles.chipTxt, categoryId === c.category_id && styles.chipTxtActive]}>{c.name}</Text>
              </TouchableOpacity>
            ))}
          </View>
        </>
      )}
      <Text style={styles.label}>Note (optional)</Text>
      <TextInput style={[styles.input, { minHeight: 50 }]} value={note} onChangeText={setNote} multiline placeholder="Any details" placeholderTextColor={colors.textMuted} />
      {initial?.request_id && (
        <TouchableOpacity onPress={remove} style={styles.deleteRow}>
          <Icon name="Trash2" size={14} color={colors.dangerText} /><Text style={styles.deleteTxt}>Delete request</Text>
        </TouchableOpacity>
      )}
    </FormSheet>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background },
  header: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: spacing.md, paddingTop: spacing.sm, paddingBottom: 4 },
  iconBtn: { width: 40, height: 40, borderRadius: 20, backgroundColor: colors.surface, alignItems: 'center', justifyContent: 'center', ...shadows.card },
  kicker: { fontSize: 11, color: colors.textMuted, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 0.5 },
  title: { fontSize: 28, fontWeight: '900', color: colors.textMain, letterSpacing: -0.5 },
  banner: { flexDirection: 'row', alignItems: 'center', gap: 8, padding: 10, marginHorizontal: spacing.md, borderRadius: radius.md, marginBottom: 6 },
  bannerTxt: { flex: 1, fontSize: 12, color: colors.textMain, lineHeight: 16 },
  tabRow: { paddingHorizontal: spacing.md, gap: 8, paddingVertical: 8 },
  tabChip: { flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 14, paddingVertical: 8, borderRadius: radius.full, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border },
  chipBadge: { minWidth: 18, height: 18, borderRadius: 9, backgroundColor: tints.pink.icon, paddingHorizontal: 5, alignItems: 'center', justifyContent: 'center', marginLeft: 2 },
  chipBadgeTxt: { fontSize: 10, fontWeight: '900', color: '#fff' },
  shopFilterRow: { flexDirection: 'row', gap: 6, flexWrap: 'wrap', marginBottom: 8 },
  shopFilterChip: { flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 10, paddingVertical: 6, borderRadius: radius.full, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border },
  shopFilterActive: { backgroundColor: colors.textMain, borderColor: colors.textMain },
  shopFilterTxt: { fontSize: 11, fontWeight: '700', color: colors.textMuted },
  shopFilterTxtActive: { color: '#fff' },
  shopThumb: { width: 44, height: 44, borderRadius: radius.sm, marginRight: 8 },
  priceChip: { flexDirection: 'row', alignItems: 'center', gap: 3, paddingHorizontal: 6, paddingVertical: 2, borderRadius: radius.sm, backgroundColor: tints.sage.bg, marginTop: 4, alignSelf: 'flex-start' },
  priceChipTxt: { fontSize: 10, fontWeight: '800', color: tints.sage.icon },
  metaTime: { fontSize: 10, color: colors.textMuted, marginTop: 2 },
  tabTxt: { fontSize: 12, fontWeight: '700', color: colors.textMuted },
  scroll: { padding: spacing.md, paddingBottom: 120 },
  empty: { alignItems: 'center', paddingVertical: 40 },
  heroIcon: { width: 80, height: 80, borderRadius: 40, alignItems: 'center', justifyContent: 'center', marginBottom: spacing.md },
  emptyTitle: { fontSize: 18, fontWeight: '800', color: colors.textMain, textAlign: 'center' },
  emptySub: { fontSize: 13, color: colors.textMuted, textAlign: 'center', marginTop: 8, lineHeight: 20, paddingHorizontal: spacing.md },
  ctaBtn: { flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: colors.primary, paddingHorizontal: 20, paddingVertical: 12, borderRadius: radius.full, marginTop: 20, ...shadows.button },
  ctaTxt: { color: '#fff', fontWeight: '800' },
  row: { flexDirection: 'row', alignItems: 'center', gap: 12, backgroundColor: colors.surface, padding: spacing.md, borderRadius: radius.md, ...shadows.card },
  avatar: { width: 44, height: 44, borderRadius: 16, alignItems: 'center', justifyContent: 'center', overflow: 'hidden' },
  avatarImg: { width: '100%', height: '100%' },
  avatarTxt: { color: '#fff', fontWeight: '800', fontSize: 16 },
  rowName: { fontSize: 15, fontWeight: '700', color: colors.textMain },
  rowSub: { fontSize: 11, color: colors.textMuted, marginTop: 2 },
  badge: { flexDirection: 'row', alignItems: 'center', gap: 4, alignSelf: 'flex-start', paddingHorizontal: 8, paddingVertical: 3, borderRadius: radius.full, marginTop: 6 },
  badgeTxt: { fontSize: 10, fontWeight: '800' },
  sectionTitle: { fontSize: 12, fontWeight: '800', color: colors.textMuted, textTransform: 'uppercase', letterSpacing: 0.5 },
  handbookCard: { flexDirection: 'row', alignItems: 'flex-start', gap: 12, padding: spacing.md, borderRadius: radius.lg },
  hbIcon: { width: 36, height: 36, borderRadius: 12, alignItems: 'center', justifyContent: 'center' },
  hbTitle: { fontSize: 14, fontWeight: '800', color: colors.textMain },
  hbPhoto: { width: '100%', height: 120, borderRadius: 10, marginTop: 8, backgroundColor: '#00000010' },
  hbBody: { fontSize: 12, color: colors.textMuted, marginTop: 4, lineHeight: 18 },
  templateChip: { flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 12, paddingVertical: 8, borderRadius: radius.full, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border },
  templateTxt: { fontSize: 12, fontWeight: '700', color: colors.textMain },

  modalOverlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.4)', justifyContent: 'flex-end' },
  sheet: { backgroundColor: colors.surface, borderTopLeftRadius: 32, borderTopRightRadius: 32, padding: spacing.lg, paddingBottom: 32, maxHeight: '92%' },
  sheetHandle: { width: 40, height: 4, borderRadius: 2, backgroundColor: colors.border, alignSelf: 'center', marginBottom: 16 },
  sheetTitle: { fontSize: 18, fontWeight: '800', color: colors.textMain, marginBottom: spacing.md },
  label: { fontSize: 11, fontWeight: '800', color: colors.textMuted, textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 6, marginTop: 10 },
  helper: { fontSize: 11, color: colors.textMuted, fontStyle: 'italic', marginTop: -2 },
  input: { backgroundColor: colors.surfaceAlt, borderRadius: radius.md, paddingHorizontal: spacing.md, paddingVertical: 12, fontSize: 15, color: colors.textMain },
  chipWrap: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  chip: { paddingHorizontal: 12, paddingVertical: 8, borderRadius: radius.full, backgroundColor: colors.surfaceAlt },
  chipActive: { backgroundColor: colors.primary },
  chipTxt: { fontSize: 12, fontWeight: '700', color: colors.textMain },
  chipTxtActive: { color: '#fff' },
  iconRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  iconChip: { width: 40, height: 40, borderRadius: 12, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.surfaceAlt },
  colorChip: { width: 32, height: 32, borderRadius: 16 },
  photoPicker: { width: 80, height: 80, borderRadius: 16, alignItems: 'center', justifyContent: 'center', borderWidth: 2, borderStyle: 'dashed', alignSelf: 'center', marginBottom: spacing.sm, gap: 4, overflow: 'hidden' },
  photoImg: { width: '100%', height: '100%' },
  photoRemove: { position: 'absolute', top: 4, right: 4, backgroundColor: 'rgba(0,0,0,0.6)', width: 22, height: 22, borderRadius: 11, alignItems: 'center', justifyContent: 'center' },
  photoTxt: { fontSize: 11, fontWeight: '700' },
  actionRow: { flexDirection: 'row', gap: 10, marginTop: spacing.lg },
  cancelBtn: { flex: 1, paddingVertical: 14, borderRadius: radius.full, alignItems: 'center', backgroundColor: colors.surfaceAlt },
  cancelTxt: { color: colors.textMain, fontWeight: '700' },
  saveBtn: { flex: 2, paddingVertical: 14, borderRadius: radius.full, alignItems: 'center', backgroundColor: colors.primary, ...shadows.button },
  saveTxt: { color: '#fff', fontWeight: '800' },
  deleteRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, padding: 12, marginTop: 12 },
  deleteTxt: { fontSize: 12, color: colors.dangerText, fontWeight: '700' },
  inviteBox: { flexDirection: 'row', alignItems: 'center', gap: 12, backgroundColor: tints.blue.bg, padding: spacing.md, borderRadius: radius.md, marginTop: spacing.md },
  inviteCode: { fontSize: 22, fontWeight: '900', color: tints.blue.icon, letterSpacing: 3, marginVertical: 2 },
  copyBtn: { flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 12, paddingVertical: 8, backgroundColor: colors.surface, borderRadius: radius.full },
  copyTxt: { fontSize: 12, fontWeight: '800', color: colors.textMain },
  payBox: { backgroundColor: tints.peach.bg, padding: spacing.md, borderRadius: radius.md, marginTop: spacing.md, gap: 8 },
  payNowBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, backgroundColor: colors.primary, paddingVertical: 12, borderRadius: radius.full, ...shadows.button },
  permRow: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 10 },
  switch: { width: 44, height: 24, borderRadius: 12, backgroundColor: '#D6CFC9', padding: 2 },
  switchDot: { width: 20, height: 20, borderRadius: 10, backgroundColor: '#fff', position: 'absolute', top: 2, left: 2 },
  staffActions: { flexDirection: 'row', gap: 6, paddingHorizontal: spacing.md, paddingBottom: spacing.sm },
  actionBtn: { flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 4, paddingVertical: 8, borderRadius: radius.full, backgroundColor: colors.surfaceAlt, borderWidth: 1, borderColor: colors.border },
  actionTxt: { fontSize: 11, fontWeight: '800', color: colors.textMain },
  quickPanel: { padding: spacing.md, paddingTop: 0, gap: 2 },
  scChip: { flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 10, paddingVertical: 6, borderRadius: radius.full, backgroundColor: tints.mint.bg, borderWidth: 1, borderColor: tints.mint.icon },
  scChipTxt: { fontSize: 11, fontWeight: '800', color: colors.primary },
  sendBtn: { flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 4, paddingVertical: 10, borderRadius: radius.full, backgroundColor: colors.primary },
  sendBtnTxt: { color: '#fff', fontWeight: '800', fontSize: 12 },
  sendBtnAlt: { flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 4, paddingVertical: 10, borderRadius: radius.full, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.primary },
  sendBtnAltTxt: { color: colors.primary, fontWeight: '800', fontSize: 12 },
  activeToggle: { flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 10, paddingVertical: 10, borderRadius: radius.md, backgroundColor: colors.surfaceAlt, borderWidth: 1, borderColor: colors.border },
  activeToggleTxt: { fontSize: 11, fontWeight: '800', color: colors.textMuted },
  codeChip: { flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 8, paddingVertical: 3, borderRadius: radius.sm, backgroundColor: tints.yellow.bg, borderWidth: 1, borderColor: tints.yellow.icon, marginTop: 4, alignSelf: 'flex-start' },
  codeChipTxt: { fontSize: 10, fontWeight: '900', color: tints.yellow.icon, letterSpacing: 1.2 },
  payNowTxt: { color: '#fff', fontWeight: '800' },
  checkBox: { width: 28, height: 28, borderRadius: 8, borderWidth: 2, borderColor: colors.border, alignItems: 'center', justifyContent: 'center' },
  checkBoxDone: { backgroundColor: colors.primary, borderColor: colors.primary },
  dateNav: { flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: colors.surface, padding: 8, borderRadius: radius.md, marginBottom: 4, ...shadows.card },
  navBtn: { width: 36, height: 36, borderRadius: 18, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.surfaceAlt },
  dateTxt: { fontSize: 14, fontWeight: '800', color: colors.textMain },
  todayLink: { fontSize: 11, color: colors.primary, marginTop: 2, fontWeight: '700' },
  attChip: { paddingHorizontal: 10, paddingVertical: 5, borderRadius: radius.full, backgroundColor: colors.surfaceAlt, borderWidth: 1, borderColor: 'transparent' },
  attTxt: { fontSize: 11, fontWeight: '700', color: colors.textMuted },
  miniBtn: { paddingHorizontal: 10, paddingVertical: 6, borderRadius: radius.full },
  miniBtnTxt: { color: '#fff', fontWeight: '800', fontSize: 11 },
  photoCheckRow: { flexDirection: 'row', alignItems: 'center', gap: 10, marginTop: 14, padding: 8 },
});
