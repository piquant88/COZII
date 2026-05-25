import { Alert, Platform, Linking } from 'react-native';
import * as ImagePicker from 'expo-image-picker';

export type PickedImage = {
  uri: string;
  base64?: string | null;
  width?: number;
  height?: number;
  /** Always a `data:image/jpeg;base64,...` string when base64 is available,
   *  otherwise the raw uri. Convenient for direct upload to the backend. */
  dataUri: string;
};

export type PickerOptions = {
  /** "camera" → launch the camera. "library" → launch the photo library. */
  source: 'camera' | 'library';
  allowsEditing?: boolean;
  /** Aspect ratio when editing, e.g. [1,1] for square. */
  aspect?: [number, number];
  /** 0..1 JPEG compression quality. */
  quality?: number;
  /** Whether to include base64 in the result. Default: true. */
  base64?: boolean;
};

function openSettings() {
  try { Linking.openSettings(); } catch {}
}

async function ensurePermission(source: 'camera' | 'library'): Promise<boolean> {
  if (Platform.OS === 'web') return true; // Browser asks via getUserMedia / <input>
  try {
    if (source === 'camera') {
      const cur = await ImagePicker.getCameraPermissionsAsync();
      if (cur.status === 'granted') return true;
      if (cur.canAskAgain) {
        const req = await ImagePicker.requestCameraPermissionsAsync();
        if (req.status === 'granted') return true;
      }
      Alert.alert(
        'Camera access needed',
        'Enable camera access for Cozii in Settings to take photos.',
        [
          { text: 'Cancel', style: 'cancel' },
          { text: 'Open Settings', onPress: openSettings },
        ],
      );
      return false;
    } else {
      const cur = await ImagePicker.getMediaLibraryPermissionsAsync();
      if (cur.status === 'granted') return true;
      if (cur.canAskAgain) {
        const req = await ImagePicker.requestMediaLibraryPermissionsAsync();
        if (req.status === 'granted') return true;
      }
      Alert.alert(
        'Photo library access needed',
        'Enable photo library access for Cozii in Settings to pick photos.',
        [
          { text: 'Cancel', style: 'cancel' },
          { text: 'Open Settings', onPress: openSettings },
        ],
      );
      return false;
    }
  } catch (e) {
    console.warn('[imagePicker] permission check failed', e);
    return false;
  }
}

/** Single entry-point that:
 *   1. Requests the right permission (with a friendly Settings prompt on deny)
 *   2. Launches the camera / library
 *   3. Returns null on cancel
 *   4. Returns the chosen image with a ready-to-upload data URI
 *
 * Compatible with all expo-image-picker versions we ship (SDK 50–55).
 * Throws nothing — caller can rely on null vs. PickedImage. */
export async function pickImage(opts: PickerOptions): Promise<PickedImage | null> {
  const granted = await ensurePermission(opts.source);
  if (!granted) return null;

  // `mediaTypes` accepts both the deprecated MediaTypeOptions enum AND the new
  // string array. The enum still works on SDK 55 but is logged as deprecated.
  const mediaTypes: any = (ImagePicker as any).MediaTypeOptions?.Images ?? ['images'];

  const baseOptions = {
    mediaTypes,
    allowsEditing: opts.allowsEditing ?? false,
    aspect: opts.aspect,
    quality: opts.quality ?? 0.6,
    base64: opts.base64 ?? true,
    // iOS: disables HEIC and gives us JPEG that the backend & web can consume.
    exif: false,
  } as any;

  let result;
  try {
    if (opts.source === 'camera') {
      result = await ImagePicker.launchCameraAsync(baseOptions);
    } else {
      result = await ImagePicker.launchImageLibraryAsync(baseOptions);
    }
  } catch (e: any) {
    console.warn('[imagePicker] launch failed', e);
    Alert.alert(
      opts.source === 'camera' ? 'Camera failed to open' : 'Photo library failed to open',
      e?.message || 'Please try again.',
    );
    return null;
  }

  if (!result || (result as any).canceled) return null;
  const assets = (result as any).assets || [];
  const a = assets[0];
  if (!a) return null;

  const dataUri = a.base64
    ? `data:image/jpeg;base64,${a.base64}`
    : a.uri;

  return {
    uri: a.uri,
    base64: a.base64 || null,
    width: a.width,
    height: a.height,
    dataUri,
  };
}

/** Convenience: prompt the user with a small Alert to choose camera/library. */
export async function pickImageWithChoice(opts?: Partial<PickerOptions>): Promise<PickedImage | null> {
  return new Promise((resolve) => {
    Alert.alert(
      'Add a photo',
      'Take a new photo or choose from your library?',
      [
        {
          text: 'Take photo',
          onPress: async () => resolve(await pickImage({ source: 'camera', ...opts } as PickerOptions)),
        },
        {
          text: 'Choose from library',
          onPress: async () => resolve(await pickImage({ source: 'library', ...opts } as PickerOptions)),
        },
        { text: 'Cancel', style: 'cancel', onPress: () => resolve(null) },
      ],
      { cancelable: true, onDismiss: () => resolve(null) },
    );
  });
}
