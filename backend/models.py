"""Pydantic request/response models for the Cozii backend.

All models are dataclass-like (no business logic). Keep it that way so
this module stays import-cycle free.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, EmailStr, model_validator
from pydantic import field_serializer

from core import now_utc, gen_id, gen_invite_code



# =========================
# Pydantic Models
# =========================
class TZAware(BaseModel):
    """Base model that converts naive datetimes (from MongoDB) into UTC-aware ones."""
    @model_validator(mode='before')
    @classmethod
    def _ensure_tz_aware(cls, data):
        if isinstance(data, dict):
            for k, v in list(data.items()):
                if isinstance(v, datetime) and v.tzinfo is None:
                    data[k] = v.replace(tzinfo=timezone.utc)
        return data



class User(TZAware):
    user_id: str
    email: str
    name: str
    picture: Optional[str] = None
    created_at: datetime
    auth_provider: str = "email"  # email | google



class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    name: str = Field(min_length=1, max_length=80)



class LoginRequest(BaseModel):
    email: EmailStr
    password: str



class GoogleSessionRequest(BaseModel):
    session_id: str



class AuthResponse(BaseModel):
    token: str
    user: User



class FamilySpace(TZAware):
    space_id: str
    name: str
    owner_id: str
    member_ids: List[str]
    invite_code: str
    currency: str = "USD"
    space_type: str = "roommates"
    created_at: datetime



class CreateSpaceRequest(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    currency: str = "USD"
    space_type: str = "roommates"



class UpdateSpaceRequest(BaseModel):
    name: Optional[str] = None
    currency: Optional[str] = None
    space_type: Optional[str] = None



class JoinSpaceRequest(BaseModel):
    invite_code: str



class CategoryField(BaseModel):
    key: str
    label: str
    type: str  # text | number | date | price | select
    options: List[str] = []  # for select type



class Category(TZAware):
    category_id: str
    space_id: str
    name: str
    icon: str
    tint: str  # color tint key
    fields: List[CategoryField]
    shared_with: List[str] = []  # user_ids that split costs in this category; empty = not shared
    staff_can_edit: bool = False  # owner toggles which categories staff can add/edit/delete items in
    created_by: str
    created_at: datetime



class CreateCategoryRequest(BaseModel):
    space_id: str
    name: str = Field(min_length=1, max_length=40)
    icon: str = "Box"
    tint: str = "mint"
    fields: List[CategoryField] = []
    shared_with: List[str] = []
    staff_can_edit: bool = False



class UpdateCategoryRequest(BaseModel):
    name: Optional[str] = None
    icon: Optional[str] = None
    tint: Optional[str] = None
    fields: Optional[List[CategoryField]] = None
    shared_with: Optional[List[str]] = None
    staff_can_edit: Optional[bool] = None



class Item(TZAware):
    item_id: str
    space_id: str
    category_id: str
    name: str
    photo_base64: Optional[str] = None  # uploaded photo override (still supported)
    image_url: Optional[str] = None  # auto-fetched product image URL (preferred for display)
    receipt_base64: Optional[str] = None  # original receipt/proof file (image base64)
    event_tag: Optional[str] = None  # free-text tag for grouping (e.g. "Birthday June 8")
    status: str = "available"  # available | low | finished
    quantity: float = 1
    unit: Optional[str] = None
    price: Optional[float] = None
    purchase_date: Optional[str] = None
    expiry_date: Optional[str] = None
    notes: Optional[str] = None
    fields: Dict[str, Any] = {}
    created_by: str
    created_by_name: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None



class CreateItemRequest(BaseModel):
    space_id: str
    category_id: str
    name: str = Field(min_length=1, max_length=80)
    photo_base64: Optional[str] = None
    image_url: Optional[str] = None
    receipt_base64: Optional[str] = None
    event_tag: Optional[str] = None
    status: str = "available"
    quantity: float = 1
    unit: Optional[str] = None
    price: Optional[float] = None
    purchase_date: Optional[str] = None
    expiry_date: Optional[str] = None
    notes: Optional[str] = None
    fields: Dict[str, Any] = {}



class UpdateItemRequest(BaseModel):
    name: Optional[str] = None
    photo_base64: Optional[str] = None
    image_url: Optional[str] = None
    receipt_base64: Optional[str] = None
    event_tag: Optional[str] = None
    status: Optional[str] = None
    quantity: Optional[float] = None
    unit: Optional[str] = None
    price: Optional[float] = None
    purchase_date: Optional[str] = None
    expiry_date: Optional[str] = None
    notes: Optional[str] = None
    fields: Optional[Dict[str, Any]] = None
    category_id: Optional[str] = None



class ActivityItem(TZAware):
    activity_id: str
    space_id: str
    user_id: str
    user_name: str
    action: str  # added | updated | finished | deleted
    entity: str  # item | category
    entity_id: str
    entity_name: str
    timestamp: datetime



# =========================
# AI Receipt Scan
# =========================
class ScanReceiptRequest(BaseModel):
    image_base64: str  # data URI or raw base64
    target_fields: List[CategoryField] = []  # optional: when scanning into a specific category, fill these



class ScannedItem(BaseModel):
    name: str
    quantity: float = 1
    price: Optional[float] = None
    category_hint: Optional[str] = None
    fields: Dict[str, Any] = {}



class ScanReceiptResponse(BaseModel):
    items: List[ScannedItem]
    raw: Optional[str] = None



class BulkCreateItemsRequest(BaseModel):
    space_id: str
    category_id: str  # Default category
    per_item_category: Dict[str, str] = {}  # index -> category_id override
    items: List[ScannedItem]
    purchase_date: Optional[str] = None
    receipt_photo_base64: Optional[str] = None  # original receipt (kept as proof, not display)
    event_tag: Optional[str] = None  # e.g. "Birthday June 8"
    auto_fetch_images: bool = True  # auto-search the web for product images



# Manual product-image refetch endpoint for an item
class RefreshImageRequest(BaseModel):
    query: Optional[str] = None  # override search query



# =========================
# Settlements / Splits
# =========================
class Settlement(TZAware):
    settlement_id: str
    space_id: str
    from_user_id: str
    to_user_id: str
    from_name: str
    to_name: str
    amount: float
    note: Optional[str] = None
    evidence_photo_base64: Optional[str] = None
    created_at: datetime



class CreateSettlementRequest(BaseModel):
    space_id: str
    to_user_id: str
    amount: float
    note: Optional[str] = None
    evidence_photo_base64: Optional[str] = None



# =========================
# Recurring Bills
# =========================
class Bill(TZAware):
    bill_id: str
    space_id: str
    name: str
    amount: float
    frequency: str  # monthly | weekly | yearly | once
    due_day: int  # day of month (1-31) for monthly, weekday (0-6) for weekly
    category_id: Optional[str] = None
    shared_with: List[str] = []
    created_by: str
    notes: Optional[str] = None
    icon: str = "Receipt"
    last_paid_date: Optional[str] = None  # ISO date string
    next_due_date: Optional[str] = None
    is_paid_current_period: bool = False
    created_at: datetime



class CreateBillRequest(BaseModel):
    space_id: str
    name: str = Field(min_length=1, max_length=80)
    amount: float = Field(gt=0)
    frequency: str = "monthly"
    due_day: int = 1
    category_id: Optional[str] = None
    shared_with: List[str] = []
    notes: Optional[str] = None
    icon: str = "Receipt"



class UpdateBillRequest(BaseModel):
    name: Optional[str] = None
    amount: Optional[float] = None
    frequency: Optional[str] = None
    due_day: Optional[int] = None
    category_id: Optional[str] = None
    shared_with: Optional[List[str]] = None
    notes: Optional[str] = None
    icon: Optional[str] = None



# =========================
# Roommate Agreement
# =========================
class AgreementSignature(BaseModel):
    user_id: str
    user_name: str
    signed_at: datetime



class Agreement(TZAware):
    space_id: str
    text: str
    sections: List[Dict[str, Any]] = []  # [{title, body}]
    signatures: List[AgreementSignature] = []
    updated_at: Optional[datetime] = None
    updated_by: str



class SaveAgreementRequest(BaseModel):
    text: str = ""
    sections: List[Dict[str, Any]] = []



class HouseholdRole(BaseModel):
    role_id: str
    space_id: str
    key: str
    name: str
    icon: str = "User"
    color: str = "mint"
    category: str = "family"  # 'family' | 'staff'
    is_default: bool = False
    perms: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime



class CreateRoleRequest(BaseModel):
    space_id: str
    name: str
    icon: str = "User"
    color: str = "mint"
    category: str = "family"
    perms: Dict[str, Any] = Field(default_factory=dict)



class UpdateRoleRequest(BaseModel):
    name: Optional[str] = None
    icon: Optional[str] = None
    color: Optional[str] = None
    category: Optional[str] = None
    perms: Optional[Dict[str, Any]] = None



class FamilyMember(BaseModel):
    member_id: str
    space_id: str
    name: str
    role_id: Optional[str] = None
    role_name: Optional[str] = None
    photo_base64: Optional[str] = None
    age: Optional[int] = None
    birthday: Optional[str] = None
    school: Optional[str] = None
    allergies: Optional[str] = None
    medical_notes: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime



class CreateFamilyMemberRequest(BaseModel):
    space_id: str
    name: str
    role_id: Optional[str] = None
    photo_base64: Optional[str] = None
    age: Optional[int] = None
    birthday: Optional[str] = None
    school: Optional[str] = None
    allergies: Optional[str] = None
    medical_notes: Optional[str] = None
    notes: Optional[str] = None



class UpdateFamilyMemberRequest(BaseModel):
    name: Optional[str] = None
    role_id: Optional[str] = None
    photo_base64: Optional[str] = None
    age: Optional[int] = None
    birthday: Optional[str] = None
    school: Optional[str] = None
    allergies: Optional[str] = None
    medical_notes: Optional[str] = None
    notes: Optional[str] = None



class StaffMember(BaseModel):
    staff_id: str
    space_id: str
    name: str
    role_id: Optional[str] = None
    role_name: Optional[str] = None
    photo_base64: Optional[str] = None
    phone: Optional[str] = None
    emergency_contact: Optional[str] = None
    id_number: Optional[str] = None
    salary: Optional[float] = None
    pay_cycle: str = "monthly"  # monthly | weekly | daily
    salary_currency: Optional[str] = None
    off_day: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    active: bool = True
    notes: Optional[str] = None
    user_id: Optional[str] = None  # set when staff signs up to the app
    invite_code: Optional[str] = None
    permissions: Dict[str, bool] = Field(default_factory=dict)
    requires_wage_confirmation: bool = False  # if True, staff must confirm receipt of payment
    created_at: datetime



class CreateStaffRequest(BaseModel):
    space_id: str
    name: str
    role_id: Optional[str] = None
    photo_base64: Optional[str] = None
    phone: Optional[str] = None
    emergency_contact: Optional[str] = None
    id_number: Optional[str] = None
    salary: Optional[float] = None
    pay_cycle: str = "monthly"
    salary_currency: Optional[str] = None
    off_day: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    active: bool = True
    notes: Optional[str] = None
    requires_wage_confirmation: bool = False



class UpdateStaffRequest(BaseModel):
    name: Optional[str] = None
    role_id: Optional[str] = None
    photo_base64: Optional[str] = None
    phone: Optional[str] = None
    emergency_contact: Optional[str] = None
    id_number: Optional[str] = None
    salary: Optional[float] = None
    pay_cycle: Optional[str] = None
    salary_currency: Optional[str] = None
    off_day: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    active: Optional[bool] = None
    notes: Optional[str] = None
    requires_wage_confirmation: Optional[bool] = None



class HandbookEntry(BaseModel):
    entry_id: str
    space_id: str
    title: str
    body: str
    icon: str = "BookOpen"
    color: str = "mint"
    photo_base64: Optional[str] = None
    sort: int = 0
    created_at: datetime
    updated_at: Optional[datetime] = None



class CreateHandbookEntryRequest(BaseModel):
    space_id: str
    title: str
    body: str
    icon: str = "BookOpen"
    color: str = "mint"
    photo_base64: Optional[str] = None
    sort: int = 0



class UpdateHandbookEntryRequest(BaseModel):
    title: Optional[str] = None
    body: Optional[str] = None
    icon: Optional[str] = None
    color: Optional[str] = None
    photo_base64: Optional[str] = None
    sort: Optional[int] = None



class UpdateStaffPermissionsRequest(BaseModel):
    permissions: Dict[str, bool]



class JoinStaffRequest(BaseModel):
    invite_code: str



# =========================
# Phase 3 — Payroll (wages as finance items)
# =========================
class StaffPayment(BaseModel):
    payment_id: str
    space_id: str
    staff_id: str
    staff_name: Optional[str] = None
    period: str
    gross: float
    advances: float = 0.0
    deductions: float = 0.0
    bonus: float = 0.0
    net: float
    currency: str = "USD"
    receipt_photo: Optional[str] = None
    notes: Optional[str] = None
    item_id: Optional[str] = None
    paid_at: datetime
    confirmed_at: Optional[datetime] = None
    confirmed_by_staff_id: Optional[str] = None
    requires_confirmation: bool = False



class ConfirmPaymentRequest(BaseModel):
    note: Optional[str] = None



class CreateStaffPaymentRequest(BaseModel):
    space_id: str
    staff_id: str
    period: Optional[str] = None
    gross: Optional[float] = None
    advances: float = 0.0
    deductions: float = 0.0
    bonus: float = 0.0
    receipt_photo: Optional[str] = None
    notes: Optional[str] = None



# =========================
# Household Phase 2 — Tasks, Attendance, Shopping requests
# =========================
class TaskTemplate(BaseModel):
    task_id: str
    space_id: str
    title: str
    description: Optional[str] = None
    staff_id: Optional[str] = None
    role_id: Optional[str] = None
    recurrence: str = "daily"  # daily | weekly | monthly | once
    weekdays: List[int] = Field(default_factory=list)  # 0=Mon..6=Sun, used when recurrence=weekly
    monthly_day: Optional[int] = None  # used when recurrence=monthly
    once_date: Optional[str] = None  # YYYY-MM-DD, used when recurrence=once
    due_time: Optional[str] = None  # HH:MM
    requires_photo: bool = False
    active: bool = True
    created_at: datetime



class CreateTaskRequest(BaseModel):
    space_id: str
    title: str
    description: Optional[str] = None
    staff_id: Optional[str] = None
    role_id: Optional[str] = None
    recurrence: str = "daily"
    weekdays: List[int] = Field(default_factory=list)
    monthly_day: Optional[int] = None
    once_date: Optional[str] = None
    due_time: Optional[str] = None
    requires_photo: bool = False



class UpdateTaskRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    staff_id: Optional[str] = None
    role_id: Optional[str] = None
    recurrence: Optional[str] = None
    weekdays: Optional[List[int]] = None
    monthly_day: Optional[int] = None
    once_date: Optional[str] = None
    due_time: Optional[str] = None
    requires_photo: Optional[bool] = None
    active: Optional[bool] = None



class TaskCompletion(BaseModel):
    completion_id: str
    task_id: str
    space_id: str
    date: str  # YYYY-MM-DD
    completed_at: datetime
    completed_by: str
    completed_by_name: Optional[str] = None
    staff_id: Optional[str] = None
    photo_base64: Optional[str] = None
    notes: Optional[str] = None  # staff's own completion note
    owner_note: Optional[str] = None  # owner review/comment



class CompleteTaskRequest(BaseModel):
    date: Optional[str] = None  # YYYY-MM-DD, defaults to today
    photo_base64: Optional[str] = None
    notes: Optional[str] = None



class AnnotateCompletionRequest(BaseModel):
    owner_note: str



class AttendanceLog(BaseModel):
    attendance_id: str
    space_id: str
    staff_id: str
    date: str
    status: str  # present | off | sick | leave | late
    notes: Optional[str] = None
    recorded_by: str
    created_at: datetime



class SetAttendanceRequest(BaseModel):
    space_id: str
    staff_id: str
    date: str
    status: str
    notes: Optional[str] = None



class ShoppingRequest(BaseModel):
    request_id: str
    space_id: str
    item_name: str
    quantity: Optional[str] = None
    note: Optional[str] = None
    category_id: Optional[str] = None
    category_name: Optional[str] = None
    urgency: str = "normal"  # low | normal | high
    status: str = "pending"  # pending | approved | purchased | rejected
    kind: str = "request"  # 'request' (asking for approval to buy) | 'reimbursement' (already bought, needs payback)
    estimated_price: Optional[float] = None
    actual_price: Optional[float] = None
    currency: Optional[str] = None
    photo_base64: Optional[str] = None
    requested_by: str
    requested_by_name: Optional[str] = None
    requested_by_staff_id: Optional[str] = None
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None
    rejected_reason: Optional[str] = None
    purchased_by: Optional[str] = None
    purchased_at: Optional[datetime] = None
    fulfilled_at: Optional[datetime] = None
    created_at: datetime



class CreateShoppingRequest(BaseModel):
    space_id: str
    item_name: str
    quantity: Optional[str] = None
    note: Optional[str] = None
    category_id: Optional[str] = None
    urgency: str = "normal"
    requested_by_staff_id: Optional[str] = None
    estimated_price: Optional[float] = None
    photo_base64: Optional[str] = None
    kind: str = "request"  # 'request' | 'reimbursement'
    actual_price: Optional[float] = None  # for reimbursements (already spent)



class UpdateShoppingRequest(BaseModel):
    item_name: Optional[str] = None
    quantity: Optional[str] = None
    note: Optional[str] = None
    category_id: Optional[str] = None
    urgency: Optional[str] = None
    status: Optional[str] = None
    estimated_price: Optional[float] = None
    actual_price: Optional[float] = None
    photo_base64: Optional[str] = None
    rejected_reason: Optional[str] = None



class MarkPurchasedRequest(BaseModel):
    actual_price: Optional[float] = None
    note: Optional[str] = None



# =========================
# Task Shortcuts & Quick-fire
# =========================
class TaskShortcut(BaseModel):
    shortcut_id: str
    space_id: str
    staff_id: Optional[str] = None  # None = shared across all staff
    title: str
    icon: Optional[str] = "Zap"
    created_at: datetime



class CreateTaskShortcutRequest(BaseModel):
    space_id: str
    staff_id: Optional[str] = None
    title: str
    icon: Optional[str] = "Zap"



class QuickTaskRequest(BaseModel):
    space_id: str
    staff_id: str
    title: str
    description: Optional[str] = None
    due_time: Optional[str] = None
    save_as_shortcut: bool = False



class CompleteTaskRequest(BaseModel):
    date: Optional[str] = None
    photo_base64: Optional[str] = None
    notes: Optional[str] = None



# =========================
# Documents vault
# =========================
class Document(BaseModel):
    document_id: str
    space_id: str
    name: str
    folder: Optional[str] = None  # e.g. "contracts", "ids", "insurance"
    mime: str = "image/jpeg"
    file_base64: Optional[str] = None  # base64 (image/pdf)
    note: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    size_kb: Optional[int] = None
    uploaded_by: str
    uploaded_by_name: Optional[str] = None
    created_at: datetime
    related_to: Optional[Dict[str, str]] = None  # {kind:'payment'|'item', id:..}



class CreateDocumentRequest(BaseModel):
    space_id: str
    name: str
    folder: Optional[str] = None
    mime: str = "image/jpeg"
    file_base64: str
    note: Optional[str] = None
    tags: List[str] = []
    related_to: Optional[Dict[str, str]] = None



class UpdateDocumentRequest(BaseModel):
    name: Optional[str] = None
    folder: Optional[str] = None
    note: Optional[str] = None
    tags: Optional[List[str]] = None



# =========================
# Notifications (in-app)
# =========================
class Notification(BaseModel):
    notification_id: str
    space_id: str
    user_id: str
    kind: str  # 'wage_paid' | 'task_assigned' | 'info'
    title: str
    body: Optional[str] = None
    data: Dict[str, Any] = Field(default_factory=dict)
    read: bool = False
    created_at: datetime



class AlertsToShoppingRequest(BaseModel):
    space_id: str
    item_ids: List[str] = []
    urgency: str = "normal"  # low | normal | high
    note: Optional[str] = None



class ContractSignature(BaseModel):
    role: str  # "owner" | "staff"
    user_id: str
    name: Optional[str] = None
    typed_name: Optional[str] = None
    drawing_base64: Optional[str] = None  # PNG/SVG base64 dataURL
    signed_at: datetime
    ip: Optional[str] = None
    user_agent: Optional[str] = None



class Contract(BaseModel):
    contract_id: str
    space_id: str
    template_kind: str  # nda | employment | confidentiality | blank | custom
    title: str
    body: str
    variables: Dict[str, Any] = Field(default_factory=dict)
    assigned_staff_id: Optional[str] = None
    assigned_staff_name: Optional[str] = None
    require_owner_signature: bool = True
    require_staff_signature: bool = True
    require_drawn_signature_owner: bool = False
    require_drawn_signature_staff: bool = False
    status: str = "pending"  # pending | signed | void
    owner_signature: Optional[ContractSignature] = None
    staff_signature: Optional[ContractSignature] = None
    created_by: str
    created_by_name: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None



class CreateContractRequest(BaseModel):
    space_id: str
    template_kind: str = "blank"
    title: str
    body: str
    variables: Dict[str, Any] = {}
    assigned_staff_id: Optional[str] = None
    require_owner_signature: bool = True
    require_staff_signature: bool = True
    require_drawn_signature_owner: bool = False
    require_drawn_signature_staff: bool = False



class UpdateContractRequest(BaseModel):
    title: Optional[str] = None
    body: Optional[str] = None
    variables: Optional[Dict[str, Any]] = None
    assigned_staff_id: Optional[str] = None
    require_owner_signature: Optional[bool] = None
    require_staff_signature: Optional[bool] = None
    require_drawn_signature_owner: Optional[bool] = None
    require_drawn_signature_staff: Optional[bool] = None



class SignContractRequest(BaseModel):
    typed_name: Optional[str] = None
    drawing_base64: Optional[str] = None



class DigestPrefRequest(BaseModel):
    daily_digest_enabled: Optional[bool] = None
    daily_digest_utc_hour: Optional[int] = None  # 0-23 UTC



# =========================
# Push tokens & notification preferences
# =========================
class RegisterPushTokenRequest(BaseModel):
    token: str
    platform: Optional[str] = None  # "ios" | "android" | "web"
    device_name: Optional[str] = None



class NotificationPrefsRequest(BaseModel):
    daily_digest: Optional[bool] = None
    important_alerts: Optional[bool] = None
