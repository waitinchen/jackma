from pydantic_settings import BaseSettings, SettingsConfigDict
import os
from pathlib import Path

# 獲取專案根目錄 (.env 所在的目錄)
ROOT_DIR = Path(__file__).resolve().parent.parent.parent

class Settings(BaseSettings):
    PROJECT_NAME: str = "JackMa Voice Spirit"
    # Cloud Run 會自動注入 DATABASE_URL，本地開發可使用默認值
    # GCP Cloud SQL 格式: postgresql://user:pass@/dbname?host=/cloudsql/PROJECT:REGION:INSTANCE
    DATABASE_URL: str = "postgresql://localhost/jiangbin"

    # API Keys (GCP 會透過 Secret Manager 注入)
    GEMINI_API_KEY: str = ""
    ELEVENLABS_API_KEY: str = ""      # KB 操作仍在用
    ELEVENLABS_VOICE_ID: str = ""     # KB 操作仍在用
    ELEVENLABS_AGENT_ID: str | None = None   # turn.py signed-url 在用
    ELEVENLABS_KB_FOLDER_ID: str | None = None  # elevenlabs_kb.py 在用

    # JWT Auth 設定
    JWT_SECRET_KEY: str = "please-change-this-to-a-random-secret-key-at-least-32-chars"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 24 小時

    # ============================================
    # Phase 2: 長期記憶系統功能開關
    # ============================================
    
    # Phase 2A: UserProfile 用戶基本資料
    ENABLE_USER_PROFILE: bool = True
    
    # Phase 2B: UserEvent 用戶事件
    ENABLE_USER_EVENTS: bool = True
    USER_EVENTS_LOOKBACK_DAYS: int = 7  # 查詢最近幾天的事件
    
    # Phase 2C: JackmaAction 馬雲說過的話
    ENABLE_JACKMA_ACTIONS: bool = True
    JACKMA_ACTIONS_LOOKBACK_DAYS: int = 14  # 查詢最近幾天的行動
    
    # Phase 2D: LLM 自動抽取 (需要 2A 先啟用)
    ENABLE_AUTO_EXTRACT: bool = False
    AUTO_EXTRACT_MIN_CONFIDENCE: float = 0.7  # 最低信心度才自動更新
    
    # Phase 2E: 主動關心機制
    ENABLE_PROACTIVE_CARE: bool = True
    
    # Phase 3: 圖片辨識
    ENABLE_VISION: bool = True
    VISION_MAX_IMAGE_SIZE_MB: float = 5.0  # 最大圖片大小 (MB)

    # LiveKit 設定
    LIVEKIT_URL: str = ""
    LIVEKIT_API_KEY: str = ""
    LIVEKIT_API_SECRET: str = ""

    # MiniMax 設定（TTS + LLM 共用）
    MINIMAX_API_KEY: str = ""
    MINIMAX_GROUP_ID: str = ""
    MINIMAX_VOICE_ID: str = ""  # 代碼裡硬編碼更安全，此欄位僅供參考

    # Anthropic (Claude) LLM
    ANTHROPIC_API_KEY: str = ""

    # KB sync controls
    SYNC_KB_ENABLED: bool = False
    SYNC_KB_MIN_NEW_ITEMS: int = 5
    SYNC_KB_MAX_ITEMS: int = 20
    SYNC_KB_CANDIDATE_LIMIT: int = 200
    SYNC_KB_MIN_INTERVAL_SECONDS: int = 86400
    SYNC_KB_MAX_TEXT_CHARS: int = 180
    SYNC_KB_MAX_DOC_BYTES: int = 20000

    # 使用新的 Pydantic Settings V2 配置方式
    model_config = SettingsConfigDict(
        env_file=str(ROOT_DIR / ".env"),
        env_file_encoding='utf-8',
        extra="ignore"
    )

settings = Settings()

# 偵錯用：確保主要金鑰有讀到
if settings.MINIMAX_API_KEY:
    print(f"[OK] Config loaded. MiniMax Key starts with: {settings.MINIMAX_API_KEY[:8]}...")
else:
    print("[WARNING] MINIMAX_API_KEY is empty - MiniMax LLM+TTS will not work")

# 檢查是否在 Cloud Run 環境
if os.environ.get("K_SERVICE"):
    print(f"[OK] Running on Cloud Run: {os.environ.get('K_SERVICE')}")
