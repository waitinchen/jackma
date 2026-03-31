"""
對話 API 單元測試

測試項目：
- 對話上下文載入
- 對話處理流程
- API 端點回應
"""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from dataclasses import dataclass


class TestConversationContext:
    """對話上下文測試"""
    
    def test_context_dataclass(self):
        """測試 ConversationContext 資料類別"""
        from app.api.turn import ConversationContext
        
        context = ConversationContext(
            memories=["記憶1", "記憶2"],
            user_profile_context="用戶資料",
            user_events_context="用戶事件",
            jackma_actions_context="馬雲行動",
            proactive_care_context="主動關心",
            conversation_history=[{"role": "user", "content": "你好"}]
        )
        
        assert len(context.memories) == 2
        assert context.user_profile_context == "用戶資料"
    
    def test_result_dataclass(self):
        """測試 ConversationResult 資料類別"""
        from app.api.turn import ConversationResult
        
        result = ConversationResult(
            user_text="你好",
            assistant_text="欸，你好啊！",
            assistant_audio_url="/static/audio/test.mp3",
            memories_used=["記憶1"]
        )
        
        assert result.user_text == "你好"
        assert result.assistant_text == "欸，你好啊！"


class TestHelperFunctions:
    """輔助函數測試"""
    
    def test_get_or_create_conversation_id_fallback(self):
        """測試對話 ID 建立的 fallback 機制"""
        from app.api.turn import get_or_create_conversation_id
        
        with patch('app.api.turn.SessionLocal') as mock_session:
            # 模擬資料庫錯誤
            mock_session.side_effect = Exception("DB Error")
            
            result = get_or_create_conversation_id("test_user")
            
            # 應該返回 fallback ID
            assert result == "conv_test_user"
    
    def test_get_recent_conversation_history_empty(self):
        """測試空對話歷史"""
        from app.api.turn import get_recent_conversation_history
        
        with patch('app.api.turn.SessionLocal') as mock_session:
            mock_db = MagicMock()
            mock_db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []
            mock_session.return_value = mock_db
            
            result = get_recent_conversation_history("conv_test")
            
            assert result == []


class TestAPIEndpoints:
    """API 端點測試"""
    
    def test_health_check(self, client):
        """測試健康檢查端點"""
        response = client.get("/api/health")
        
        assert response.status_code == 200
        data = response.json()
        assert "llm" in data
        assert "tts" in data
    
    def test_conversation_history_without_auth(self, client):
        """測試未登入時取得對話歷史"""
        response = client.get("/api/conversation/history")
        
        # 應該返回 401 未授權
        assert response.status_code == 401
    
    def test_chat_text_without_auth(self, client):
        """測試未登入時發送文字對話"""
        response = client.post("/api/chat_text", json={
            "text": "你好"
        })
        
        # 應該返回 401 未授權
        assert response.status_code == 401
    
    def test_chat_text_empty_text(self, client, auth_headers):
        """測試空文字對話"""
        response = client.post(
            "/api/chat_text",
            json={"text": ""},
            headers=auth_headers
        )
        
        # 應該返回驗證錯誤
        assert response.status_code == 422


class TestElevenLabsEndpoints:
    """ElevenLabs 相關端點測試"""
    
    def test_elevenlabs_token_without_auth(self, client):
        """測試未登入時取得 token"""
        response = client.get("/api/elevenlabs/token")
        
        assert response.status_code == 401
    
    def test_elevenlabs_signed_url_without_auth(self, client):
        """測試未登入時取得 signed URL"""
        response = client.get("/api/elevenlabs/signed-url")
        
        assert response.status_code == 401
    
    def test_user_context_without_auth(self, client):
        """測試未登入時取得用戶 context"""
        response = client.get("/api/elevenlabs/user-context")
        
        assert response.status_code == 401
