from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import (
    attempts,
    auth,
    dashboard,
    documents,
    exam_configs,
    health,
    jobs,
    knowledge,
    notes,
    performance,
    questions,
    tests,
    topics,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(dashboard.router)
api_router.include_router(documents.router)
api_router.include_router(jobs.router)
api_router.include_router(knowledge.router)
api_router.include_router(topics.router)
api_router.include_router(notes.router)
api_router.include_router(questions.router)
api_router.include_router(tests.router)
api_router.include_router(attempts.router)
api_router.include_router(performance.router)
api_router.include_router(exam_configs.router)
