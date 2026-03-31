"""
Pytest 共用設定與 fixtures

這個檔案提供測試所需的共用設定，包括：
- 測試用的 FastAPI 客戶端
- 模擬的資料庫 session
- 測試用的認證 token
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch
import sys
from pathlib import Path

# 將專案根目錄加入 Python 路徑
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))


@pytest.fixture
def mock_db_session():
    """
    模擬資料庫 session
    
    用於測試時不需要真實資料庫連線
    """
    mock_session = MagicMock()
    return mock_session


@pytest.fixture
def test_user():
    """
    測試用的用戶資料
    """
    return {
        "id": "test_user_123",
        "email": "test@example.com",
        "name": "測試用戶",
        "is_anonymous": False
    }


@pytest.fixture
def auth_headers(test_user):
    """
    測試用的認證 headers
    
    包含有效的 JWT token
    """
    from app.core.security import create_access_token
    token = create_access_token(user_id=test_user["id"], email=test_user["email"])
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def client():
    """
    測試用的 FastAPI 客戶端
    
    注意：這會載入真實的 app，但可以搭配 mock 使用
    """
    from app.main import app
    return TestClient(app)


@pytest.fixture
def mock_llm_response():
    """
    模擬 LLM 回應
    """
    return "欸，你好啊！有什麼事嗎？"


@pytest.fixture
def mock_tts_url():
    """
    模擬 TTS 語音 URL
    """
    return "/static/audio/test_reply.mp3"
