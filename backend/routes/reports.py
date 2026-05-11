"""Auto-generated route module — split from server.py."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any, Tuple
from fastapi import HTTPException, Depends, Request, Response
from pydantic import BaseModel, Field
import asyncio
import json
import re
import os
import logging
import secrets
import string
import uuid
import httpx

from core import (
    app, api_router, db, sio, logger, client,
    now_utc, ensure_aware, hash_password, verify_password,
    gen_id, gen_invite_code, gen_session_token,
    get_current_user, record_activity, assert_space_member,
    is_space_owner, get_staff_record, assert_can_edit_category_items,
    emit_space_event, emit_user_event, notify_user, send_expo_push,
)
# Pydantic models are re-exported through `models` for convenience.
from models import *  # noqa: F401,F403
import models as _m  # noqa: F401  (typed access if needed)



@api_router.get("/reports/finance")
async def finance_report(space_id: str, period: str = "this_month", user: User = Depends(get_current_user)):
    space = await assert_space_member(space_id, user.user_id)
    currency = space.get("currency", "USD")
    start, end, label = _period_range(period)

    # Items with prices in window
    items = await db.items.find({
        "space_id": space_id,
        "created_at": {"$gte": start, "$lt": end} if period != "all" else {"$lte": end},
        "price": {"$ne": None, "$gt": 0},
    }, {"_id": 0}).to_list(20000)

    cats = await db.categories.find({"space_id": space_id}, {"_id": 0}).to_list(500)
    cat_name = {c["category_id"]: c["name"] for c in cats}
    cat_tint = {c["category_id"]: c.get("tint", "mint") for c in cats}

    members = await db.users.find({"user_id": {"$in": space["member_ids"]}}, {"_id": 0, "password_hash": 0}).to_list(100)
    member_name = {m["user_id"]: m["name"] for m in members}

    total = sum(float(it["price"]) for it in items)
    count = len(items)
    avg_per_item = (total / count) if count else 0
    largest = max((float(it["price"]) for it in items), default=0)
    smallest = min((float(it["price"]) for it in items), default=0)

    # By category
    by_cat: Dict[str, Dict[str, Any]] = {}
    for it in items:
        cid = it["category_id"]
        d = by_cat.setdefault(cid, {"category_id": cid, "name": cat_name.get(cid, "?"), "tint": cat_tint.get(cid, "mint"), "total": 0.0, "count": 0})
        d["total"] += float(it["price"]); d["count"] += 1
    by_cat_list = sorted(by_cat.values(), key=lambda d: d["total"], reverse=True)
    for d in by_cat_list:
        d["pct"] = round((d["total"] / total) * 100, 1) if total else 0
        d["total"] = round(d["total"], 2)

    # By member (who paid)
    by_mem: Dict[str, Dict[str, Any]] = {}
    for it in items:
        mid = it.get("created_by")
        d = by_mem.setdefault(mid, {"user_id": mid, "name": member_name.get(mid, "Someone"), "total": 0.0, "count": 0})
        d["total"] += float(it["price"]); d["count"] += 1
    by_mem_list = sorted(by_mem.values(), key=lambda d: d["total"], reverse=True)
    for d in by_mem_list:
        d["pct"] = round((d["total"] / total) * 100, 1) if total else 0
        d["total"] = round(d["total"], 2)

    # Daily trend (date -> total) only for periods <= 6 months
    daily: Dict[str, float] = {}
    for it in items:
        d = it.get("created_at")
        if isinstance(d, datetime):
            key = d.date().isoformat()
        else:
            try: key = datetime.fromisoformat(str(d)).date().isoformat()
            except Exception: continue
        daily[key] = daily.get(key, 0) + float(it["price"])
    daily_list = [{"date": k, "total": round(v, 2)} for k, v in sorted(daily.items())]

    # Monthly trend (last 12 months relative to end)
    monthly: Dict[str, float] = {}
    for it in items:
        d = it.get("created_at")
        if not isinstance(d, datetime): continue
        key = d.strftime("%Y-%m")
        monthly[key] = monthly.get(key, 0) + float(it["price"])
    monthly_list = [{"month": k, "total": round(v, 2)} for k, v in sorted(monthly.items())]

    # Top items
    items_sorted = sorted(items, key=lambda it: float(it["price"]), reverse=True)
    top_items = [{
        "item_id": it["item_id"],
        "name": it["name"],
        "category_name": cat_name.get(it["category_id"], "?"),
        "price": round(float(it["price"]), 2),
        "purchased_by": member_name.get(it.get("created_by"), "Someone"),
        "created_at": it["created_at"].isoformat() if isinstance(it["created_at"], datetime) else str(it["created_at"]),
    } for it in items_sorted[:20]]

    # All items (raw data for sheets export)
    all_items_raw = [{
        "item_id": it["item_id"],
        "name": it["name"],
        "category_name": cat_name.get(it["category_id"], "?"),
        "price": round(float(it["price"]), 2),
        "quantity": it.get("quantity") or 1,
        "purchased_by": member_name.get(it.get("created_by"), "Someone"),
        "purchase_date": it.get("purchase_date") or "",
        "expiry_date": it.get("expiry_date") or "",
        "status": it.get("status", "available"),
        "created_at": it["created_at"].isoformat() if isinstance(it["created_at"], datetime) else str(it["created_at"]),
    } for it in items_sorted]

    # Bills in window (all visible)
    bill_docs = await db.bills.find({"space_id": space_id}, {"_id": 0}).to_list(500)
    bills_out = []
    for b in bill_docs:
        b = _compute_bill_state(b)
        bills_out.append({
            "bill_id": b["bill_id"],
            "name": b["name"],
            "amount": round(float(b["amount"]), 2),
            "frequency": b["frequency"],
            "due_day": b["due_day"],
            "is_paid_current_period": b["is_paid_current_period"],
            "next_due_date": b.get("next_due_date"),
            "last_paid_date": b.get("last_paid_date"),
            "category_name": cat_name.get(b.get("category_id"), "") if b.get("category_id") else "",
        })

    # Settlements in window
    settle_docs = await db.settlements.find({
        "space_id": space_id,
        "created_at": {"$gte": start, "$lt": end} if period != "all" else {"$lte": end},
    }, {"_id": 0}).sort("created_at", -1).to_list(500)
    settle_out = [{
        "settlement_id": s["settlement_id"],
        "from_name": s["from_name"],
        "to_name": s["to_name"],
        "amount": round(float(s["amount"]), 2),
        "note": s.get("note") or "",
        "created_at": s["created_at"].isoformat() if isinstance(s["created_at"], datetime) else str(s["created_at"]),
    } for s in settle_docs]

    # Insights (plain English)
    insights: List[str] = []
    if count == 0:
        insights.append("No spending logged in this period yet. Start scanning receipts or adding items with prices to unlock insights.")
    else:
        insights.append(f"You logged {count} purchases totalling {total:.2f} {currency}.")
        if by_cat_list:
            top = by_cat_list[0]
            insights.append(f"{top['name']} was your top category at {top['pct']}% of spend.")
        if by_mem_list and len(by_mem_list) > 1:
            top_m = by_mem_list[0]
            insights.append(f"{top_m['name']} paid the most ({top_m['pct']}%). Use the Splits view to see what's owed.")
        if avg_per_item > 0:
            insights.append(f"Average item price was {avg_per_item:.2f} {currency}.")
        # Compare to previous equivalent period
        if period in ("this_month",):
            prev_start = (start.replace(year=start.year - 1, month=12, day=1)
                          if start.month == 1 else start.replace(month=start.month - 1))
            prev_total = 0.0
            async for r in db.items.aggregate([
                {"$match": {"space_id": space_id, "created_at": {"$gte": prev_start, "$lt": start}, "price": {"$ne": None, "$gt": 0}}},
                {"$group": {"_id": None, "total": {"$sum": "$price"}}},
            ]):
                prev_total = float(r.get("total") or 0)
            if prev_total > 0:
                delta = total - prev_total
                pct = (delta / prev_total) * 100
                if abs(pct) >= 5:
                    direction = "up" if delta > 0 else "down"
                    insights.append(f"Spending is {direction} {abs(pct):.0f}% vs last month ({prev_total:.2f} {currency}).")

    return {
        "period_key": period,
        "period_label": label,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "currency": currency,
        "totals": {
            "total": round(total, 2),
            "count": count,
            "avg_per_item": round(avg_per_item, 2),
            "largest": round(largest, 2),
            "smallest": round(smallest, 2),
        },
        "by_category": by_cat_list,
        "by_member": by_mem_list,
        "daily": daily_list,
        "monthly": monthly_list,
        "top_items": top_items,
        "all_items": all_items_raw,
        "bills": bills_out,
        "settlements": settle_out,
        "insights": insights,
    }


@api_router.get("/reports/household/export")
async def export_household_report(space_id: str, year: Optional[int] = None, month: Optional[int] = None, format: str = "csv", user: User = Depends(get_current_user)):
    space = await assert_space_member(space_id, user.user_id)
    fmt = (format or "csv").lower()
    if fmt not in ("csv", "pdf"):
        raise HTTPException(400, "format must be 'csv' or 'pdf'")
    now = now_utc()
    y = year or now.year
    m = month or now.month
    start = datetime(y, m, 1, tzinfo=timezone.utc)
    end = datetime(y + 1, 1, 1, tzinfo=timezone.utc) if m == 12 else datetime(y, m + 1, 1, tzinfo=timezone.utc)
    start_str = start.strftime("%Y-%m-%d")
    end_str = end.strftime("%Y-%m-%d")
    currency = space.get("currency") or "USD"
    space_name = space.get("name") or "Household"
    period_label = start.strftime("%B %Y")

    # Pull raw rows
    items = await db.items.find({"space_id": space_id, "created_at": {"$gte": start, "$lt": end}}, {"_id": 0}).sort("created_at", 1).to_list(5000)
    payments = await db.staff_payments.find({"space_id": space_id, "paid_at": {"$gte": start, "$lt": end}}, {"_id": 0}).sort("paid_at", 1).to_list(2000)
    shopping = await db.shopping_requests.find({"space_id": space_id, "created_at": {"$gte": start, "$lt": end}}, {"_id": 0}).sort("created_at", 1).to_list(5000)
    attendance = await db.attendance_logs.find({"space_id": space_id, "date": {"$gte": start_str, "$lt": end_str}}, {"_id": 0}).sort("date", 1).to_list(10000)
    cat_map = {c["category_id"]: c.get("name") or "?" for c in await db.categories.find({"space_id": space_id}, {"_id": 0}).to_list(500)}
    staff_map = {s["staff_id"]: s.get("name") or "?" for s in await db.staff_members.find({"space_id": space_id}, {"_id": 0}).to_list(500)}

    if fmt == "csv":
        buf = io.StringIO()
        w = _csv.writer(buf)
        w.writerow([f"# {space_name} — Household report — {period_label}"])
        w.writerow([f"# Currency: {currency}", f"Generated: {now.strftime('%Y-%m-%d %H:%M UTC')}"])
        w.writerow([])
        # Spending
        w.writerow(["[ TRANSACTIONS / EXPENSES ]"])
        w.writerow(["Date", "Category", "Item", "Quantity", "Unit", "Price", "Event tag", "Added by", "Notes"])
        for it in items:
            w.writerow([
                (it.get("purchase_date") or it.get("created_at").strftime("%Y-%m-%d") if it.get("created_at") else ""),
                cat_map.get(it.get("category_id"), ""),
                it.get("name") or "",
                it.get("quantity") or "",
                it.get("unit") or "",
                it.get("price") or "",
                it.get("event_tag") or "",
                it.get("created_by_name") or "",
                (it.get("notes") or "").replace("\n", " "),
            ])
        w.writerow([])
        # Wages
        w.writerow(["[ STAFF WAGES PAID ]"])
        w.writerow(["Paid at", "Staff", "Period", "Gross", "Bonus", "Advances", "Deductions", "Net", "Currency", "Confirmed at", "Notes"])
        for p in payments:
            paid_at = p.get("paid_at"); paid_at_s = paid_at.strftime("%Y-%m-%d %H:%M") if paid_at else ""
            conf = p.get("confirmed_at"); conf_s = conf.strftime("%Y-%m-%d %H:%M") if conf else ""
            w.writerow([
                paid_at_s, p.get("staff_name") or staff_map.get(p["staff_id"], ""), p.get("period") or "",
                p.get("gross") or 0, p.get("bonus") or 0, p.get("advances") or 0,
                p.get("deductions") or 0, p.get("net") or 0, p.get("currency") or currency,
                conf_s, (p.get("notes") or "").replace("\n", " "),
            ])
        w.writerow([])
        # Shopping
        w.writerow(["[ SHOPPING & REIMBURSEMENT REQUESTS ]"])
        w.writerow(["Created", "Type", "Status", "Item", "Qty", "Requested by", "Estimated", "Actual paid", "Note"])
        for s in shopping:
            created = s.get("created_at"); created_s = created.strftime("%Y-%m-%d") if created else ""
            req_name = s.get("requested_by_name") or staff_map.get(s.get("requested_by_staff_id"), "")
            w.writerow([
                created_s, s.get("kind", "request"), s.get("status", ""), s.get("item_name", ""),
                s.get("quantity") or "", req_name, s.get("estimated_price") or "", s.get("actual_price") or "",
                (s.get("note") or "").replace("\n", " "),
            ])
        w.writerow([])
        # Attendance
        w.writerow(["[ ATTENDANCE LOGS ]"])
        w.writerow(["Date", "Staff", "Status", "Notes"])
        for a in attendance:
            w.writerow([
                a.get("date", ""), staff_map.get(a.get("staff_id"), ""), a.get("status", ""),
                (a.get("notes") or "").replace("\n", " "),
            ])
        buf.seek(0)
        filename = f"household-report-{y}-{m:02d}.csv"
        return Response(content=buf.getvalue(), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{filename}"'})

    # PDF — use reportlab
    try:
        from reportlab.lib.pagesizes import LETTER
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib import colors as rl_colors
    except ImportError:
        raise HTTPException(500, "reportlab not installed; please use format=csv")

    pdf_buf = io.BytesIO()
    doc = SimpleDocTemplate(pdf_buf, pagesize=LETTER, leftMargin=36, rightMargin=36, topMargin=36, bottomMargin=36)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("Title", parent=styles["Heading1"], fontSize=20, spaceAfter=8)
    h2 = ParagraphStyle("H2", parent=styles["Heading2"], fontSize=13, spaceBefore=14, spaceAfter=6, textColor=rl_colors.HexColor("#3D6F2A"))
    body = styles["Normal"]
    elems = []
    elems.append(Paragraph(f"<b>{space_name}</b> — Monthly report", title_style))
    elems.append(Paragraph(f"<font color='#888'>Period: {period_label} · Currency: {currency} · Generated {now.strftime('%Y-%m-%d %H:%M UTC')}</font>", body))
    elems.append(Spacer(1, 8))

    # Summary
    total_spent = sum((it.get("price") or 0) for it in items)
    total_wages = sum((p.get("net") or 0) for p in payments)
    elems.append(Paragraph("<b>Summary</b>", h2))
    sumtbl = Table([
        ["Total expenses (incl. wages)", f"{currency} {total_spent:,.2f}"],
        ["Staff wages paid", f"{currency} {total_wages:,.2f}"],
        ["Other household spend", f"{currency} {max(total_spent - total_wages, 0):,.2f}"],
        ["Number of transactions", str(len(items))],
        ["Shopping / reimbursement requests", str(len(shopping))],
    ], colWidths=[260, 260])
    sumtbl.setStyle(TableStyle([("FONTNAME", (0, 0), (-1, -1), "Helvetica"), ("FONTSIZE", (0, 0), (-1, -1), 10), ("BOTTOMPADDING", (0, 0), (-1, -1), 6), ("BACKGROUND", (0, 0), (0, -1), rl_colors.HexColor("#F5F5F0"))]))
    elems.append(sumtbl)

    # Wages
    if payments:
        elems.append(Paragraph("<b>Staff wages paid</b>", h2))
        rows = [["Date", "Staff", "Period", "Net", "Confirmed"]]
        for p in payments:
            paid_at = p.get("paid_at"); paid_s = paid_at.strftime("%b %d") if paid_at else ""
            conf = "Yes" if p.get("confirmed_at") else ("Pending" if p.get("requires_confirmation") else "—")
            rows.append([paid_s, p.get("staff_name") or staff_map.get(p["staff_id"], ""), p.get("period") or "", f"{p.get('currency') or currency} {(p.get('net') or 0):,.0f}", conf])
        t = Table(rows, colWidths=[60, 130, 80, 110, 90])
        t.setStyle(TableStyle([("FONTNAME", (0, 0), (-1, -1), "Helvetica"), ("FONTSIZE", (0, 0), (-1, -1), 9), ("BACKGROUND", (0, 0), (-1, 0), rl_colors.HexColor("#3D6F2A")), ("TEXTCOLOR", (0, 0), (-1, 0), rl_colors.white), ("GRID", (0, 0), (-1, -1), 0.4, rl_colors.HexColor("#DDD")), ("ROWBACKGROUNDS", (0, 1), (-1, -1), [rl_colors.white, rl_colors.HexColor("#FAFAF8")])]))
        elems.append(t)

    # Shopping
    if shopping:
        elems.append(Paragraph("<b>Shopping & reimbursements</b>", h2))
        rows = [["Date", "Type", "Item", "Status", "Amount"]]
        for s in shopping:
            created = s.get("created_at"); created_s = created.strftime("%b %d") if created else ""
            amt = s.get("actual_price") or s.get("estimated_price") or 0
            rows.append([created_s, (s.get("kind") or "request").title(), s.get("item_name", "")[:30], s.get("status", "").title(), f"{currency} {amt:,.0f}"])
        t = Table(rows, colWidths=[55, 90, 180, 75, 90])
        t.setStyle(TableStyle([("FONTNAME", (0, 0), (-1, -1), "Helvetica"), ("FONTSIZE", (0, 0), (-1, -1), 9), ("BACKGROUND", (0, 0), (-1, 0), rl_colors.HexColor("#9B5A3F")), ("TEXTCOLOR", (0, 0), (-1, 0), rl_colors.white), ("GRID", (0, 0), (-1, -1), 0.4, rl_colors.HexColor("#DDD")), ("ROWBACKGROUNDS", (0, 1), (-1, -1), [rl_colors.white, rl_colors.HexColor("#FAFAF8")])]))
        elems.append(t)

    # All transactions (raw)
    if items:
        elems.append(Paragraph("<b>All transactions</b>", h2))
        rows = [["Date", "Category", "Item", "Qty", "Price", "Tag"]]
        for it in items[:200]:  # cap to avoid huge PDFs
            d = (it.get("purchase_date") or (it.get("created_at").strftime("%Y-%m-%d") if it.get("created_at") else ""))
            rows.append([d, cat_map.get(it.get("category_id"), "")[:18], (it.get("name") or "")[:30], str(it.get("quantity") or 1), f"{currency} {(it.get('price') or 0):,.0f}", (it.get("event_tag") or "")[:14]])
        if len(items) > 200:
            rows.append([f"… and {len(items) - 200} more (CSV has all)", "", "", "", "", ""])
        t = Table(rows, colWidths=[60, 80, 170, 40, 90, 70])
        t.setStyle(TableStyle([("FONTNAME", (0, 0), (-1, -1), "Helvetica"), ("FONTSIZE", (0, 0), (-1, -1), 8), ("BACKGROUND", (0, 0), (-1, 0), rl_colors.HexColor("#1F4F88")), ("TEXTCOLOR", (0, 0), (-1, 0), rl_colors.white), ("GRID", (0, 0), (-1, -1), 0.3, rl_colors.HexColor("#EEE")), ("ROWBACKGROUNDS", (0, 1), (-1, -1), [rl_colors.white, rl_colors.HexColor("#FAFAF8")])]))
        elems.append(t)

    doc.build(elems)
    pdf_buf.seek(0)
    filename = f"household-report-{y}-{m:02d}.pdf"
    return Response(content=pdf_buf.getvalue(), media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{filename}"'})


# =========================
# Household Report (Monthly summary for housewives)
# =========================
@api_router.get("/reports/household")
async def household_report(space_id: str, year: Optional[int] = None, month: Optional[int] = None, user: User = Depends(get_current_user)):
    space = await assert_space_member(space_id, user.user_id)
    now = now_utc()
    y = year or now.year
    m = month or now.month
    # month start/end
    start = datetime(y, m, 1, tzinfo=timezone.utc)
    if m == 12:
        end = datetime(y + 1, 1, 1, tzinfo=timezone.utc)
    else:
        end = datetime(y, m + 1, 1, tzinfo=timezone.utc)
    start_str = start.strftime("%Y-%m-%d")
    end_str = end.strftime("%Y-%m-%d")
    currency = space.get("currency") or "USD"

    # --- Spending (items with price in window) ---
    # We use items as the finance ledger (as seen in /reports/finance + payroll logs).
    item_pipeline = [
        {"$match": {"space_id": space_id, "created_at": {"$gte": start, "$lt": end}, "price": {"$ne": None, "$gt": 0}}},
        {"$group": {"_id": "$category_id", "total": {"$sum": "$price"}, "count": {"$sum": 1}}},
        {"$sort": {"total": -1}},
    ]
    cat_totals = []
    async for row in db.items.aggregate(item_pipeline):
        cat_totals.append(row)
    total_spent = sum((c.get("total") or 0) for c in cat_totals)
    # attach category names
    cat_ids = [c["_id"] for c in cat_totals if c.get("_id")]
    cats = await db.categories.find({"category_id": {"$in": cat_ids}}, {"_id": 0}).to_list(200)
    cat_name = {c["category_id"]: c["name"] for c in cats}
    cat_icon = {c["category_id"]: c.get("icon") or "Package" for c in cats}
    cat_tint = {c["category_id"]: c.get("tint") or c.get("color") or "mint" for c in cats}
    top_categories = []
    for c in cat_totals[:5]:
        cid = c.get("_id")
        top_categories.append({
            "category_id": cid,
            "name": cat_name.get(cid, "Uncategorized"),
            "icon": cat_icon.get(cid, "Package"),
            "tint": cat_tint.get(cid, "mint"),
            "total": round(c.get("total") or 0, 2),
            "count": c.get("count") or 0,
        })

    # --- Staff summary ---
    # Show staff that were "active during this month" OR had any payment/attendance in the window.
    # A staff is active-during-window if: (start_date <= window_end) AND (end_date is null OR end_date >= window_start) AND active != false
    all_staff = await db.staff_members.find({"space_id": space_id}, {"_id": 0}).to_list(500)
    # Attendance in window
    att_docs = await db.attendance_logs.find({"space_id": space_id, "date": {"$gte": start_str, "$lt": end_str}}, {"_id": 0}).to_list(5000)
    att_by_staff: Dict[str, Dict[str, int]] = {}
    for a in att_docs:
        sid = a["staff_id"]; st = a["status"]
        att_by_staff.setdefault(sid, {"present": 0, "off": 0, "sick": 0, "leave": 0, "late": 0})
        att_by_staff[sid][st] = att_by_staff[sid].get(st, 0) + 1
    # Payments in window
    pay_docs = await db.staff_payments.find({"space_id": space_id, "paid_at": {"$gte": start, "$lt": end}}, {"_id": 0}).to_list(1000)
    paid_by_staff: Dict[str, float] = {}
    for p in pay_docs:
        paid_by_staff[p["staff_id"]] = paid_by_staff.get(p["staff_id"], 0) + float(p.get("net") or 0)
    total_wages = sum(paid_by_staff.values())

    def _in_window(s: Dict[str, Any]) -> bool:
        # Explicitly inactive → only include if they had activity in window
        active = s.get("active", True)
        sd = s.get("start_date")
        ed = s.get("end_date")
        had_activity = (s["staff_id"] in att_by_staff) or (s["staff_id"] in paid_by_staff)
        # Exclude staff with start_date after window end (hasn't started yet), unless they had activity
        if sd and sd >= end_str and not had_activity:
            return False
        # Exclude staff ended before window start, unless they had activity (historical)
        if ed and ed < start_str and not had_activity:
            return False
        # Inactive and no activity → hide
        if not active and not had_activity:
            return False
        return True

    staff_docs = [s for s in all_staff if _in_window(s)]

    # Task completions per staff in window
    task_ids = [t["task_id"] for t in await db.task_templates.find({"space_id": space_id}, {"_id": 0, "task_id": 1, "staff_id": 1, "role_id": 1}).to_list(2000)]
    task_owner = {t["task_id"]: t for t in await db.task_templates.find({"space_id": space_id}, {"_id": 0, "task_id": 1, "staff_id": 1, "role_id": 1}).to_list(2000)}
    comp_docs = await db.task_completions.find({"space_id": space_id, "date": {"$gte": start_str, "$lt": end_str}, "task_id": {"$in": task_ids}}, {"_id": 0}).to_list(5000)
    done_by_staff: Dict[str, int] = {}
    total_tasks_done = 0
    for c in comp_docs:
        total_tasks_done += 1
        # prefer completion staff_id, fall back to task owner
        sid = c.get("staff_id") or (task_owner.get(c["task_id"], {}) or {}).get("staff_id")
        if sid:
            done_by_staff[sid] = done_by_staff.get(sid, 0) + 1

    staff_summary = []
    for s in staff_docs:
        sid = s["staff_id"]
        att = att_by_staff.get(sid, {})
        staff_summary.append({
            "staff_id": sid,
            "name": s.get("name"),
            "photo_base64": s.get("photo_base64"),
            "role_id": s.get("role_id"),
            "active": s.get("active", True),
            "start_date": s.get("start_date"),
            "end_date": s.get("end_date"),
            "days_present": att.get("present", 0) + att.get("late", 0),
            "days_off": att.get("off", 0),
            "days_sick": att.get("sick", 0),
            "days_leave": att.get("leave", 0),
            "tasks_done": done_by_staff.get(sid, 0),
            "paid": round(paid_by_staff.get(sid, 0), 2),
            "salary": s.get("salary"),
            "pay_cycle": s.get("pay_cycle"),
        })

    # --- Shopping requests in window ---
    shop_docs = await db.shopping_requests.find({"space_id": space_id, "created_at": {"$gte": start, "$lt": end}}, {"_id": 0}).to_list(2000)
    shop_pending = sum(1 for r in shop_docs if r.get("status") == "pending")
    shop_approved = sum(1 for r in shop_docs if r.get("status") == "approved")
    shop_purchased = sum(1 for r in shop_docs if r.get("status") == "purchased")

    # --- Headline blurb for housewife ---
    month_name = start.strftime("%B %Y")
    return {
        "month": month_name,
        "year": y,
        "month_num": m,
        "currency": currency,
        "total_spent": round(total_spent, 2),
        "total_wages": round(total_wages, 2),
        "top_categories": top_categories,
        "staff": staff_summary,
        "shopping": {
            "total": len(shop_docs),
            "pending": shop_pending,
            "approved": shop_approved,
            "purchased": shop_purchased,
        },
        "tasks_done": total_tasks_done,
    }
