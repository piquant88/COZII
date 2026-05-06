#====================================================================================================
# START - Testing Protocol - DO NOT EDIT OR REMOVE THIS SECTION
#====================================================================================================

# THIS SECTION CONTAINS CRITICAL TESTING INSTRUCTIONS FOR BOTH AGENTS
# BOTH MAIN_AGENT AND TESTING_AGENT MUST PRESERVE THIS ENTIRE BLOCK

# Communication Protocol:
# If the `testing_agent` is available, main agent should delegate all testing tasks to it.
#
# You have access to a file called `test_result.md`. This file contains the complete testing state
# and history, and is the primary means of communication between main and the testing agent.
#
# Main and testing agents must follow this exact format to maintain testing data. 
# The testing data must be entered in yaml format Below is the data structure:
# 
## user_problem_statement: {problem_statement}
## backend:
##   - task: "Task name"
##     implemented: true
##     working: true  # or false or "NA"
##     file: "file_path.py"
##     stuck_count: 0
##     priority: "high"  # or "medium" or "low"
##     needs_retesting: false
##     status_history:
##         -working: true  # or false or "NA"
##         -agent: "main"  # or "testing" or "user"
##         -comment: "Detailed comment about status"
##
## frontend:
##   - task: "Task name"
##     implemented: true
##     working: true  # or false or "NA"
##     file: "file_path.js"
##     stuck_count: 0
##     priority: "high"  # or "medium" or "low"
##     needs_retesting: false
##     status_history:
##         -working: true  # or false or "NA"
##         -agent: "main"  # or "testing" or "user"
##         -comment: "Detailed comment about status"
##
## metadata:
##   created_by: "main_agent"
##   version: "1.0"
##   test_sequence: 0
##   run_ui: false
##
## test_plan:
##   current_focus:
##     - "Task name 1"
##     - "Task name 2"
##   stuck_tasks:
##     - "Task name with persistent issues"
##   test_all: false
##   test_priority: "high_first"  # or "sequential" or "stuck_first"
##
## agent_communication:
##     -agent: "main"  # or "testing" or "user"
##     -message: "Communication message between agents"

# Protocol Guidelines for Main agent
#
# 1. Update Test Result File Before Testing:
#    - Main agent must always update the `test_result.md` file before calling the testing agent
#    - Add implementation details to the status_history
#    - Set `needs_retesting` to true for tasks that need testing
#    - Update the `test_plan` section to guide testing priorities
#    - Add a message to `agent_communication` explaining what you've done
#
# 2. Incorporate User Feedback:
#    - When a user provides feedback that something is or isn't working, add this information to the relevant task's status_history
#    - Update the working status based on user feedback
#    - If a user reports an issue with a task that was marked as working, increment the stuck_count
#    - Whenever user reports issue in the app, if we have testing agent and task_result.md file so find the appropriate task for that and append in status_history of that task to contain the user concern and problem as well 
#
# 3. Track Stuck Tasks:
#    - Monitor which tasks have high stuck_count values or where you are fixing same issue again and again, analyze that when you read task_result.md
#    - For persistent issues, use websearch tool to find solutions
#    - Pay special attention to tasks in the stuck_tasks list
#    - When you fix an issue with a stuck task, don't reset the stuck_count until the testing agent confirms it's working
#
# 4. Provide Context to Testing Agent:
#    - When calling the testing agent, provide clear instructions about:
#      - Which tasks need testing (reference the test_plan)
#      - Any authentication details or configuration needed
#      - Specific test scenarios to focus on
#      - Any known issues or edge cases to verify
#
# 5. Call the testing agent with specific instructions referring to test_result.md
#
# IMPORTANT: Main agent must ALWAYS update test_result.md BEFORE calling the testing agent, as it relies on this file to understand what to test next.

#====================================================================================================
# END - Testing Protocol - DO NOT EDIT OR REMOVE THIS SECTION
#====================================================================================================



#====================================================================================================
# Testing Data - Main Agent and testing sub agent both should log testing data below this section
#====================================================================================================

user_problem_statement: |
  Cozii home inventory + finance app for roommates/family. Continuing work:
    1. Itemized split breakdown — when viewing /splits, tapping on a roommate should show
       exactly WHAT items they owe for (item name, category, price, share).
    2. Recurring bills — CRUD for monthly/weekly/yearly bills (rent, wifi, electricity).
       Show reminder, user confirms "Mark paid" → logs an item in the category (which cascades
       to splits) and resets the period counter.
    3. Roommate agreement — a simple free-text document per space, everyone can view/edit/sign;
       editing resets signatures so everyone re-agrees.

backend:
  - task: "Space type field (POST/PATCH/GET /api/spaces)"
    implemented: true
    working: true
    file: "/app/backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: true
        agent: "testing"
        comment: |
          Retested 2026-05-01 after main agent added space_type field to FamilySpace,
          CreateSpaceRequest, and UpdateSpaceRequest Pydantic models. All 13 scenarios
          pass against the preview URL:
            ✅ POST /spaces {name, space_type:"household", currency:"IDR"} → 200,
               response.space_type="household", response.currency="IDR"
            ✅ POST /spaces {name only, no space_type} → 200, defaults to
               space_type="roommates"
            ✅ POST /spaces {space_type:"garbage"} → 200, falls back to
               space_type="roommates"
            ✅ PATCH /spaces/{id} {space_type:"HOUSEHOLD"} → 200, normalised to
               "household"
            ✅ PATCH /spaces/{id} {space_type:"foo"} → 200, prior value ("household")
               left unchanged
            ✅ GET /spaces → every entry includes a non-empty space_type (existing
               seeded space = "roommates"; new household/default/garbage entries
               match expected values)
            ✅ Non-member PATCH /spaces/{id} → 403
          No further work needed.
      - working: false
        agent: "testing"
        comment: |
          CRITICAL — POST /api/spaces and PATCH /api/spaces/{id} are completely broken
          (both return 500 Internal Server Error on every call, including payloads that
          don't mention space_type).

          Root cause: `CreateSpaceRequest` (server.py:133-135) and `UpdateSpaceRequest`
          (server.py:138-140) Pydantic models are missing the `space_type` field, but
          the handlers reference `body.space_type`:
            - create_space line 426:  `stype = (body.space_type or "roommates")...`
            - update_space line 517:  `if body.space_type is not None:`
          In Pydantic v2, accessing an undeclared attribute on a BaseModel instance
          raises `AttributeError: 'CreateSpaceRequest' object has no attribute
          'space_type'`. Confirmed in /var/log/supervisor/backend.err.log.

          Additional issue: `FamilySpace` response model (server.py:123-130) also has no
          `space_type` field, so every GET /spaces entry is missing `space_type` (even
          the fallback-to-"roommates" rewrite on line 527 is stripped by response_model
          serialisation).

          Fix required in main agent code (3 places):
            1. Add `space_type: str = "roommates"` to CreateSpaceRequest
            2. Add `space_type: Optional[str] = None` to UpdateSpaceRequest
            3. Add `space_type: str = "roommates"` to FamilySpace

          Test output (4 fails):
            FAIL POST /spaces {space_type: household} -> 500
            FAIL POST /spaces (no space_type) defaults to roommates -> 500
            FAIL PATCH /spaces {space_type: HOUSEHOLD} -> skipped (no space id, PATCH also 500 on direct curl)
            FAIL GET /spaces each entry has space_type -> space_type key missing

          Because POST is broken, cannot create a fresh "household" space with currency=IDR
          for the rest of the tests — had to fall back to an existing USD space which is
          owned by test@cozii.app.

  - task: "Household Roles (/api/household/roles)"
    implemented: true
    working: true
    file: "/app/backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: true
        agent: "testing"
        comment: |
          All 6 scenarios pass against the live preview URL:
            - GET on a space auto-seeds 10 defaults (Owner, Spouse, Child, Parent, Maid,
              Driver, Nanny, Cook, Gardener, Security), all is_default=true
            - POST custom role {name:"Tutor", icon:"BookOpen", color:"lavender",
              category:"staff"} returns is_default=false
            - PATCH role updates name/icon/color
            - DELETE on a default role returns 400
            - DELETE on custom role returns 200 and disappears from GET
            - Non-member GET returns 403

  - task: "Household Family members (/api/household/family)"
    implemented: true
    working: true
    file: "/app/backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: true
        agent: "testing"
        comment: |
          All 5 scenarios pass:
            - POST {name:"Maya", role_id:<Child>, age:8, school:"Bali Primary",
              allergies:"peanuts"} returns FamilyMember with role_name="Child"
            - GET lists it with role_name resolved
            - PATCH name + photo_base64 persisted
            - DELETE removes (GET no longer returns it)
            - Non-member GET returns 403

  - task: "Household Staff (/api/household/staff)"
    implemented: true
    working: true
    file: "/app/backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: true
        agent: "testing"
        comment: |
          Retested 2026-05-01 after main agent updated create_staff to reuse the
          dict returned by assert_space_member (server.py:1917,1929). All 3 salary
          default scenarios pass:
            ✅ POST /household/staff into USD space, no salary_currency in body →
               response.salary_currency = "USD"
            ✅ POST /household/staff into IDR space (new household space,
               currency=IDR), no salary_currency in body →
               response.salary_currency = "IDR"
            ✅ POST /household/staff with explicit salary_currency="EUR" → response
               returns "EUR" (override wins over space currency)
          Prior pass remains: GET list with role_name resolved, PATCH phone/notes,
          DELETE, and non-member 403.
      - working: false
        agent: "testing"
        comment: |
          4/5 scenarios pass, but salary_currency default is broken.

          POST /household/staff without salary_currency returns `salary_currency: null`
          instead of defaulting to the space's currency. Verified via curl:
            Space space_13322312d867476a has currency="USD" (confirmed via GET /spaces).
            POST /household/staff {name,salary,pay_cycle,off_day} on that space returns
            `"salary_currency": null`. Expected: `"USD"` (or `"IDR"` for a household
            space using that currency).

          The line looks correct:
            server.py:1927
            "salary_currency": (body.salary_currency or (space.get("currency") if space else "USD"))
          but the returned value is null. Main agent should debug whether `space` is
          actually being fetched (the `assert_space_member` call happens before the
          find_one, and returns the space doc — but the new find_one here could be
          returning None if `body.space_id` is ever re-assigned or projected oddly). A
          safer fix is to re-use the dict returned by `assert_space_member`:

            space = await assert_space_member(body.space_id, user.user_id)
            ...
            "salary_currency": body.salary_currency or space.get("currency") or "USD",

          Other staff flows pass:
            - GET list returns new staff with role_name resolved
            - PATCH phone + notes updates correctly
            - DELETE removes it
            - Non-member GET returns 403

  - task: "Household Handbook (/api/household/handbook)"
    implemented: true
    working: true
    file: "/app/backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: true
        agent: "testing"
        comment: |
          All 5 scenarios pass:
            - POST {title:"Wifi", body:"Network:...\nPassword:12345", icon:"Star",
              color:"sage"} returns HandbookEntry with sort=0
            - GET list includes the entry (sorted by sort, created_at)
            - PATCH title/body changes `updated_at` (confirmed before != after)
            - DELETE removes it
            - Non-member GET returns 403

  - task: "Itemized balance breakdown endpoint"
    implemented: true
    working: true
    file: "/app/backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: "NA"
        agent: "main"
        comment: |
          Added GET /api/balance-details?space_id=X&with_user_id=Y. Returns
          breakdown[] (item_id, name, category_name, price, share_each, split_count,
          direction='they_owe_you'|'you_owe_them', amount, photo_base64) and settlements[].
          Only items in shared categories that include BOTH current user and target user.
      - working: true
        agent: "testing"
        comment: |
          Verified end-to-end via /app/backend_test.py against the public preview URL.
          Setup: registered users A (Alex Morgan) + B (Riley Chen), A created space, B joined
          via invite_code, A created a 'Groceries (Shared)' Category with shared_with=[A,B].
          A created 2 priced items ($24.50 + $60.00), B created 1 priced item ($18.00).
          Result for A: breakdown has exactly 3 items, 2 with direction='they_owe_you'
          (A's purchases) and 1 with direction='you_owe_them' (B's purchase). For B: mirror
          (1 they_owe_you, 2 you_owe_them). share_each verified = price / split_count
          rounded to 2 decimals (e.g. $18 / 2 = $9.00). settlements[] is present and
          populated correctly after creating a settlement (1 returned). No regressions in
          /api/balances (net math = $33.25, expected).

  - task: "Recurring bills CRUD"
    implemented: true
    working: true
    file: "/app/backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: "NA"
        agent: "main"
        comment: |
          POST /api/bills, GET /api/bills?space_id=, PATCH /api/bills/{id},
          DELETE /api/bills/{id}, POST /api/bills/{id}/pay. Pay endpoint marks last_paid_date
          and (if category_id) creates an item in that category so it flows into finance
          + splits. Frequencies: monthly | weekly | yearly | once. Computes next_due_date
          and is_paid_current_period server-side.
      - working: false
        agent: "testing"
        comment: |
          CRUD + pay-creates-item flow works, BUT _compute_bill_state has a bug for monthly
          bills paid after the due_day. Repro: today=2026-04-30, bill due_day=15
          (frequency=monthly). After POST /api/bills/{id}/pay, last_paid_date is set
          correctly to 2026-04-30, but the response returns is_paid_current_period=false.
          
          Root cause in /app/backend/server.py _compute_bill_state monthly branch
          (~lines 1141-1158): when today > this_month_due, next_due is correctly set to the
          following month's 15th, but period_start is then computed as
          next_due.replace(day=1) (= 2026-05-01). The check
          `last_paid_d (2026-04-30) >= period_start (2026-05-01)` is therefore False, so
          a payment made in the SAME month after the due day is treated as not paid.
          
          Suggested fix: when next_due is in a future month, period_start should be
          this_month_due.replace(day=1) (i.e. 2026-04-01), not
          next_due.replace(day=1). Equivalently, period_start = the 1st of the month of
          this_month_due.
          
          Other bills tests pass:
          - POST /bills (monthly, due_day=15, amount=100) → next_due_date set, is_paid=false
          - GET /bills?space_id=... lists the bill (B can see A's bill)
          - PATCH /bills/{id} updates name + amount
          - POST /bills/{id}/pay creates an item in the bill's category with the bill name
            and price == bill.amount (verified via GET /items)
          - The new item appears in /balance-details breakdown after payment
          - DELETE /bills/{id} removes the bill but leaves historical items intact
      - working: true
        agent: "testing"
        comment: |
          Re-tested after fix to _compute_bill_state monthly branch (period_start now uses
          this_month_due.replace(day=1) on line 1157). Verified end-to-end against the
          public preview URL (today=2026-04-30 UTC):
          
          Scenario A — monthly bill with due_day=15 (today > this_month_due):
            - POST /api/bills (monthly, due_day=15, amount=60) → 200, next_due_date=2026-05-15,
              is_paid_current_period=false, last_paid_date=null. ✅
            - POST /api/bills/{id}/pay → 200, is_paid_current_period=TRUE,
              last_paid_date=2026-04-30, next_due_date=2026-05-15. ✅ (was the bug)
            - GET /api/bills?space_id=... → same bill returns is_paid_current_period=TRUE,
              last_paid_date=2026-04-30, next_due_date=2026-05-15. ✅
          
          Scenario B — monthly bill with due_day=1 (today=30 also > this_month_due=2026-04-01):
            - Created, paid, list — all return is_paid_current_period=TRUE,
              last_paid_date=2026-04-30, next_due_date=2026-05-01. ✅
          
          The previous bug (period_start = next month) is resolved. No regressions observed.

  - task: "Roommate agreement CRUD + sign"
    implemented: true
    working: true
    file: "/app/backend/server.py"
    stuck_count: 0
    priority: "medium"
    needs_retesting: false
    status_history:
      - working: "NA"
        agent: "main"
        comment: |
          GET /api/agreement?space_id=, PUT /api/agreement?space_id= (resets signatures),
          POST /api/agreement/sign?space_id=. Only space members can read/write. Upsert so
          every space gets at most 1 agreement.
      - working: true
        agent: "testing"
        comment: |
          All flows verified:
          - GET /api/agreement?space_id=<fresh space> returns 200 with body null
          - PUT /api/agreement?space_id=... creates Agreement with signatures=[]
          - POST /api/agreement/sign as A → signatures=[A]
          - Re-sign as A → still exactly 1 entry (deduplicated, signed_at updated)
          - Sign as B → signatures has both [A, B]
          - PUT /api/agreement (edit text) as B → signatures reset to []
          - Access control verified: a non-member (user C, not joined) gets 403 on GET, PUT,
            and POST /sign.

frontend:
  - task: "Splits screen — itemized breakdown expansion"
    implemented: true
    working: "NA"
    file: "/app/frontend/app/splits.tsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: "NA"
        agent: "main"
        comment: |
          Balance rows are now tappable. Expanding fetches /balance-details and renders
          each shared item (name, category, price, share) under the row. Mark-paid flow unchanged.

  - task: "Recurring bills screen"
    implemented: true
    working: "NA"
    file: "/app/frontend/app/bills.tsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: "NA"
        agent: "main"
        comment: |
          New full screen with empty-state hero, due/upcoming/paid sections, add/edit modal
          (name, amount, icon, frequency, due_day, category, split-with members, notes),
          and a confirm-before-pay dialog. Linked from Profile → "Recurring bills" and from
          Finance tab quick-links.

  - task: "Roommate agreement screen"
    implemented: true
    working: "NA"
    file: "/app/frontend/app/agreement.tsx"
    stuck_count: 0
    priority: "medium"
    needs_retesting: false
    status_history:
      - working: "NA"
        agent: "main"
        comment: |
          Full-screen editor + viewer. Guided template button populates a skeleton. Saving
          resets signatures; each member can sign / re-sign. Linked from Profile.

  - task: "Household Phase 2 — Tasks (/api/household/tasks)"
    implemented: true
    working: true
    file: "/app/backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: true
        agent: "testing"
        comment: |
          All 18/18 task scenarios pass against preview URL (2026-XX-XX).
          - POST recurrence=daily → returns TaskTemplate, active=true, requires_photo=false ✅
          - POST recurrence=weekly weekdays=[0,2,4] → weekdays list returned ✅
          - POST recurrence=monthly monthly_day=15 → ok ✅
          - POST recurrence=once once_date="2026-06-15" → ok ✅
          - GET ?space_id=&date=TODAY → {date, tasks[]} shape, due_today logic correct
            for daily/weekly/monthly/once (verified against today.weekday()=5,
            today.day, exact-date match) ✅
          - PATCH task title + description updates ✅
          - POST /complete first call → {completed:true}; GET shows completed_today=true ✅
          - POST /complete second call → {completed:false} (toggle); GET shows
            completed_today=false ✅
          - DELETE task → 200 and disappears from GET ✅
          - Non-member GET 403 + POST 403 ✅

  - task: "Household Phase 2 — Attendance (/api/household/attendance)"
    implemented: true
    working: true
    file: "/app/backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: true
        agent: "testing"
        comment: |
          All 7/7 attendance scenarios pass.
          - POST {space_id, staff_id, date:"2026-06-01", status:"present"} → AttendanceLog ✅
          - POST same (staff_id+date) status:"sick" → upsert keeps attendance_id,
            status flips to "sick" ✅
          - POST status:"partying" → 400 ✅
          - GET ?date_from=2026-06-01&date_to=2026-06-01 returns the record ✅
          - GET ?staff_id=... returns only that staff's records (verified by adding a
            second staff with their own attendance row, then filtering) ✅
          - Non-member GET + POST → 403 ✅

  - task: "Household Phase 2 — Shopping requests (/api/household/shopping)"
    implemented: true
    working: true
    file: "/app/backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: true
        agent: "testing"
        comment: |
          All 11/11 shopping scenarios pass.
          - POST {Rice, 5kg, urgency:"high", category_id} → status=pending, urgency=high ✅
          - POST urgency:"xyz" → normalised to "normal" ✅
          - GET list sorted by created_at desc ✅
          - GET entries enriched with requested_by_name + category_name ✅
          - GET ?status=pending filters correctly ✅
          - PATCH status:"approved" → approved_by = current user, status updated ✅
          - PATCH status:"purchased" → fulfilled_at set ✅
          - DELETE → 200 and disappears from GET ✅
          - Non-member GET + POST → 403 ✅

metadata:
  created_by: "main_agent"
  version: "3.2"
  test_sequence: 5
  run_ui: false

test_plan:
  current_focus: []
  stuck_tasks: []
  test_all: false
  test_priority: "high_first"

agent_communication:
  - agent: "testing"
    message: |
      Focused retest (2026-05-01) on the two previously-failing tasks. Both PASS.
      
      ✅ Space type field (POST/PATCH/GET /api/spaces) — all 13 scenarios pass:
         - POST {name, space_type:"household", currency:"IDR"} → space_type=household,
           currency=IDR
         - POST {name only} → defaults to space_type=roommates
         - POST {space_type:"garbage"} → falls back to space_type=roommates
         - PATCH {space_type:"HOUSEHOLD"} → normalised to "household"
         - PATCH {space_type:"foo"} → prior value unchanged
         - GET /spaces → every entry has a non-empty space_type (existing rows="roommates")
         - Non-member PATCH → 403
      
      ✅ Household Staff salary_currency default — all 3 scenarios pass:
         - POST /household/staff into USD space, no salary_currency → "USD"
         - POST /household/staff into IDR space, no salary_currency → "IDR"
         - POST with explicit salary_currency="EUR" → "EUR" (override wins)
      
      Both tasks updated in test_result.md to working=true, needs_retesting=false.
      No further backend work required on these two items.

agent_communication:
  - agent: "main"
    message: |
      Added three new backend capabilities:
        1. GET /api/balance-details (itemized per-roommate debt breakdown)
        2. Bills CRUD + pay flow (/api/bills, /api/bills/{id}/pay) which also creates an item
           in the bill's category on pay so it cascades into finance and splits.
        3. Agreement GET/PUT/sign (/api/agreement, /api/agreement/sign).
      Credentials in /app/memory/test_credentials.md (test@cozii.app / test1234).
      Please test:
        - Create a bill (category_id optional), mark paid, verify last_paid_date, is_paid_current_period
          flips to true, and if category_id was set, a new item appears in /items for that category.
        - Deleting a bill should not delete historical items.
        - /balance-details returns only items from categories where both current user and with_user_id
          are in shared_with (len >= 2). Direction is 'they_owe_you' when current user created item,
          'you_owe_them' when the other user created it.
        - Agreement PUT resets signatures[]; sign adds exactly one signature per user (upsert behavior
          when same user signs again).
  - agent: "testing"
    message: |
      Backend regression run completed via /app/backend_test.py (37/38 PASS).
      
      ✅ Itemized balance breakdown (/api/balance-details) — fully working, all scenarios match
         (counts, mirroring, share_each math, settlements list).
      ✅ Roommate agreement (/api/agreement, /api/agreement/sign) — fully working including
         dedup, signature reset on edit, and 403 access control for non-members.
      ✅ Existing endpoints regression: /auth/register, /auth/login, /spaces, /spaces/join,
         /spaces/{id}/members, /categories, /items, /balances (net math correct), /settlements.
      
      ❌ ONE BUG in Recurring bills — POST /api/bills/{id}/pay sets last_paid_date correctly
         but returns is_paid_current_period=false when today is past the due_day in the
         current month. Root cause: in _compute_bill_state monthly branch
         (/app/backend/server.py around lines 1141-1158), period_start is set to
         next_due.replace(day=1) (= 1st of NEXT month) when next_due was bumped forward,
         instead of the 1st of THIS month. Reproduction with today=2026-04-30, due_day=15:
         next_due=2026-05-15 → period_start=2026-05-01 → last_paid_d (2026-04-30) >=
         period_start fails. Suggested fix: period_start should always be
         this_month_due.replace(day=1) (i.e. start of the month containing today's due_day).
         The rest of the bills flow (CRUD, pay creates an item with bill name + amount in
         the category, item appears in /balance-details, DELETE keeps historical items) all
         work correctly.
  - agent: "testing"
    message: |
      Re-tested Recurring bills CRUD after the _compute_bill_state fix
      (period_start now uses this_month_due.replace(day=1)).
      
      ✅ Monthly bill due_day=15, today=2026-04-30 (today > this_month_due):
         POST /api/bills/{id}/pay returns is_paid_current_period=true,
         last_paid_date=2026-04-30, next_due_date=2026-05-15. GET /api/bills returns the
         same state. The original bug is fixed.
      ✅ Edge: monthly bill due_day=1, today=2026-04-30 (today > 2026-04-01) — same flow
         returns is_paid_current_period=true, next_due_date=2026-05-01. No regression.
      
      Marking task working=true, needs_retesting=false. No further bills work needed.
  - agent: "testing"
    message: |
      New-feature backend test run (2026-05-01) via /app/backend_test.py — 47/47 PASS.
      Covers:
        1) Currency on Space + PATCH /api/spaces/{space_id}
  - agent: "testing"
    message: |
      Household Phase 1 backend testing complete (2026-05-01). 20/24 PASS.

      ❌ CRITICAL — Space type field (POST /api/spaces and PATCH /api/spaces) is
         completely broken: every request returns 500 Internal Server Error.
         Root cause: `CreateSpaceRequest` and `UpdateSpaceRequest` Pydantic models
         are missing the `space_type` field, but handlers at server.py:426 and :517
         access `body.space_type`, raising `AttributeError: 'CreateSpaceRequest'
         object has no attribute 'space_type'`. Additionally `FamilySpace` response
         model is missing `space_type`, so GET /spaces entries never include it.

         Fix (3 model additions, no logic changes):
           class CreateSpaceRequest:   space_type: str = "roommates"
           class UpdateSpaceRequest:   space_type: Optional[str] = None
           class FamilySpace:          space_type: str = "roommates"

         This blocks the ability to create new spaces of any kind right now, not
         just household ones. It is a regression on existing /spaces behaviour.

      ❌ Staff salary_currency default is null, not space.currency.
         POST /household/staff without salary_currency returns
         `"salary_currency": null` on a space whose currency is "USD".
         Reproduction (curl) shown in task status_history. Suggested fix:
         reuse the dict returned by `assert_space_member` instead of a second
         find_one, and guard against None currency:
           space = await assert_space_member(body.space_id, user.user_id)
           ...
           "salary_currency": body.salary_currency or space.get("currency") or "USD",

      ✅ Roles (/api/household/roles) — 6/6 scenarios pass (auto-seed of 10
         defaults, POST custom, PATCH, DELETE default→400, DELETE custom→200,
         non-member→403).
      ✅ Family (/api/household/family) — 5/5 scenarios pass (create with
         role_name resolved to "Child", list, PATCH name+photo_base64, DELETE,
         non-member→403).
      ✅ Handbook (/api/household/handbook) — 5/5 scenarios pass (POST with
         sort=0, GET list, PATCH changes updated_at, DELETE, non-member→403).
      ✅ Staff (/api/household/staff) — 4/5 scenarios pass (GET with role_name
         "Maid", PATCH phone+notes, DELETE, non-member→403). Only salary_currency
         default failed (see above).

      NOTE: Because POST /spaces is broken I could not create a fresh household
      space with currency=IDR; the household tests were run against the existing
      USD space owned by test@cozii.app (space_13322312d867476a). Once POST/PATCH
      /spaces are fixed, the review test will be able to verify the IDR default
      for salary_currency end-to-end.

           ✅ POST /spaces with currency="CAD" → response currency "CAD"
           ✅ POST /spaces without currency → defaults to "USD"
           ✅ PATCH /spaces {currency:"idr"} → normalized to "IDR"
           ✅ PATCH /spaces name-only → name updates, currency unchanged (still "IDR")
           ✅ PATCH /spaces by non-member → 403
           ✅ GET /spaces → every entry contains a `currency` field
        2) GET /api/reports/finance (new)
           Pre-seeded: 1 space (currency=EUR), 1 category, 3 items priced 10/20/30
           with created_at at today, today-2d, today-5d (overridden directly in MongoDB to
           avoid API-only now_utc() timestamping).
           Primary shape assertions run against period="ytd" because today (2026-05-01) is
           the first of the month, so the -2d and -5d items straddle into April (last_month).
           Using period="ytd" keeps all 3 items in window and lets us assert the full shape.
           ✅ 200 response with all required top-level keys:
              period_key, period_label, start, end, currency, totals, by_category,
              by_member, daily, monthly, top_items, all_items, bills, settlements, insights
           ✅ currency inherited from space ("EUR")
           ✅ totals == {total:60, count:3, avg_per_item:20, largest:30, smallest:10}
           ✅ by_category has 1 entry (Groceries, mint tint, total:60, count:3, pct:100)
           ✅ by_member has current user at total:60, count:3, pct:100
           ✅ daily has 3 entries (one per seeded day)
           ✅ monthly has ≥1 entry (2 in this case: April + May)
           ✅ top_items sorted desc: 30, 20, 10, each with item_id/name/category_name/price/
              purchased_by/created_at populated
           ✅ all_items has 3 entries with item_id, name, category_name, price, quantity,
              purchased_by, purchase_date, expiry_date, status, created_at
           ✅ bills == [] initially, settlements == [] initially
           ✅ insights non-empty; first insight reads
              "You logged 3 purchases totalling 60.00 EUR."
           Period filtering:
           ✅ period=this_month (today.day=1) returned count=1 — proves the -5d item is
              correctly excluded. On any day≥6 all 3 items would be in-window; on day 3–5 at
              least the -5d item is filtered out; on day 1–2 only today's item survives. Test
              adapts to today.day and passed.
           ✅ period=last_month / last_3_months / ytd / all all return 200.
           ✅ Non-member receives 403 on /reports/finance for the space.
        3) Smoke on existing endpoints — all green:
           ✅ /auth/login (seeded test@cozii.app / test1234)
           ✅ /spaces GET
           ✅ /categories: POST / GET / PATCH / DELETE
           ✅ /items: POST / GET / PATCH / DELETE
           ✅ /bills: POST / GET / PATCH / POST /pay (is_paid_current_period=true) / DELETE
           ✅ /agreement: GET / PUT / POST /sign (1 signature)
           ✅ /balance-details
           ✅ /balances
      
      Conclusion: new currency + finance report features are production-ready. Existing
      endpoints unaffected. No backend bugs surfaced in this run.
  - agent: "testing"
    message: |
      Household Phase 2 backend testing complete — 36/36 PASS via /app/backend_test.py
      against the preview URL.

      ✅ Tasks (/api/household/tasks): create with daily / weekly+weekdays /
         monthly+monthly_day / once+once_date all return correct TaskTemplate.
         GET ?date=TODAY returns {date, tasks[]} with due_today computed correctly
         per recurrence (daily=true; weekly only when today.weekday() ∈ weekdays;
         monthly only when today.day == monthly_day; once only when once_date == TODAY).
         PATCH updates title/description. POST /complete toggles
         completed↔not-completed and GET reflects completed_today both ways.
         DELETE removes from GET. Non-member 403 on GET + POST.
      ✅ Attendance (/api/household/attendance): present create works, then re-POST
         with status="sick" upserts (same attendance_id, status flips). Invalid
         "partying" → 400. Date-range filter and staff_id filter both work
         (verified by adding a 2nd staff with their own attendance row).
         Non-member 403 on GET + POST.
      ✅ Shopping (/api/household/shopping): POST {Rice, 5kg, urgency:"high",
         category_id} → status=pending, urgency=high. urgency:"xyz" → normalised
         to "normal". GET sorted desc by created_at and enriched with
         requested_by_name + category_name. ?status=pending filter works.
         PATCH status=approved sets approved_by; PATCH status=purchased sets
         fulfilled_at. DELETE works. Non-member 403.

      No bugs surfaced. All Phase 2 endpoints are production-ready.


## 2026-06-XX — Phase 4 additions (staff permissions, notifications, household report)

backend:
  - task: "Staff permissions incl. view_inventory"
    implemented: true
    working: true
    file: "/app/backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: true
        agent: "testing"
        comment: |
          Re-tested 2026-06-XX after main agent added `invite_code: Optional[str]`
          and `permissions: Dict[str, bool] = Field(default_factory=dict)` fields
          to the StaffMember Pydantic response model (server.py:1702-1703).
          /app/backend_test_phase4_retest.py — 18/18 PASS:
            ✅ POST /household/staff response.invite_code = 6-char alphanumeric
               (e.g. "533845")
            ✅ POST response.permissions is a non-empty dict containing all 9
               keys including `view_inventory: false`
            ✅ PATCH /household/staff/{id}/permissions returns 200 with
               invite_code + permissions populated; view_inventory=True merged
               correctly while retaining other defaults (view_tasks=True etc).
            ✅ GET /household/staff list entries include invite_code and the
               merged permissions dict (view_inventory=True after PATCH).
          The Phase 4 staff-join UX is now unblocked — owner can read invite_code
          from the create-staff response and share it with the staff member.
      - working: "NA"
        agent: "main"
        comment: |
          Added `view_inventory` key to DEFAULT_STAFF_PERMS (default False).
          /api/spaces/{space_id}/my_role returns permissions merged with new key.
          PATCH /api/household/staff/{staff_id}/permissions accepts the new key.
      - working: false
        agent: "testing"
        comment: |
          Tested 2026-06-?? via /app/backend_test_phase4.py against the preview URL.
          Functional flow IS working end-to-end (verified through /spaces/{id}/my_role
          and via direct MongoDB inspection):
            ✅ DEFAULT_STAFF_PERMS now includes `view_inventory: False` (mongo doc on
               new staff has all 9 keys: view_tasks, log_attendance, request_shopping,
               view_handbook, view_wage_amount, view_other_staff, view_family,
               view_finance, view_inventory)
            ✅ Owner PATCH /household/staff/{id}/permissions merges new keys (set
               view_inventory=True + view_finance=True; other defaults preserved:
               view_tasks=True, view_handbook=True, view_other_staff=False)
            ✅ Non-member PATCH → 403 ("Not a member of this space")
            ✅ Staff (non-owner member) PATCH after joining → 403 ("Only the space
               owner can change staff permissions")
            ✅ POST /household/staff/join with invite_code links the user as staff,
               adds them to space.member_ids, returns {ok, space_id, staff_id}
            ✅ GET /spaces/{space_id}/my_role as staff user returns
               {role:"staff", staff_id, permissions:{... view_inventory:true,
               view_finance:true ...}}

          ❌ CRITICAL — `StaffMember` Pydantic response model
             (server.py:1672-1689) is missing the `invite_code` and `permissions`
             fields. Because POST /household/staff, GET /household/staff, and
             PATCH /household/staff/{id}/permissions all return
             `StaffMember(**doc)`, these two fields are stripped from every
             response — even though the data is correctly stored in MongoDB.

             Repro:
               POST /household/staff (owner) →
                 response.invite_code == null   (mongo has 'E4F8E9')
                 response.permissions == null   (mongo has full 9-key dict)
               GET /household/staff →
                 each entry's permissions == {}
               PATCH /household/staff/{id}/permissions →
                 response keys = [..., 'salary', 'salary_currency', ...]
                 (no 'permissions' or 'invite_code')

             Impact (frontend-blocking):
               - The owner UI cannot read the invite_code from the create-staff
                 response → cannot show / share the invite code with the staff
                 member, breaking the Phase 4 staff-join flow entirely.
               - The Staff list cannot render permission toggles (always empty).
               - The "perms editor" PATCH UI cannot reflect the merged result
                 returned by the server.

             Fix (3 lines in server.py around line 1689 — add to StaffMember):
               invite_code: Optional[str] = None
               permissions: Dict[str, bool] = Field(default_factory=dict)

             (Permissions are also currently being read by the frontend via
             /spaces/{id}/my_role, which works — but invite_code must come from
             the staff record itself, so the response model fix is required.)

  - task: "Notifications collection + endpoints (GET /notifications, POST /notifications/{id}/read, POST /notifications/read_all)"
    implemented: true
    working: true
    file: "/app/backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: "NA"
        agent: "main"
        comment: |
          New Notification model + CRUD endpoints. POST /household/payroll now
          creates a `wage_paid` notification for the linked staff user (if
          staff.user_id is set). User can list own notifications, optionally
          filtered by space_id + unread_only, and mark individual or all read.
      - working: true
        agent: "testing"
        comment: |
          All 14/14 notification scenarios pass via /app/backend_test_phase4.py:
            ✅ GET /api/notifications?space_id=... initially returns []
            ✅ POST /api/household/payroll creates a `wage_paid` notification
               addressed to the linked staff user_id (verified after staff
               joined via invite_code).
            ✅ Notification fields:
                 - kind == "wage_paid"
                 - title == "Wage received · 2026-05"
                 - body  == "Sari Putri, your monthly pay of IDR 2500000.00
                            was logged by the owner."
                 - data  == {payment_id:"pay_…", period:"2026-05",
                            net:2500000.0, currency:"IDR"}
                 - read  == false initially
            ✅ GET ?unread_only=true returns only the unread record
            ✅ POST /notifications/{id}/read → 200; subsequent GET shows read=true
            ✅ Second POST /household/payroll creates a 2nd wage_paid notification
            ✅ POST /notifications/read_all?space_id=… marks all in scope as read
               (verified count=2, both reads=true)
            ✅ Outsider account (not a member of the space) gets [] from
               /api/notifications (cannot see other users' notifications)
          No bugs surfaced in this area. Production-ready.

  - task: "Household monthly report (/api/reports/household)"
    implemented: true
    working: true
    file: "/app/backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: "NA"
        agent: "main"
        comment: |
          GET /api/reports/household?space_id=...&year=YYYY&month=MM returns:
            { month, year, month_num, currency, total_spent, total_wages,
              top_categories:[...], staff:[...], shopping:{...}, tasks_done }
      - working: true
        agent: "testing"
        comment: |
          18/18 report scenarios pass:
            ✅ Default (no year/month) returns current month — month="May 2026",
               year=2026, month_num=5
            ✅ All required top-level keys present: month, year, month_num,
               currency, total_spent, total_wages, top_categories, staff,
               shopping, tasks_done
            ✅ currency inherited from space ("IDR")
            ✅ total_wages (5,000,000) == sum of two payroll.net in window
            ✅ staff[] item has all required fields: staff_id, name,
               photo_base64, role_id, days_present, days_off, days_sick,
               days_leave, tasks_done, paid, salary, pay_cycle.
               days_present=2 (we logged 2 'present' attendance rows),
               paid=5,000,000 (sum of that staff's payroll in window).
            ✅ top_categories[] items: category_id, name, icon, tint, total, count.
               Sum(top_categories.total) == total_spent (5,175,000).
               Includes "Staff wages" (auto-created by payroll) AND a Food&Pantry
               category with the seeded 175,000 IDR item.
            ✅ shopping summary {total:1, pending:1, approved:0, purchased:0}
               reflects the request created in window.
            ✅ Far-past month (year=2020 month=1) returns 200 with total_spent=0,
               total_wages=0, top_categories=[], shopping all zeros, tasks_done=0,
               currency still "IDR" from space.
            ✅ Non-member (outsider account) GET → 403 "Not a member of this space".

  - task: "GET /api/categories after payroll regression"
    implemented: true
    working: true
    file: "/app/backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: true
        agent: "testing"
        comment: |
          Re-tested 2026-06-XX after main agent fix:
            - `_ensure_wages_category` now accepts user_id and inserts
              "created_by": user_id (server.py:2078).
            - `list_categories` self-heals legacy docs missing `created_by` by
              backfilling with the space owner's user_id (server.py:567-579).
          /app/backend_test_phase4_retest.py — 18/18 PASS:
            ✅ POST /household/payroll succeeds (returns 200, payment_id created).
            ✅ GET /api/categories?space_id=<household> returns 200 (was 500
               previously due to Category.created_by ValidationError).
            ✅ Response includes "Staff wages" category.
            ✅ "Staff wages".created_by == owner.user_id (non-null,
               matches the owner who triggered payroll).
          The categories listing is fully usable for any household space after
          payroll has run. Regression resolved.
      - working: false
        agent: "testing"
        comment: |
          ❌ CRITICAL REGRESSION surfaced while running Phase 4 tests — once
          POST /api/household/payroll runs in any space, GET /api/categories
          for that space starts returning 500 Internal Server Error.

          Root cause: `_ensure_wages_category` (server.py:2048-2063) inserts a
          new "Staff wages" category document WITHOUT a `created_by` field.
          The `Category` response model (server.py:157-166) declares
          `created_by: str` as required. When `list_categories`
          (server.py:567) does `[Category(**d) for d in accessible]`, the
          auto-created Staff wages doc fails validation:

            pydantic_core._pydantic_core.ValidationError: 1 validation error
            for Category
            created_by
              Field required [type=missing, input_value={'category_id': 'cat_…
              =datetime.timezone.utc)}, input_type=dict]

          Reproduction (curl, fresh household space):
            POST /api/household/staff (owner)
            POST /api/household/payroll (owner) → 200
            GET  /api/categories?space_id=…  → 500 Internal Server Error

          This makes the entire categories listing endpoint unusable for ANY
          household space the moment payroll is logged, which cascades to
          every UI screen that calls /categories (Inventory tabs, Add-item
          modals, Finance pickers, etc.).

          Fix (one line in _ensure_wages_category, ~line 2052):
            "created_by": "system",   # or pass user.user_id from caller

          Or, alternatively, make `Category.created_by` Optional[str] with a
          default — but stamping the system identifier is cleaner.

          Note: This bug almost certainly existed before Phase 4 (since the
          payroll auto-category code is from Phase 3) but only surfaced now
          because previous tests reused a space whose Staff wages category
          had been seeded by an earlier API path that did include
          created_by, OR because tests didn't hit /categories after payroll
          in a fresh household space. The Phase 4 review request asks for
          the household report to be tested in a fresh household with
          payroll already run, which exposes the issue.

frontend:
  - task: "Permission-based staff routing & tab filtering"
    implemented: true
    working: "NA"
    file: "/app/frontend/app/(tabs)/_layout.tsx, /app/frontend/src/AuthContext.tsx, /app/frontend/app/index.tsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: "NA"
        agent: "main"
        comment: |
          AuthContext exposes spaceRole (role+permissions) from /api/spaces/{id}/my_role.
          Index redirects staff → /staff-home. Tabs layout hides inventory/finance
          tabs unless staff has view_inventory / view_finance.
  - task: "Staff join flow from /space-setup"
    implemented: true
    working: "NA"
    file: "/app/frontend/app/space-setup.tsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: "NA"
        agent: "main"
        comment: "Added 'I'm staff' tab, enters invite code, calls joinAsStaff which hits /api/household/staff/join"
  - task: "Staff permission toggles inside owner's Staff form"
    implemented: true
    working: "NA"
    file: "/app/frontend/app/(tabs)/household.tsx"
    stuck_count: 0
    priority: "medium"
    needs_retesting: false
    status_history:
      - working: "NA"
        agent: "main"
        comment: "StaffPermissionsEditor renders groups of toggles; PATCHes /api/household/staff/{id}/permissions"
  - task: "Household monthly report screen"
    implemented: true
    working: "NA"
    file: "/app/frontend/app/household-report.tsx, /app/frontend/app/(tabs)/household.tsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: "NA"
        agent: "main"
        comment: "Simple glanceable monthly dashboard for housewives: spending hero, top categories bars, staff cards (attendance+wages+tasks), shopping summary. Linked via PieChart icon in Household hub header."
  - task: "Staff notifications (wage paid)"
    implemented: true
    working: "NA"
    file: "/app/frontend/app/staff-home.tsx"
    stuck_count: 0
    priority: "medium"
    needs_retesting: false
    status_history:
      - working: "NA"
        agent: "main"
        comment: "Heart-icon bell with unread count badge, toggles a panel of notifications with per-item and mark-all-read actions."

metadata:
  created_by: "main_agent"
  version: "1.5"
  test_sequence: 8
  run_ui: false

test_plan:
  current_focus: []
  stuck_tasks: []
  test_all: false
  test_priority: "high_first"

agent_communication:
  - agent: "main"
    message: |
      Phase 4 extensions (backend) ready for testing.
      Please verify:
        1) DEFAULT_STAFF_PERMS now includes `view_inventory` (defaults false).
           PATCH /api/household/staff/{staff_id}/permissions accepts it.
           GET /api/spaces/{space_id}/my_role returns it.
        2) Notification endpoints + auto-create on payroll.
        3) /api/reports/household?space_id=X aggregations.
      Credentials: /app/memory/test_credentials.md (test@cozii.app / test1234).

  - agent: "testing"
    message: |
      Focused Phase 4 retest (2026-06-XX) on the two regressions previously flagged.
      /app/backend_test_phase4_retest.py — 18/18 PASS.

      ✅ FIX VERIFIED #1 — StaffMember response model
         (server.py:1702-1703) now exposes `invite_code: Optional[str]` and
         `permissions: Dict[str, bool] = Field(default_factory=dict)`.
         POST /household/staff returns invite_code (6-char e.g. "533845")
         and permissions dict (9 keys incl. view_inventory:false).
         PATCH /household/staff/{id}/permissions returns the same fields with
         the merged perms (view_inventory:true preserved with other defaults).
         GET /household/staff list entries also expose both fields. Staff-join
         UX is unblocked.

      ✅ FIX VERIFIED #2 — _ensure_wages_category now accepts user_id and
         inserts "created_by": user_id (server.py:2078). list_categories
         additionally self-heals legacy docs missing created_by by backfilling
         with the space owner's user_id (server.py:567-579).
         Repro flow (fresh household space → POST staff → POST payroll →
         GET /api/categories?space_id=...) now returns 200 with the
         "Staff wages" category whose created_by == owner.user_id.
         No more 500 ValidationError.

      Both flagged tasks updated to working=true, needs_retesting=false.
      No regressions surfaced. No further backend work required for these two
      items. Per protocol, frontend testing was NOT performed.

  - agent: "testing"
    message: |
      Phase 4 backend testing complete via /app/backend_test_phase4.py
      (46/51 assertions pass). Two distinct backend bugs surfaced — both
      easy fixes; the underlying business logic in all three Phase 4 areas
      is functionally correct.

      ❌ BUG #1 (HIGH) — StaffMember response model strips `invite_code`
         and `permissions` fields.
         File: /app/backend/server.py
         Class: StaffMember (server.py:1672-1689)
         Endpoints affected (3): POST /household/staff,
            GET /household/staff, PATCH /household/staff/{id}/permissions.
         Symptom: response.invite_code is null and response.permissions is
            null, even though MongoDB has them populated correctly. Means
            owner cannot read the invite_code from create-staff to share
            with the new staff member, blocking the staff-join UX.
         Fix:
            class StaffMember(BaseModel):
                ...
                invite_code: Optional[str] = None
                permissions: Dict[str, bool] = Field(default_factory=dict)

      ❌ BUG #2 (HIGH, regression) — GET /api/categories returns 500 once
         payroll has run in a space.
         File: /app/backend/server.py
         Function: _ensure_wages_category (lines 2048-2063)
         Cause: doc inserted without `created_by`; Category model (line 165)
            requires it → ValidationError on /api/categories listing.
         Fix (one line):
            doc = {
              ...
              "created_by": "system",  # or pass user.user_id
              "created_at": now_utc(),
            }

      ✅ Staff permissions FUNCTIONALITY (verified via /spaces/{id}/my_role
         and direct mongo) — DEFAULT_STAFF_PERMS now has 9 keys including
         view_inventory:false; PATCH merges correctly; non-owner gets 403;
         after join, /spaces/{id}/my_role returns role=staff with merged
         permissions.

      ✅ Notifications — wage_paid auto-created on payroll, title format
         "Wage received · YYYY-MM", body contains staff name + cycle + net,
         data has payment_id+period+net+currency, /read flips read=true,
         /read_all bulk-marks, ?unread_only filters, outsiders cannot see
         other users' notifications. 14/14 PASS.

      ✅ Household monthly report — all keys present, currency from space,
         total_wages == sum(payroll.net), staff[] complete with
         days_present/days_off/days_sick/days_leave/tasks_done/paid/salary/
         pay_cycle/name/photo_base64/role_id, top_categories sum ≈
         total_spent, includes Staff wages auto-category, shopping counts
         match window, far-past month returns zeros with currency=IDR,
         non-member 403. 18/18 PASS.

      Once main agent applies the two fixes above (StaffMember response
      model + _ensure_wages_category created_by), the Phase 4 surface is
      production-ready. No frontend testing performed (per protocol).

## 2026-06-XX — Phase 5: Quick-send tasks, task shortcuts, preview-as-staff, task notifications

backend:
  - task: "Task shortcuts CRUD (GET/POST/DELETE /api/household/shortcuts)"
    implemented: true
    working: true
    file: "/app/backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: "NA"
        agent: "main"
        comment: |
          New `task_shortcuts` collection. GET supports optional staff_id filter
          (returns scoped to staff OR shared (staff_id=null)). POST creates one.
          DELETE removes by id. All require space membership.
      - working: true
        agent: "testing"
        comment: |
          Verified via /app/backend_test_phase5.py against the public preview URL
          (37/37 PASS). All scenarios:
            ✅ POST /api/household/shortcuts {space_id, staff_id, title, icon}
               → 200 with shortcut_id, staff_id preserved.
            ✅ POST shared shortcut (staff_id omitted) → 200, response.staff_id=null.
            ✅ GET /api/household/shortcuts?space_id=... returns all 3 created.
            ✅ GET ?space_id=...&staff_id=X returns BOTH the staff-specific
               shortcut AND the shared (staff_id=null) one, but excludes shortcuts
               for a different staff in the same space.
            ✅ DELETE /api/household/shortcuts/{id} → 200; shortcut absent on
               next GET.
            ✅ Non-member of space → 403 on GET, POST, and DELETE.
  - task: "Quick-fire one-time task (POST /api/household/tasks/quick)"
    implemented: true
    working: true
    file: "/app/backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: "NA"
        agent: "main"
        comment: |
          Creates a task_templates doc with recurrence='once', once_date=today,
          staff_id=<target>. If `save_as_shortcut: true`, also upserts into
          task_shortcuts. If staff.user_id is linked, creates a `task_assigned`
          notification for the staff user.
      - working: true
        agent: "testing"
        comment: |
          All 11 scenarios PASS (today=2026-05-02 UTC):
            ✅ POST /household/tasks/quick {space_id, staff_id, title} → 200,
               recurrence='once', once_date=today (2026-05-02), staff_id=target,
               active=true. (Created via task_templates collection.)
            ✅ Empty/whitespace title → 400 "Title required".
            ✅ Non-existent staff_id → 404 "Staff not found".
            ✅ save_as_shortcut=true → creates the task AND inserts into
               task_shortcuts; new shortcut visible via GET shortcuts
               (count=1 for that staff+title).
            ✅ Calling quick twice with same title + save_as_shortcut=true does
               NOT create a duplicate shortcut (existing-by-(space,staff,title)
               check works); count remains 1.
            ✅ When the target staff has a linked user_id (joined via
               POST /household/staff/join with invite_code), the staff user's
               GET /api/notifications?space_id=... returns a `task_assigned`
               notification with:
                 - title == "Quick task: <title>"
                 - data.task_id present
                 - data.quick == true
  - task: "Task-assigned notification on POST /api/household/tasks"
    implemented: true
    working: true
    file: "/app/backend/server.py"
    stuck_count: 0
    priority: "medium"
    needs_retesting: false
    status_history:
      - working: "NA"
        agent: "main"
        comment: |
          If create_task has staff_id set and that staff has user_id linked,
          posts a `task_assigned` notification. Title shows task title, body
          says today/once/<recurrence> and due time when present.
      - working: true
        agent: "testing"
        comment: |
          ✅ As owner: POST /household/tasks {space_id, title, staff_id=<linked>,
             recurrence='daily'} → 200.
          ✅ As staff user: GET /api/notifications?space_id=...&unread_only=true
             returns exactly one `task_assigned` notification titled
             "New task: <title>" (verified end-to-end against preview URL).
  - task: "Preview staff home (GET /api/household/staff/{staff_id}/view)"
    implemented: true
    working: true
    file: "/app/backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: "NA"
        agent: "main"
        comment: |
          Any space member (owner/admin) can fetch a given staff's home view —
          returns same shape as /household/staff/me: staff, permissions,
          today_tasks, attendance, payments (respecting view_wage_amount).
          Non-member of space → 403. Unknown staff → 404.
      - working: true
        agent: "testing"
        comment: |
          All 11 scenarios PASS:
            ✅ Owner GET /household/staff/{staff_id}/view → 200 with all required
               keys: staff, permissions, today_tasks, attendance, payments,
               preview. preview === true.
            ✅ today_tasks, attendance, payments are arrays.
            ✅ staff object has name, role_id, invite_code populated.
            ✅ When the target staff has permissions.view_wage_amount=false,
               payments=[] in the response (verified by PATCH-ing perms first).
            ✅ Non-member of the space → 403 "Not a member of this space".
            ✅ Random fake staff_id → 404 "Staff not found".

frontend:
  - task: "Quick-send per staff + shortcut chips"
    implemented: true
    working: "NA"
    file: "/app/frontend/app/(tabs)/household.tsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: "NA"
        agent: "main"
        comment: |
          StaffCard now expands into a Quick-send panel with: shortcut chips
          (tap to fire, X to delete), free-text input, Send, and Send+save
          buttons. Saves become per-staff shortcuts for next time.
  - task: "Preview staff home button (owner)"
    implemented: true
    working: "NA"
    file: "/app/frontend/app/(tabs)/household.tsx, /app/frontend/app/staff-home.tsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: "NA"
        agent: "main"
        comment: |
          Each staff card has a 'Preview home' button → /staff-home?preview=<id>.
          staff-home reads ?preview= query param, fetches /staff/{id}/view,
          shows blue 'Previewing as X · read-only' banner at the top, disables
          write actions with an alert, and replaces Log out with Exit preview.
  - task: "Clarify staff invite code label"
    implemented: true
    working: "NA"
    file: "/app/frontend/app/(tabs)/household.tsx"
    stuck_count: 0
    priority: "low"
    needs_retesting: false
    status_history:
      - working: "NA"
        agent: "main"
        comment: "Label 'Staff-only invite code' + explainer that it's different from the space invite code."

agent_communication:
  - agent: "testing"
    message: |
      Phase 5 backend testing complete (2026-05-02) via /app/backend_test_phase5.py
      against the public preview URL. **37/37 PASS — all four endpoints
      production-ready.**

      ✅ Task shortcuts CRUD (GET/POST/DELETE /api/household/shortcuts)
         - POST staff-specific + POST shared (staff_id omitted) both work.
         - GET ?space_id&staff_id includes the staff-specific entry AND the
           shared (staff_id=null) one, while excluding shortcuts for other staff.
         - DELETE removes the doc; non-member 403 on GET/POST/DELETE.
      ✅ POST /api/household/tasks/quick
         - Creates task_templates with recurrence='once', once_date=today (UTC),
           staff_id=target, active=true.
         - Empty title → 400; missing staff_id → 404.
         - save_as_shortcut=true creates shortcut and is idempotent for the
           same (space, staff, title) → no duplicates on repeat calls.
         - When the staff has user_id linked (POST /staff/join), the staff
           user's GET /api/notifications shows a `task_assigned` notif titled
           "Quick task: <title>" with data.task_id present and data.quick=true.
      ✅ task_assigned notification on POST /api/household/tasks
         - Owner POST /household/tasks {staff_id=<linked>, recurrence='daily'}
           → staff user GET /api/notifications?unread_only=true returns one
           `task_assigned` notif titled "New task: <title>".
      ✅ GET /api/household/staff/{staff_id}/view
         - Owner → 200 with keys: staff, permissions, today_tasks (array),
           attendance (array), payments (array), preview=true.
         - staff has name, role_id, invite_code populated.
         - When permissions.view_wage_amount=false → payments=[].
         - Non-member of the space → 403.
         - Random fake staff_id → 404.

      No regressions surfaced. No frontend testing performed (per protocol).

  - agent: "main"
    message: |
      Phase 5 backend ready for testing. Focus on:
      1) POST /api/household/shortcuts + GET + DELETE with staff_id filter.
         Ensure staff_id=None (shared) is included when filter is set.
      2) POST /api/household/tasks/quick:
         - Creates a task (recurrence='once', once_date=today, staff_id set).
         - If save_as_shortcut=true, shortcut is stored and will appear in GET.
         - Duplicate quick-tasks with same title + save_as_shortcut=true should
           NOT create duplicate shortcuts (the upsert check by title).
         - If the target staff has user_id linked (after /staff/join), a
           `task_assigned` notification is created for that user.
      3) POST /api/household/tasks (normal) with staff_id=<linked staff> also
         creates `task_assigned` notification for that user.
      4) GET /api/household/staff/{staff_id}/view:
         - Owner/member → 200 with same keys as /staff/me plus `preview: true`.
         - Non-space-member → 403. Unknown staff_id → 404.
         - view_wage_amount=false on that staff → payments: [].


## 2026-06-XX — Phase 6: Staff lifecycle + label/format polish

backend:
  - task: "Staff active/end_date lifecycle + report filter"
    implemented: true
    working: true
    file: "/app/backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: true
        agent: "testing"
        comment: |
          Phase 6 retest 2026-05-02 via /app/backend_test_phase6.py.
          ALL 33/33 ASSERTIONS PASS after main agent fixes.
          
          Verified fixes:
            ✅ create_staff now persists `end_date` and `active` to the
               inserted doc. POST {active:false} → response.active == false,
               Mongo doc has active=false stored.
            ✅ update_staff now accepts `end_date` and `active` in the
               update tuple. PATCH {end_date:"2026-01-31", active:false} →
               response.end_date == "2026-01-31", response.active == false.
          
          /api/reports/household current-month filter works as expected:
            ✅ Staff A (active, paid in window) → INCLUDED
            ✅ Staff B (active=false, no activity) → EXCLUDED
            ✅ Staff C (start_date=2099-01-01) → EXCLUDED
            ✅ Staff D (end_date=2020-01-31) → EXCLUDED
            ✅ report.staff has exactly {A}
          
          Historical integrity intact:
            ✅ /reports/household?year=2020&month=1 includes D
               (end_date=2020-01-31) with paid==2,000,000 IDR after a
               historical staff_payments doc was injected for 2020-01-15.
          
          Spot-checks all green: /reports/finance, /household/tasks/quick,
          legacy items/categories without updated_at.
          
          Marking task working=true, needs_retesting=false. Production-ready.
      - working: "NA"
        agent: "main"
        comment: |
          StaffMember / CreateStaffRequest / UpdateStaffRequest now expose:
            - end_date: Optional[str] (YYYY-MM-DD)
            - active: bool (default True)
          /api/reports/household staff loop now INCLUDES a staff member only if:
            (active != false) AND (start_date <= end_of_month OR has activity)
            AND (end_date is null OR end_date >= start_of_month OR has activity)
          "has activity" = had an attendance log or a payment in the window, so
          historical reports (e.g. looking at April for a former staff) still
          show them correctly. Current-month reports hide staff who haven't
          started yet or have ended before the month begins.
      - working: false
        agent: "testing"
        comment: |
          Phase 6 retest 2026-05-02 via /app/backend_test_phase6.py.
          The Pydantic models DO declare `active: bool = True` and
          `end_date: Optional[str] = None`, but neither field is actually
          persisted to MongoDB on POST/PATCH. As a result:
            - POST /api/household/staff with body {space_id,name,salary,active:false}
              returns response.active == TRUE (Pydantic default), end_date is null.
              MongoDB doc has NO `active` and NO `end_date` keys.
            - PATCH /api/household/staff/{id} with {end_date:"2026-01-31",
              active:false} returns 200 but response.end_date == null and
              response.active == TRUE. The PATCH silently drops both fields.
            - GET /api/reports/household current-month returns staff B
              (active=false), C is correctly excluded (start_date is the only
              lifecycle field that IS persisted), and D (end_date=2020-01-31)
              is INCLUDED because its end_date never made it to MongoDB.
              Expected: only A. Got: A, B, D.
            - Historical /reports/household?year=2020&month=1 correctly
              includes D with paid > 0 (works because the historical-activity
              path uses payments-in-window — independent of the lifecycle
              fields). Past-month integrity is fine.

          ROOT CAUSE 1 — `create_staff` (server.py:1960-1986) builds the
          insert doc but never adds `end_date` or `active`. Fix: include
          these keys explicitly:
            "end_date": body.end_date,
            "active": True if body.active is None else bool(body.active),

          ROOT CAUSE 2 — `update_staff` (server.py:2213-2228) loops over a
          hard-coded tuple of allowed update keys that omits `end_date` and
          `active`. Fix: add both names to the tuple at line 2220:
            for k in ("name", "role_id", ..., "start_date", "end_date",
                      "active", "notes"):

          Side effects on /reports/household filter — the filter logic itself
          (server.py:2968-2983) is correct; once the fields are persisted,
          B/C/D will all be excluded as the test expects. Verified by
          manually setting active/end_date directly in Mongo: filter passes.

          Other tests in this run pass:
            ✅ POST response.end_date == null when not specified (default).
            ✅ start_date is persisted (C correctly excluded).
            ✅ /reports/household total_spent + total_wages match.
            ✅ Historical 2020-01 report shows D with paid==2000000.

  - task: "Pre-existing Item.updated_at missing bug"
    implemented: true
    working: true
    file: "/app/backend/server.py"
    stuck_count: 0
    priority: "low"
    needs_retesting: false
    status_history:
      - working: "NA"
        agent: "main"
        comment: "Made updated_at optional on Item/Category/etc. so legacy docs without the field load via GET /api/items."
      - working: true
        agent: "testing"
        comment: |
          Verified 2026-05-02 via /app/backend_test_phase6.py.
          Repro: POST a category and an item, then $unset updated_at on
          both directly in Mongo to simulate legacy docs.
            ✅ GET /api/items?space_id=... → 200, legacy item present,
               item.updated_at == null in response (not 500).
            ✅ GET /api/categories?space_id=... → 200, no validation error.
          Item / Category Pydantic models tolerate the missing field as
          intended.

frontend:
  - task: "Staff end-date / active toggle + former badge"
    implemented: true
    working: "NA"
    file: "/app/frontend/app/(tabs)/household.tsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: "NA"
        agent: "main"
        comment: |
          Added 'End date' field + 'Currently employed / Former staff' toggle
          inside StaffForm. Staff cards now show a 'former' badge when inactive.
          Tapping the new invite-code chip on the card copies the staff-only
          code to the clipboard.
  - task: "Contextual labels: 'House rules' vs 'Roommate agreement' and 'Family invite code'"
    implemented: true
    working: "NA"
    file: "/app/frontend/app/agreement.tsx, /app/frontend/app/(tabs)/profile.tsx"
    stuck_count: 0
    priority: "low"
    needs_retesting: false
    status_history:
      - working: "NA"
        agent: "main"
        comment: |
          When space_type === 'household', the agreement screen title and the
          profile row read 'House rules'. Profile invite code is labeled
          'Family invite code' in household mode with a helper that points
          staff to the separate staff-only code.
  - task: "Home 'spent this month' now uses formatMoney"
    implemented: true
    working: "NA"
    file: "/app/frontend/app/(tabs)/home.tsx"
    stuck_count: 0
    priority: "medium"
    needs_retesting: false
    status_history:
      - working: "NA"
        agent: "main"
        comment: |
          Replaced `${(stats?.spent_this_month ?? 0).toFixed(0)}` with
          `formatMoney(value, activeSpace.currency)` so IDR shows 'Rp 2.000.000'
          and USD shows '$2,000.00'. Also added adjustsFontSizeToFit so long
          numbers don't overflow the card.

agent_communication:
  - agent: "main"
    message: |
      Phase 6 backend ready for testing. Focus areas:
      1) Create staff with active=false and hit /api/reports/household for the
         current month → that staff should NOT appear in response.staff.
      2) Create staff with start_date in the FUTURE (e.g., next month) → also
         not in report.staff for current month.
      3) Create staff with end_date in the past, then post a payroll dated in
         that past month → when requesting /reports/household for THAT past
         month (year + month params), the staff MUST appear with paid > 0 and
         metrics intact. Historical integrity.
      4) PATCH /api/household/staff/{id} accepts end_date and active and merges
         them. Returns StaffMember with the new fields populated.
      5) GET /api/categories and GET /api/items no longer 500 for legacy docs
         without updated_at (return null for the field).

  - agent: "testing"
    message: |
      Phase 6 backend retest 2026-05-02 via /app/backend_test_phase6.py.
      25/33 PASS, 8 FAIL — all 8 failures trace back to ONE bug surface
      (active + end_date are not persisted by the staff endpoints).

      ❌ BUG (HIGH) — Staff lifecycle fields are not persisted on
         POST/PATCH /api/household/staff. The Pydantic models declare
         `active: bool = True` and `end_date: Optional[str] = None`, but
         the handler code never writes these to MongoDB.

         File: /app/backend/server.py
         Repro:
           POST /household/staff {space_id, name, salary, active:false}
             → response.active == TRUE (Pydantic default), end_date null
             → Mongo doc has NO `active` and NO `end_date` keys
           PATCH /household/staff/{id} {end_date:"2026-01-31", active:false}
             → 200, response.end_date == null, response.active == TRUE
             → Mongo doc unchanged

         FIX 1 — create_staff (server.py:1960-1986). The doc dict is
            missing both keys. Add:
              "end_date": body.end_date,
              "active": True if body.active is None else bool(body.active),

         FIX 2 — update_staff (server.py:2213-2228). The allowed-update
            tuple at line 2220 omits both. Change to:
              for k in ("name", "role_id", "photo_base64", "phone",
                        "emergency_contact", "id_number", "salary",
                        "pay_cycle", "salary_currency", "off_day",
                        "start_date", "end_date", "active", "notes"):

         Knock-on effect on /api/reports/household: because B (active=false)
         and D (end_date=2020-01-31) never had those fields persisted, the
         current-month report INCLUDES B and D when it should only include
         A. The filter logic in household_report (server.py:2968-2983) is
         actually correct — once the fields land in Mongo, B/C/D are all
         excluded as expected. Verified by manually setting active/end_date
         in Mongo: filter behaves correctly. So no changes are needed in
         the report code.

      ✅ Pre-existing Item.updated_at bug — FIXED. Stripped `updated_at`
         on a Mongo item + category and confirmed GET /api/items and
         GET /api/categories both return 200 with updated_at = null.

      ✅ Historical /api/reports/household?year=2020&month=1 correctly
         shows staff D with paid == 2,000,000 after a manually-injected
         staff_payments doc dated 2020-01-15. Historical integrity holds
         (the activity-window path is independent of the active/end_date
         bug and is working).

      ✅ Spot-checks: POST /household/tasks/quick returns
         recurrence='once'; GET /reports/finance returns the full shape.
         No regressions in existing endpoints.

      ✅ Section 1 partial passes:
         - POST /household/staff w/ active=false → response 200 (just the
           returned `active` value is wrong).
         - POST response.end_date is null when not provided (default).
         - C correctly excluded from current-month report (start_date IS
           persisted, only active/end_date are dropped).

      Action for main agent:
        1. Apply the two-line fixes above to create_staff and update_staff.
        2. Optionally add /api/household/staff/me reads or migrations for
           old staff docs that don't carry `active` (default to True on
           read is already in place via _in_window).
        3. Re-run /app/backend_test_phase6.py — should hit 33/33.


  - agent: "testing"
    message: |
      Phase 6 Staff lifecycle retest 2026-05-02 via /app/backend_test_phase6.py.
      33/33 PASS. Both bugs confirmed fixed:
      
      ✅ FIX VERIFIED #1 — create_staff now persists `end_date` and `active`
         to the inserted MongoDB doc. POST /household/staff {active:false}
         returns response.active == false; Mongo has active=false.
      
      ✅ FIX VERIFIED #2 — update_staff now allows `end_date` and `active`
         in the update tuple. PATCH {end_date:"2026-01-31", active:false}
         returns 200 with both fields populated in the response.
      
      ✅ /api/reports/household current-month filter behaves as expected:
         A (active, paid in window) → INCLUDED
         B (active=false) → EXCLUDED
         C (start_date=2099-01-01 future) → EXCLUDED
         D (end_date=2020-01-31 past) → EXCLUDED
         report.staff == {A} exactly.
      
      ✅ Historical integrity preserved: /reports/household?year=2020&month=1
         still includes D with paid==2,000,000 IDR after injecting a
         staff_payments doc dated 2020-01-15.
      
      ✅ Spot-checks all green: /reports/finance shape, /household/tasks/quick
         (recurrence='once'), legacy items/categories without updated_at.
      
      Task "Staff active/end_date lifecycle + report filter" updated to
      working=true, needs_retesting=false, stuck_count=0. No further backend
      work required. No frontend testing performed (per protocol).

## 2026-06-XX — Phase 7: Shopping/Task upgrades (prices, photos, notifications, timestamps)

backend:
  - task: "Shopping requests: price + photo + notifications + purchase flow"
    implemented: true
    working: true
    file: "/app/backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: "NA"
        agent: "main"
        comment: |
          ShoppingRequest now includes estimated_price, actual_price, currency,
          photo_base64, approved_at, rejected_reason, purchased_by, purchased_at.
          POST /household/shopping accepts estimated_price and photo_base64 and
          creates a 'shopping_request' notification for the space owner + members
          (not the requester). PATCH adds approved_at on approve/reject and
          notifies the requester with a 'shopping_status' notification.
          New: POST /household/shopping/{id}/purchase {actual_price?, note?} marks
          purchased with timestamp, appends purchase note, and notifies requester.
      - working: true
        agent: "testing"
        comment: |
          Phase 7 backend testing 2026-06-XX via /app/backend_test_phase7.py
          (33/33 PASS) against the public preview URL. Setup: registered fresh
          owner (Anya Sharma) + staff (Sari Putri) + outsider; created a
          household space currency=IDR; staff joined via the staff invite_code.
          ✅ POST /household/shopping as STAFF with {item_name:"Rice",
             quantity:"5 kg", estimated_price:50000, photo_base64:<jpeg data
             URI>, requested_by_staff_id, urgency:"high"} → 200 with
             estimated_price=50000, photo_base64 preserved verbatim,
             currency="IDR" (matches space), status="pending", urgency="high".
          ✅ Owner GET /api/notifications?space_id=... returns a
             'shopping_request' notification titled exactly
             "Shopping request: Rice".
          ✅ Owner PATCH /household/shopping/{id} {status:"approved"} → 200,
             approved_at populated, approved_by==owner.user_id. Staff GET
             /notifications shows a 'shopping_status' notif titled
             "Shopping: Rice · approved".
          ✅ For a separate pending request, PATCH {status:"rejected",
             rejected_reason:"too expensive"} stores rejected_reason and the
             staff's 'shopping_status' notif body contains "too expensive".
          ✅ POST /household/shopping/{id}/purchase {actual_price:55000,
             note:"bought at supermarket"} → status="purchased",
             purchased_at populated, actual_price=55000, request.note
             appended with "[Purchase] bought at supermarket".
          ✅ Requester (staff) GET /notifications shows a 'shopping_status'
             notif titled "Purchased: Rice".
  - task: "Task completions: photo enforcement, owner comments, timestamps, staff link"
    implemented: true
    working: true
    file: "/app/backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: "NA"
        agent: "main"
        comment: |
          complete_task now 400's if task.requires_photo && no photo_base64.
          TaskCompletion doc now stores completed_by_name, staff_id (linked
          staff if completer is staff), and owner_note. Completion also
          broadcasts 'task_done' notifications to space owner and members.
          New endpoint: PATCH /household/completions/{id}/annotate {owner_note}
          lets owner add a comment — notifies the staff.
          New endpoint: GET /household/completions?space_id=&task_id=&date_from=
          lists completions for review.
      - working: true
        agent: "testing"
        comment: |
          Phase 7 task-completion enforcement verified end-to-end:
          ✅ Owner POST /household/tasks {space_id, title:"Clean kitchen",
             staff_id, recurrence:"daily", requires_photo:true} → 200,
             requires_photo=true on the returned TaskTemplate.
          ✅ As STAFF user, POST /household/tasks/{id}/complete {} → 400 with
             detail message containing "requires a photo".
          ✅ POST /household/tasks/{id}/complete {photo_base64:<jpeg>} → 200,
             completion_id returned. GET /household/completions confirms the
             stored row has staff_id linked to the joined staff and
             completed_by_name="Sari Putri".
          ✅ Owner GET /api/notifications shows a 'task_done' notification
             titled "Task done: Clean kitchen".
          ✅ Owner PATCH /household/completions/{completion_id}/annotate
             {owner_note:"Great job"} → 200; staff GET /api/notifications
             returns a 'task_comment' notification with body containing
             "Great job".
  - task: "Badge counts for household tabs"
    implemented: true
    working: true
    file: "/app/backend/server.py"
    stuck_count: 0
    priority: "medium"
    needs_retesting: false
    status_history:
      - working: "NA"
        agent: "main"
        comment: |
          New GET /household/counts?space_id returns
            { shopping_pending, shopping_approved, tasks_open_today }.
          Used as a backend truth for badge counts, but frontend also computes
          locally from already-loaded data for immediate feedback.
      - working: true
        agent: "testing"
        comment: |
          ✅ GET /api/household/counts?space_id=X returns integer values for
             shopping_pending, shopping_approved, tasks_open_today.
          ✅ After creating a fresh pending shopping request and a fresh
             non-completed daily task, the counts increment correctly
             (shopping_pending 0→1; tasks_open_today 0→1).
          ✅ Non-member GET /household/counts → 403 ("Not a member of this
             space"). Regression spot-check: quick task notification
             (POST /household/tasks/quick) still creates a 'task_assigned'
             notif titled "Quick task: Take out trash" for the linked staff
             user. 33/33 PASS overall.

frontend:
  - task: "Staff shopping form — price, photo, richer UX"
    implemented: true
    working: "NA"
    file: "/app/frontend/app/staff-home.tsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
  - task: "Staff task completion — photo proof, required enforcement, note, timestamps"
    implemented: true
    working: "NA"
    file: "/app/frontend/app/staff-home.tsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: "NA"
        agent: "main"
        comment: |
          Each task row now has an inline 📷 photo picker + note input. If
          task.requires_photo is true, tapping the checkbox without a photo
          shows an Alert 'Photo required'. After completion, the photo and
          note are rendered below the row. Owner comments (owner_note) show
          as a blue call-out.
  - task: "Owner ShoppingSection — filter sub-tabs, price/photo/timestamps"
    implemented: true
    working: "NA"
    file: "/app/frontend/app/(tabs)/household.tsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: "NA"
        agent: "main"
        comment: |
          ShoppingSection now has Pending / Approved / Purchased / Rejected /
          All filter chips with counts. Each card shows photo thumbnail,
          price (estimated vs actual), category, urgency, timestamps
          (requested, approved, purchased) and rejection reason.
          Approve → Reject flows prompt for reason (web/Android fallback);
          Purchase flow prompts for actual price and hits the dedicated
          /purchase endpoint so finance gets actual numbers.
  - task: "Household tab chip badges (Shopping pending / Tasks open today)"
    implemented: true
    working: "NA"
    file: "/app/frontend/app/(tabs)/household.tsx"
    stuck_count: 0
    priority: "medium"
    needs_retesting: false

agent_communication:
  - agent: "main"
    message: |
      Phase 7 backend ready for testing:
      1) POST /api/household/shopping with { estimated_price: 50000, photo_base64, requested_by_staff_id } as a STAFF user → owner/members should receive 'shopping_request' notification; response includes those fields.
      2) PATCH /api/household/shopping/{id} with { status: 'approved' } → approved_at set, requester receives 'shopping_status' notification.
      3) PATCH … { status: 'rejected', rejected_reason: 'too expensive' } → rejected_reason stored; notification body contains reason.
      4) POST /api/household/shopping/{id}/purchase { actual_price: 55000, note: 'bought at supermarket' } → status=purchased, purchased_at set, note appended, notification goes to requester titled 'Purchased: ...'.
      5) POST /api/household/tasks/{id}/complete on a task with requires_photo=true WITHOUT photo_base64 → 400 'This task requires a photo to mark complete'. With photo_base64 set → ok.
      6) After completion, owners should receive 'task_done' notifications. PATCH /household/completions/{id}/annotate { owner_note: 'Good job' } → stores it and notifies the completer.
      7) GET /api/household/counts?space_id=X → { shopping_pending, shopping_approved, tasks_open_today } counts.
      All existing endpoints must continue to work.

  - agent: "testing"
    message: |
      Phase 7 backend testing complete (2026-06-XX) via /app/backend_test_phase7.py
      against the public preview URL — 33/33 PASS, no failures.

      Setup: registered fresh owner (Anya Sharma) + staff (Sari Putri) + outsider
      via /api/auth/register; created household space currency=IDR; staff joined
      via the staff invite_code returned by POST /household/staff.

      ✅ 1) Shopping create with price + photo
         - POST /household/shopping as STAFF with estimated_price=50000,
           photo_base64=<jpeg data URI>, requested_by_staff_id, urgency='high'
           returns 200 with all fields preserved, currency='IDR' (from space),
           status='pending', urgency='high'.
         - Owner GET /api/notifications?space_id=… returns 'shopping_request'
           titled exactly "Shopping request: Rice".

      ✅ 2) Shopping status transitions
         - PATCH {status:'approved'} → approved_at populated,
           approved_by==owner.user_id; staff sees 'shopping_status' titled
           "Shopping: Rice · approved".
         - On a separate pending request, PATCH {status:'rejected',
           rejected_reason:'too expensive'} stores the reason; staff
           rejection notif body contains "too expensive".
         - POST /shopping/{id}/purchase {actual_price:55000,
           note:'bought at supermarket'} → status='purchased', purchased_at
           populated, actual_price stored, note appended with
           "[Purchase] bought at supermarket". Requester receives notif
           titled "Purchased: Rice".

      ✅ 3) Task completion photo enforcement
         - POST /household/tasks {requires_photo:true} → ok.
         - POST /tasks/{id}/complete {} → 400 with detail
           "This task requires a photo to mark complete".
         - POST /tasks/{id}/complete {photo_base64} → 200,
           completion has staff_id linked to staff and
           completed_by_name='Sari Putri'.
         - Owner gets 'task_done' notif "Task done: Clean kitchen".
         - PATCH /completions/{id}/annotate {owner_note:'Great job'} →
           staff gets 'task_comment' notif body contains "Great job".

      ✅ 4) Household counts
         - GET /household/counts?space_id=X returns integer
           shopping_pending, shopping_approved, tasks_open_today.
         - After creating a fresh pending request and a fresh non-completed
           daily task, both shopping_pending (0→1) and tasks_open_today
           (0→1) increment correctly.
         - Non-member GET /counts → 403 "Not a member of this space".

      ✅ 5) Quick task notification regression
         - POST /household/tasks/quick still creates a 'task_assigned'
           notification titled "Quick task: Take out trash" for the linked
           staff user.

      All three Phase 7 backend tasks updated to working=true,
      needs_retesting=false. No backend bugs surfaced. Per protocol, frontend
      testing was NOT performed.


## 2026-06-XX — Phase 8: Item images + Documents vault

backend:
  - task: "Item model new fields (image_url, receipt_base64, event_tag) + PATCH"
    implemented: true
    working: true
    file: "/app/backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: true
        agent: "testing"
        comment: |
          Verified via /app/backend_test_phase8.py — 6/6 PASS.
          - POST /api/items {space_id, category_id, name:"Dior Joy Bag",
            image_url:"https://example.com/dior_joy.jpg",
            receipt_base64:<jpeg base64>, event_tag:"Birthday June 8",
            price:4500} → 200; response keeps image_url, receipt_base64
            (non-empty), event_tag exactly.
          - PATCH /api/items/{id} {image_url:"https://example.com/dior_joy_updated.png"}
            → 200; response.image_url updated.

  - task: "/api/items/bulk (event_tag, auto_fetch_images, receipt_photo_base64→receipt_base64)"
    implemented: true
    working: true
    file: "/app/backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: true
        agent: "testing"
        comment: |
          12/12 PASS:
          - POST /items/bulk {event_tag, auto_fetch_images:true,
            receipt_photo_base64, items:[Dior Joy Bag, Coca Cola can]} → 200,
            no 500.
          - Each created item has event_tag preserved, receipt_base64 ==
            receipt_photo_base64 (NOT photo_base64), photo_base64 is null
            (so display defaults to nicer images).
          - image_url is either null or http URL — DuckDuckGo appears
            unreachable from this environment so values came back null,
            but the endpoint never 500s and the field is correctly stored.
          - auto_fetch_images:false branch verified: no DDG call, image_url
            stays null.

  - task: "POST /api/items/{id}/refresh-image"
    implemented: true
    working: true
    file: "/app/backend/server.py"
    stuck_count: 0
    priority: "medium"
    needs_retesting: false
    status_history:
      - working: true
        agent: "testing"
        comment: |
          DDG appears blocked from this environment, so the endpoint
          correctly returned 404 with detail "No image found for this query.
          Try a more specific name (e.g. brand + model)." Test passed for
          the 404 branch; the 200 branch (image_url updated, photo_base64
          cleared) is implemented in code (server.py:980) and would activate
          when DDG is reachable.

  - task: "GET /api/products/image-search"
    implemented: true
    working: true
    file: "/app/backend/server.py"
    stuck_count: 0
    priority: "medium"
    needs_retesting: false
    status_history:
      - working: true
        agent: "testing"
        comment: |
          3/3 PASS. GET /api/products/image-search?q=Dior%20Joy%20Bag → 200
          with body {query:"Dior Joy Bag", image_url:null|str}. DDG returned
          null from this environment but the response shape is exactly as
          specified.

  - task: "Documents vault (POST/GET/PATCH/DELETE /api/documents + folder filter + 8MB cap)"
    implemented: true
    working: true
    file: "/app/backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: true
        agent: "testing"
        comment: |
          21/21 PASS via /app/backend_test_phase8.py:
          - POST /api/documents {space_id, name:"Lease 2026.pdf",
            folder:"contracts", mime:"image/jpeg", file_base64:<base64>} →
            200 with size_kb >= 1 (computed from base64 payload),
            uploaded_by == current user, folder preserved.
          - GET /api/documents?space_id=X → 200 list with both docs.
          - GET /api/documents?space_id=X&folder=contracts → only docs in
            'contracts' folder.
          - PATCH /api/documents/{id} {name, note} → updates persisted.
          - DELETE /api/documents/{id} → 200; subsequent GET excludes it.
          - 8 MB cap: POST with file_base64 of ~11 MB chars (~8.25 MB raw)
            → 413 "File too large (max ~8 MB)".
          - Non-member access control: outsider account (not in
            space.member_ids) gets 403 on GET, POST, PATCH, and DELETE.

metadata:
  created_by: "main_agent"
  version: "1.8"
  test_sequence: 11
  run_ui: false

test_plan:
  current_focus: []
  stuck_tasks: []
  test_all: false
  test_priority: "high_first"

agent_communication:
  - agent: "testing"
    message: |
      Phase 8 backend testing complete (2026-06-XX) via
      /app/backend_test_phase8.py — 42/42 PASS against the public preview URL.

      ✅ 1) Item model new fields (image_url, receipt_base64, event_tag):
         POST /api/items keeps all three; PATCH /api/items/{id} with
         image_url updates correctly.

      ✅ 2) /api/items/bulk:
         - event_tag stored on every created item.
         - receipt_photo_base64 stored as receipt_base64 (NOT photo_base64) —
           verified by inspecting both fields on the bulk response items.
         - auto_fetch_images:true → endpoint does NOT 500. DuckDuckGo appears
           blocked from this environment so image_url came back null on every
           bulk item; per the review request, this is acceptable. With
           auto_fetch_images:false, no DDG call attempted.

      ✅ 3) POST /api/items/{id}/refresh-image — DDG blocked here, so the
         endpoint correctly returned 404 "No image found...". The 200 branch
         (image_url updated, photo_base64 cleared) is the correct code path
         in server.py:980 and will work when DDG is reachable.

      ✅ 4) GET /api/products/image-search?q=... → returns
         {query, image_url:null|str} with the right shape (image_url is null
         here due to the DDG block).

      ✅ 5) Documents vault — POST/GET/PATCH/DELETE all work; folder filter
         works; size_kb computed; >8MB upload → 413; non-member → 403 on
         every method.

      No backend bugs surfaced. Note: DDG-dependent assertions only verified
      the not-500 / 404 / null-shape branches because outbound HTTPS to
      duckduckgo.com appears blocked from the container. The endpoints
      themselves are implemented correctly. Per protocol, frontend testing
      was NOT performed.



## 2026-06-XX — Phase 7: Contract Templates + e-Sign

backend:
  - task: "Contract templates list (GET /api/contract-templates)"
    implemented: true
    working: true
    file: "/app/backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: "NA"
        agent: "main"
        comment: |
          Returns 4 built-in templates (NDA, Employment, Confidentiality, Blank)
          each with kind, title, icon, summary, default_variables, body containing
          {{placeholder}} tokens. Auth-required.
      - working: true
        agent: "testing"
        comment: |
          GET /api/contract-templates verified via /app/backend_test_phase7_contracts.py.
          - 200 auth response returns exactly 4 templates with kinds
            ["blank", "confidentiality", "employment", "nda"].
          - Every template has keys kind, title, icon, summary, default_variables
            (dict), body (string). NDA body contains {{household_name}},
            {{staff_name}}, {{start_date}}, {{city}} placeholders — render test
            (see below) confirmed these are replaced from contract.variables.
          - No auth → 403 (expected).

  - task: "Contracts CRUD (POST/GET/PATCH/DELETE /api/contracts)"
    implemented: true
    working: true
    file: "/app/backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: "NA"
        agent: "main"
        comment: |
          POST creates a contract for a space (owner only). Optional
          assigned_staff_id resolves staff name. Auto-creates a `contract_assigned`
          notification for the staff user if linked. GET lists; for staff users
          only contracts assigned to them. PATCH owner-only and only when no
          signatures yet. DELETE owner-only. Status starts as `pending`.
      - working: true
        agent: "testing"
        comment: |
          Verified end-to-end via /app/backend_test_phase7_contracts.py against
          the preview URL — all assertions green.
          POST /api/contracts:
            ✅ Happy path (owner, template_kind="nda", assigned_staff_id,
               require_drawn_signature_staff=true) returns Contract with
               contract_id, status="pending", assigned_staff_name="Sari Putri",
               owner_signature=null, staff_signature=null.
            ✅ Empty body → 400 "body cannot be empty".
            ✅ assigned_staff_id not in space → 404 "Staff not found".
            ✅ Non-owner member (staff user) → 403 with message mentioning
               "Only the space owner can create contracts".
            ✅ Non-member (outsider) → 403 "Not a member of this space".
            ✅ After POST with assigned_staff_id linked to a user_id via
               /staff/join, staff user's GET /api/notifications returns exactly
               one `contract_assigned` notification with data.contract_id set.
          GET /api/contracts:
            ✅ Owner sees all contracts in the space.
            ✅ Staff user sees only contracts where assigned_staff_id ==
               their staff_id (verified by reassigning a second contract to a
               different staff and confirming staff user's list does not
               include it).
            ✅ staff_id query filter correctly excludes contracts for other
               staff; status=pending filter returns only pending.
            ✅ Non-member → 403.
          GET /api/contracts/{id}:
            ✅ Owner + assigned staff both get 200.
            ✅ Another staff (linked to a different staff_id in the same space)
               → 403 "Not authorized to view this contract".
            ✅ Non-member → 403.
          PATCH /api/contracts/{id}:
            ✅ Non-owner member → 403.
            ✅ Owner PATCH assigned_staff_id with a different staff in the
               space updates assigned_staff_name correctly; revert also works.
            ✅ PATCH after any signature present → 400 "Cannot edit a contract
               once any party has signed".
          DELETE /api/contracts/{id}:
            ✅ Outsider / non-owner member → 403.
            ✅ Owner → 200 {ok:true}; subsequent GET → 404 (cleaned up).

  - task: "Contract sign flow (POST /api/contracts/{id}/sign)"
    implemented: true
    working: true
    file: "/app/backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: "NA"
        agent: "main"
        comment: |
          Records ContractSignature {role, user_id, name, typed_name,
          drawing_base64, signed_at, ip, user_agent} in either owner_signature
          or staff_signature based on caller. IP read via x-forwarded-for /
          x-real-ip / request.client.host fallback. Validates required-drawn flag
          per role, refuses empty signature. When all required signatures are
          present, status flips to `signed` and a record is auto-archived in
          /api/documents (folder=contracts). Notifies the other party while
          waiting.
      - working: true
        agent: "testing"
        comment: |
          All sign flow scenarios PASS:
            ✅ POST /sign with neither typed_name nor drawing_base64 → 400
               "Type your name or draw your signature to sign."
            ✅ Owner role detected via space.owner_id == user.user_id: owner
               sign with {typed_name:"Test User"} → 200, owner_signature
               populated with role="owner", user_id=owner, typed_name,
               signed_at present, user_agent captured.
            ✅ Owner signed (staff still pending) → status remains "pending"
               AND staff user gets a `contract_owner_signed` notification with
               data.contract_id.
            ✅ Staff user (whose staff record is the assignee) sign without
               drawing_base64 (require_drawn_signature_staff=true) → 400
               "A hand-drawn signature is required for this contract."
            ✅ Staff sign with drawing_base64="data:image/svg+xml;base64,PHN2Zy8+"
               → 200; staff_signature populated, role="staff", user_id=staff
               user id, drawing_base64 stored.
            ✅ Both required signatures present → contract.status flipped to
               "signed".
            ✅ When status hits "signed", a record is auto-archived in
               /api/documents with folder="contracts" and
               related_to == {kind:"contract", id:contract_id}. Verified via
               GET /documents?space_id=... by the owner.
            ✅ Signing a voided contract → 400 "Contract has been voided".

  - task: "Contract void + render endpoints"
    implemented: true
    working: true
    file: "/app/backend/server.py"
    stuck_count: 0
    priority: "medium"
    needs_retesting: false
    status_history:
      - working: "NA"
        agent: "main"
        comment: |
          POST /contracts/{id}/void → owner-only, sets status=void.
          GET /contracts/{id}/render → returns rendered_body with {{vars}}
          substituted from contract.variables. Both enforce membership;
          staff can only render contracts assigned to them.
      - working: true
        agent: "testing"
        comment: |
          POST /api/contracts/{id}/void:
            ✅ Non-owner (staff) → 403 "Only the owner can void contracts".
            ✅ Owner → 200, status="void"; subsequent /sign call → 400
               "Contract has been voided".
          GET /api/contracts/{id}/render:
            ✅ Returns {title, rendered_body, status, variables} (all four keys).
            ✅ rendered_body has every {{key}} placeholder replaced with the
               matching value from contract.variables. Verified with NDA
               template and variables {household_name:"Rumah Bali",
               staff_name:"Sari Putri", start_date:"2026-05-02",
               city:"Denpasar"} — none of the raw tokens remain and the values
               appear in the body.
            ✅ Staff assigned to the contract can GET /render.
            ✅ Non-member → 403.
          NOTE on placeholder syntax: the review request described tokens as
          `{placeholder}` (single braces) but the actual server templates and
          render function use `{{placeholder}}` (double braces), which is the
          established convention (_render_contract_body at server.py:3999
          replaces `{{key}}`). This is consistent and working correctly — no
          bug here; just flagging the doc discrepancy for the main agent.

frontend:
  - task: "Contracts list screen (/contracts)"
    implemented: true
    working: "NA"
    file: "/app/frontend/app/contracts.tsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: "NA"
        agent: "main"
        comment: |
          Shows agreements with status pill, owner/staff signature badges,
          staff filter chips for owners, and a + button to create new.
          Linked from Household tab header (FileText icon) and from staff-home
          header (FileText icon).

  - task: "Contract creator screen (/contract-new)"
    implemented: true
    working: "NA"
    file: "/app/frontend/app/contract-new.tsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: "NA"
        agent: "main"
        comment: |
          Two-step flow: 1) Pick template (4 cards), 2) Fill variables (with
          smart defaults from active space + selected staff), edit body, set
          per-role signature requirements (require + drawn-required toggles),
          live preview. Submits to /api/contracts then routes to /contract-view.

  - task: "Contract viewer + e-Sign (/contract-view)"
    implemented: true
    working: "NA"
    file: "/app/frontend/app/contract-view.tsx, /app/frontend/src/SignaturePad.tsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: "NA"
        agent: "main"
        comment: |
          Renders body with {{vars}} substituted server-side. SignaturePad
          built in-house with react-native-svg + PanResponder, exports SVG
          dataURL. Sign modal accepts typed_name + optional/required drawing.

agent_communication:
  - agent: "testing"
    message: |
      Phase 7 backend (Contract Templates + e-Sign) testing complete via
      /app/backend_test_phase7_contracts.py against the preview URL
      (https://family-wallet-21.preview.emergentagent.com/api).
      **59/59 assertions PASS — all four Phase 7 backend tasks are production-ready.**

      ✅ GET /api/contract-templates — 4 kinds present (blank, confidentiality,
         employment, nda), full shape (kind/title/icon/summary/default_variables/
         body) verified, auth required.
      ✅ POST /api/contracts — owner-only (non-owner member 403, non-member 403
         "Not a member"), empty body 400, bad assigned_staff_id 404, happy path
         returns status="pending" + assigned_staff_name resolved, null
         signatures, and creates a `contract_assigned` notification for the
         linked staff user.
      ✅ GET /api/contracts list — owner sees all; staff only sees own assigned
         contracts; staff_id and status filters work; non-member 403.
      ✅ GET /api/contracts/{id} — owner OK, assigned staff OK, staff who is
         not the assignee 403, non-member 403.
      ✅ PATCH /api/contracts/{id} — owner-only (non-owner 403), PATCH
         assigned_staff_id refreshes assigned_staff_name, PATCH after any
         signature → 400 "Cannot edit a contract once any party has signed".
      ✅ POST /api/contracts/{id}/sign — empty body 400, require_drawn_signature
         enforced per role (400 with message), owner role auto-detected via
         space.owner_id, staff role auto-detected via staff_members.user_id
         (assignee check enforced). Signature records include role, user_id,
         name, typed_name, drawing_base64, signed_at, ip, user_agent (capped).
         Single-side sign keeps status=pending AND notifies the other party
         (contract_owner_signed / contract_staff_signed). When both required
         signatures are present, status flips to "signed" AND a document is
         auto-archived at /api/documents with folder="contracts" and
         related_to == {kind:"contract", id:contract_id}. Signing a voided
         contract → 400.
      ✅ POST /api/contracts/{id}/void — owner-only (non-owner 403), sets
         status="void"; subsequent /sign correctly returns 400.
      ✅ DELETE /api/contracts/{id} — owner-only (outsider 403, non-owner
         member 403), owner deletes successfully.
      ✅ GET /api/contracts/{id}/render — returns {title, rendered_body,
         status, variables}; every {{key}} placeholder in the NDA body is
         replaced from contract.variables (verified none remain). Staff
         assignee can render; non-member 403.

      Doc-vs-code nit (not a bug): the review request mentions placeholder
      syntax `{key}` (single braces). The actual templates and the
      `_render_contract_body` function (server.py:3999) use `{{key}}` (double
      braces), and this is consistent and working. No code change needed —
      just flagging so you know the test suite targets `{{key}}`.

      No frontend testing performed (per protocol). All Phase 7 backend tasks
      updated in test_result.md to working:true, needs_retesting:false.

          Records and shows IP + user-agent + timestamp on each signature
          card. Owner can void/delete from header.


## 2026-06-XX — Phase 7: Retroactive contract notification on staff join

backend:
  - task: "Retroactive contract notification on staff join"
    implemented: true
    working: true
    file: "/app/backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: "NA"
        agent: "main"
        comment: |
          Updated POST /api/household/staff/join (~lines 2188-2222) to backfill
          contract_assigned notifications. After linking the staff record's
          user_id and adding the user to space.member_ids, the handler queries
          db.contracts for any non-void, unsigned contract assigned to the
          staff_id, and inserts a contract_assigned notification per pending
          contract. Idempotent: skips if a notification with same kind +
          data.contract_id already exists for the user.
      - working: true
        agent: "testing"
        comment: |
          Verified end-to-end via /app/backend_test_retro_contract.py against the
          preview URL — 21/21 assertions PASS.
          Flow:
            1. Registered owner A (owner_retro_<ts>@cozii.app), created household
               space (currency=USD).
            2. Created staff "RetroStaff" (salary=1,000,000 monthly) — captured
               staff_id and 6-char invite_code; verified user_id is null.
            3. As A, POST /api/contracts {template_kind:"confidentiality",
               assigned_staff_id, title:"Retro test NDA", body, ...} → 200,
               returned contract_id. Because staff.user_id was null, no
               notification was created at this point (verified via a 3rd
               throwaway user account: their notifications are empty).
            4. Registered staff user B (staff_retro_<ts>@cozii.app); confirmed
               B has no contract_assigned notifications BEFORE joining.
            5. POST /api/household/staff/join {invite_code} as B → 200
               {ok:true, space_id, staff_id} (matches owner-side values).
            6. GET /api/notifications?space_id=...&unread_only=true as B →
               returned exactly one contract_assigned notification with:
                 - data.contract_id == retro contract id
                 - title == "Please review & sign: Retro test NDA"
                 - read == false
            7. Idempotency: second POST /api/household/staff/join with the same
               invite_code as B → 200. GET /notifications (full list) → still
               exactly 1 contract_assigned for that contract_id (no duplicate
               created — find_one({user_id, kind, data.contract_id}) check
               works as designed).
            8. Created a SECOND contract assigned to the same now-linked staff:
               POST /api/contracts {template_kind:"nda", title:"Post-join
               contract", ...}. As B, GET /notifications returned BOTH
               contract_assigned entries (retro NDA + post-join NDA),
               confirming the existing immediate-create flow still works.
            9. Voided-contract exclusion: created a 2nd unlinked staff
               (RetroStaff2) → created a contract assigned to it →
               POST /api/contracts/{id}/void (status="void"). Registered staff
               user C and joined via the 2nd invite_code → GET /notifications
               for C contains NO entry for the voided contract.
          All scenarios match the spec. Production-ready.

agent_communication:
  - agent: "testing"
    message: |
      Retroactive contract notification on staff join — fully verified against
      the preview URL via /app/backend_test_retro_contract.py (21/21 PASS).

      ✅ Pending contract assigned BEFORE staff joins → backfilled
         contract_assigned notification on join (title contains contract title,
         data.contract_id matches, read=false).
      ✅ Idempotent: re-join with same invite_code does NOT create duplicate
         notification.
      ✅ Existing immediate notification flow on /api/contracts still creates
         the post-join notification, so B sees both retro + post-join entries.
      ✅ Voided contracts are excluded from the backfill (status:{$ne:"void"}
         filter behaves correctly): a freshly-joined user does not receive a
         contract_assigned for a contract that was voided before their join.

      No bugs found. No frontend testing performed (per protocol).

## 2026-05-06 — Phase 8: Socket.IO real-time sync

backend:
  - task: "Socket.IO server mount + auth + auto-join rooms (connect / disconnect / hello)"
    implemented: true
    working: true
    file: "/app/backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: true
        agent: "testing"
        comment: |
          Retested 2026-05-06 after main agent fixed the collection name bug at
          /app/backend/server.py:55 (now reads from `db.user_sessions`). All
          connection lifecycle + join_room scenarios PASS via
          /app/backend_test.py (python-socketio AsyncClient against
          http://localhost:8001):
            ✅ connect with valid token succeeds; `hello` event received with
               user_id == current user and spaces[] including the owned space_id.
            ✅ connect with no token → refused (ConnectionError).
            ✅ connect with bad/invalid token → refused (ConnectionError).
            ✅ connect with wrong path (/socket.io instead of /api/socket.io) →
               refused (ConnectionError).
            ✅ join_room with valid space_id → ack {ok:true, joined:<space_id>}.
            ✅ join_room with invalid/unknown space_id → ack {ok:false}.
            ✅ join_room with empty {} payload → ack {ok:false}.
            ✅ Reconnect with same valid token works (fresh AsyncClient instance).
            ✅ Reconnect with invalid token refused.
            ✅ Concurrent rooms — owner with two spaces gets hello.spaces
               including both, and receives space.event from the second space
               while the first one is also active.
          The single-line fix has fully unblocked this surface. Retest done
          against a live backend (supervisor-managed) with 3 fresh users
          (A=Alex, B=Riley-staff, C=Quinn-outsider).
      - working: false
        agent: "testing"
        comment: |
          CRITICAL BLOCKER — Socket.IO connect handler rejects EVERY valid session
          token, so no real-time feature can be exercised.

          Root cause (server.py:55, inside `_resolve_user_from_token`):
            sess = await db.sessions.find_one(
                {"session_token": token, "expires_at": {"$gt": now_utc()}}, {"_id": 0})
          The REST auth code uses `db.user_sessions` (server.py:418, 479, 499, 542,
          577). The sockets path queries `db.sessions`, which does not exist in
          `test_database` — so `sess is None`, `_resolve_user_from_token` returns
          None, and the connect handler raises `ConnectionRefusedError("Unauthorized")`
          for every token.

          Verified:
            - mongosh: only `user_sessions` exists; `sessions` does not.
            - Backend log: "socket <sid> rejected (no/invalid token)" for every
              valid-token connect attempt.
            - python-socketio AsyncClient: `socketio.exceptions.ConnectionError:
              One or more namespaces failed to connect: /` on every call.

          Fix (1 line in server.py:55):
              sess = await db.user_sessions.find_one(...)

          Impact: the entire Phase 8 real-time surface is non-functional — hello,
          join_room, all space.event / user.event emissions, cross-space isolation,
          reconnection, concurrent rooms are all blocked by this one bug. None of
          them can be positively verified until the collection name is corrected.

          Test results (/app/backend_test.py, 3 PASS / 7 FAIL):
            FAIL  connect with valid token (ConnectionError)
            PASS* connect with no token refused
            PASS* connect with bad token refused
            PASS* connect with wrong path fails
            FAIL  join_room suite (could not connect)
            FAIL  contract_events suite (could not connect)
            FAIL  contract_update suite (could not connect)
            FAIL  staff_join suite (could not connect)
            FAIL  reconnect: initial connect (could not connect)
            FAIL  concurrent_rooms suite (could not connect)

          * The 3 "PASS" cases only pass because the server is rejecting ALL
            tokens (including the bad ones we expect it to reject). Once the
            collection fix is applied, these cases still need to be re-verified
            so we know valid vs invalid tokens are actually being distinguished.

          Additional implementation detail worth double-checking after the fix:
          the `hello` event is emitted with `to=sid` immediately after
          `enter_room`. In python-socketio 5.16 the default AsyncClient buffers
          events sent before `connect()` returns on the server side. We observed
          the backend log correctly ordering: connect → enter_room → emit hello,
          so this should be fine, but it's worth a retest.

  - task: "emit_space_event + emit_user_event helpers wired into contract + staff endpoints"
    implemented: true
    working: true
    file: "/app/backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: true
        agent: "testing"
        comment: |
          Retested 2026-05-06 after the sign_contract notification-asymmetry
          fix (notify_user branches now run regardless of final status; only
          the Documents Vault archive stays gated on "fully signed"). Full
          /app/backend_test.py run against supervisor-managed backend on
          http://localhost:8001: 33/33 PASS. The previously-missing case is
          now covered:

            ✅ Owner signs first (status pending_staff):
               - A receives space.event contract.signed by=owner
               - B receives space.event contract.signed by=owner
               - B receives user.event notification contract_owner_signed
            ✅ Staff signs LAST (status flips to "signed"):
               - A receives space.event contract.signed by=staff status=signed
               - B receives space.event contract.signed by=staff
               - A receives user.event notification contract_staff_signed  ← FIXED
            ✅ Documents Vault archive still inserted on fully-signed flow
               (no regression — REST notification persistence continues to
               work and the signed-copy doc is written).

          All other Phase 8 coverage unchanged and green:
            ✅ connect + hello + join_room (valid / invalid / empty / bad token /
               wrong path)
            ✅ POST/PATCH/DELETE/void contract space.event emissions
            ✅ contract_assigned notification on POST /contracts
            ✅ staff.join event on POST /household/staff/join
            ✅ Cross-space isolation (outsider C receives no events)
            ✅ Reconnect with valid / invalid token
            ✅ Concurrent rooms (two spaces same owner)

          No further work required.
      - working: false
        agent: "testing"
        comment: |
          Retested 2026-05-06 after the connect-auth fix. 20 of 21 event
          scenarios PASS; 1 FAIL remains (owner does NOT receive the
          `contract_staff_signed` notification when the staff signs last).

          ✅ Contract CRUD emissions:
            - POST /contracts  → both A (owner) and B (assigned staff) receive
              space.event {kind:"contract", action:"created"}.
            - B also receives user.event {kind:"notification", action:"created"}
              with payload.kind=="contract_assigned" (and REST
              GET /api/notifications confirms persistence).
            - PATCH /contracts/{id} → A receives space.event contract.updated.
            - POST /contracts/{id}/void → A receives space.event contract.voided.
            - DELETE /contracts/{id}  → A receives space.event contract.deleted.
            - POST /household/staff/join → owner A receives
              space.event {kind:"staff", action:"joined"}.

          ✅ Owner signs first (contract not yet fully signed):
            - A receives space.event contract.signed {by:"owner", status:"pending_staff"}.
            - B receives space.event contract.signed {by:"owner"}.
            - B receives user.event notification contract_owner_signed.

          ✅ Staff signs last (contract becomes fully signed):
            - A receives space.event contract.signed {by:"staff", status:"signed"}.
            - B receives space.event contract.signed {by:"staff"}.

          ❌ FAIL — A does NOT receive user.event notification
             `contract_staff_signed` in this flow. Root cause in
             /app/backend/server.py sign_contract (~lines 4383-4406):
             the notification branch is guarded by
             `if update.get("status") != "signed":` — but when the staff signs
             LAST the update flips status to "signed", so the
             `notify_user(..., kind="contract_staff_signed", ...)` call never
             runs. The REST notifications collection also never records a
             `contract_staff_signed` for the owner in this case.

             Fix: move the "notify the other side" block out of the
             `if update.get("status") != "signed":` branch so the owner is
             always notified when the staff signs (and, symmetrically, the
             staff is always notified when the owner signs), regardless of
             whether the signing completes the contract. Equivalent to:

               # always notify the other side on any sign event
               if role == "owner" and d.get("assigned_staff_id"):
                   ...notify staff with kind="contract_owner_signed"
               if role == "staff":
                   ...notify owner with kind="contract_staff_signed"

             (The only thing that must remain inside the "fully signed"
             branch is the Documents Vault archive insert.)

          ✅ Cross-space isolation: outsider C (member of a different space)
             received no space.event and no user.event from any of A/B's
             contract activity.

          ✅ Persistence: REST GET /api/notifications?space_id=... on B
             includes the `contract_assigned` record after the contract is
             created. (The `contract_staff_signed` record would be persisted
             too once the fix above is applied.)

      - working: "NA"
        agent: "testing"
        comment: |
          Cannot be tested until the connect auth bug above is fixed, because
          every broadcast depends on clients being in the relevant room, and
          no client can connect. The code wiring itself looks correct:
            - create_contract → emit_space_event(..., "contract", "created", ...)
            - update_contract → emit_space_event(..., "contract", "updated", ...)
            - sign_contract   → emit_space_event(..., "contract", "signed", {by,status})
            - void_contract   → emit_space_event(..., "contract", "voided", ...)
            - delete_contract → emit_space_event(..., "contract", "deleted", ...)
            - staff_join      → emit_space_event(..., "staff", "joined", {staff_id,user_id})
            - notify_user     → emit_user_event(..., "notification", "created", ...)
          Will retest once `_resolve_user_from_token` is pointed at the correct
          collection.

metadata:
  created_by: "main_agent"
  version: "1.9"
  test_sequence: 14
  run_ui: false

test_plan:
  current_focus: []
  stuck_tasks: []
  test_all: false
  test_priority: "high_first"

agent_communication:
  - agent: "testing"
    message: |
      Phase 8 Socket.IO final retest (2026-05-06) after the notification-
      asymmetry fix in /app/backend/server.py sign_contract. Full
      /app/backend_test.py run against supervisor-managed backend at
      http://localhost:8001: 33/33 PASS.

      Specifically verified:
        ✅ Owner signs first → staff receives `contract_owner_signed`
           notification (was already working).
        ✅ Staff signs LAST (status flips to "signed") → OWNER now receives
           `contract_staff_signed` user.event notification. This was the
           missing case and is now fixed.
        ✅ Documents Vault archive still inserted on fully-signed flow
           (no regression).
        ✅ All other Phase 8 coverage unchanged: connect/auth, hello,
           join_room, contract CRUD space.event emissions, contract_assigned
           notification, staff.joined, cross-space isolation, reconnect,
           concurrent rooms — all green.

      Marked 'emit_space_event + emit_user_event helpers wired into contract
      + staff endpoints' task as working=true, needs_retesting=false,
      stuck_count=0. No further backend work required for Phase 8.

  - agent: "testing"
    message: |
      Phase 8 retest (2026-05-06) after the 1-line fix at server.py:55
      (`db.sessions` → `db.user_sessions`). Result via /app/backend_test.py
      (python-socketio AsyncClient, supervisor-managed backend on
      http://localhost:8001): 32 PASS / 1 FAIL.

      Test script note: the test payload field was renamed from `body_md`
      to `body` (the actual field name on CreateContractRequest). This is
      a test-file-only correction and does not affect the backend.

      ✅ Socket.IO connect/auth + hello + join_room + cross-space isolation
         + reconnect + concurrent rooms — all PASS.
      ✅ Contract create/update/void/delete and staff.join — all emit the
         expected space.event to the right rooms; outsider does NOT receive.
      ✅ contract_assigned user.event to assigned staff on POST /contracts,
         and corresponding REST GET /api/notifications shows the record.
      ✅ contract_owner_signed user.event to staff when owner signs first.

      ❌ ONE BUG — owner does NOT receive `contract_staff_signed` user.event
         when the staff is the LAST signer (i.e. both required sigs become
         present). File: /app/backend/server.py, function sign_contract,
         lines ~4383-4406. The notify block is gated by
         `if update.get("status") != "signed":`, so when staff signs last
         and the status flips to "signed", the
         `notify_user(kind="contract_staff_signed", ...)` call never
         fires. Same asymmetry affects the owner→staff direction if the
         contract only requires the owner's sig.
         Fix: move the "notify the other party" branches OUT of the
         `status != "signed"` guard; keep only the Documents Vault archive
         insert inside the "fully signed" branch.

      Marked the 'Socket.IO server mount + auth + auto-join rooms' task
      as working=true (all connect/lifecycle/join_room cases green).
      Kept the 'emit_space_event + emit_user_event helpers' task as
      working=false / needs_retesting=true with the single signing-
      notification gap documented above. No other Phase 8 regressions
      surfaced.

  - agent: "testing"
    message: |
      Phase 8 (Socket.IO real-time sync) backend testing attempted via
      /app/backend_test.py (python-socketio AsyncClient). Result: 3 PASS / 7
      FAIL, blocked by ONE single-line bug in the connect handler.

      ❌ CRITICAL — /app/backend/server.py line 55:
          sess = await db.sessions.find_one(...)
         should be:
          sess = await db.user_sessions.find_one(...)
         Every other auth path in the file uses `db.user_sessions`
         (lines 418, 479, 499, 542, 577). With this typo, the socket.io
         connect handler rejects all valid tokens as "Unauthorized".

         Verified: only `user_sessions` collection exists in
         `test_database`. Backend log: "socket <sid> rejected (no/invalid
         token)" for valid-token connects. python-socketio AsyncClient:
         `ConnectionError: One or more namespaces failed to connect: /`.

      ✅ What the negative paths show (accidental PASS):
         - connect with no token → refused (expected)
         - connect with bad token → refused (expected)
         - connect with wrong path (/socket.io instead of /api/socket.io)
           → refused (expected)
         These 3 pass trivially because the server is rejecting *all*
         tokens. They must be re-verified once the fix is applied so we
         can distinguish "rejected because invalid" from "rejected because
         code queries the wrong collection".

      📝 Cannot be verified yet (all blocked on the same bug):
         - hello event payload {user_id, spaces:[...]}
         - join_room valid / invalid / empty payload acks
         - space.event emissions on contract created/updated/signed/voided/deleted
         - user.event emissions on notify_user (contract_assigned,
           contract_owner_signed, contract_staff_signed)
         - cross-space isolation (outsider C must not receive A/B events)
         - reconnection with same vs invalid token
         - concurrent rooms (user with two spaces)
         - staff.joined emission on /household/staff/join

      Main agent: please apply the 1-line fix above and request a retest;
      the full test suite at /app/backend_test.py will validate everything
      end-to-end without additional code changes.


## 2026-05-06 — Phase 9: Per-category staff edit + global socket emit

backend:
  - task: "Per-category staff_can_edit field on Category + staff edit_inventory perm gating (assert_can_edit_category_items)"
    implemented: true
    working: false
    file: "/app/backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
      - working: false
        agent: "testing"
        comment: |
          Phase 9 backend testing 2026-05-06 via /app/backend_test_phase9.py against
          the public preview URL — 64/65 PASS, 1 FAIL.

          ✅ A) Category CRUD + staff_can_edit field — all green:
             - Owner POST /api/categories with staff_can_edit:true → response.staff_can_edit==true.
             - Owner POST without staff_can_edit → defaults to false.
             - Owner PATCH staff_can_edit:true then :false → both 200, GET reflects updated value.
             - Non-owner space member POST /api/categories → 403, detail mentions "owner".
             - Non-owner space member PATCH /api/categories/{id} → 403.
             - Non-owner space member DELETE /api/categories/{id} → 403.

          ✅ B) Item CRUD permission gating for STAFF — all green:
             - Setup: owner created household IDR space, two categories
               (catA staff_can_edit=true, catB staff_can_edit=false), staff user
               joined via invite_code, owner PATCHed perms to edit_inventory:true.
             - With edit_inventory=true:
                 POST /api/items into catA → 200 ✅
                 POST /api/items into catB → 403 (detail: "Staff cannot edit
                   items in this category. Ask the owner to enable it.") ✅
                 PATCH /api/items/{id} on item in catA → 200 ✅
                 PATCH /api/items/{id} on owner-created item in catB → 403 ✅
                 DELETE /api/items/{id} on item in catA → 200 ✅
                 DELETE /api/items/{id} on item in catB → 403 ✅
                 POST /api/items/bulk into catA → 200 ✅
                 POST /api/items/bulk into catB → 403 ✅
             - After PATCHing staff perms to edit_inventory:false:
                 POST/PATCH/DELETE on items in catA all → 403, detail mentions
                 "permission" or "inventory" ✅
             - Owner: POST/PATCH/DELETE in either category → always 200 ✅

          ❌ C) CRITICAL — non-staff non-owner space members are now BLOCKED
             from creating items in categories where staff_can_edit=False.
             The review request explicitly states this should remain 200
             (no regression for regular family members).

             Repro: registered member M (not staff), joined space via the space
             invite_code. POST /api/items {space_id, category_id=cat_B (staff_can_edit
             false), name:"Member item in B"} → 403 with detail
             "Staff cannot edit items in this category. Ask the owner to enable it."
             Expected: 200.

             ROOT CAUSE — assert_can_edit_category_items
             (/app/backend/server.py:475-491) checks the category's
             staff_can_edit flag BEFORE looking up the staff record:

                 if await is_space_owner(...): return
                 cat = await db.categories.find_one(...)
                 if not cat.get("staff_can_edit"):
                     raise HTTPException(403, "Staff cannot edit items in this category. ...")
                 staff = await get_staff_record(...)
                 if not staff:
                     return   # <-- never reached when staff_can_edit is False

             A regular space member who is NOT the owner and NOT a staff member
             therefore hits the 403 at line 484 before the "Not staff and not
             owner — regular space members are allowed" short-circuit at line 487.
             This contradicts the documented intent in the helper itself
             ("regular space members are allowed (existing behaviour)") and the
             Phase 9 review request.

             FIX (reorder the checks so the gate only applies to staff): look
             up the staff record first; only enforce the staff_can_edit gate
             when the caller IS a staff member. Suggested rewrite:

                 if await is_space_owner(space_id, user_id):
                     return
                 staff = await get_staff_record(space_id, user_id)
                 if not staff:
                     # Regular space member (not owner, not staff) —
                     # existing behaviour was no gating; preserve that.
                     return
                 cat = await db.categories.find_one(
                     {"category_id": category_id, "space_id": space_id},
                     {"_id": 0},
                 )
                 if not cat:
                     raise HTTPException(404, "Category not found")
                 if not cat.get("staff_can_edit"):
                     raise HTTPException(403, "Staff cannot edit items in this category. Ask the owner to enable it.")
                 perms = {**DEFAULT_STAFF_PERMS, **(staff.get("permissions") or {})}
                 if not perms.get("edit_inventory"):
                     raise HTTPException(403, "You don't have permission to edit inventory.")

             All other Phase 9 surface (A + B + D + E) is correct; this is the
             only behavioural deviation from the spec.

  - task: "Socket.IO emit hook in record_activity (global space.event broadcast on every entity action) — non-regression"
    implemented: true
    working: true
    file: "/app/backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: true
        agent: "testing"
        comment: |
          ✅ All endpoints that call record_activity still respond with their
             expected codes — no 500 from emit failure. Verified
             POST /api/items, PATCH /api/items/{id}, DELETE /api/items/{id},
             POST /api/categories, PATCH /api/categories/{id},
             DELETE /api/categories/{id}, POST /api/household/tasks,
             PATCH /api/household/tasks/{id}, POST /api/household/shopping,
             POST /api/household/attendance, POST /api/household/payroll
             all return 200 (Phase 9 D suite, 11/11 PASS).
          ✅ The emit is wrapped in try/except and any failure is silenced
             (log.warning), confirmed by reading server.py:451-454.
          ✅ Phase 7/8 contract regression smoke (E suite, 7/7 PASS): owner
             creates contract, owner signs (status pending), staff signs
             (status flips to "signed"), owner receives `contract_staff_signed`
             notification, document is auto-archived in /api/documents
             (folder=contracts) with related_to.kind=="contract" and
             related_to.id == contract_id.

metadata:
  created_by: "main_agent"
  version: "2.0"
  test_sequence: 15
  run_ui: false

test_plan:
  current_focus:
    - "Per-category staff_can_edit field on Category + staff edit_inventory perm gating (assert_can_edit_category_items)"
  stuck_tasks: []
  test_all: false
  test_priority: "high_first"

agent_communication:
  - agent: "testing"
    message: |
      Phase 9 backend testing complete (2026-05-06) via /app/backend_test_phase9.py
      against the public preview URL — 64/65 PASS, 1 FAIL.

      ✅ Category CRUD with new staff_can_edit field works exactly per spec:
         - POST/GET/PATCH all expose the field; defaults to false; booleans
           round-trip correctly.
         - Only the household owner can create / edit / delete categories.
           Regular members get 403 with a message mentioning "owner".

      ✅ Staff item-edit permission gating works per spec when the caller IS
         a staff member:
         - With permissions.edit_inventory=true AND category.staff_can_edit=true
           → POST/PATCH/DELETE/bulk on items in that category all 200.
         - With staff_can_edit=false → 403 "Staff cannot edit items in this
           category. Ask the owner to enable it."
         - With edit_inventory=false → 403 "You don't have permission to edit
           inventory." regardless of category staff_can_edit.
         - Owner is always allowed.

      ✅ Socket emit non-regression: every endpoint that calls record_activity
         (POST/PATCH/DELETE /items, /categories, /household/tasks,
         /household/shopping, /household/attendance, /household/payroll)
         still returns 200. The emit is wrapped in try/except so any websocket
         failure is silenced. No 500s.

      ✅ Phase 7/8 contract flow regression smoke is green: create contract,
         owner signs (status stays pending_staff), staff signs (status flips
         to "signed"), owner receives contract_staff_signed notification,
         document auto-archived in the documents vault with related_to.kind
         == "contract".

      ❌ ONE BUG (HIGH) — Regular non-staff non-owner space members are now
         BLOCKED from creating items in categories where staff_can_edit=False.
         The review explicitly stated this case should remain 200 (no
         regression for ordinary family members), and the helper docstring
         agrees ("regular space members are allowed (existing behaviour)"),
         but the implementation order is wrong.

         File: /app/backend/server.py
         Function: assert_can_edit_category_items (lines 475-491)
         Repro: register a fresh user M (not staff), join the space via the
         space invite_code, then POST /api/items into a category with
         staff_can_edit=False → 403 with detail "Staff cannot edit items in
         this category. Ask the owner to enable it." Expected: 200.

         The category staff_can_edit gate is evaluated BEFORE the staff
         record lookup, so non-staff non-owner members never reach the
         "regular space members are allowed" short-circuit at line 487.

         Suggested fix (reorder the checks — see task status_history for the
         full snippet): owner short-circuit, then look up the staff record
         FIRST, return for non-staff non-owner, then enforce
         category.staff_can_edit and perms.edit_inventory only for staff.

      No frontend testing performed (per protocol). The fix is one ~10-line
      reorder; once applied, please retest by re-running
      /app/backend_test_phase9.py — should hit 65/65.
