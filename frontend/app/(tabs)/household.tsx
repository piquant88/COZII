import React, { useState, useCallback } from 'react';
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
import type { HouseholdRole, FamilyMember, StaffMember, HandbookEntry } from '../../src/types';

const SECTIONS = [
  { key: 'people', label: 'People', icon: 'Users', tint: 'peach' },
  { key: 'staff', label: 'Staff', icon: 'User', tint: 'blue' },
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

  // modal state — generic dispatch
  const [edit, setEdit] = useState<{ kind: 'people' | 'staff' | 'role' | 'handbook'; data?: any } | null>(null);

  const load = useCallback(async () => {
    if (!activeSpace) return;
    try {
      const [r, p, s, h] = await Promise.all([
        api.get<HouseholdRole[]>(`/household/roles?space_id=${activeSpace.space_id}`),
        api.get<FamilyMember[]>(`/household/family?space_id=${activeSpace.space_id}`),
        api.get<StaffMember[]>(`/household/staff?space_id=${activeSpace.space_id}`),
        api.get<HandbookEntry[]>(`/household/handbook?space_id=${activeSpace.space_id}`),
      ]);
      setRoles(r); setPeople(p); setStaff(s); setHandbook(h);
    } catch (e) { console.warn(e); }
    finally { setLoading(false); }
  }, [activeSpace]);

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
        <TouchableOpacity
          style={styles.iconBtn}
          onPress={() => {
            if (section === 'people') setEdit({ kind: 'people' });
            else if (section === 'staff') setEdit({ kind: 'staff' });
            else if (section === 'roles') setEdit({ kind: 'role' });
            else if (section === 'handbook') setEdit({ kind: 'handbook' });
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
            return (
              <TouchableOpacity
                key={s.key}
                style={[styles.tabChip, active && { backgroundColor: t.bg, borderColor: t.icon }]}
                onPress={() => setSection(s.key)}
                testID={`household-tab-${s.key}`}
              >
                <Icon name={s.icon} size={16} color={active ? t.icon : colors.textMuted} />
                <Text style={[styles.tabTxt, active && { color: t.icon, fontWeight: '800' }]}>{s.label}</Text>
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
          <StaffSection staff={staff} roles={roles.filter((r) => r.category === 'staff')} currency={activeSpace.currency || 'USD'} onEdit={(s) => setEdit({ kind: 'staff', data: s })} />
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

function StaffSection({ staff, roles, currency, onEdit }: { staff: StaffMember[]; roles: HouseholdRole[]; currency: string; onEdit: (s?: StaffMember) => void }) {
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
      {staff.map((s) => {
        const role = roles.find((r) => r.role_id === s.role_id);
        const t = tints[(role?.color as keyof typeof tints) || 'blue'];
        return (
          <TouchableOpacity key={s.staff_id} style={styles.row} onPress={() => onEdit(s)} testID={`household-staff-${s.staff_id}`} activeOpacity={0.8}>
            <View style={[styles.avatar, { backgroundColor: t.icon }]}>
              {s.photo_base64 ? <Image source={{ uri: s.photo_base64 }} style={styles.avatarImg} /> : <Text style={styles.avatarTxt}>{s.name?.[0]?.toUpperCase()}</Text>}
            </View>
            <View style={{ flex: 1 }}>
              <Text style={styles.rowName}>{s.name}</Text>
              <Text style={styles.rowSub}>
                {role?.name || 'No role'}
                {s.phone ? ` · ${s.phone}` : ''}
                {s.off_day ? ` · off ${s.off_day}` : ''}
              </Text>
              {s.salary ? (
                <View style={[styles.badge, { backgroundColor: tints.sage.bg }]}>
                  <Icon name="DollarSign" size={10} color={tints.sage.icon} />
                  <Text style={[styles.badgeTxt, { color: tints.sage.icon }]}>{formatMoney(s.salary, s.salary_currency || currency)} / {s.pay_cycle}</Text>
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
  const [notes, setNotes] = useState(initial?.notes || '');
  const [saving, setSaving] = useState(false);

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
        notes: notes || null,
      };
      if (initial?.staff_id) await api.patch(`/household/staff/${initial.staff_id}`, payload);
      else await api.post('/household/staff', { space_id: spaceId, ...payload });
      onSaved();
    } catch (e: any) { Alert.alert('Error', e?.message || ''); }
    finally { setSaving(false); }
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
      <Text style={styles.label}>Notes</Text>
      <TextInput style={[styles.input, { minHeight: 60 }]} value={notes} onChangeText={setNotes} multiline placeholder="responsibilities, agreement, anything important" placeholderTextColor={colors.textMuted} />
      {initial?.staff_id && (
        <TouchableOpacity onPress={remove} style={styles.deleteRow}><Icon name="Trash2" size={14} color={colors.dangerText} /><Text style={styles.deleteTxt}>Remove from staff</Text></TouchableOpacity>
      )}
    </FormSheet>
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
  const [saving, setSaving] = useState(false);

  const save = async () => {
    if (!title.trim()) return;
    setSaving(true);
    try {
      const payload: any = { title: title.trim(), body, icon, color };
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
});
