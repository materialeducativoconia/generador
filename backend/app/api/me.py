import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy import text

from app.api.deps import current_user_id
from app.errors import ApiError

router = APIRouter()

PROFILE_WITH_USAGE = text(
    """
    select p.id, p.email, p.display_name, p.avatar_url, p.daily_lesson_quota, p.is_active,
           (select count(*) from public.generation_jobs j
             where j.user_id = p.id
               and j.kind in ('lesson', 'lesson_block')
               and j.created_at >= date_trunc('day', now() at time zone 'utc') at time zone 'utc') as used_today
      from public.profiles p
     where p.id = :user_id
    """
)


@router.get("/api/me")
async def get_me(request: Request, user_id: Annotated[uuid.UUID, Depends(current_user_id)]) -> dict:
    async with request.app.state.engine.connect() as conn:
        row = (await conn.execute(PROFILE_WITH_USAGE, {"user_id": user_id})).mappings().one_or_none()
    if row is None or not row["is_active"]:
        raise ApiError(403, "forbidden", "Esta cuenta no está activa.")
    used = row["used_today"]
    return {
        "id": str(row["id"]),
        "email": row["email"],
        "display_name": row["display_name"],
        "avatar_url": row["avatar_url"],
        "quota": {
            "daily_lessons": row["daily_lesson_quota"],
            "used_today": used,
            "remaining_today": max(row["daily_lesson_quota"] - used, 0),
        },
    }
