"""
馬雲語氣靈 — 上下文組裝器
從現有 services 載入用戶資料，組裝完整系統提示供 LiveKit Agent 使用
"""
import asyncio
import logging
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

# 直接匯入現有的 SYSTEM_PROMPT 和 services
from app.services.llm import SYSTEM_PROMPT
from app.services.memory import retrieve_memories
from app.services.user_profile import format_profile_for_prompt
from app.services.user_event import get_recent_events, get_current_date_gmt8
from app.services.jackma_action import get_recent_actions
from app.services.proactive_care import generate_proactive_care_context
from app.services.user_key_note import format_key_notes_for_prompt, get_key_notes, CATEGORY_LABELS
from app.core.config import settings


def _fetch_profile(user_id):
    if settings.ENABLE_USER_PROFILE:
        return format_profile_for_prompt(user_id)
    return None

def _fetch_key_notes(user_id):
    notes = get_key_notes(user_id, limit=5)
    if not notes:
        return None
    lines = []
    for n in notes:
        label = CATEGORY_LABELS.get(n["category"], "")
        lines.append(f"- （{label}）{n['summary']}" if label else f"- {n['summary']}")
    return "【這位朋友的重要事項（永久記憶）】\n" + "\n".join(lines)

def _fetch_events(user_id):
    if not settings.ENABLE_USER_EVENTS:
        return None
    events = get_recent_events(user_id, days=7, limit=5, include_resolved=False)
    if not events:
        return None
    today = get_current_date_gmt8()
    lines = []
    for e in events:
        event_date = e["event_date"]
        if event_date == today:
            date_str = "今天"
        else:
            days_ago = (datetime.strptime(today, "%Y-%m-%d") - datetime.strptime(event_date, "%Y-%m-%d")).days
            date_str = "昨天" if days_ago == 1 else "前天" if days_ago == 2 else f"{days_ago}天前"
        type_labels = {'mood': '心情', 'activity': '活動', 'plan': '計畫', 'health': '健康', 'work': '工作', 'relationship': '人際'}
        label = type_labels.get(e["event_type"], "")
        lines.append(f"- {date_str}（{label}）：{e['summary']}" if label else f"- {date_str}：{e['summary']}")
    return "【這位朋友最近的狀況】\n" + "\n".join(lines) if lines else None

def _fetch_actions(user_id):
    if not settings.ENABLE_JACKMA_ACTIONS:
        return None
    actions = get_recent_actions(user_id, days=7, limit=5, include_fulfilled=False)
    if not actions:
        return None
    today = get_current_date_gmt8()
    lines = []
    for a in actions:
        action_date = a["action_date"]
        if action_date == today:
            date_str = "今天"
        else:
            days_ago = (datetime.strptime(today, "%Y-%m-%d") - datetime.strptime(action_date, "%Y-%m-%d")).days
            date_str = "昨天" if days_ago == 1 else "前天" if days_ago == 2 else f"{days_ago}天前"
        type_labels = {'promise': '我答應過', 'suggestion': '我建議過', 'question': '我問過', 'reminder': '我提醒過', 'encouragement': '我鼓勵過'}
        label = type_labels.get(a["action_type"], "我說過")
        lines.append(f"- {date_str}{label}：{a['summary']}")
    return "【我對這位朋友說過的話】\n" + "\n".join(lines) if lines else None

def _fetch_proactive_care(user_id):
    if not settings.ENABLE_PROACTIVE_CARE:
        return None
    return generate_proactive_care_context(user_id)

def _fetch_memories(conversation_id):
    try:
        memories = retrieve_memories(conversation_id, "最近的對話", limit=2)
        if memories:
            return "【記憶參考】\n" + "\n".join([f"- {m}" for m in memories])
    except Exception as e:
        logger.warning(f"Failed to load memories: {e}")
    return None

def _fetch_history(conversation_id):
    try:
        from app.api.turn import get_recent_conversation_history
        history = get_recent_conversation_history(conversation_id, limit=6)
        if history:
            lines = []
            for msg in history:
                role_label = "用戶" if msg["role"] == "user" else "馬雲"
                time_prefix = f"[{msg['created_at']}] " if msg.get("created_at") else ""
                lines.append(f"{time_prefix}{role_label}：{msg['content']}")
            return "【最近對話紀錄】\n" + "\n".join(lines)
    except Exception as e:
        logger.warning(f"Failed to load conversation history: {e}")
    return None


async def build_jackma_prompt(user_id: str, conversation_id: str = None) -> str:
    """
    組裝完整的馬雲系統提示 + 用戶動態上下文（並行查詢 DB）
    """
    if conversation_id is None:
        conversation_id = f"conv_{user_id}"

    prompt_parts = [SYSTEM_PROMPT]

    # 當前時間（GMT+8）
    tw_tz = timezone(timedelta(hours=8))
    now = datetime.now(tw_tz)
    weekday_names = ['一', '二', '三', '四', '五', '六', '日']
    time_str = now.strftime(f"%Y年%m月%d日 星期{weekday_names[now.weekday()]} %H:%M")
    prompt_parts.append(
        f"【當前時間】{time_str}\n"
        "（請根據對話紀錄的時間戳判斷時間遠近：同一天內的事用「剛才」「剛剛」，"
        "昨天的用「昨天」，超過兩天才用「前幾天」「上次」。"
        "絕對不要把幾分鐘前的事說成「上次」「之前」。）"
    )

    # 7 個 DB 查詢並行執行（省 5-10s → ~2s）
    (
        profile_ctx,
        key_notes_ctx,
        events_ctx,
        actions_ctx,
        care_ctx,
        memories_ctx,
        history_ctx,
    ) = await asyncio.gather(
        asyncio.to_thread(_fetch_profile, user_id),
        asyncio.to_thread(_fetch_key_notes, user_id),
        asyncio.to_thread(_fetch_events, user_id),
        asyncio.to_thread(_fetch_actions, user_id),
        asyncio.to_thread(_fetch_proactive_care, user_id),
        asyncio.to_thread(_fetch_memories, conversation_id),
        asyncio.to_thread(_fetch_history, conversation_id),
    )

    # 按順序組裝（保持 prompt 結構不變）
    for ctx in [profile_ctx, key_notes_ctx, events_ctx, actions_ctx, care_ctx, memories_ctx, history_ctx]:
        if ctx:
            prompt_parts.append(ctx)

    full_prompt = "\n\n".join(prompt_parts)
    logger.info(f"Built JackMa prompt for user {user_id}: {len(full_prompt)} chars")
    return full_prompt
