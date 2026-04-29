"""Tomato acquisition, slicing, and squeezing routes."""

import time

from fastapi import APIRouter, Depends, HTTPException

from api.models import (
    AcquireTomatoRequest,
    JuiceProperties,
    JuiceResult,
    SlicePiece,
    SliceRequest,
    SliceResult,
    SqueezeRequest,
    Tomato,
    TomatoProperties,
)
from api.logic import generate_id, generate_pieces, get_object, store_object
from api.logger import log_api_request
from api.routes.deps import get_session_id, verify_api_key

router = APIRouter(prefix="/tomato", tags=["tomato"])

ACIDITY_MAP = {
    "San Marzano": 0.9,
    "Roma": 0.7,
    "Cherry": 0.5,
    "Heirloom": 0.6,
    "Beefsteak": 0.4,
}

SUGAR_MAP = {
    "San Marzano": 0.6,
    "Roma": 0.5,
    "Cherry": 0.8,
    "Heirloom": 0.7,
    "Beefsteak": 0.45,
}

SLICE_COUNT = {
    "fine": 16,
    "small": 12,
    "medium": 8,
    "large": 6,
    "chunk": 4,
}


@router.post("/acquire", response_model=Tomato)
async def acquire_tomato(
    body: AcquireTomatoRequest,
    api_key: str = Depends(verify_api_key),
    session_id: str = Depends(get_session_id),
):
    start = time.time()
    tomato_id = generate_id("tom_")
    acidity = round(body.ripeness * ACIDITY_MAP[body.variety], 4)
    sugar_content = round(body.ripeness * SUGAR_MAP[body.variety], 4)

    tomato = Tomato(
        id=tomato_id,
        variety=body.variety,
        ripeness=body.ripeness,
        weight=body.weight,
        type="raw",
        properties=TomatoProperties(acidity=acidity, sugar_content=sugar_content),
    )
    store_object(session_id, tomato_id, tomato.model_dump())

    resp = tomato.model_dump()
    log_api_request(
        session_id=session_id,
        endpoint="/tomato/acquire",
        method="POST",
        request_body=body.model_dump(),
        response_body=resp,
        response_status=200,
        latency_ms=int((time.time() - start) * 1000),
    )
    return resp


@router.post("/slice", response_model=SliceResult)
async def slice_tomato(
    body: SliceRequest,
    api_key: str = Depends(verify_api_key),
    session_id: str = Depends(get_session_id),
):
    start = time.time()

    total_weight = 0.0
    for tid in body.tomato_ids:
        obj = get_object(session_id, tid)
        if obj is None:
            raise HTTPException(status_code=400, detail=f"Tomato {tid} not found in session")
        total_weight += obj.get("weight", 0)

    slice_id = generate_id("slc_")
    count = SLICE_COUNT.get(body.size, 8)
    pieces_raw = generate_pieces(count, body.size, total_weight)
    pieces = [SlicePiece(**p) for p in pieces_raw]

    result = SliceResult(
        id=slice_id,
        source_tomato_ids=body.tomato_ids,
        method=body.method,
        size=body.size,
        consistency=body.consistency,
        type="sliced",
        pieces=pieces,
    )
    store_object(session_id, slice_id, result.model_dump())

    resp = result.model_dump()
    log_api_request(
        session_id=session_id,
        endpoint="/tomato/slice",
        method="POST",
        request_body=body.model_dump(),
        response_body=resp,
        response_status=200,
        latency_ms=int((time.time() - start) * 1000),
    )
    return resp


@router.post("/squeeze", response_model=JuiceResult)
async def squeeze_tomato(
    body: SqueezeRequest,
    api_key: str = Depends(verify_api_key),
    session_id: str = Depends(get_session_id),
):
    start = time.time()

    total_weight = 0.0
    total_acidity = 0.0
    count = 0
    for tid in body.tomato_ids:
        obj = get_object(session_id, tid)
        if obj is None:
            raise HTTPException(status_code=400, detail=f"Tomato {tid} not found in session")
        total_weight += obj.get("weight", 0)
        props = obj.get("properties", {})
        total_acidity += props.get("acidity", 0.5)
        count += 1

    juice_id = generate_id("jce_")
    volume = round(total_weight * body.pressure * 0.7, 3)
    concentration = round(body.pressure * 0.8 + 0.1, 4)
    avg_acidity = round(total_acidity / max(count, 1), 4)
    viscosity = round((1 - body.pressure) * 0.6 + 0.2, 4)

    result = JuiceResult(
        id=juice_id,
        volume=volume,
        concentration=concentration,
        type="juice",
        properties=JuiceProperties(acidity=avg_acidity, viscosity=viscosity),
    )
    store_object(session_id, juice_id, result.model_dump())

    resp = result.model_dump()
    log_api_request(
        session_id=session_id,
        endpoint="/tomato/squeeze",
        method="POST",
        request_body=body.model_dump(),
        response_body=resp,
        response_status=200,
        latency_ms=int((time.time() - start) * 1000),
    )
    return resp
