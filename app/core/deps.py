"""
依賴注入模組：提供 API 路由使用的共用依賴
"""
import logging
from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.db.models import User
from app.core.security import decode_access_token, TokenData

logger = logging.getLogger(__name__)

# HTTP Bearer Token 驗證
security = HTTPBearer(auto_error=False)


def get_db():
    """取得資料庫 Session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db)
) -> Optional[User]:
    """
    取得當前用戶 (可選)
    - 有 Token 且有效：回傳用戶
    - 無 Token 或無效：回傳 None
    """
    if not credentials:
        return None
    
    token_data = decode_access_token(credentials.credentials)
    if not token_data:
        return None

    try:
        user = db.query(User).filter(User.id == token_data.user_id).first()
        return user
    except SQLAlchemyError as e:
        logger.error("Database error in get_current_user_optional: %s", e, exc_info=True)
        return None


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db)
) -> User:
    """
    取得當前用戶 (必要)
    - 有 Token 且有效：回傳用戶
    - 無 Token 或無效：拋出 401 錯誤
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未提供認證 Token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    token_data = decode_access_token(credentials.credentials)
    if not token_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token 無效或已過期",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        user = db.query(User).filter(User.id == token_data.user_id).first()
    except SQLAlchemyError as e:
        logger.error("Database error in get_current_user: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="資料庫暫時無法連線，請稍後再試",
        ) from e

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用戶不存在",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user
