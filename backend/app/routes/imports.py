from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.auth.deps import CurrentUser
from app.database import get_db
from app.schemas.imports import ImportPreviewOut
from app.services.bank_import import MultipleAccountsError, build_preview
from app.services.csv_parsers import UnknownFormatError

router = APIRouter(prefix="/api/imports", tags=["imports"])


@router.post("/preview", response_model=ImportPreviewOut)
async def preview_import_route(
    _user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    file: Annotated[UploadFile, File()],
) -> ImportPreviewOut:
    content = await file.read()
    try:
        return build_preview(db, file.filename or "upload.csv", content)
    except (UnknownFormatError, MultipleAccountsError) as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
