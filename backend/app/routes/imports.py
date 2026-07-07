from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.auth.deps import CurrentUser
from app.database import get_db
from app.schemas.imports import ImportCommitIn, ImportPreviewOut, ImportResultOut
from app.services.bank_import import (
    ConcurrentImportError,
    MultipleAccountsError,
    UnknownAccountError,
    build_preview,
    commit_import,
)
from app.services.csv_parsers import UnknownFormatError
from app.services.transactions import UnknownCategoryError

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


@router.post("/commit", status_code=status.HTTP_201_CREATED, response_model=ImportResultOut)
def commit_import_route(
    body: ImportCommitIn,
    _user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> ImportResultOut:
    try:
        return commit_import(db, body)
    except (UnknownAccountError, UnknownCategoryError) as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ConcurrentImportError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
