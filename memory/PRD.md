# Cozii — Product Requirements (Phase 1)

## Vision
Cozii is a cozy, pastel-themed home inventory and finance management app for families and roommates. Members share spaces where they track what's in the pantry, closet, skincare shelf, and wallet — so no one double-buys milk again.

## Phase 1 — Delivered MVP

### Authentication
- Email/Password registration & login (bcrypt, 7-day session tokens)
- Emergent Google Social Login (web flow via session_id in URL fragment)
- `/api/auth/me`, `/api/auth/logout`, session cookies + Bearer token support

### Family Spaces (shared households)
- Create a space with a name; 6-character invite code auto-generated
- Join a space by invite code
- Switch between multiple spaces
- View members with owner badge
- Copy invite code (clipboard)

### Customizable Categories
- Starter categories auto-seeded on space creation (Food, Skincare, Closet, Toiletries, Cleaning)
- Custom category creation with:
  - Name, Icon (13+ options), Color tint (7 pastel options)
  - Custom fields per category (text / number / date / price)
- Delete category (cascades items)

### Items CRUD
- Name, photo (base64), status (available / low / finished)
- Quantity, unit, price, purchase date, expiry date, notes
- Dynamic category-specific custom fields
- **Edit finished items** (user-requested — status can be changed back)
- Quick mark-finished / restore toggle
- Delete item
- Filters: All, Available, Low, Finished

### Real-time feel
- Polling refresh every 10s on focus
- Pull-to-refresh on every list screen
- Activity feed shows who added/updated/finished what

### Finance Dashboard
- Monthly spend total with vs-last-month delta
- Spending by category with proportional bars
- Recent purchases list with thumbnails

### Home Dashboard
- Greeting + user name
- Space switcher
- Stats grid (in-stock count, expiring soon within 7 days, running low, spent this month)
- Quick-add + Browse actions
- Recent activity feed with member avatars & relative timestamps

## Tech Stack
- **Frontend**: React Native Expo (SDK 54) + Expo Router + TypeScript
  - Storage: AsyncStorage for token + active space id
  - Images: expo-image-picker (base64 storage)
  - Icons: lucide-react-native
- **Backend**: FastAPI + Motor (async MongoDB)
- **Database**: MongoDB (custom `user_id`, all queries exclude `_id`)
- **Auth**: bcrypt password hashing, opaque session tokens (7 days)

## Design Language
- Pastel archetype: peach primary (#FFB5A7), mint, lavender, yellow, sage, pink, blue tints
- Soft rounded corners (24px cards, pill buttons)
- Cozy off-white background (#FEF9F8)
- Nunito-style bold headings with -0.5 letter spacing

## Phase 2 (Partially Delivered)
- ✅ AI receipt / item scanning with GPT-4o Vision (via Emergent LLM key) — full bulk flow from photo → extracted editable items → save in one step, with default + per-item category assignment
- ⏳ Socket.io real-time push (polling still active)
- ⏳ Investment tracking module
- ⏳ Low-stock alerts & expiry reminders
- ⏳ Shopping list with "already have" cross-check
