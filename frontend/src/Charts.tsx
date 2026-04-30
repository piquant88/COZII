import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import Svg, { Path, Circle, G, Rect, Line } from 'react-native-svg';
import { colors, radius, spacing, tints } from './theme';

type Slice = { label: string; value: number; color: string };

export function PieChart({ slices, size = 180, hole = 60 }: { slices: Slice[]; size?: number; hole?: number }) {
  const total = slices.reduce((s, x) => s + x.value, 0);
  if (total <= 0) {
    return (
      <View style={{ width: size, height: size, alignItems: 'center', justifyContent: 'center' }}>
        <View style={{
          width: size - 20, height: size - 20, borderRadius: (size - 20) / 2,
          borderWidth: 16, borderColor: colors.surfaceAlt,
        }} />
      </View>
    );
  }
  const cx = size / 2;
  const cy = size / 2;
  const r = size / 2;
  let cumulative = 0;
  const paths = slices.map((s, i) => {
    const startAngle = (cumulative / total) * Math.PI * 2 - Math.PI / 2;
    cumulative += s.value;
    const endAngle = (cumulative / total) * Math.PI * 2 - Math.PI / 2;
    const large = endAngle - startAngle > Math.PI ? 1 : 0;
    const x1 = cx + r * Math.cos(startAngle);
    const y1 = cy + r * Math.sin(startAngle);
    const x2 = cx + r * Math.cos(endAngle);
    const y2 = cy + r * Math.sin(endAngle);
    const d = `M ${cx} ${cy} L ${x1} ${y1} A ${r} ${r} 0 ${large} 1 ${x2} ${y2} Z`;
    return <Path key={i} d={d} fill={s.color} />;
  });
  return (
    <Svg width={size} height={size}>
      <G>{paths}</G>
      <Circle cx={cx} cy={cy} r={hole} fill={colors.surface} />
    </Svg>
  );
}

export function BarChart({
  data, height = 160, width = 320, color = colors.primary,
}: {
  data: { label: string; value: number }[];
  height?: number;
  width?: number;
  color?: string;
}) {
  const padding = { top: 18, right: 12, bottom: 28, left: 12 };
  const cw = width - padding.left - padding.right;
  const ch = height - padding.top - padding.bottom;
  const max = Math.max(1, ...data.map((d) => d.value));
  const slot = cw / Math.max(1, data.length);
  const barW = Math.min(28, slot * 0.6);
  return (
    <Svg width={width} height={height}>
      {/* baseline */}
      <Line
        x1={padding.left}
        y1={padding.top + ch}
        x2={padding.left + cw}
        y2={padding.top + ch}
        stroke={colors.border}
        strokeWidth={1}
      />
      {data.map((d, i) => {
        const h = (d.value / max) * ch;
        const x = padding.left + slot * i + (slot - barW) / 2;
        const y = padding.top + ch - h;
        return (
          <G key={i}>
            <Rect x={x} y={y} width={barW} height={h} rx={6} fill={color} opacity={d.value > 0 ? 1 : 0.3} />
          </G>
        );
      })}
    </Svg>
  );
}

export function PieLegend({ slices }: { slices: Slice[] }) {
  const total = slices.reduce((s, x) => s + x.value, 0);
  return (
    <View style={legendStyles.wrap}>
      {slices.map((s, i) => {
        const pct = total > 0 ? (s.value / total) * 100 : 0;
        return (
          <View key={i} style={legendStyles.row}>
            <View style={[legendStyles.dot, { backgroundColor: s.color }]} />
            <Text style={legendStyles.label} numberOfLines={1}>{s.label}</Text>
            <Text style={legendStyles.value}>${s.value.toFixed(2)}</Text>
            <Text style={legendStyles.pct}>{pct.toFixed(0)}%</Text>
          </View>
        );
      })}
    </View>
  );
}

const legendStyles = StyleSheet.create({
  wrap: { gap: 8, marginTop: spacing.md },
  row: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  dot: { width: 10, height: 10, borderRadius: 5 },
  label: { flex: 1, fontSize: 13, color: colors.textMain, fontWeight: '600' },
  value: { fontSize: 13, color: colors.textMain, fontWeight: '700' },
  pct: { fontSize: 12, color: colors.textMuted, fontWeight: '600', minWidth: 32, textAlign: 'right' },
});
