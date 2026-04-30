import React from 'react';
import {
  Refrigerator, Sparkles, Shirt, Bath, Wind, Wallet, Box, Home, PieChart,
  User as UserIcon, Plus, Camera, Search, ChevronRight, ArrowLeft, X,
  LogOut, Users, Copy, Check, Trash2, Edit3, MinusCircle, PlusCircle,
  Calendar, DollarSign, Package, Tag, Image as ImageIcon, CircleDot,
  ShoppingBag, Droplet, BookOpen, Apple, Pill, Heart, Star,
} from 'lucide-react-native';

export const ICON_MAP: Record<string, any> = {
  Refrigerator, Sparkles, Shirt, Bath, Wind, Wallet, Box, Home, PieChart,
  User: UserIcon, Plus, Camera, Search, ChevronRight, ArrowLeft, X,
  LogOut, Users, Copy, Check, Trash2, Edit3, MinusCircle, PlusCircle,
  Calendar, DollarSign, Package, Tag, ImageIcon, CircleDot,
  ShoppingBag, Droplet, BookOpen, Apple, Pill, Heart, Star,
};

export const CATEGORY_ICON_OPTIONS = [
  'Refrigerator', 'Sparkles', 'Shirt', 'Bath', 'Wind', 'ShoppingBag',
  'Apple', 'Pill', 'Droplet', 'BookOpen', 'Heart', 'Star', 'Box',
];

type Props = {
  name: string;
  size?: number;
  color?: string;
};

export function Icon({ name, size = 22, color = '#2D3436' }: Props) {
  const Cmp = ICON_MAP[name] || Box;
  return <Cmp size={size} color={color} strokeWidth={2} />;
}
