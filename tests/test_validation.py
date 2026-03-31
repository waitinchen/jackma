"""
輸入驗證單元測試

測試項目：
- EventCreateRequest 驗證
- ActionCreateRequest 驗證
- ProfileUpdateRequest 驗證
- ExtractRequest 驗證
"""
import pytest
from pydantic import ValidationError


class TestEventValidation:
    """事件輸入驗證測試"""
    
    def test_valid_event_type(self):
        """測試有效的事件類型"""
        from app.api.events import EventCreateRequest
        
        valid_types = ["mood", "activity", "plan", "health", "work", "relationship", "other"]
        
        for event_type in valid_types:
            req = EventCreateRequest(
                event_type=event_type,
                summary="測試事件"
            )
            assert req.event_type == event_type
    
    def test_invalid_event_type(self):
        """測試無效的事件類型"""
        from app.api.events import EventCreateRequest
        
        with pytest.raises(ValidationError):
            EventCreateRequest(
                event_type="invalid_type",
                summary="測試事件"
            )
    
    def test_summary_too_long(self):
        """測試摘要超過長度限制"""
        from app.api.events import EventCreateRequest
        
        with pytest.raises(ValidationError):
            EventCreateRequest(
                event_type="mood",
                summary="x" * 501  # 超過 500 字
            )
    
    def test_summary_empty(self):
        """測試空摘要"""
        from app.api.events import EventCreateRequest
        
        with pytest.raises(ValidationError):
            EventCreateRequest(
                event_type="mood",
                summary=""
            )
    
    def test_valid_date_format(self):
        """測試有效的日期格式"""
        from app.api.events import EventCreateRequest
        
        req = EventCreateRequest(
            event_type="plan",
            summary="測試事件",
            event_date="2026-02-04"
        )
        assert req.event_date == "2026-02-04"
    
    def test_invalid_date_format(self):
        """測試無效的日期格式"""
        from app.api.events import EventCreateRequest
        
        with pytest.raises(ValidationError):
            EventCreateRequest(
                event_type="plan",
                summary="測試事件",
                event_date="02-04-2026"  # 錯誤格式
            )
    
    def test_valid_time_format(self):
        """測試有效的時間格式"""
        from app.api.events import EventCreateRequest
        
        req = EventCreateRequest(
            event_type="plan",
            summary="測試事件",
            event_time="14:30"
        )
        assert req.event_time == "14:30"
    
    def test_invalid_time_format(self):
        """測試無效的時間格式"""
        from app.api.events import EventCreateRequest
        
        with pytest.raises(ValidationError):
            EventCreateRequest(
                event_type="plan",
                summary="測試事件",
                event_time="2:30 PM"  # 錯誤格式
            )


class TestActionValidation:
    """馬雲行動輸入驗證測試"""
    
    def test_valid_action_type(self):
        """測試有效的行動類型"""
        from app.api.actions import ActionCreateRequest
        
        valid_types = ["promise", "suggestion", "question", "reminder", "encouragement", "other"]
        
        for action_type in valid_types:
            req = ActionCreateRequest(
                action_type=action_type,
                summary="測試行動"
            )
            assert req.action_type == action_type
    
    def test_invalid_action_type(self):
        """測試無效的行動類型"""
        from app.api.actions import ActionCreateRequest
        
        with pytest.raises(ValidationError):
            ActionCreateRequest(
                action_type="invalid_type",
                summary="測試行動"
            )


class TestProfileValidation:
    """用戶資料輸入驗證測試"""
    
    def test_valid_field_name(self):
        """測試有效的欄位名稱"""
        from app.api.profile import ProfileUpdateRequest
        
        valid_fields = [
            "name", "nickname", "birthday", "age", "gender",
            "occupation", "company", "location", "personality",
            "interests", "preferences", "extra_info"
        ]
        
        for field in valid_fields:
            req = ProfileUpdateRequest(
                field_name=field,
                value="測試值"
            )
            assert req.field_name == field
    
    def test_invalid_field_name(self):
        """測試無效的欄位名稱"""
        from app.api.profile import ProfileUpdateRequest
        
        with pytest.raises(ValidationError):
            ProfileUpdateRequest(
                field_name="invalid_field",
                value="測試值"
            )


class TestExtractValidation:
    """資訊抽取輸入驗證測試"""
    
    def test_valid_extract_request(self):
        """測試有效的抽取請求"""
        from app.api.extract import ExtractRequest
        
        req = ExtractRequest(
            user_text="我明天要去看牙醫",
            assistant_text="好，記得準時去喔"
        )
        assert req.user_text == "我明天要去看牙醫"
    
    def test_empty_user_text(self):
        """測試空的用戶文字"""
        from app.api.extract import ExtractRequest
        
        with pytest.raises(ValidationError):
            ExtractRequest(
                user_text="",
                assistant_text="回覆"
            )
    
    def test_text_too_long(self):
        """測試文字超過長度限制"""
        from app.api.extract import ExtractRequest
        
        with pytest.raises(ValidationError):
            ExtractRequest(
                user_text="x" * 2001,  # 超過 2000 字
                assistant_text="回覆"
            )


class TestChatTextValidation:
    """文字對話輸入驗證測試"""
    
    def test_valid_chat_request(self):
        """測試有效的對話請求"""
        from app.api.turn import ChatTextRequest
        
        req = ChatTextRequest(text="你好")
        assert req.text == "你好"
    
    def test_empty_text(self):
        """測試空文字"""
        from app.api.turn import ChatTextRequest
        
        with pytest.raises(ValidationError):
            ChatTextRequest(text="")
    
    def test_text_too_long(self):
        """測試文字超過長度限制"""
        from app.api.turn import ChatTextRequest
        
        with pytest.raises(ValidationError):
            ChatTextRequest(text="x" * 2001)
