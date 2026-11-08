"""FastAPI 入口 — Phase 2。

已实现：公开 API（/api/topics/rank、/api/topics/{slug}、/api/companies/{code}、
/api/institutions、/api/reports、/api/reports/{id}、/api/search）+
管理 API（/api/admin/*，全部 require_admin）+ SSE /api/tasks/{id}/stream。
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from .db import engine
from .models import Base
from .routers import admin, public


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="热门题材研究站", version="0.2.0-phase2", lifespan=lifespan)
app.include_router(public.router)
app.include_router(admin.router)


@app.get("/health")
def health():
    return {"ok": True}
