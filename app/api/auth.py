"""
認證 API：註冊、登入、取得用戶資訊
"""
import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, field_validator
from sqlalchemy.orm import Session
from app.db.models import User, Conversation, Memory
from app.core.deps import get_db, get_current_user, get_current_user_optional
from app.core.security import (
    get_password_hash, 
    verify_password, 
    create_access_token,
    Token
)

router = APIRouter()


# ============================================
# Request/Response Models
# ============================================

class UserRegisterRequest(BaseModel):
    """註冊請求"""
    email: EmailStr
    password: str
    name: Optional[str] = None
    
    @field_validator('password')
    @classmethod
    def password_min_length(cls, v):
        if len(v) < 6:
            raise ValueError('密碼至少需要 6 個字元')
        return v


class UserLoginRequest(BaseModel):
    """登入請求"""
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    """用戶資訊回應"""
    id: str
    email: Optional[str] = None
    name: Optional[str] = None
    is_anonymous: bool
    
    class Config:
        from_attributes = True


class MergeAnonymousRequest(BaseModel):
    """合併匿名用戶資料請求"""
    anonymous_user_id: str


# ============================================
# API Endpoints
# ============================================

@router.post("/register", response_model=Token)
def register(
    request: UserRegisterRequest,
    db: Session = Depends(get_db)
):
    """
    註冊新用戶
    """
    # 檢查 Email 是否已存在
    existing_user = db.query(User).filter(User.email == request.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="此 Email 已被註冊"
        )
    
    # 建立新用戶
    user_id = f"user_{uuid.uuid4().hex[:12]}"
    user_name = request.name or request.email.split("@")[0]
    user = User(
        id=user_id,
        email=request.email,
        password_hash=get_password_hash(request.password),
        name=user_name,
        is_anonymous=False
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    
    # 自動建立 UserProfile，讓馬雲記得用戶的暱稱
    try:
        from app.services.user_profile import update_profile_field
        if user_name:
            update_profile_field(
                user_id=user_id,
                field_name="nickname",
                new_value=user_name,
                change_reason="用戶註冊時填寫的暱稱"
            )
    except Exception as e:
        print(f"[WARNING] Failed to create user profile: {e}")
    
    # 產生 Token
    access_token = create_access_token(user_id=user.id, email=user.email)
    
    return Token(access_token=access_token)


@router.post("/login", response_model=Token)
def login(
    request: UserLoginRequest,
    db: Session = Depends(get_db)
):
    """
    用戶登入
    """
    # 查找用戶
    user = db.query(User).filter(User.email == request.email).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email 或密碼錯誤"
        )
    
    # 驗證密碼
    if not user.password_hash or not verify_password(request.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email 或密碼錯誤"
        )
    
    # 產生 Token
    access_token = create_access_token(user_id=user.id, email=user.email)
    
    return Token(access_token=access_token)


@router.get("/me", response_model=UserResponse)
def get_me(
    current_user: User = Depends(get_current_user)
):
    """
    取得當前登入用戶資訊
    """
    return current_user


@router.patch("/me")
def update_me(
    request: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """更新當前用戶的暱稱"""
    new_name = request.get("name", "").strip()
    if not new_name:
        raise HTTPException(status_code=400, detail="暱稱不能為空")
    if len(new_name) > 20:
        raise HTTPException(status_code=400, detail="暱稱不能超過 20 字")
    current_user.name = new_name
    db.commit()
    db.refresh(current_user)
    return {"name": current_user.name, "message": "暱稱已更新"}


@router.post("/merge-anonymous")
def merge_anonymous_data(
    request: MergeAnonymousRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    合併匿名用戶的對話記憶到當前登入用戶
    
    使用情境：用戶先以匿名身份使用，之後註冊/登入，
    希望保留之前的對話記憶。
    """
    anonymous_user_id = request.anonymous_user_id
    
    # 檢查匿名用戶是否存在
    anonymous_user = db.query(User).filter(
        User.id == anonymous_user_id,
        User.is_anonymous == True
    ).first()
    
    if not anonymous_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="找不到指定的匿名用戶資料"
        )
    
    # 統計要合併的資料
    conversations_count = 0
    memories_count = 0
    
    # 更新 Conversations 的 user_id
    conversations = db.query(Conversation).filter(
        Conversation.user_id == anonymous_user_id
    ).all()
    
    for conv in conversations:
        conv.user_id = current_user.id
        conversations_count += 1
    
    # 更新 Memories (透過 conversation_id 關聯)
    # 注意：memories 是透過 conversation_id 關聯，不需要直接更新
    # 但我們需要統計數量
    for conv in conversations:
        memories = db.query(Memory).filter(
            Memory.conversation_id == conv.id
        ).count()
        memories_count += memories
    
    # 刪除匿名用戶 (資料已轉移)
    db.delete(anonymous_user)
    db.commit()
    
    return {
        "message": "資料合併成功",
        "merged_conversations": conversations_count,
        "merged_memories": memories_count
    }


@router.post("/anonymous", response_model=Token)
def create_anonymous_user(
    db: Session = Depends(get_db)
):
    """
    建立匿名用戶 (供前端首次使用時呼叫)
    
    回傳 Token，讓匿名用戶也能有持久的身份識別
    """
    user_id = f"anon_{uuid.uuid4().hex[:12]}"
    user = User(
        id=user_id,
        is_anonymous=True,
        name="訪客"
    )
    db.add(user)
    db.commit()
    
    access_token = create_access_token(user_id=user.id)
    
    return Token(access_token=access_token)
