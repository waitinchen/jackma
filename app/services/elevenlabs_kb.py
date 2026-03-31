from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Iterable, List, Tuple

import requests

from app.core.config import settings
from app.db.models import Conversation, KnowledgeBaseSyncState, KnowledgeBaseSyncedMemory, Memory
from app.db.session import SessionLocal

KB_BASE_URL = "https://api.elevenlabs.io/v1/convai/knowledge-base"
KB_FILE_URL = f"{KB_BASE_URL}/file"

HIGH_VALUE_KEYWORDS = [
    "我喜歡", "我不喜歡", "我討厭", "我怕", "我愛",
    "我叫", "我的名字", "我是", "我在", "我住",
    "我的工作", "我的職業", "我的公司", "我的生日",
    "我習慣", "我常", "我需要", "我不能",
    "不要", "請記得", "請記住", "約定", "共識",
    "偏好", "禁忌", "規則", "長期",
]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_text(text: str) -> str:
    return " ".join(text.split()).strip()


def _score_memory(text: str) -> int:
    score = 0
    for keyword in HIGH_VALUE_KEYWORDS:
        if keyword in text:
            score += 2
    if "用戶問：" in text or "大哥答：" in text:
        score += 1
    return score


def _trim_text(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3].rstrip() + "..."


def _extract_summary(text: str) -> str:
    normalized = _normalize_text(text)
    if "用戶問：" in normalized and "大哥答：" in normalized:
        try:
            user_part = normalized.split("用戶問：", 1)[1]
            user_text, assistant_text = user_part.split(" | 大哥答：", 1)
            user_text = _trim_text(user_text.strip(), settings.SYNC_KB_MAX_TEXT_CHARS)
            assistant_text = _trim_text(assistant_text.strip(), settings.SYNC_KB_MAX_TEXT_CHARS)
            return f"用戶：{user_text} / 回覆：{assistant_text}"
        except ValueError:
            pass
    return _trim_text(normalized, settings.SYNC_KB_MAX_TEXT_CHARS)


def _hash_content(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _build_document(user_id: str, summaries: Iterable[str]) -> str:
    header = [
        f"User: {user_id}",
        f"Generated: {_now().isoformat()}",
        "Notes: condensed memory for agent knowledge base.",
        "",
    ]
    body = [f"- {summary}" for summary in summaries]
    return "\n".join(header + body)


def _upload_document(content: str, name: str) -> Tuple[str, str]:
    headers = {"xi-api-key": settings.ELEVENLABS_API_KEY}
    files = {"file": ("kb.txt", content.encode("utf-8"), "text/plain")}
    data = {"name": name}
    if settings.ELEVENLABS_KB_FOLDER_ID:
        data["parent_folder_id"] = settings.ELEVENLABS_KB_FOLDER_ID

    # If agent id is configured, use legacy endpoint to attach directly.
    if settings.ELEVENLABS_AGENT_ID:
        resp = requests.post(
            KB_BASE_URL,
            headers=headers,
            params={"agent_id": settings.ELEVENLABS_AGENT_ID},
            files=files,
            data=data,
            timeout=20,
        )
    else:
        resp = requests.post(
            KB_FILE_URL,
            headers=headers,
            files=files,
            data=data,
            timeout=20,
        )

    if resp.status_code >= 300:
        raise RuntimeError(f"KB upload failed: {resp.status_code} {resp.text}")

    payload = resp.json()
    return payload.get("id", ""), payload.get("name", name)


def _delete_document(document_id: str) -> None:
    if not document_id:
        return
    headers = {"xi-api-key": settings.ELEVENLABS_API_KEY}
    resp = requests.delete(
        f"{KB_BASE_URL}/{document_id}",
        headers=headers,
        params={"force": "true"},
        timeout=20,
    )
    if resp.status_code >= 300:
        print(f"[WARNING] KB delete failed: {resp.status_code} {resp.text}")


def _load_unsynced_memories(user_id: str, limit: int) -> List[Memory]:
    db = SessionLocal()
    try:
        synced_subq = db.query(KnowledgeBaseSyncedMemory.memory_id).filter(
            KnowledgeBaseSyncedMemory.user_id == user_id
        )
        memories = (
            db.query(Memory)
            .join(Conversation, Memory.conversation_id == Conversation.id)
            .filter(Conversation.user_id == user_id)
            .filter(~Memory.id.in_(synced_subq))
            .order_by(Memory.created_at.desc())
            .limit(limit)
            .all()
        )
        return memories
    finally:
        db.close()


def _count_unsynced_memories(user_id: str) -> int:
    db = SessionLocal()
    try:
        synced_subq = db.query(KnowledgeBaseSyncedMemory.memory_id).filter(
            KnowledgeBaseSyncedMemory.user_id == user_id
        )
        return (
            db.query(Memory)
            .join(Conversation, Memory.conversation_id == Conversation.id)
            .filter(Conversation.user_id == user_id)
            .filter(~Memory.id.in_(synced_subq))
            .count()
        )
    finally:
        db.close()


def _get_or_create_state(db, user_id: str) -> KnowledgeBaseSyncState:
    state = db.query(KnowledgeBaseSyncState).filter(KnowledgeBaseSyncState.user_id == user_id).first()
    if not state:
        state = KnowledgeBaseSyncState(user_id=user_id)
        db.add(state)
        db.commit()
    return state


def maybe_sync_kb_for_user(user_id: str) -> dict:
    if not settings.SYNC_KB_ENABLED:
        return {"status": "disabled"}

    pending_count = _count_unsynced_memories(user_id)
    if pending_count < settings.SYNC_KB_MIN_NEW_ITEMS:
        return {"status": "skip", "reason": "not_enough_items", "pending": pending_count}

    db = SessionLocal()
    try:
        state = _get_or_create_state(db, user_id)
        if state.last_synced_at:
            elapsed = (_now() - state.last_synced_at).total_seconds()
            if elapsed < settings.SYNC_KB_MIN_INTERVAL_SECONDS:
                return {"status": "skip", "reason": "cooldown", "pending": pending_count}
    finally:
        db.close()

    return sync_kb_for_user(user_id)


def sync_kb_for_user(user_id: str) -> dict:
    if not settings.SYNC_KB_ENABLED:
        return {"status": "disabled"}

    memories = _load_unsynced_memories(user_id, settings.SYNC_KB_CANDIDATE_LIMIT)
    if not memories:
        return {"status": "skip", "reason": "no_candidates"}

    scored = sorted(
        memories,
        key=lambda m: (_score_memory(m.content), m.created_at or _now()),
        reverse=True,
    )
    selected = scored[: settings.SYNC_KB_MAX_ITEMS]
    summaries = [_extract_summary(m.content) for m in selected]

    document = _build_document(user_id, summaries)
    document = document[: settings.SYNC_KB_MAX_DOC_BYTES]
    doc_hash = _hash_content(document)

    db = SessionLocal()
    try:
        state = _get_or_create_state(db, user_id)
        if state.last_doc_hash == doc_hash:
            return {"status": "skip", "reason": "no_change"}

        doc_name = f"kb-sync-{user_id}-{_now().strftime('%Y%m%d-%H%M%S')}"
        doc_id, _ = _upload_document(document, doc_name)

        for memory in selected:
            db.add(
                KnowledgeBaseSyncedMemory(
                    user_id=user_id,
                    memory_id=memory.id,
                    content_hash=_hash_content(_normalize_text(memory.content)),
                )
            )

        previous_doc_id = state.last_doc_id
        state.last_doc_id = doc_id
        state.last_doc_hash = doc_hash
        state.last_synced_at = _now()
        db.commit()

    finally:
        db.close()

    if previous_doc_id:
        _delete_document(previous_doc_id)

    return {
        "status": "ok",
        "synced_items": len(selected),
        "document_id": doc_id,
    }
