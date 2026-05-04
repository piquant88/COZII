import React, { useRef, useState, useCallback } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, PanResponder, GestureResponderEvent, PanResponderGestureState, LayoutChangeEvent, Platform } from 'react-native';
import Svg, { Path } from 'react-native-svg';
import { colors, radius, spacing } from './theme';
import { Icon } from './Icon';

type Stroke = string; // SVG path "M x y L x y L ..."

type Props = {
  height?: number;
  strokeColor?: string;
  strokeWidth?: number;
  onChange?: (svgDataUrl: string | null) => void;
  testID?: string;
};

/**
 * Lightweight in-house signature pad using react-native-svg + PanResponder.
 * Produces an SVG data URL the size of the drawing surface.
 */
export function SignaturePad({ height = 220, strokeColor = '#1F1F1F', strokeWidth = 2.4, onChange, testID }: Props) {
  const [strokes, setStrokes] = useState<Stroke[]>([]);
  const currentRef = useRef<string>('');
  const [, forceTick] = useState(0);
  const sizeRef = useRef<{ w: number; h: number }>({ w: 320, h: height });
  const offsetRef = useRef<{ x: number; y: number }>({ x: 0, y: 0 });

  const emit = useCallback((all: Stroke[]) => {
    if (!onChange) return;
    if (all.length === 0) {
      onChange(null);
      return;
    }
    const { w, h } = sizeRef.current;
    const paths = all
      .map((d) => `<path d="${d}" fill="none" stroke="${strokeColor}" stroke-width="${strokeWidth}" stroke-linecap="round" stroke-linejoin="round"/>`)
      .join('');
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${w} ${h}" width="${w}" height="${h}">${paths}</svg>`;
    // base64 encode (utf-8 safe)
    let b64 = '';
    try {
      // @ts-ignore - btoa available on RN web; on native we polyfill
      b64 = typeof btoa === 'function' ? btoa(unescape(encodeURIComponent(svg))) : Buffer.from(svg, 'utf-8').toString('base64');
    } catch {
      b64 = '';
    }
    onChange(`data:image/svg+xml;base64,${b64}`);
  }, [onChange, strokeColor, strokeWidth]);

  const onLayout = (e: LayoutChangeEvent) => {
    sizeRef.current = { w: e.nativeEvent.layout.width, h: e.nativeEvent.layout.height };
  };

  const startStroke = (x: number, y: number) => {
    currentRef.current = `M ${x.toFixed(1)} ${y.toFixed(1)}`;
    forceTick((n) => n + 1);
  };
  const continueStroke = (x: number, y: number) => {
    if (!currentRef.current) return;
    currentRef.current += ` L ${x.toFixed(1)} ${y.toFixed(1)}`;
    forceTick((n) => n + 1);
  };
  const endStroke = () => {
    if (!currentRef.current) return;
    setStrokes((prev) => {
      const next = [...prev, currentRef.current];
      currentRef.current = '';
      emit(next);
      return next;
    });
  };

  const responder = useRef(
    PanResponder.create({
      onStartShouldSetPanResponder: () => true,
      onStartShouldSetPanResponderCapture: () => true,
      onMoveShouldSetPanResponder: () => true,
      onMoveShouldSetPanResponderCapture: () => true,
      onPanResponderTerminationRequest: () => false,
      onShouldBlockNativeResponder: () => true,
      onPanResponderGrant: (evt: GestureResponderEvent) => {
        const { locationX, locationY } = evt.nativeEvent;
        startStroke(locationX, locationY);
      },
      onPanResponderMove: (evt: GestureResponderEvent, _g: PanResponderGestureState) => {
        const { locationX, locationY } = evt.nativeEvent;
        continueStroke(locationX, locationY);
      },
      onPanResponderRelease: () => endStroke(),
      onPanResponderTerminate: () => endStroke(),
    })
  ).current;

  const clear = () => {
    setStrokes([]);
    currentRef.current = '';
    emit([]);
  };

  const undo = () => {
    setStrokes((prev) => {
      const next = prev.slice(0, -1);
      emit(next);
      return next;
    });
  };

  const allPaths = [...strokes];
  if (currentRef.current) allPaths.push(currentRef.current);
  const isEmpty = allPaths.length === 0;

  return (
    <View style={styles.wrap} testID={testID}>
      <View
        style={[styles.pad, { height }]}
        {...responder.panHandlers}
        onLayout={onLayout}
        // For web platform: needed for proper pointer events
        // @ts-ignore
        onStartShouldSetResponder={() => true}
      >
        <Svg width="100%" height="100%" style={StyleSheet.absoluteFill}>
          {allPaths.map((d, i) => (
            <Path key={i} d={d} fill="none" stroke={strokeColor} strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" />
          ))}
        </Svg>
        {isEmpty && (
          <View pointerEvents="none" style={styles.placeholder}>
            <Icon name="Pen" size={18} color={colors.textMuted} />
            <Text style={styles.phTxt}>Sign here with your finger</Text>
          </View>
        )}
        <View pointerEvents="none" style={styles.baseline} />
      </View>
      <View style={styles.actionsRow}>
        <TouchableOpacity onPress={undo} style={[styles.actionBtn, { opacity: strokes.length === 0 ? 0.4 : 1 }]} disabled={strokes.length === 0} testID={`${testID}-undo`}>
          <Icon name="ArrowLeft" size={14} color={colors.textMain} />
          <Text style={styles.actionTxt}>Undo</Text>
        </TouchableOpacity>
        <TouchableOpacity onPress={clear} style={[styles.actionBtn, { opacity: isEmpty ? 0.4 : 1 }]} disabled={isEmpty} testID={`${testID}-clear`}>
          <Icon name="Eraser" size={14} color={colors.textMain} />
          <Text style={styles.actionTxt}>Clear</Text>
        </TouchableOpacity>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: spacing.sm },
  pad: {
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    backgroundColor: '#FFFEFB',
    overflow: 'hidden',
    position: 'relative',
  },
  placeholder: {
    position: 'absolute', inset: 0 as any, top: 0, left: 0, right: 0, bottom: 0,
    alignItems: 'center', justifyContent: 'center', flexDirection: 'row', gap: 8,
  },
  phTxt: { color: colors.textMuted, fontStyle: 'italic', fontSize: 13 },
  baseline: {
    position: 'absolute', left: 12, right: 12, bottom: 28,
    height: 1, backgroundColor: '#E2D9D2',
  },
  actionsRow: { flexDirection: 'row', gap: 8 },
  actionBtn: {
    flexDirection: 'row', alignItems: 'center', gap: 6,
    paddingHorizontal: 10, paddingVertical: 6,
    backgroundColor: colors.surface, borderRadius: radius.full,
    borderWidth: 1, borderColor: colors.border,
  },
  actionTxt: { fontSize: 12, fontWeight: '700', color: colors.textMain },
});

export default SignaturePad;
