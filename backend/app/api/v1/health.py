from fastapi import APIRouter, Request

from app.api.response import envelope

router = APIRouter(tags=["ops"])


@router.get("/health")
def health(request: Request) -> dict:
    return envelope(request, {"status": "ok"})

