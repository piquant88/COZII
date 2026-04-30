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
    working: false
    file: "/app/backend/server.py"
    stuck_count: 1
    priority: "high"
    needs_retesting: true
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

metadata:
  created_by: "main_agent"
  version: "3.0"
  test_sequence: 3
  run_ui: false

test_plan:
  current_focus:
    - "Recurring bills CRUD"
  stuck_tasks: []
  test_all: false
  test_priority: "high_first"

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
