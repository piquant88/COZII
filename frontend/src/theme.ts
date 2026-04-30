// Cozii theme — pastel, minimalist, cozy
export const colors = {
  background: '#FEF9F8',
  surface: '#FFFFFF',
  surfaceAlt: '#F8F9FA',
  primary: '#FFB5A7',
  primaryHover: '#FCA394',
  secondary: '#A3E4D7',
  lavender: '#D7BDE2',
  yellow: '#F9E79F',
  peach: '#FFDAC1',
  sage: '#B5EAD7',
  mint: '#A3E4D7',
  textMain: '#2D3436',
  textMuted: '#636E72',
  textInverse: '#FFFFFF',
  border: 'rgba(45, 52, 54, 0.08)',
  shadow: 'rgba(0, 0, 0, 0.06)',
  success: '#A3E4D7',
  warning: '#F9E79F',
  danger: '#FFB5A7',
  dangerText: '#E74C3C',
};

export const tints: Record<string, { bg: string; icon: string }> = {
  mint:     { bg: '#E3F7F2', icon: '#3CB4A0' },
  lavender: { bg: '#F0E6F5', icon: '#9B6FB0' },
  peach:    { bg: '#FFEDE0', icon: '#E8936F' },
  yellow:   { bg: '#FCF5D7', icon: '#C9A227' },
  sage:     { bg: '#E6F5E8', icon: '#5FA06A' },
  pink:     { bg: '#FFE4DC', icon: '#E08B7A' },
  blue:     { bg: '#DCEBF5', icon: '#6A94B8' },
};

export const tintKeys = Object.keys(tints);

export const radius = { sm: 12, md: 20, lg: 28, full: 9999 };
export const spacing = { xs: 4, sm: 8, md: 16, lg: 24, xl: 32 };

export const shadows = {
  card: {
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 6 },
    shadowOpacity: 0.06,
    shadowRadius: 16,
    elevation: 3,
  },
  button: {
    shadowColor: '#FFB5A7',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.25,
    shadowRadius: 8,
    elevation: 4,
  },
};

export const fonts = {
  regular: 'System',
  bold: 'System',
};

export const STATUS_LABELS: Record<string, { label: string; bg: string; color: string }> = {
  available: { label: 'In stock',  bg: '#E3F7F2', color: '#3CB4A0' },
  low:       { label: 'Low',       bg: '#FCF5D7', color: '#B58814' },
  finished:  { label: 'Finished',  bg: '#FFE4DC', color: '#D45B43' },
};
