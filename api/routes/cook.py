"""Cooking routes: simmer and roast."""

import time

from fastapi import APIRouter, Depends, HTTPException

from api.models import (
    Ingredient,
    RoastRequest,
    Sauce,
    SauceProperties,
    SimmerRequest,
)
from api.logic import (
    generate_id,
    get_object,
    resolve_ingredient_quality,
    store_object,
)
from api.logger import log_api_request
from api.routes.deps import get_session_id, verify_api_key

router = APIRouter(prefix="/cook", tags=["cook"])


@router.post("/simmer", response_model=Sauce)
async def simmer(
    body: SimmerRequest,
    api_key: str = Depends(verify_api_key),
    session_id: str = Depends(get_session_id),
):
    start = time.time()

    sauce_quality = "optimal"
    degradation_reason = None

    for ing in body.ingredients:
        quality = resolve_ingredient_quality(ing.id, session_id)
        if quality == "degraded":
            sauce_quality = "degraded"
            degradation_reason = "raw_ingredient"
            break

    sauce_id = generate_id("sce_")
    total_volume = sum(ing.amount for ing in body.ingredients)
    consistency = "smooth" if sauce_quality == "optimal" else "grainy"

    sauce = Sauce(
        id=sauce_id,
        name="tomato_sauce",
        sauce_quality=sauce_quality,
        degradation_reason=degradation_reason,
        ingredients=body.ingredients,
        temperature=body.temperature,
        duration=body.duration,
        properties=SauceProperties(consistency=consistency, volume=round(total_volume, 2)),
    )
    data = sauce.model_dump()
    data["type"] = "sauce"
    store_object(session_id, sauce_id, data)

    resp = sauce.model_dump()
    log_api_request(
        session_id=session_id,
        endpoint="/cook/simmer",
        method="POST",
        request_body=body.model_dump(),
        response_body=resp,
        response_status=200,
        latency_ms=int((time.time() - start) * 1000),
    )
    return resp


@router.post("/roast")
async def roast(
    body: RoastRequest,
    api_key: str = Depends(verify_api_key),
    session_id: str = Depends(get_session_id),
):
    start = time.time()

    roasted_id = generate_id("rst_")
    result = {
        "id": roasted_id,
        "type": "roasted",
        "ingredients": [ing.model_dump() for ing in body.ingredients],
        "temperature": body.temperature,
        "duration": body.duration,
        "turning_frequency": body.turning_frequency,
    }
    store_object(session_id, roasted_id, result)

    log_api_request(
        session_id=session_id,
        endpoint="/cook/roast",
        method="POST",
        request_body=body.model_dump(),
        response_body=result,
        response_status=200,
        latency_ms=int((time.time() - start) * 1000),
    )
    return result
