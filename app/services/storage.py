"""
Cloud Storage 服務
上傳圖片到 GCP Cloud Storage
"""
import uuid
from datetime import datetime
from typing import Optional, Tuple
from google.cloud import storage
from app.core.config import settings


# Bucket 名稱
BUCKET_NAME = "jackma-images"

# 支援的圖片格式
SUPPORTED_EXTENSIONS = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/gif": "gif",
    "image/webp": "webp",
    "image/heic": "heic",
    "image/heif": "heif",
}


def get_storage_client():
    """取得 Storage Client"""
    return storage.Client()


async def upload_image(
    image_data: bytes,
    mime_type: str = "image/jpeg",
    user_id: Optional[str] = None
) -> Tuple[bool, str]:
    """
    上傳圖片到 Cloud Storage
    
    Args:
        image_data: 圖片的二進位資料
        mime_type: 圖片的 MIME 類型
        user_id: 用戶 ID（用於組織檔案路徑）
    
    Returns:
        (success, url_or_error) - 是否成功和圖片 URL 或錯誤訊息
    """
    try:
        # 取得副檔名
        extension = SUPPORTED_EXTENSIONS.get(mime_type, "jpg")
        
        # 產生唯一檔名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_id = uuid.uuid4().hex[:8]
        
        # 檔案路徑：images/{user_id}/{timestamp}_{unique_id}.{ext}
        if user_id:
            blob_name = f"images/{user_id}/{timestamp}_{unique_id}.{extension}"
        else:
            blob_name = f"images/anonymous/{timestamp}_{unique_id}.{extension}"
        
        # 上傳到 Cloud Storage
        client = get_storage_client()
        bucket = client.bucket(BUCKET_NAME)
        blob = bucket.blob(blob_name)
        
        # 設定 Content-Type
        blob.content_type = mime_type
        
        # 上傳
        blob.upload_from_string(image_data, content_type=mime_type)
        
        # 產生公開 URL
        public_url = f"https://storage.googleapis.com/{BUCKET_NAME}/{blob_name}"
        
        print(f"[INFO] Image uploaded: {public_url}")
        return True, public_url
        
    except Exception as e:
        print(f"[ERROR] Failed to upload image: {e}")
        return False, str(e)


def get_public_url(blob_name: str) -> str:
    """取得圖片的公開 URL"""
    return f"https://storage.googleapis.com/{BUCKET_NAME}/{blob_name}"
