"""Taste analysis and comparison routes."""

import random
import time

from fastapi import APIRouter, Depends, HTTPException

from api.models import AnalyzeRequest, CompareRequest
from api.logic import get_object
from api.logger import log_api_request
from api.routes.deps import get_session_id, verify_api_key

router = APIRouter(prefix="/taste", tags=["taste"])


def _taste_profile() -> dict:
    return {
        "sweetness": round(random.uniform(0.1, 0.9), 2),
        "acidity": round(random.uniform(0.1, 0.9), 2),
        "umami": round(random.uniform(0.2, 0.95), 2),
        "saltiness": round(random.uniform(0.1, 0.7), 2),
        "bitterness": round(random.uniform(0.0, 0.3), 2),
    }


def _aroma_profile() -> dict:
    return {
        "intensity": round(random.uniform(0.3, 0.9), 2),
        "complexity": round(random.uniform(0.2, 0.8), 2),
        "notes": random.sample(
            ["smoky", "herbal", "fruity", "earthy", "spicy", "sweet", "roasted"],
            k=random.randint(2, 4),
        ),
    }


def _texture_profile() -> dict:
    return {
        "crispness": round(random.uniform(0.2, 0.95), 2),
        "chewiness": round(random.uniform(0.1, 0.8), 2),
        "moisture": round(random.uniform(0.2, 0.7), 2),
    }


@router.post("/analyze")
async def analyze(
    body: AnalyzeRequest,
    api_key: str = Depends(verify_api_key),
    session_id: str = Depends(get_session_id),
):
    start = time.time()

    obj = get_object(session_id, body.dish_id)
    if obj is None:
        raise HTTPException(status_code=400, detail=f"Dish {body.dish_id} not found in session")

    result: dict = {
        "dish_id": body.dish_id,
        "depth": body.depth or "basic",
        "taste_profile": _taste_profile(),
    }

    if body.include_aroma:
        result["aroma_profile"] = _aroma_profile()
    if body.include_texture:
        result["texture_profile"] = _texture_profile()

    log_api_request(
        session_id=session_id,
        endpoint="/taste/analyze",
        method="POST",
        request_body=body.model_dump(),
        response_body=result,
        response_status=200,
        latency_ms=int((time.time() - start) * 1000),
    )
    return result


@router.post("/compare")
async def compare(
    body: CompareRequest,
    api_key: str = Depends(verify_api_key),
    session_id: str = Depends(get_session_id),
):
    start = time.time()

    for did in body.dish_ids:
        obj = get_object(session_id, did)
        if obj is None:
            raise HTTPException(status_code=400, detail=f"Dish {did} not found in session")

    comparisons = []
    for did in body.dish_ids:
        entry = {"dish_id": did}
        for metric in body.metrics:
            if metric == "overall_score":
                entry[metric] = round(random.uniform(0.3, 0.98), 2)
            else:
                entry[metric] = round(random.uniform(0.1, 0.9), 2)
        comparisons.append(entry)

    result = {
        "dish_ids": body.dish_ids,
        "metrics": body.metrics,
        "comparisons": comparisons,
    }

    log_api_request(
        session_id=session_id,
        endpoint="/taste/compare",
        method="POST",
        request_body=body.model_dump(),
        response_body=result,
        response_status=200,
        latency_ms=int((time.time() - start) * 1000),
    )
    return result
