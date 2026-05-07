import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity, TextInput,
  ActivityIndicator, Alert, KeyboardAvoidingView, Platform, Image, Modal,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { useAuth } from '../src/AuthContext';
import { api } from '../src/api';
import { colors, radius, spacing, shadows, tints } from '../src/theme';
import { Icon } from '../src/Icon';
import { SignaturePad } from '../src/SignaturePad';
import { realtime } from '../src/realtime';

type Sig = {
  role: 'owner' | 'staff';
  user_id: string;
  name?: string | null;
  typed_name?: string | null;
  drawing_base64?: string | null;
  signed_at: string;
  ip?: string | null;
  user_agent?: string | null;
};

type Contract = {
  contract_id: string;
  space_id: string;
  template_kind: string;
  title: string;
  body: string;
  variables: Record<string, any>;
  assigned_staff_id?: string | null;
  assigned_staff_name?: string | null;
  require_owner_signature: boolean;
  require_staff_signature: boolean;
  require_drawn_signature_owner: boolean;
  require_drawn_signature_staff: boolean;
  status: 'pending' | 'signed' | 'void';
  owner_signature: Sig | null;
  staff_signature: Sig | null;
  created_by: string;
  created_by_name?: string | null;
  created_at: string;
};

export default function ContractViewScreen() {
  const router = useRouter();
  const params = useLocalSearchParams<{ id: string }>();
  const { activeSpace, user, spaceRole } = useAuth();
  const [contract, setContract] = useState<Contract | null>(null);
  const [renderedBody, setRenderedBody] = useState('');
  const [loading, setLoading] = useState(true);
  const [signOpen, setSignOpen] = useState(false);
  const [typedName, setTypedName] = useState('');
  const [drawing, setDrawing] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [assignedStaff, setAssignedStaff] = useState<any>(null);
  const [allStaff, setAllStaff] = useState<any[]>([]);
  const [reassignOpen, setReassignOpen] = useState(false);
  const [drawingActive, setDrawingActive] = useState(false);

  const load = useCallback(async () => {
    if (!params.id) return;
    setLoading(true);
    try {
      const c = await api.get<Contract>(`/contracts/${params.id}`);
      setContract(c);
      const r = await api.get<{ rendered_body: string }>(`/contracts/${params.id}/render`);
      setRenderedBody(r.rendered_body || c.body);
      // Fetch staff list (used for assignment + invite-code callout)
      if (activeSpace) {
        try {
          const staffList = await api.get<any[]>(`/household/staff?space_id=${activeSpace.space_id}`);
          setAllStaff(staffList || []);
          if (c.assigned_staff_id) {
            setAssignedStaff((staffList || []).find((s) => s.staff_id === c.assigned_staff_id) || null);
          } else {
            setAssignedStaff(null);
          }
        } catch {}
      }
    } catch (e: any) {
      Alert.alert('Could not load', e?.message || 'Try again.');
    } finally { setLoading(false); }
  }, [params.id, activeSpace]);
  useEffect(() => { load(); }, [load]);

  // Realtime: refresh this contract on relevant events
  useEffect(() => {
    if (!params.id) return;
    const off = realtime.onSpaceEvent((e) => {
      if (e.kind === 'contract' && e.payload?.contract_id === params.id) {
        load();
      }
    });
    return off;
  }, [params.id, load]);

  const reassign = async (staffId: string) => {
    if (!contract) return;
    try {
      const updated = await api.patch<Contract>(`/contracts/${contract.contract_id}`, { assigned_staff_id: staffId });
      setContract(updated);
      const sm = allStaff.find((s) => s.staff_id === staffId) || null;
      setAssignedStaff(sm);
      setReassignOpen(false);
      Alert.alert('Assigned', `Contract assigned to ${sm?.name || 'staff'}. ${sm?.user_id ? 'They have been notified.' : 'Share their invite code to let them sign.'}`);
    } catch (e: any) {
      Alert.alert('Could not reassign', e?.message || 'Try again.');
    }
  };

  const isOwner = useMemo(() => spaceRole?.role !== 'staff', [spaceRole]);

  const myRole: 'owner' | 'staff' | null = useMemo(() => {
    if (!contract) return null;
    if (isOwner) return 'owner';
    return 'staff';
  }, [contract, isOwner]);

  const mySignature: Sig | null = useMemo(() => {
    if (!contract || !myRole) return null;
    return myRole === 'owner' ? contract.owner_signature : contract.staff_signature;
  }, [contract, myRole]);

  const otherSignature: Sig | null = useMemo(() => {
    if (!contract || !myRole) return null;
    return myRole === 'owner' ? contract.staff_signature : contract.owner_signature;
  }, [contract, myRole]);

  const requireDrawnForMe = useMemo(() => {
    if (!contract || !myRole) return false;
    return myRole === 'owner' ? contract.require_drawn_signature_owner : contract.require_drawn_signature_staff;
  }, [contract, myRole]);

  const myTurnToSign = useMemo(() => {
    if (!contract || !myRole) return false;
    if (contract.status === 'void') return false;
    if (myRole === 'owner' && contract.require_owner_signature && !contract.owner_signature) return true;
    if (myRole === 'staff' && contract.require_staff_signature && !contract.staff_signature) return true;
    return false;
  }, [contract, myRole]);

  const submitSign = async () => {
    if (!contract) return;
    if (requireDrawnForMe && !drawing) {
      Alert.alert('Draw your signature', 'This contract requires a hand-drawn signature.');
      return;
    }
    if (!drawing && !typedName.trim()) {
      Alert.alert('Sign first', 'Type your name or draw your signature.');
      return;
    }
    setSubmitting(true);
    try {
      const updated = await api.post<Contract>(`/contracts/${contract.contract_id}/sign`, {
        typed_name: typedName.trim() || null,
        drawing_base64: drawing || null,
      });
      setContract(updated);
      setSignOpen(false);
      setTypedName('');
      setDrawing(null);
      Alert.alert('Signed', 'Your signature has been recorded.');
    } catch (e: any) {
      Alert.alert('Could not sign', e?.message || 'Try again.');
    } finally { setSubmitting(false); }
  };

  const voidIt = () => {
    if (!contract) return;
    Alert.alert('Void this contract?', 'This will mark the agreement as void. It cannot be signed any more.', [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Void it', style: 'destructive', onPress: async () => {
        try {
          const updated = await api.post<Contract>(`/contracts/${contract.contract_id}/void`, {});
          setContract(updated);
        } catch (e: any) { Alert.alert('Error', e?.message || ''); }
      }},
    ]);
  };

  const deleteIt = () => {
    if (!contract) return;
    Alert.alert('Delete contract?', 'Permanently remove this draft.', [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Delete', style: 'destructive', onPress: async () => {
        try {
          await api.delete(`/contracts/${contract.contract_id}`);
          router.back();
        } catch (e: any) { Alert.alert('Error', e?.message || ''); }
      }},
    ]);
  };

  if (loading || !contract) {
    return (
      <SafeAreaView style={styles.container} edges={['top']}>
        <ActivityIndicator color={colors.primary} style={{ marginTop: 80 }} />
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.container} edges={['top', 'bottom']}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.backBtn}>
          <Icon name="ChevronRight" size={18} color={colors.textMain} />
        </TouchableOpacity>
        <View style={{ flex: 1 }}>
          <Text style={styles.kicker}>{contract.template_kind.toUpperCase()}</Text>
          <Text style={styles.title} numberOfLines={1}>{contract.title}</Text>
        </View>
        {isOwner && contract.status !== 'void' && (
          <TouchableOpacity onPress={voidIt} style={styles.iconBtn} testID="contract-void">
            <Icon name="X" size={16} color={colors.dangerText} />
          </TouchableOpacity>
        )}
        {isOwner && (
          <TouchableOpacity onPress={deleteIt} style={styles.iconBtn} testID="contract-delete">
            <Icon name="Trash2" size={16} color={colors.dangerText} />
          </TouchableOpacity>
        )}
      </View>

      <ScrollView contentContainerStyle={styles.scroll}>
        {/* Status pill */}
        <View style={styles.statusRow}>
          <View style={[styles.statusPill, {
            backgroundColor: contract.status === 'signed' ? tints.sage.bg : contract.status === 'void' ? tints.pink.bg : tints.yellow.bg,
          }]}>
            <Icon
              name={contract.status === 'signed' ? 'CheckCircle2' : contract.status === 'void' ? 'X' : 'Clock'}
              size={14}
              color={contract.status === 'signed' ? tints.sage.icon : contract.status === 'void' ? tints.pink.icon : tints.yellow.icon}
            />
            <Text style={[styles.statusTxt, {
              color: contract.status === 'signed' ? tints.sage.icon : contract.status === 'void' ? tints.pink.icon : tints.yellow.icon,
            }]}>
              {contract.status === 'signed' ? 'Fully signed' : contract.status === 'void' ? 'Voided' : 'Pending signatures'}
            </Text>
          </View>
          {contract.assigned_staff_name ? (
            <Text style={styles.assignedTxt}>For {contract.assigned_staff_name}</Text>
          ) : null}
        </View>

        {/* Owner has not assigned a staff yet — block the flow with an obvious CTA */}
        {isOwner && !contract.assigned_staff_id && contract.status !== 'void' && (
          <TouchableOpacity style={[styles.inviteBox, { borderColor: tints.pink.icon, backgroundColor: tints.pink.bg }]} onPress={() => setReassignOpen(true)} testID="contract-assign-cta">
            <View style={{ flex: 1 }}>
              <Text style={[styles.inviteTitle, { color: tints.pink.icon }]}>No staff assigned</Text>
              <Text style={styles.inviteSub}>
                This agreement isn't linked to a staff member, so they cannot see it. Tap to assign now.
              </Text>
            </View>
            <Icon name="ChevronRight" size={18} color={tints.pink.icon} />
          </TouchableOpacity>
        )}

        {/* Invite-code callout: owner viewing, staff not yet joined */}
        {isOwner && assignedStaff && !assignedStaff.user_id && contract.status !== 'void' && (
          <View style={[styles.inviteBox]}>
            <View style={{ flex: 1 }}>
              <Text style={styles.inviteTitle}>Staff hasn't joined yet</Text>
              <Text style={styles.inviteSub}>
                {contract.assigned_staff_name} needs to register in Cozii and enter this code under "I'm staff" to see and sign this agreement.
              </Text>
              <View style={styles.inviteCodeRow}>
                <Text style={styles.inviteCode}>{assignedStaff.invite_code || '—'}</Text>
                <TouchableOpacity
                  onPress={async () => {
                    try {
                      const Clipboard = await import('expo-clipboard');
                      await Clipboard.setStringAsync(assignedStaff.invite_code || '');
                      Alert.alert('Copied', 'Invite code copied to clipboard.');
                    } catch {
                      Alert.alert('Invite code', assignedStaff.invite_code || '—');
                    }
                  }}
                  style={styles.copyBtn}
                >
                  <Icon name="Copy" size={14} color={colors.textMain} />
                  <Text style={styles.copyTxt}>Copy code</Text>
                </TouchableOpacity>
                <TouchableOpacity onPress={() => setReassignOpen(true)} style={[styles.copyBtn, { marginLeft: 6 }]}>
                  <Icon name="Edit3" size={14} color={colors.textMain} />
                  <Text style={styles.copyTxt}>Reassign</Text>
                </TouchableOpacity>
              </View>
            </View>
          </View>
        )}

        {/* Body */}
        <View style={styles.bodyCard}>
          <Text style={styles.bodyTxt}>{renderedBody}</Text>
        </View>

        {/* Signatures section */}
        <Text style={styles.sectionLabel}>Signatures</Text>
        <SignatureCard sig={contract.owner_signature} who="Owner" required={contract.require_owner_signature} />
        <SignatureCard sig={contract.staff_signature} who={contract.assigned_staff_name ? `Staff · ${contract.assigned_staff_name}` : 'Staff'} required={contract.require_staff_signature} />

        {/* Sign action */}
        {myTurnToSign && (
          <TouchableOpacity style={styles.signBtn} onPress={() => setSignOpen(true)} testID="contract-open-sign">
            <Icon name="Pen" size={16} color="#fff" />
            <Text style={styles.signTxt}>Agree & Sign</Text>
          </TouchableOpacity>
        )}

        {/* Owner signed but contract not fully signed yet */}
        {!myTurnToSign && contract.status === 'pending' && mySignature && (
          <View style={[styles.bannerCard, { backgroundColor: tints.sage.bg }]}>
            <Icon name="CheckCircle2" size={20} color={tints.sage.icon} />
            <View style={{ flex: 1 }}>
              <Text style={[styles.bannerTitle, { color: tints.sage.icon }]}>You've signed ✓</Text>
              <Text style={styles.bannerSub}>
                {otherSignature
                  ? 'Both parties have signed.'
                  : isOwner
                    ? `Now waiting for ${contract.assigned_staff_name || 'the staff member'} to sign.`
                    : 'Waiting for the household owner to sign.'}
              </Text>
            </View>
          </View>
        )}

        {/* Fully signed — show a finalize/done banner with back button */}
        {contract.status === 'signed' && (
          <>
            <View style={[styles.bannerCard, { backgroundColor: tints.sage.bg }]}>
              <Icon name="CheckCircle2" size={22} color={tints.sage.icon} />
              <View style={{ flex: 1 }}>
                <Text style={[styles.bannerTitle, { color: tints.sage.icon }]}>Fully signed & finalized</Text>
                <Text style={styles.bannerSub}>
                  A copy has been archived in Documents Vault under "contracts".
                </Text>
              </View>
            </View>
            <TouchableOpacity style={styles.signBtn} onPress={() => router.back()} testID="contract-done">
              <Icon name="Check" size={16} color="#fff" />
              <Text style={styles.signTxt}>Done — back to contracts</Text>
            </TouchableOpacity>
          </>
        )}

        {/* Voided */}
        {contract.status === 'void' && (
          <View style={[styles.bannerCard, { backgroundColor: tints.pink.bg }]}>
            <Icon name="X" size={20} color={tints.pink.icon} />
            <View style={{ flex: 1 }}>
              <Text style={[styles.bannerTitle, { color: tints.pink.icon }]}>This contract is void</Text>
              <Text style={styles.bannerSub}>It can no longer be signed.</Text>
            </View>
          </View>
        )}

        <View style={{ height: 60 }} />
      </ScrollView>

      {/* Reassign Modal */}
      <Modal visible={reassignOpen} animationType="slide" transparent onRequestClose={() => setReassignOpen(false)}>
        <View style={styles.modalBg}>
          <SafeAreaView style={styles.modalSheet} edges={['bottom']}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>Assign to staff</Text>
              <TouchableOpacity onPress={() => setReassignOpen(false)} style={styles.iconBtn}>
                <Icon name="X" size={18} color={colors.textMain} />
              </TouchableOpacity>
            </View>
            <ScrollView contentContainerStyle={{ padding: spacing.md, gap: 8 }}>
              {allStaff.length === 0 ? (
                <Text style={styles.helpTxt}>No staff in this space yet. Add a staff member from the Household tab first.</Text>
              ) : (
                allStaff.filter((s) => s.active !== false).map((s) => (
                  <TouchableOpacity
                    key={s.staff_id}
                    style={[styles.row, contract.assigned_staff_id === s.staff_id && { borderColor: colors.primary, borderWidth: 1 }]}
                    onPress={() => reassign(s.staff_id)}
                    testID={`reassign-${s.staff_id}`}
                  >
                    <View style={[styles.kindIcon || { width: 40, height: 40, borderRadius: 12 }, { backgroundColor: tints.blue.icon, alignItems: 'center', justifyContent: 'center' }]}>
                      <Text style={{ color: '#fff', fontWeight: '800' }}>{(s.name || '?')[0]?.toUpperCase()}</Text>
                    </View>
                    <View style={{ flex: 1 }}>
                      <Text style={styles.rowName}>{s.name}</Text>
                      <Text style={styles.rowSub}>
                        {s.role_name || 'Staff'} · {s.user_id ? '✓ Joined' : `Invite code: ${s.invite_code || '—'}`}
                      </Text>
                    </View>
                    {contract.assigned_staff_id === s.staff_id && (
                      <Icon name="Check" size={18} color={colors.primary} />
                    )}
                  </TouchableOpacity>
                ))
              )}
            </ScrollView>
          </SafeAreaView>
        </View>
      </Modal>

      {/* Sign Modal */}
      <Modal visible={signOpen} animationType="slide" transparent onRequestClose={() => setSignOpen(false)}>
        <View style={styles.modalBg}>
          <SafeAreaView style={styles.modalSheet} edges={['bottom']}>
            <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={{ flex: 1 }}>
              <View style={styles.modalHeader}>
                <Text style={styles.modalTitle}>Sign as {myRole === 'owner' ? 'Owner' : 'Staff'}</Text>
                <TouchableOpacity onPress={() => setSignOpen(false)} style={styles.iconBtn}>
                  <Icon name="X" size={18} color={colors.textMain} />
                </TouchableOpacity>
              </View>
              <ScrollView
                contentContainerStyle={{ padding: spacing.md, gap: 10, paddingBottom: 24 }}
                keyboardShouldPersistTaps="handled"
                scrollEnabled={!drawingActive}
                style={{ flex: 1 }}
              >
                <Text style={styles.helpTxt}>
                  By signing below, you confirm you have read and agree to the terms of "{contract.title}".
                  Your signature, IP address, device info and timestamp will be recorded.
                </Text>

                <Text style={styles.label}>Type your full name {requireDrawnForMe ? '(optional)' : ''}</Text>
                <TextInput
                  style={styles.input}
                  value={typedName}
                  onChangeText={setTypedName}
                  placeholder={user?.name || 'Your full name'}
                  placeholderTextColor={colors.textMuted}
                  autoCapitalize="words"
                />

                <Text style={styles.label}>Hand-drawn signature {requireDrawnForMe ? '(required)' : '(optional)'}</Text>
                <SignaturePad
                  onChange={setDrawing}
                  onDrawStart={() => setDrawingActive(true)}
                  onDrawEnd={() => setDrawingActive(false)}
                  testID="sigpad"
                />

                {/* Live "captured" affirmation so the user knows their drawing is being recorded */}
                {drawing ? (
                  <View style={[styles.bannerCard, { backgroundColor: tints.sage.bg, marginTop: 4 }]}>
                    <Icon name="CheckCircle2" size={16} color={tints.sage.icon} />
                    <Text style={[styles.bannerSub, { fontWeight: '700', color: tints.sage.icon }]}>
                      Signature captured. Tap "Agree & Sign" below to submit.
                    </Text>
                  </View>
                ) : null}
              </ScrollView>

              {/* Sticky submit bar — always visible at the bottom of the modal */}
              <View style={styles.submitBar}>
                <TouchableOpacity
                  style={[styles.submitBtn, (submitting || (requireDrawnForMe && !drawing) || (!drawing && !typedName.trim())) && { opacity: 0.4 }]}
                  onPress={submitSign}
                  disabled={submitting || (requireDrawnForMe && !drawing) || (!drawing && !typedName.trim())}
                  testID="sign-submit"
                >
                  {submitting ? <ActivityIndicator color="#fff" /> : (
                    <>
                      <Icon name="CheckCircle2" size={18} color="#fff" />
                      <Text style={styles.signTxt}>Agree & Sign</Text>
                    </>
                  )}
                </TouchableOpacity>
                {requireDrawnForMe && !drawing ? (
                  <Text style={styles.submitHint}>Draw your signature above to enable</Text>
                ) : (!drawing && !typedName.trim()) ? (
                  <Text style={styles.submitHint}>Type your name or draw a signature above</Text>
                ) : null}
              </View>
            </KeyboardAvoidingView>
          </SafeAreaView>
        </View>
      </Modal>
    </SafeAreaView>
  );
}

function SignatureCard({ sig, who, required }: { sig: Sig | null; who: string; required: boolean }) {
  if (!sig) {
    return (
      <View style={[styles.sigCard, { borderStyle: 'dashed', borderWidth: 1, borderColor: colors.border, backgroundColor: 'transparent' }]}>
        <View style={styles.sigCardHead}>
          <Icon name="Clock" size={14} color={colors.textMuted} />
          <Text style={styles.sigWho}>{who}</Text>
          <View style={[styles.statusPill, { backgroundColor: required ? tints.yellow.bg : tints.lavender.bg, paddingVertical: 2 }]}>
            <Text style={[styles.statusTxt, { color: required ? tints.yellow.icon : tints.lavender.icon }]}>
              {required ? 'Pending' : 'Optional · not required'}
            </Text>
          </View>
        </View>
      </View>
    );
  }
  return (
    <View style={styles.sigCard}>
      <View style={styles.sigCardHead}>
        <Icon name="CheckCircle2" size={14} color={tints.sage.icon} />
        <Text style={styles.sigWho}>{who}</Text>
        <View style={[styles.statusPill, { backgroundColor: tints.sage.bg, paddingVertical: 2 }]}>
          <Text style={[styles.statusTxt, { color: tints.sage.icon }]}>Signed</Text>
        </View>
      </View>
      {sig.drawing_base64 ? (
        <View style={styles.drawingWrap}>
          <Image source={{ uri: sig.drawing_base64 }} style={styles.drawing} resizeMode="contain" />
        </View>
      ) : null}
      {sig.typed_name ? <Text style={styles.typedName}>{sig.typed_name}</Text> : null}
      <Text style={styles.sigMeta}>
        Signed by <Text style={{ fontWeight: '700' }}>{sig.name || sig.typed_name || '—'}</Text>
        {' · '}{new Date(sig.signed_at).toLocaleString()}
      </Text>
      {(sig.ip || sig.user_agent) && (
        <Text style={styles.sigMetaSmall}>
          {sig.ip ? `IP: ${sig.ip}` : ''}{sig.ip && sig.user_agent ? ' · ' : ''}{sig.user_agent ? `Device: ${(sig.user_agent || '').slice(0, 80)}` : ''}
        </Text>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background },
  header: { flexDirection: 'row', alignItems: 'center', gap: 8, padding: spacing.md },
  backBtn: { width: 40, height: 40, borderRadius: 20, backgroundColor: colors.surface, alignItems: 'center', justifyContent: 'center', transform: [{ rotate: '180deg' }], ...shadows.card },
  iconBtn: { width: 36, height: 36, borderRadius: 18, backgroundColor: colors.surface, alignItems: 'center', justifyContent: 'center', ...shadows.card },
  kicker: { fontSize: 11, color: colors.textMuted, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 0.5 },
  title: { fontSize: 22, fontWeight: '900', color: colors.textMain, letterSpacing: -0.5 },
  scroll: { padding: spacing.md, paddingTop: 0 },
  statusRow: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: spacing.md },
  statusPill: { flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 10, paddingVertical: 4, borderRadius: radius.full },
  statusTxt: { fontSize: 11, fontWeight: '800' },
  assignedTxt: { fontSize: 12, color: colors.textMuted, fontWeight: '700' },
  inviteBox: {
    flexDirection: 'row', gap: 10,
    backgroundColor: tints.peach.bg,
    padding: spacing.md, borderRadius: radius.md,
    marginBottom: spacing.md,
    borderWidth: 1, borderColor: tints.peach.icon,
  },
  inviteTitle: { fontSize: 14, fontWeight: '800', color: tints.peach.icon },
  inviteSub: { fontSize: 12, color: colors.textMain, marginTop: 4, lineHeight: 17 },
  inviteCodeRow: { flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 10 },
  inviteCode: { fontSize: 22, fontWeight: '900', color: colors.textMain, letterSpacing: 2, fontFamily: Platform.select({ ios: 'Menlo', android: 'monospace' }) as any },
  copyBtn: {
    flexDirection: 'row', alignItems: 'center', gap: 6,
    paddingHorizontal: 10, paddingVertical: 6,
    backgroundColor: '#fff', borderRadius: radius.full,
    borderWidth: 1, borderColor: colors.border,
  },
  copyTxt: { fontSize: 11, fontWeight: '800', color: colors.textMain },
  row: { flexDirection: 'row', alignItems: 'center', gap: 12, backgroundColor: colors.surface, padding: spacing.md, borderRadius: radius.md, marginBottom: 6, ...shadows.card },
  rowName: { fontSize: 14, fontWeight: '800', color: colors.textMain },
  rowSub: { fontSize: 11, color: colors.textMuted, marginTop: 2 },
  kindIcon: { width: 40, height: 40, borderRadius: 12, alignItems: 'center', justifyContent: 'center' },
  bodyCard: {
    backgroundColor: '#FFFEFB',
    borderWidth: 1, borderColor: colors.border,
    borderRadius: radius.md, padding: spacing.md,
    marginBottom: spacing.md,
  },
  bodyTxt: { fontSize: 13, color: colors.textMain, lineHeight: 21 },
  sectionLabel: { fontSize: 12, fontWeight: '800', color: colors.textMuted, textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: spacing.sm, marginTop: spacing.sm },
  sigCard: { backgroundColor: colors.surface, padding: spacing.md, borderRadius: radius.md, marginBottom: 8, ...shadows.card },
  sigCardHead: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 6 },
  sigWho: { flex: 1, fontSize: 13, fontWeight: '800', color: colors.textMain },
  drawingWrap: { backgroundColor: '#FFFEFB', borderRadius: radius.sm, marginVertical: 6, height: 100, overflow: 'hidden' },
  drawing: { width: '100%', height: '100%' },
  typedName: { fontSize: 18, fontStyle: 'italic', fontWeight: '700', color: colors.textMain, marginVertical: 4 },
  sigMeta: { fontSize: 11, color: colors.textMuted, marginTop: 4 },
  sigMetaSmall: { fontSize: 10, color: colors.textMuted, marginTop: 2, fontFamily: Platform.select({ ios: 'Menlo', android: 'monospace' }) as any },
  signBtn: {
    flexDirection: 'row', gap: 8, marginTop: spacing.md,
    backgroundColor: colors.primary, padding: 14, borderRadius: radius.full,
    alignItems: 'center', justifyContent: 'center',
    ...shadows.button,
  },
  signTxt: { color: '#fff', fontWeight: '800', fontSize: 14 },
  bannerCard: {
    flexDirection: 'row', alignItems: 'center', gap: 10,
    padding: spacing.md, borderRadius: radius.md,
    marginTop: spacing.md,
  },
  bannerTitle: { fontSize: 14, fontWeight: '900' },
  bannerSub: { fontSize: 12, color: colors.textMain, marginTop: 2, lineHeight: 17 },
  helpTxt: { fontSize: 12, color: colors.textMuted, marginTop: spacing.sm, textAlign: 'center', lineHeight: 17 },
  modalBg: { flex: 1, backgroundColor: 'rgba(0,0,0,0.5)', justifyContent: 'flex-end' },
  modalSheet: { backgroundColor: colors.background, borderTopLeftRadius: 24, borderTopRightRadius: 24, maxHeight: '92%', height: '92%' },
  modalHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', padding: spacing.md, borderBottomWidth: 1, borderBottomColor: colors.border },
  modalTitle: { fontSize: 18, fontWeight: '800', color: colors.textMain },
  label: { fontSize: 12, fontWeight: '800', color: colors.textMuted, textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 6 },
  input: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, padding: 12, fontSize: 14, color: colors.textMain },
  submitBar: {
    padding: spacing.md, paddingTop: 10,
    borderTopWidth: 1, borderTopColor: colors.border,
    backgroundColor: colors.background,
    gap: 6,
  },
  submitBtn: {
    flexDirection: 'row', gap: 8,
    backgroundColor: colors.primary, padding: 16, borderRadius: radius.full,
    alignItems: 'center', justifyContent: 'center',
    ...shadows.button,
  },
  submitHint: { fontSize: 11, color: colors.textMuted, textAlign: 'center', fontStyle: 'italic' },
});
