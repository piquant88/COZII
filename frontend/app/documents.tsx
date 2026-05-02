import React, { useState, useCallback } from 'react';
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity, RefreshControl,
  ActivityIndicator, Image, TextInput, Modal, Alert, Platform,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useFocusEffect, useRouter } from 'expo-router';
import { useAuth } from '../src/AuthContext';
import { api } from '../src/api';
import { colors, radius, spacing, shadows, tints } from '../src/theme';
import { Icon } from '../src/Icon';

const FOLDERS = [
  { key: 'contracts', label: 'Contracts', icon: 'FileText', tint: 'sage' },
  { key: 'ids', label: 'IDs & passports', icon: 'User', tint: 'blue' },
  { key: 'insurance', label: 'Insurance', icon: 'Shield' as any, tint: 'lavender' },
  { key: 'receipts', label: 'Receipts', icon: 'ShoppingBag', tint: 'pink' },
  { key: 'wages', label: 'Wage proofs', icon: 'Wallet', tint: 'peach' },
  { key: 'other', label: 'Other', icon: 'Box', tint: 'mint' },
];

export default function DocumentsScreen() {
  const router = useRouter();
  const { activeSpace } = useAuth();
  const [docs, setDocs] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [folder, setFolder] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [viewing, setViewing] = useState<any>(null);

  const load = useCallback(async () => {
    if (!activeSpace) return;
    setLoading(true);
    try {
      const list = await api.get<any[]>(`/documents?space_id=${activeSpace.space_id}`);
      setDocs(list);
    } catch (e) { console.warn(e); }
    finally { setLoading(false); }
  }, [activeSpace]);

  useFocusEffect(useCallback(() => { load(); }, [load]));
  const onRefresh = async () => { setRefreshing(true); await load(); setRefreshing(false); };

  const filtered = folder ? docs.filter((d) => d.folder === folder) : docs;
  const counts: Record<string, number> = {};
  docs.forEach((d) => { counts[d.folder || 'other'] = (counts[d.folder || 'other'] || 0) + 1; });

  return (
    <SafeAreaView style={styles.container} edges={['top', 'bottom']}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.backBtn}>
          <Icon name="ChevronRight" size={18} color={colors.textMain} />
        </TouchableOpacity>
        <View style={{ flex: 1 }}>
          <Text style={styles.kicker}>{activeSpace?.name}</Text>
          <Text style={styles.title}>Documents</Text>
        </View>
        <TouchableOpacity style={styles.addBtn} onPress={() => setAdding(true)} testID="docs-add">
          <Icon name="Plus" size={18} color="#fff" />
        </TouchableOpacity>
      </View>

      <ScrollView contentContainerStyle={styles.scroll} refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.primary} />}>
        <View style={styles.folderGrid}>
          <TouchableOpacity style={[styles.folderCard, !folder && styles.folderActive]} onPress={() => setFolder(null)}>
            <Icon name="Box" size={18} color={!folder ? '#fff' : colors.textMain} />
            <Text style={[styles.folderTxt, !folder && { color: '#fff' }]}>All</Text>
            <Text style={[styles.folderCount, !folder && { color: '#fff' }]}>{docs.length}</Text>
          </TouchableOpacity>
          {FOLDERS.map((f) => (
            <TouchableOpacity
              key={f.key}
              style={[styles.folderCard, folder === f.key && styles.folderActive]}
              onPress={() => setFolder(folder === f.key ? null : f.key)}
              testID={`folder-${f.key}`}
            >
              <Icon name={f.icon as any} size={18} color={folder === f.key ? '#fff' : tints[f.tint as keyof typeof tints]?.icon || colors.textMain} />
              <Text style={[styles.folderTxt, folder === f.key && { color: '#fff' }]}>{f.label}</Text>
              <Text style={[styles.folderCount, folder === f.key && { color: '#fff' }]}>{counts[f.key] || 0}</Text>
            </TouchableOpacity>
          ))}
        </View>

        {loading ? <ActivityIndicator color={colors.primary} style={{ marginTop: 30 }} /> :
          filtered.length === 0 ? (
            <View style={styles.empty}>
              <View style={[styles.heroIcon, { backgroundColor: tints.sage.bg }]}><Icon name="FileText" size={28} color={tints.sage.icon} /></View>
              <Text style={styles.emptyTitle}>No documents{folder ? ` in ${FOLDERS.find((f) => f.key === folder)?.label}` : ' yet'}</Text>
              <Text style={styles.emptySub}>Upload contracts, IDs, insurance, wage proofs and other house papers. Stored securely tied to this space.</Text>
              <TouchableOpacity style={styles.ctaBtn} onPress={() => setAdding(true)}>
                <Icon name="Plus" color="#fff" size={16} />
                <Text style={styles.ctaTxt}>Upload first document</Text>
              </TouchableOpacity>
            </View>
          ) : (
            filtered.map((d) => {
              const isImg = (d.mime || '').startsWith('image/') || (d.file_base64 || '').startsWith('data:image/');
              return (
                <TouchableOpacity key={d.document_id} style={styles.docRow} onPress={() => setViewing(d)} testID={`doc-${d.document_id}`}>
                  <View style={styles.thumb}>
                    {isImg && d.file_base64 ? (
                      <Image source={{ uri: d.file_base64 }} style={styles.thumbImg} />
                    ) : (
                      <Icon name="FileText" size={22} color={colors.textMuted} />
                    )}
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.docName}>{d.name}</Text>
                    <Text style={styles.docSub}>
                      {d.folder ? `${FOLDERS.find((f) => f.key === d.folder)?.label || d.folder} · ` : ''}
                      {d.size_kb ? `${d.size_kb} KB · ` : ''}
                      {new Date(d.created_at).toLocaleDateString()}
                    </Text>
                    {d.note ? <Text style={styles.docNote} numberOfLines={1}>"{d.note}"</Text> : null}
                  </View>
                  <Icon name="ChevronRight" size={16} color={colors.textMuted} />
                </TouchableOpacity>
              );
            })
          )
        }
        <View style={{ height: 40 }} />
      </ScrollView>

      {/* Add modal */}
      {adding && (
        <DocumentForm
          spaceId={activeSpace!.space_id}
          defaultFolder={folder}
          onClose={() => setAdding(false)}
          onSaved={async () => { setAdding(false); await load(); }}
        />
      )}

      {/* View modal */}
      <Modal visible={!!viewing} animationType="slide" transparent onRequestClose={() => setViewing(null)}>
        {viewing && (
          <View style={styles.viewerBg}>
            <SafeAreaView style={{ flex: 1 }} edges={['top', 'bottom']}>
              <View style={styles.viewerHeader}>
                <Text style={styles.viewerTitle} numberOfLines={1}>{viewing.name}</Text>
                <TouchableOpacity onPress={async () => {
                  Alert.alert('Delete document?', '', [
                    { text: 'Cancel', style: 'cancel' },
                    { text: 'Delete', style: 'destructive', onPress: async () => {
                      try { await api.delete(`/documents/${viewing.document_id}`); setViewing(null); await load(); }
                      catch (e: any) { Alert.alert('Error', e?.message || ''); }
                    }},
                  ]);
                }} style={styles.viewerBtn}><Icon name="Trash2" size={18} color={colors.dangerText} /></TouchableOpacity>
                <TouchableOpacity onPress={() => setViewing(null)} style={styles.viewerBtn}><Icon name="X" size={18} color={colors.textMain} /></TouchableOpacity>
              </View>
              <ScrollView contentContainerStyle={{ padding: spacing.md }}>
                {(viewing.mime || '').startsWith('image/') && viewing.file_base64 ? (
                  <Image source={{ uri: viewing.file_base64 }} style={styles.viewerImg} resizeMode="contain" />
                ) : (
                  <View style={styles.viewerPdf}>
                    <Icon name="FileText" size={64} color={colors.textMuted} />
                    <Text style={styles.viewerPdfTxt}>{viewing.mime}</Text>
                    <Text style={styles.docSub}>Preview not available. {viewing.size_kb} KB</Text>
                  </View>
                )}
                {viewing.note ? <Text style={styles.viewerNote}>{viewing.note}</Text> : null}
                <Text style={styles.viewerMeta}>Uploaded by {viewing.uploaded_by_name || 'someone'} on {new Date(viewing.created_at).toLocaleString()}</Text>
              </ScrollView>
            </SafeAreaView>
          </View>
        )}
      </Modal>
    </SafeAreaView>
  );
}


function DocumentForm({ spaceId, defaultFolder, onClose, onSaved }: any) {
  const [name, setName] = useState('');
  const [folder, setFolder] = useState<string>(defaultFolder || 'other');
  const [note, setNote] = useState('');
  const [fileB64, setFileB64] = useState<string | null>(null);
  const [mime, setMime] = useState('image/jpeg');
  const [saving, setSaving] = useState(false);

  const pickFile = async () => {
    try {
      const { launchImageLibraryAsync, MediaTypeOptions } = await import('expo-image-picker');
      const res = await launchImageLibraryAsync({ mediaTypes: MediaTypeOptions.Images, base64: true, quality: 0.7 });
      if (!res.canceled && res.assets?.[0]?.base64) {
        setFileB64(`data:image/jpeg;base64,${res.assets[0].base64}`);
        setMime('image/jpeg');
        if (!name && res.assets[0].fileName) setName(res.assets[0].fileName);
      }
    } catch (e: any) { Alert.alert('Error', e?.message || ''); }
  };

  const save = async () => {
    if (!fileB64) { Alert.alert('Pick a file first'); return; }
    if (!name.trim()) { Alert.alert('Give it a name'); return; }
    setSaving(true);
    try {
      await api.post('/documents', {
        space_id: spaceId, name: name.trim(), folder, mime,
        file_base64: fileB64, note: note || null,
      });
      onSaved();
    } catch (e: any) { Alert.alert('Error', e?.message || 'Could not upload'); }
    finally { setSaving(false); }
  };

  return (
    <Modal visible animationType="slide" transparent onRequestClose={onClose}>
      <View style={styles.modalBg}>
        <SafeAreaView style={styles.modalSheet} edges={['bottom']}>
          <View style={styles.modalHeader}>
            <Text style={styles.modalTitle}>Upload document</Text>
            <TouchableOpacity onPress={onClose} style={styles.viewerBtn}><Icon name="X" size={18} color={colors.textMain} /></TouchableOpacity>
          </View>
          <ScrollView contentContainerStyle={{ padding: spacing.md, gap: 10 }}>
            <TouchableOpacity style={styles.filePick} onPress={pickFile}>
              {fileB64 ? <Image source={{ uri: fileB64 }} style={styles.filePreview} /> : (
                <>
                  <Icon name="Camera" size={28} color={colors.primary} />
                  <Text style={styles.filePickTxt}>Pick an image</Text>
                  <Text style={styles.docSub}>PDF support coming soon. Compress big files first.</Text>
                </>
              )}
            </TouchableOpacity>
            <Text style={styles.label}>Name</Text>
            <TextInput style={styles.input} value={name} onChangeText={setName} placeholder="e.g. Lease agreement 2026" placeholderTextColor={colors.textMuted} />
            <Text style={styles.label}>Folder</Text>
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 }}>
              {FOLDERS.map((f) => (
                <TouchableOpacity key={f.key} style={[styles.folderChip, folder === f.key && styles.folderChipActive]} onPress={() => setFolder(f.key)}>
                  <Icon name={f.icon as any} size={12} color={folder === f.key ? '#fff' : colors.textMain} />
                  <Text style={[styles.folderChipTxt, folder === f.key && { color: '#fff' }]}>{f.label}</Text>
                </TouchableOpacity>
              ))}
            </View>
            <Text style={styles.label}>Note (optional)</Text>
            <TextInput style={[styles.input, { minHeight: 60 }]} value={note} onChangeText={setNote} placeholder="Anything important about this doc" placeholderTextColor={colors.textMuted} multiline />
            <TouchableOpacity style={[styles.saveBtn, (!fileB64 || !name.trim() || saving) && { opacity: 0.5 }]} onPress={save} disabled={!fileB64 || !name.trim() || saving}>
              <Text style={styles.saveTxt}>{saving ? 'Uploading…' : 'Upload'}</Text>
            </TouchableOpacity>
          </ScrollView>
        </SafeAreaView>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background },
  header: { flexDirection: 'row', alignItems: 'center', gap: 12, padding: spacing.md },
  backBtn: { width: 40, height: 40, borderRadius: 20, backgroundColor: colors.surface, alignItems: 'center', justifyContent: 'center', transform: [{ rotate: '180deg' }], ...shadows.card },
  addBtn: { width: 40, height: 40, borderRadius: 20, backgroundColor: colors.primary, alignItems: 'center', justifyContent: 'center', ...shadows.button },
  kicker: { fontSize: 11, color: colors.textMuted, fontWeight: '700', textTransform: 'uppercase' },
  title: { fontSize: 24, fontWeight: '900', color: colors.textMain, letterSpacing: -0.5 },
  scroll: { padding: spacing.md, paddingTop: 0 },
  folderGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: spacing.md },
  folderCard: { width: '31%', backgroundColor: colors.surface, padding: 10, borderRadius: radius.md, alignItems: 'center', gap: 4, borderWidth: 1, borderColor: colors.border },
  folderActive: { backgroundColor: colors.textMain, borderColor: colors.textMain },
  folderTxt: { fontSize: 11, fontWeight: '700', color: colors.textMain, textAlign: 'center' },
  folderCount: { fontSize: 10, color: colors.textMuted, fontWeight: '700' },
  docRow: { flexDirection: 'row', alignItems: 'center', gap: 12, backgroundColor: colors.surface, padding: spacing.md, borderRadius: radius.md, marginBottom: 8, ...shadows.card },
  thumb: { width: 48, height: 48, borderRadius: radius.sm, backgroundColor: colors.surfaceAlt, alignItems: 'center', justifyContent: 'center', overflow: 'hidden' },
  thumbImg: { width: '100%', height: '100%' },
  docName: { fontSize: 14, fontWeight: '700', color: colors.textMain },
  docSub: { fontSize: 11, color: colors.textMuted, marginTop: 2 },
  docNote: { fontSize: 11, color: colors.textMuted, fontStyle: 'italic', marginTop: 2 },
  empty: { alignItems: 'center', padding: spacing.xl, gap: 12 },
  heroIcon: { width: 64, height: 64, borderRadius: 22, alignItems: 'center', justifyContent: 'center' },
  emptyTitle: { fontSize: 18, fontWeight: '800', color: colors.textMain },
  emptySub: { fontSize: 13, color: colors.textMuted, textAlign: 'center', lineHeight: 19 },
  ctaBtn: { flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: colors.primary, paddingHorizontal: 18, paddingVertical: 12, borderRadius: radius.full, ...shadows.button },
  ctaTxt: { color: '#fff', fontWeight: '800' },
  viewerBg: { flex: 1, backgroundColor: 'rgba(0,0,0,0.95)' },
  viewerHeader: { flexDirection: 'row', alignItems: 'center', gap: 10, padding: spacing.md },
  viewerTitle: { flex: 1, color: '#fff', fontSize: 16, fontWeight: '800' },
  viewerBtn: { width: 36, height: 36, borderRadius: 18, backgroundColor: 'rgba(255,255,255,0.15)', alignItems: 'center', justifyContent: 'center' },
  viewerImg: { width: '100%', height: 500, borderRadius: radius.md, backgroundColor: '#000' },
  viewerPdf: { backgroundColor: colors.surface, padding: spacing.xl, borderRadius: radius.md, alignItems: 'center', gap: 8 },
  viewerPdfTxt: { fontSize: 13, color: colors.textMuted, fontWeight: '700' },
  viewerNote: { color: '#fff', marginTop: spacing.md, fontSize: 14, lineHeight: 20 },
  viewerMeta: { color: 'rgba(255,255,255,0.6)', fontSize: 11, marginTop: spacing.sm },
  modalBg: { flex: 1, backgroundColor: 'rgba(0,0,0,0.5)', justifyContent: 'flex-end' },
  modalSheet: { backgroundColor: colors.background, borderTopLeftRadius: 24, borderTopRightRadius: 24, maxHeight: '90%' },
  modalHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', padding: spacing.md, borderBottomWidth: 1, borderBottomColor: colors.border },
  modalTitle: { fontSize: 18, fontWeight: '800', color: colors.textMain },
  filePick: { borderWidth: 1, borderStyle: 'dashed', borderColor: colors.border, borderRadius: radius.md, padding: spacing.md, alignItems: 'center', gap: 6, minHeight: 140, justifyContent: 'center', overflow: 'hidden' },
  filePreview: { width: '100%', height: 200, borderRadius: radius.sm },
  filePickTxt: { color: colors.primary, fontWeight: '800' },
  label: { fontSize: 12, fontWeight: '800', color: colors.textMuted, textTransform: 'uppercase', letterSpacing: 0.5 },
  input: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, padding: 12, fontSize: 14, color: colors.textMain },
  folderChip: { flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 10, paddingVertical: 6, borderRadius: radius.full, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border },
  folderChipActive: { backgroundColor: colors.textMain, borderColor: colors.textMain },
  folderChipTxt: { fontSize: 11, fontWeight: '700', color: colors.textMain },
  saveBtn: { backgroundColor: colors.primary, padding: 14, borderRadius: radius.full, alignItems: 'center', marginTop: 6, ...shadows.button },
  saveTxt: { color: '#fff', fontWeight: '800', fontSize: 14 },
});
