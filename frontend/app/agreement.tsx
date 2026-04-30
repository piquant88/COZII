import React, { useState, useCallback } from 'react';
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity, RefreshControl,
  TextInput, KeyboardAvoidingView, Platform, ActivityIndicator, Alert,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useFocusEffect, useRouter } from 'expo-router';
import { useAuth } from '../src/AuthContext';
import { api } from '../src/api';
import { colors, radius, spacing, shadows, tints } from '../src/theme';
import { Icon } from '../src/Icon';
import type { Agreement as AgreementDoc } from '../src/types';

const TEMPLATE = `## Household
A brief about our shared home and what we aim for together.

## Rent & utilities
Describe how rent and bills are split (e.g. equal share, by room size).

## Cleaning & chores
Who does what and how often (e.g. kitchen rotates weekly).

## Quiet hours
When the home should be quiet (e.g. 10pm–7am on weekdays).

## Guests & shared items
Rules for overnight guests and sharing groceries / toiletries.

## Leaving the house
How notice will be given and how the deposit is handled.
`;

export default function Agreement() {
  const router = useRouter();
  const { activeSpace, user } = useAuth();
  const [doc, setDoc] = useState<AgreementDoc | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState('');
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    if (!activeSpace) return;
    try {
      const d = await api.get<AgreementDoc | null>(`/agreement?space_id=${activeSpace.space_id}`);
      setDoc(d || null);
      setText(d?.text || '');
    } catch (e) { console.warn(e); }
    finally { setLoading(false); }
  }, [activeSpace]);

  useFocusEffect(useCallback(() => { load(); }, [load]));

  const onRefresh = async () => { setRefreshing(true); await load(); setRefreshing(false); };

  const save = async () => {
    if (!activeSpace) return;
    setSaving(true);
    try {
      await api.put(`/agreement?space_id=${activeSpace.space_id}`, { text, sections: [] });
      setEditing(false);
      await load();
      Alert.alert('Saved', 'Agreement updated. Ask members to re-sign.');
    } catch (e: any) {
      Alert.alert('Error', e?.message || 'Failed to save');
    } finally { setSaving(false); }
  };

  const sign = async () => {
    if (!activeSpace) return;
    try {
      await api.post(`/agreement/sign?space_id=${activeSpace.space_id}`);
      await load();
    } catch (e: any) {
      Alert.alert('Error', e?.message || 'Failed to sign');
    }
  };

  const signedByMe = !!doc?.signatures?.find((s) => s.user_id === user?.user_id);

  const useTemplate = () => { setText(TEMPLATE); };

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <View style={styles.header}>
        <TouchableOpacity style={styles.iconBtn} onPress={() => router.back()} testID="agreement-back">
          <Icon name="ArrowLeft" color={colors.textMain} />
        </TouchableOpacity>
        <Text style={styles.title}>Roommate agreement</Text>
        {!editing && doc ? (
          <TouchableOpacity style={styles.iconBtn} onPress={() => { setText(doc.text); setEditing(true); }} testID="agreement-edit">
            <Icon name="Edit3" color={colors.textMain} size={18} />
          </TouchableOpacity>
        ) : (
          <View style={{ width: 40 }} />
        )}
      </View>

      {loading ? (
        <ActivityIndicator color={colors.primary} style={{ marginTop: 40 }} />
      ) : editing || !doc ? (
        <KeyboardAvoidingView
          behavior={Platform.OS === 'ios' ? 'padding' : undefined}
          style={{ flex: 1 }}
          keyboardVerticalOffset={0}
        >
          <ScrollView contentContainerStyle={styles.scroll} keyboardShouldPersistTaps="handled">
            <View style={styles.infoCard}>
              <Icon name="FileText" size={20} color={tints.lavender.icon} />
              <View style={{ flex: 1 }}>
                <Text style={styles.infoTitle}>Write it together</Text>
                <Text style={styles.infoSub}>Roommates can edit and sign. Every change resets signatures so everyone re-agrees.</Text>
              </View>
            </View>
            {!doc && !text && (
              <TouchableOpacity style={styles.templateBtn} onPress={useTemplate} testID="agreement-template">
                <Icon name="Sparkles" size={16} color={colors.textMain} />
                <Text style={styles.templateTxt}>Start from a guided template</Text>
              </TouchableOpacity>
            )}
            <TextInput
              style={styles.textarea}
              value={text}
              onChangeText={setText}
              multiline
              placeholder="Draft the house rules, chore split, rent share, quiet hours, guest policy..."
              placeholderTextColor={colors.textMuted}
              textAlignVertical="top"
              testID="agreement-textarea"
            />
            <View style={styles.actionRow}>
              {doc && (
                <TouchableOpacity style={styles.cancelBtn} onPress={() => { setEditing(false); setText(doc.text); }}>
                  <Text style={styles.cancelTxt}>Cancel</Text>
                </TouchableOpacity>
              )}
              <TouchableOpacity
                style={[styles.saveBtn, (saving || !text.trim()) && { opacity: 0.5 }]}
                onPress={save}
                disabled={saving || !text.trim()}
                testID="agreement-save"
              >
                <Text style={styles.saveTxt}>{saving ? 'Saving...' : doc ? 'Save changes' : 'Create agreement'}</Text>
              </TouchableOpacity>
            </View>
          </ScrollView>
        </KeyboardAvoidingView>
      ) : (
        <ScrollView
          contentContainerStyle={styles.scroll}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.primary} />}
        >
          <View style={styles.docCard}>
            <Text style={styles.docText} testID="agreement-text">{doc.text}</Text>
          </View>

          <Text style={styles.sectionTitle}>Signatures</Text>
          {(doc.signatures || []).length === 0 ? (
            <Text style={styles.emptyLine}>No one has signed yet.</Text>
          ) : (
            (doc.signatures || []).map((s) => (
              <View key={s.user_id} style={styles.sigRow}>
                <View style={[styles.avatar, { backgroundColor: tints.sage.icon }]}>
                  <Text style={styles.avatarTxt}>{s.user_name?.[0]?.toUpperCase()}</Text>
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={styles.sigName}>{s.user_name}</Text>
                  <Text style={styles.sigDate}>Signed {new Date(s.signed_at).toLocaleString()}</Text>
                </View>
                <Icon name="Check" size={16} color={tints.sage.icon} />
              </View>
            ))
          )}

          <TouchableOpacity
            style={[styles.signBtn, signedByMe && { backgroundColor: tints.sage.icon }]}
            onPress={sign}
            testID="agreement-sign"
          >
            <Icon name="PenLine" size={16} color="#fff" />
            <Text style={styles.signTxt}>{signedByMe ? 'Re-sign agreement' : 'I agree & sign'}</Text>
          </TouchableOpacity>
          <Text style={styles.footer}>Last updated {new Date(doc.updated_at).toLocaleDateString()}</Text>
        </ScrollView>
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background },
  header: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingHorizontal: spacing.md, paddingVertical: spacing.sm,
  },
  iconBtn: {
    width: 40, height: 40, borderRadius: 20,
    backgroundColor: colors.surface,
    alignItems: 'center', justifyContent: 'center',
    ...shadows.card,
  },
  title: { fontSize: 18, fontWeight: '800', color: colors.textMain },
  scroll: { padding: spacing.md, paddingBottom: 100 },
  infoCard: {
    flexDirection: 'row', alignItems: 'flex-start', gap: 12,
    backgroundColor: tints.lavender.bg, padding: spacing.md, borderRadius: radius.md,
    marginBottom: spacing.md,
  },
  infoTitle: { fontSize: 14, fontWeight: '800', color: colors.textMain },
  infoSub: { fontSize: 12, color: colors.textMuted, marginTop: 2, lineHeight: 18 },
  templateBtn: {
    flexDirection: 'row', alignItems: 'center', gap: 8,
    backgroundColor: colors.surfaceAlt, padding: 12, borderRadius: radius.md,
    marginBottom: spacing.sm,
  },
  templateTxt: { fontSize: 13, fontWeight: '700', color: colors.textMain },
  textarea: {
    backgroundColor: colors.surface, borderRadius: radius.md,
    padding: spacing.md, fontSize: 14, color: colors.textMain,
    minHeight: 260, ...shadows.card, lineHeight: 22,
  },
  docCard: {
    backgroundColor: colors.surface, borderRadius: radius.lg,
    padding: spacing.lg, ...shadows.card,
    marginBottom: spacing.md,
  },
  docText: { fontSize: 14, color: colors.textMain, lineHeight: 22 },
  sectionTitle: { fontSize: 13, fontWeight: '800', color: colors.textMuted, textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 8, marginTop: 4 },
  sigRow: {
    flexDirection: 'row', alignItems: 'center', gap: 12,
    backgroundColor: colors.surface, padding: spacing.md, borderRadius: radius.md,
    marginBottom: 6, ...shadows.card,
  },
  avatar: { width: 36, height: 36, borderRadius: 18, alignItems: 'center', justifyContent: 'center' },
  avatarTxt: { color: '#fff', fontWeight: '800', fontSize: 14 },
  sigName: { fontSize: 14, fontWeight: '700', color: colors.textMain },
  sigDate: { fontSize: 11, color: colors.textMuted, marginTop: 2 },
  emptyLine: { fontSize: 12, color: colors.textMuted, fontStyle: 'italic', padding: spacing.md, textAlign: 'center' },
  signBtn: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8,
    backgroundColor: colors.primary, paddingVertical: 14, borderRadius: radius.full,
    marginTop: spacing.md, ...shadows.button,
  },
  signTxt: { color: '#fff', fontWeight: '800', fontSize: 14 },
  footer: { fontSize: 11, color: colors.textMuted, textAlign: 'center', marginTop: spacing.md },
  actionRow: { flexDirection: 'row', gap: 10, marginTop: spacing.md },
  cancelBtn: {
    flex: 1, paddingVertical: 14, borderRadius: radius.full,
    alignItems: 'center', backgroundColor: colors.surfaceAlt,
  },
  cancelTxt: { color: colors.textMain, fontWeight: '700' },
  saveBtn: {
    flex: 2, paddingVertical: 14, borderRadius: radius.full,
    alignItems: 'center', backgroundColor: colors.primary,
    ...shadows.button,
  },
  saveTxt: { color: '#fff', fontWeight: '800' },
});
