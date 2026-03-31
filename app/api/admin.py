from fastapi import APIRouter
from pydantic import BaseModel

from app.services.elevenlabs_kb import maybe_sync_kb_for_user, sync_kb_for_user

router = APIRouter()

class KBSyncRequest(BaseModel):
    user_id: str = "admin"
    force: bool = False

@router.get("/")
async def get_admin():
    return {"message": "Admin API Placeholder"}

@router.post("/kb-sync")
async def kb_sync(payload: KBSyncRequest):
    if payload.force:
        return sync_kb_for_user(payload.user_id)
    return maybe_sync_kb_for_user(payload.user_id)
