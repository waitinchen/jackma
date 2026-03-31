from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from contextlib import asynccontextmanager
from pathlib import Path
import glob
import os
import sys
import logging
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from app.api import turn, admin, auth, profile, events, actions, extract, care, vision, livekit

# 設定 logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 取得專案根目錄的絕對路徑
BASE_DIR = Path(__file__).resolve().parent.parent

# 判斷是否為生產環境 (Cloud Run 會設定 K_SERVICE 環境變數)
IS_PRODUCTION = os.environ.get("K_SERVICE") is not None

# Rate Limiter 設定 (每分鐘 20 次請求)
limiter = Limiter(key_func=get_remote_address)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 啟動時執行：初始化資料庫
    logger.info("Lifespan starting...")
    
    # Cloud Run 環境下跳過 init_db（資料表應該已經存在）
    # 但仍然執行必要的 migration
    if IS_PRODUCTION:
        logger.info("Production mode: running migrations only")
        try:
            from sqlalchemy import text
            from app.db.session import engine
            from app.db.base import Base
            from app.db.models import UserKeyNote  # 確保新 model 被載入
            
            # 確保 pgvector 擴展存在
            with engine.connect() as conn:
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
                conn.commit()
            logger.info("Migration: pgvector extension ensured.")

            # 建立可能缺少的新表（如 user_key_notes）
            Base.metadata.create_all(bind=engine)
            logger.info("Migration: ensured all tables exist.")
            
            with engine.connect() as conn:
                # Migration: turns.source 欄位
                result = conn.execute(text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name='turns' AND column_name='source'"
                ))
                if result.fetchone() is None:
                    conn.execute(text("ALTER TABLE turns ADD COLUMN source VARCHAR DEFAULT 'text'"))
                    conn.commit()
                    logger.info("Migration: Added 'source' column to turns table.")
                
                # Migration: 清理「文翊啊，」「喔，文翊，」等開頭的回覆
                result = conn.execute(text(
                    "UPDATE turns SET reply_text = regexp_replace(reply_text, "
                    "'^[喔噢嗯啊唉欸哎][，,、]?\\s*文翊[啊阿呀]?[，,、]?\\s*', '', 'g') "
                    "WHERE reply_text ~ '^[喔噢嗯啊唉欸哎].*文翊' OR reply_text ~ '^文翊[啊阿]'"
                ))
                cleaned = result.rowcount
                # 也清理純「文翊啊，」開頭
                result1b = conn.execute(text(
                    "UPDATE turns SET reply_text = regexp_replace(reply_text, '^文翊[啊阿呀][，,、]?\\s*', '', 'g') "
                    "WHERE reply_text ~ '^文翊[啊阿呀]'"
                ))
                cleaned += result1b.rowcount
                result2 = conn.execute(text(
                    "UPDATE memories SET content = regexp_replace(content, '文翊[啊阿][，,、]?\\s*', '', 'g') "
                    "WHERE content LIKE '%文翊啊%' OR content LIKE '%文翊阿%'"
                ))
                cleaned2 = result2.rowcount
                conn.commit()
                if cleaned or cleaned2:
                    logger.info(f"Migration: Cleaned name-prefix patterns from {cleaned} turns, {cleaned2} memories.")
        except Exception as e:
            logger.warning(f"Migration failed (non-fatal): {e}")
    else:
        try:
            import sys
            from pathlib import Path
            # 將專案根目錄加入 Python 路徑
            root_dir = Path(__file__).resolve().parent.parent
            sys.path.insert(0, str(root_dir))

            logger.info("Importing init_db...")
            from init_db import init_db
            logger.info("Running init_db()...")
            init_db()
            logger.info("Database initialized successfully")
        except Exception as e:
            logger.warning(f"Database initialization failed: {e}")
            logger.info("App will continue, but database operations may fail")

    logger.info("Lifespan setup complete.")
    yield
    logger.info("Lifespan shutting down.")

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

app = FastAPI(title="JackMa Voice Spirit API", lifespan=lifespan)

# 加入 Rate Limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# 全域錯誤處理：避免洩漏內部資訊（HTTPException / ValidationError 由 FastAPI 內建處理）
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """統一處理未捕獲的錯誤"""
    # 記錄完整錯誤到日誌（方便除錯）
    logger.error(f"Unhandled exception: {exc}", exc_info=True)

    if IS_PRODUCTION:
        # 生產環境：只回傳通用錯誤訊息
        return JSONResponse(
            status_code=500,
            content={"detail": "伺服器發生錯誤，請稍後再試"}
        )
    else:
        # 開發環境：回傳詳細錯誤（方便除錯）
        import traceback
        return JSONResponse(
            status_code=500,
            content={
                "detail": str(exc),
                "traceback": traceback.format_exc()
            }
        )

# CORS 設定
# 只允許指定的前端網址呼叫 API
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://jackma-frontend-652703327350.asia-east1.run.app",  # 正式前端
        "https://jackma.tonetown.ai",  # 自訂網域前端
        "http://localhost:5173",  # 本地開發 (Vite)
        "http://localhost:8000",  # 本地開發 (後端)
        "http://127.0.0.1:5173",
        "http://127.0.0.1:8000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 基礎設施：靜態檔案路徑 (供播放音檔使用)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

# 前端資源 (Vite build)
WEB_STATIC_DIR = str(BASE_DIR / "web_static")
app.mount("/assets", StaticFiles(directory=f"{WEB_STATIC_DIR}/assets"), name="web_assets")
app.mount("/api/assets", StaticFiles(directory=f"{WEB_STATIC_DIR}/assets"), name="web_assets_api")

# 註冊路由
app.include_router(auth.router, prefix="/api/auth", tags=["Auth"])
app.include_router(profile.router, prefix="/api", tags=["Profile"])
app.include_router(events.router, prefix="/api", tags=["Events"])
app.include_router(actions.router, prefix="/api", tags=["Actions"])
app.include_router(extract.router, prefix="/api", tags=["Extract"])
app.include_router(care.router, prefix="/api", tags=["Care"])
app.include_router(vision.router, prefix="/api", tags=["Vision"])
app.include_router(turn.router, prefix="/api", tags=["Turn"])
app.include_router(livekit.router, prefix="/api/livekit", tags=["LiveKit"])
app.include_router(admin.router, prefix="/admin", tags=["Admin"])

@app.get("/")
async def read_index():
    return FileResponse(os.path.join(WEB_STATIC_DIR, "index.html"))

@app.get("/index.html")
async def read_root_index():
    return FileResponse(os.path.join(WEB_STATIC_DIR, "index.html"))

@app.get("/api/index.html")
async def read_root_index_api():
    return FileResponse(os.path.join(WEB_STATIC_DIR, "index.html"))

@app.get("/manifest.webmanifest")
async def web_manifest():
    return FileResponse(os.path.join(WEB_STATIC_DIR, "manifest.webmanifest"), media_type="application/manifest+json")

@app.get("/api/manifest.webmanifest")
async def web_manifest_api():
    return FileResponse(os.path.join(WEB_STATIC_DIR, "manifest.webmanifest"), media_type="application/manifest+json")

@app.get("/registerSW.js")
async def register_sw():
    return FileResponse(os.path.join(WEB_STATIC_DIR, "registerSW.js"), media_type="application/javascript")

@app.get("/api/registerSW.js")
async def register_sw_api():
    return FileResponse(os.path.join(WEB_STATIC_DIR, "registerSW.js"), media_type="application/javascript")

@app.get("/sw.js")
async def service_worker():
    return FileResponse(os.path.join(WEB_STATIC_DIR, "sw.js"), media_type="application/javascript")

@app.get("/api/sw.js")
async def service_worker_api():
    return FileResponse(os.path.join(WEB_STATIC_DIR, "sw.js"), media_type="application/javascript")

# Workbox 檔名隨 build 變動，依 web_static 內實際 workbox-*.js 動態註冊路由
def _register_workbox_routes():
    pattern = os.path.join(WEB_STATIC_DIR, "workbox-*.js")
    for fp in glob.glob(pattern):
        name = os.path.basename(fp)

        async def _serve(p: str = fp):
            return FileResponse(p, media_type="application/javascript")

        app.add_api_route(f"/{name}", _serve, methods=["GET"])
        app.add_api_route(f"/api/{name}", _serve, methods=["GET"])


_register_workbox_routes()

@app.get("/pwa-192x192.png")
async def pwa_icon_small():
    return FileResponse(os.path.join(WEB_STATIC_DIR, "pwa-192x192.png"))

@app.get("/api/pwa-192x192.png")
async def pwa_icon_small_api():
    return FileResponse(os.path.join(WEB_STATIC_DIR, "pwa-192x192.png"))

@app.get("/pwa-512x512.png")
async def pwa_icon_large():
    return FileResponse(os.path.join(WEB_STATIC_DIR, "pwa-512x512.png"))

@app.get("/api/pwa-512x512.png")
async def pwa_icon_large_api():
    return FileResponse(os.path.join(WEB_STATIC_DIR, "pwa-512x512.png"))

@app.get("/icon.png")
async def favicon_icon():
    return FileResponse(os.path.join(WEB_STATIC_DIR, "icon.png"))

@app.get("/apple-touch-icon-180x180.png")
async def apple_touch_icon_180():
    return FileResponse(os.path.join(WEB_STATIC_DIR, "apple-touch-icon-180x180.png"))

@app.get("/apple-touch-icon-152x152.png")
async def apple_touch_icon_152():
    return FileResponse(os.path.join(WEB_STATIC_DIR, "apple-touch-icon-152x152.png"))

@app.get("/apple-touch-icon-120x120.png")
async def apple_touch_icon_120():
    return FileResponse(os.path.join(WEB_STATIC_DIR, "apple-touch-icon-120x120.png"))

@app.get("/api/icon.png")
async def favicon_icon_api():
    return FileResponse(os.path.join(WEB_STATIC_DIR, "icon.png"))

@app.get("/favicon.ico")
async def favicon_ico():
    return FileResponse(os.path.join(WEB_STATIC_DIR, "icon.png"))

@app.get("/api/favicon.ico")
async def favicon_ico_api():
    return FileResponse(os.path.join(WEB_STATIC_DIR, "icon.png"))

@app.get("/realtime")
async def read_realtime():
    # 返回 React 應用的 index.html，讓前端路由處理 /realtime
    return FileResponse(os.path.join(WEB_STATIC_DIR, "index.html"))

@app.get("/health")
async def health():
    return {"status": "ok"}
