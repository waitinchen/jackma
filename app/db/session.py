from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool
from app.core.config import settings
import os

# Cloud Run 環境使用 NullPool 避免連線池問題
is_cloud_run = os.environ.get("K_SERVICE") is not None

if is_cloud_run:
    # Cloud Run + Cloud SQL: 使用 NullPool 和較短的超時
    engine = create_engine(
        settings.DATABASE_URL,
        poolclass=NullPool,
        connect_args={
            "connect_timeout": 10,
        }
    )
else:
    # 本地開發
    engine = create_engine(settings.DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
