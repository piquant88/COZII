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
  currency?: string;
  space_type?: 'roommates' | 'household';
  created_at: string;
};

export type HouseholdRole = {
  role_id: string;
  space_id: string;
  key: string;
  name: string;
  icon: string;
  color: string;
  category: 'family' | 'staff';
  is_default: boolean;
  perms: Record<string, any>;
  created_at: string;
};

export type FamilyMember = {
  member_id: string;
  space_id: string;
  name: string;
  role_id?: string | null;
  role_name?: string | null;
  photo_base64?: string | null;
  age?: number | null;
  birthday?: string | null;
  school?: string | null;
  allergies?: string | null;
  medical_notes?: string | null;
  notes?: string | null;
  created_at: string;
};

export type StaffMember = {
  staff_id: string;
  space_id: string;
  name: string;
  role_id?: string | null;
  role_name?: string | null;
  photo_base64?: string | null;
  phone?: string | null;
  emergency_contact?: string | null;
  id_number?: string | null;
  salary?: number | null;
  pay_cycle: 'monthly' | 'weekly' | 'daily';
  salary_currency?: string | null;
  off_day?: string | null;
  start_date?: string | null;
  notes?: string | null;
  user_id?: string | null;
  created_at: string;
};

export type HandbookEntry = {
  entry_id: string;
  space_id: string;
  title: string;
  body: string;
  icon: string;
  color: string;
  sort: number;
  created_at: string;
  updated_at: string;
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
  icon: string;        // either an icon name OR a "data:image/..." base64 URI
  tint: string;
  fields: CategoryField[];
  shared_with: string[];
  created_by: string;
  created_at: string;
};

export type Settlement = {
  settlement_id: string;
  space_id: string;
  from_user_id: string;
  to_user_id: string;
  from_name: string;
  to_name: string;
  amount: number;
  note?: string | null;
  evidence_photo_base64?: string | null;
  created_at: string;
};

export type Balance = {
  from_user_id: string;
  from_name: string;
  to_user_id: string;
  to_name: string;
  amount: number;
};

export type Balances = {
  you_owe: Balance[];
  owed_to_you: Balance[];
  others: Balance[];
  total_you_owe: number;
  total_owed_to_you: number;
  net: number;
  shared_categories_count: number;
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

export type BalanceItem = {
  item_id: string;
  name: string;
  category_name: string;
  category_id: string;
  price: number;
  share_each: number;
  split_count: number;
  paid_by: string;
  paid_by_name: string;
  direction: 'they_owe_you' | 'you_owe_them';
  amount: number;
  created_at: string;
  photo_base64?: string | null;
};

export type BalanceDetails = {
  breakdown: BalanceItem[];
  settlements: Settlement[];
};

export type Bill = {
  bill_id: string;
  space_id: string;
  name: string;
  amount: number;
  frequency: 'monthly' | 'weekly' | 'yearly' | 'once';
  due_day: number;
  category_id?: string | null;
  shared_with: string[];
  created_by: string;
  notes?: string | null;
  icon: string;
  last_paid_date?: string | null;
  next_due_date?: string | null;
  is_paid_current_period: boolean;
  created_at: string;
};

export type AgreementSignature = {
  user_id: string;
  user_name: string;
  signed_at: string;
};

export type Agreement = {
  space_id: string;
  text: string;
  sections: { title: string; body: string }[];
  signatures: AgreementSignature[];
  updated_at: string;
  updated_by: string;
};
