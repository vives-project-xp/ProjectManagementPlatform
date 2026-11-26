"""Publish links (ADR 0010, #117): the one public route besides the health
check. Mounted only when PUBLIC_MEDIA_URL is set; Caddy forwards only
/social/<code> to it."""

import re
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse

from pmp_backend.api.deps import SessionDep, SettingsDep
from pmp_backend.errors import NotFound
from pmp_backend.services import publishing

router = APIRouter(tags=["publish links"])

_CODE = re.compile(r"^[A-Za-z0-9_-]{32,64}$")


@router.get("/social/{code}")
def linked_medium(code: str, session: SessionDep, settings: SettingsDep):
    # TikTok's URL-prefix verification file (#150), when set.
    if (
        settings.tiktok_verification_file
        and code == settings.tiktok_verification_file
        and settings.tiktok_verification_content
    ):
        return PlainTextResponse(
            settings.tiktok_verification_content,
            headers={"X-Content-Type-Options": "nosniff"},
        )
    if not _CODE.match(code):
        raise HTTPException(status_code=404, detail=publishing.NO_LINK)
    try:
        medium, path = publishing.linked_medium(
            session, settings.social_media_dir, code, datetime.now(UTC)
        )
    except NotFound as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    media_type = "image/jpeg" if medium.kind == "photo" else "video/mp4"
    return FileResponse(
        path,
        media_type=media_type,
        headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "no-store"},
    )
