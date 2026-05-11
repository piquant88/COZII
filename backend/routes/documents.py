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



@api_router.get("/documents", response_model=List[Document])
async def list_documents(space_id: str, folder: Optional[str] = None, user: User = Depends(get_current_user)):
    await assert_space_member(space_id, user.user_id)
    q: Dict[str, Any] = {"space_id": space_id}
    if folder:
        q["folder"] = folder
    docs = await db.documents.find(q, {"_id": 0}).sort("created_at", -1).to_list(500)
    return [Document(**d) for d in docs]


@api_router.post("/documents", response_model=Document)
async def create_document(body: CreateDocumentRequest, user: User = Depends(get_current_user)):
    await assert_space_member(body.space_id, user.user_id)
    if not body.file_base64:
        raise HTTPException(400, "file_base64 is required")
    raw = body.file_base64
    # Estimate size in KB
    payload = raw.split(",", 1)[1] if "," in raw and raw.startswith("data:") else raw
    size_kb = max(1, int(len(payload) * 3 / 4 / 1024))
    if size_kb > 8 * 1024:  # 8 MB hard cap
        raise HTTPException(413, "File too large (max ~8 MB). Please compress or split.")
    doc = {
        "document_id": gen_id("doc"),
        "space_id": body.space_id,
        "name": body.name.strip() or "Untitled",
        "folder": body.folder,
        "mime": body.mime or "image/jpeg",
        "file_base64": body.file_base64,
        "note": body.note,
        "tags": body.tags or [],
        "size_kb": size_kb,
        "uploaded_by": user.user_id,
        "uploaded_by_name": user.name,
        "created_at": now_utc(),
        "related_to": body.related_to,
    }
    await db.documents.insert_one(doc)
    doc.pop("_id", None)
    return Document(**doc)


@api_router.patch("/documents/{document_id}", response_model=Document)
async def update_document(document_id: str, body: UpdateDocumentRequest, user: User = Depends(get_current_user)):
    d = await db.documents.find_one({"document_id": document_id}, {"_id": 0})
    if not d:
        raise HTTPException(404, "Document not found")
    await assert_space_member(d["space_id"], user.user_id)
    updates = {k: v for k, v in body.dict(exclude_unset=True).items() if v is not None}
    if updates:
        await db.documents.update_one({"document_id": document_id}, {"$set": updates})
    out = await db.documents.find_one({"document_id": document_id}, {"_id": 0})
    return Document(**out)


@api_router.delete("/documents/{document_id}")
async def delete_document(document_id: str, user: User = Depends(get_current_user)):
    d = await db.documents.find_one({"document_id": document_id}, {"_id": 0})
    if not d:
        raise HTTPException(404, "Document not found")
    await assert_space_member(d["space_id"], user.user_id)
    await db.documents.delete_one({"document_id": document_id})
    return {"ok": True}


@api_router.get("/documents/folders")
async def list_doc_folders(space_id: str, user: User = Depends(get_current_user)):
    await assert_space_member(space_id, user.user_id)
    pipeline = [{"$match": {"space_id": space_id, "folder": {"$ne": None}}}, {"$group": {"_id": "$folder", "count": {"$sum": 1}}}]
    folders = []
    async for r in db.documents.aggregate(pipeline):
        folders.append({"folder": r["_id"], "count": r["count"]})
    return folders
