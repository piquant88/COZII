// Tiny CSV utilities + cross-platform export
import { Platform, Alert, Share } from 'react-native';

function escape(v: any): string {
  if (v === null || v === undefined) return '';
  const s = String(v);
  if (s.includes(',') || s.includes('"') || s.includes('\n') || s.includes('\r')) {
    return `"${s.replace(/"/g, '""')}"`;
  }
  return s;
}

export function toCSV<T extends Record<string, any>>(rows: T[], columns?: { key: string; label: string }[]): string {
  if (!rows.length && !columns?.length) return '';
  const cols = columns || Object.keys(rows[0] || {}).map((k) => ({ key: k, label: k }));
  const header = cols.map((c) => escape(c.label)).join(',');
  const body = rows.map((r) => cols.map((c) => escape((r as any)[c.key])).join(',')).join('\n');
  return `${header}\n${body}`;
}

export function combineCSV(sections: { title: string; csv: string }[]): string {
  return sections.map((s) => `# ${s.title}\n${s.csv}`).join('\n\n');
}

// Web-only download helper
function downloadWeb(filename: string, content: string, mime = 'text/csv;charset=utf-8') {
  if (typeof document === 'undefined') return;
  const blob = new Blob(['\uFEFF' + content], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = filename; document.body.appendChild(a);
  a.click();
  setTimeout(() => { document.body.removeChild(a); URL.revokeObjectURL(url); }, 100);
}

export async function exportText(filename: string, content: string, mime = 'text/csv') {
  if (Platform.OS === 'web') {
    downloadWeb(filename, content, `${mime};charset=utf-8`);
    return true;
  }
  try {
    const FS = await import('expo-file-system');
    const Sharing = await import('expo-sharing');
    const dir = (FS as any).documentDirectory || (FS as any).cacheDirectory;
    const uri = `${dir}${filename}`;
    await (FS as any).writeAsStringAsync(uri, content, { encoding: (FS as any).EncodingType?.UTF8 || 'utf8' });
    const canShare = await (Sharing as any).isAvailableAsync();
    if (canShare) {
      await (Sharing as any).shareAsync(uri, { mimeType: mime, dialogTitle: filename });
    } else {
      await Share.share({ message: content, title: filename });
    }
    return true;
  } catch (e: any) {
    Alert.alert('Export failed', e?.message || 'Could not save file');
    return false;
  }
}

export async function exportPDFFromHTML(filename: string, html: string) {
  if (Platform.OS === 'web') {
    // Open print preview
    if (typeof window !== 'undefined') {
      const w = window.open('', '_blank');
      if (w) {
        w.document.write(html);
        w.document.close();
        w.focus();
        setTimeout(() => { try { w.print(); } catch {} }, 300);
      } else {
        Alert.alert('Pop-up blocked', 'Please allow pop-ups to download the PDF.');
      }
    }
    return true;
  }
  try {
    const Print = await import('expo-print');
    const Sharing = await import('expo-sharing');
    const { uri } = await (Print as any).printToFileAsync({ html, base64: false });
    const canShare = await (Sharing as any).isAvailableAsync();
    if (canShare) {
      await (Sharing as any).shareAsync(uri, { mimeType: 'application/pdf', dialogTitle: filename, UTI: 'com.adobe.pdf' });
    } else {
      await (Print as any).printAsync({ uri });
    }
    return true;
  } catch (e: any) {
    Alert.alert('PDF failed', e?.message || 'Could not generate PDF');
    return false;
  }
}
