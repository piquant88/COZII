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
