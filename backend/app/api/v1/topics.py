from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.security import CurrentUser, get_current_user
from app.db.session import get_db
from app.repositories.document_repo import DocumentRepository
from app.repositories.knowledge_repo import KnowledgeRepository
from app.schemas.topics import SubjectListResponse, TopicListResponse
from app.services.classification.topic_mapper import SUBJECT_CATALOG

router = APIRouter(tags=["topics"])


def _assert_owned_document(db: Session, *, document_id: UUID, user_id: UUID) -> None:
    doc = DocumentRepository(db).get_by_id(document_id)
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    if doc.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this document",
        )


@router.get("/documents/{document_id}/topics", response_model=TopicListResponse)
def list_document_topics(
    document_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TopicListResponse:
    """List detected topics for an owned document with counts and source pages."""
    _assert_owned_document(db, document_id=document_id, user_id=current_user.id)
    items = KnowledgeRepository(db).list_topics_for_document(document_id)
    return TopicListResponse(items=items, total=len(items))


@router.get("/topics", response_model=TopicListResponse)
def list_topics(
    subject_code: str | None = Query(default=None),
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TopicListResponse:
    """List canonical and user-discovered topics, optionally filtered by subject."""
    items = KnowledgeRepository(db).list_topics_for_user(
        current_user.id, subject_code=subject_code
    )
    return TopicListResponse(items=items, total=len(items))


@router.get("/subjects", response_model=SubjectListResponse)
def list_subjects(
    _: CurrentUser = Depends(get_current_user),
) -> SubjectListResponse:
    """List configured subjects and supported solving strategy capabilities."""
    return SubjectListResponse(items=list(SUBJECT_CATALOG))
