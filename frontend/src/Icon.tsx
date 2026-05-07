import React from 'react';
import { Image, View, StyleSheet } from 'react-native';
import {
  Refrigerator, Sparkles, Shirt, Bath, Wind, Wallet, Box, Home, PieChart,
  User as UserIcon, Plus, Camera, Search, ChevronRight, ChevronLeft, ChevronDown, ChevronUp, ArrowLeft, X,
  LogOut, Users, Copy, Check, Trash2, Edit3, MinusCircle, PlusCircle,
  Calendar, DollarSign, Package, Tag, Image as ImageIcon, CircleDot,
  ShoppingBag, Droplet, BookOpen, Apple, Pill, Heart, Star, Lock, Globe, ImagePlus,
  Receipt, ArrowRight, FileText, FilePlus, Clock, CreditCard, Zap, Wifi, Phone, Lightbulb,
  Repeat, PenLine, Bell, Shield, Download, CheckCircle2, Pen, Eraser, Send, Sun,
} from 'lucide-react-native';

export const ICON_MAP: Record<string, any> = {
  Refrigerator, Sparkles, Shirt, Bath, Wind, Wallet, Box, Home, PieChart,
  User: UserIcon, Plus, Camera, Search, ChevronRight, ChevronLeft, ChevronDown, ChevronUp, ArrowLeft, X,
  LogOut, Users, Copy, Check, Trash2, Edit3, MinusCircle, PlusCircle,
  Calendar, DollarSign, Package, Tag, ImageIcon, CircleDot,
  ShoppingBag, Droplet, BookOpen, Apple, Pill, Heart, Star, Lock, Globe, ImagePlus,
  Receipt, ArrowRight, FileText, FilePlus, Clock, CreditCard, Zap, Wifi, Phone, Lightbulb,
  Repeat, PenLine, Bell, Shield, Download, CheckCircle2, Pen, Eraser, Send, Sun,
};

export const CATEGORY_ICON_OPTIONS = [
  'Refrigerator', 'Sparkles', 'Shirt', 'Bath', 'Wind', 'ShoppingBag',
  'Apple', 'Pill', 'Droplet', 'BookOpen', 'Heart', 'Star', 'Box',
];

export const BILL_ICON_OPTIONS = [
  'Receipt', 'Zap', 'Wifi', 'Phone', 'Home', 'Droplet', 'Wallet', 'CreditCard', 'Lightbulb',
];

type Props = {
  name: string;
  size?: number;
  color?: string;
};

export function isImageIcon(name: string): boolean {
  return typeof name === 'string' && name.startsWith('data:image');
}

export function Icon({ name, size = 22, color = '#2D3436' }: Props) {
  if (isImageIcon(name)) {
    return (
      <View style={{ width: size, height: size, borderRadius: size / 2, overflow: 'hidden' }}>
        <Image source={{ uri: name }} style={{ width: '100%', height: '100%' }} resizeMode="cover" />
      </View>
    );
  }
  const Cmp = ICON_MAP[name] || Box;
  return <Cmp size={size} color={color} strokeWidth={2} />;
}
