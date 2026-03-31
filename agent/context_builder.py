"""
馬雲語氣靈 — 上下文組裝器
從現有 services 載入用戶資料，組裝完整系統提示供 LiveKit Agent 使用
"""
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
from app.services.user_key_note import format_key_notes_for_prompt
from app.core.config import settings


def build_jackma_prompt(user_id: str, conversation_id: str = None) -> str:
    """
    組裝完整的馬雲系統提示 + 用戶動態上下文

    這段邏輯等同 turn.py 的 _load_conversation_context() + llm.py 的 prompt 組裝
    但輸出為單一 system prompt 字串，供 LiveKit Agent 的 LLM 使用
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

    # 用戶基本資料
    if settings.ENABLE_USER_PROFILE:
        ctx = format_profile_for_prompt(user_id)
        if ctx:
            prompt_parts.append(ctx)

    # 永久筆記（語音模式限 5 條，減少 prompt 長度）
    from app.services.user_key_note import get_key_notes, CATEGORY_LABELS
    key_notes = get_key_notes(user_id, limit=5)
    if key_notes:
        lines = []
        for n in key_notes:
            label = CATEGORY_LABELS.get(n["category"], "")
            lines.append(f"- （{label}）{n['summary']}" if label else f"- {n['summary']}")
        prompt_parts.append("【這位朋友的重要事項（永久記憶）】\n" + "\n".join(lines))

    # 用戶事件（語音模式：7 天內、最多 5 條）
    if settings.ENABLE_USER_EVENTS:

        events = get_recent_events(user_id, days=7, limit=5, include_resolved=False)
        if events:
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
            if lines:
                prompt_parts.append("【這位朋友最近的狀況】\n" + "\n".join(lines))

    # 馬雲承諾 / 說過的話（語音模式：7 天內、最多 5 條）
    if settings.ENABLE_JACKMA_ACTIONS:

        actions = get_recent_actions(user_id, days=7, limit=5, include_fulfilled=False)
        if actions:
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
            if lines:
                prompt_parts.append("【我對這位朋友說過的話】\n" + "\n".join(lines))

    # 主動關心提示
    if settings.ENABLE_PROACTIVE_CARE:
        ctx = generate_proactive_care_context(user_id)
        if ctx:
            prompt_parts.append(ctx)

    # 記憶（用空查詢取得最近的記憶）
    try:
        memories = retrieve_memories(conversation_id, "最近的對話", limit=2)
        if memories:
            memory_text = "\n".join([f"- {m}" for m in memories])
            prompt_parts.append(f"【記憶參考】\n{memory_text}")
    except Exception as e:
        logger.warning(f"Failed to load memories: {e}")

    # 對話歷史
    try:
        from app.api.turn import get_recent_conversation_history
        history = get_recent_conversation_history(conversation_id, limit=6)
        if history:
            history_lines = []
            for msg in history:
                role_label = "用戶" if msg["role"] == "user" else "馬雲"
                time_prefix = f"[{msg['created_at']}] " if msg.get("created_at") else ""
                history_lines.append(f"{time_prefix}{role_label}：{msg['content']}")
            prompt_parts.append(f"【最近對話紀錄】\n" + "\n".join(history_lines))
    except Exception as e:
        logger.warning(f"Failed to load conversation history: {e}")

    full_prompt = "\n\n".join(prompt_parts)
    logger.info(f"Built JackMa prompt for user {user_id}: {len(full_prompt)} chars")
    return full_prompt
