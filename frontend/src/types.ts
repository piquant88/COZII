export type User = {
  user_id: string;
  email: string;
  name: string;
  picture?: string | null;
  auth_provider?: string;
  created_at: string;
};

export type FamilySpace = {
  space_id: string;
  name: string;
  owner_id: string;
  member_ids: string[];
  invite_code: string;
  created_at: string;
};

export type CategoryField = {
  key: string;
  label: string;
  type: 'text' | 'number' | 'date' | 'price' | 'select';
  options?: string[];
};

export type Category = {
  category_id: string;
  space_id: string;
  name: string;
  icon: string;
  tint: string;
  fields: CategoryField[];
  created_by: string;
  created_at: string;
};

export type Item = {
  item_id: string;
  space_id: string;
  category_id: string;
  name: string;
  photo_base64?: string | null;
  status: 'available' | 'low' | 'finished';
  quantity: number;
  unit?: string | null;
  price?: number | null;
  purchase_date?: string | null;
  expiry_date?: string | null;
  notes?: string | null;
  fields: Record<string, any>;
  created_by: string;
  created_by_name?: string | null;
  created_at: string;
  updated_at: string;
};

export type Activity = {
  activity_id: string;
  space_id: string;
  user_id: string;
  user_name: string;
  action: string;
  entity: string;
  entity_id: string;
  entity_name: string;
  timestamp: string;
};

export type Stats = {
  total_items: number;
  low_items: number;
  expiring_soon: number;
  spent_this_month: number;
};
