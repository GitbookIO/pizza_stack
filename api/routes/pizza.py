"""Pizza base, assembly, and baking routes."""

import time

from fastapi import APIRouter, Depends, HTTPException

from api.models import (
    AssembleRequest,
    AssembledPizza,
    BakeRequest,
    BakedPizza,
    PizzaBase,
    PizzaBaseRequest,
    QualityMetrics,
    Sauce,
)
from api.logic import (
    compute_final_score,
    compute_sub_scores,
    generate_id,
    get_object,
    propagate_quality,
    store_object,
)
from api.logger import log_api_request
from api.routes.deps import get_session_id, verify_api_key

router = APIRouter(prefix="/pizza", tags=["pizza"])


@router.post("/base", response_model=PizzaBase)
async def create_base(
    body: PizzaBaseRequest,
    api_key: str = Depends(verify_api_key),
    session_id: str = Depends(get_session_id),
):
    start = time.time()
    base_id = generate_id("bas_")

    base = PizzaBase(
        id=base_id,
        thickness=body.thickness,
        size=body.size,
        style=body.style,
        hydration=body.hydration,
        fermentation_time=body.fermentation_time,
        flour_type=body.flour_type,
        salt_content=body.salt_content,
    )
    data = base.model_dump()
    data["type"] = "base"
    store_object(session_id, base_id, data)

    resp = base.model_dump()
    log_api_request(
        session_id=session_id,
        endpoint="/pizza/base",
        method="POST",
        request_body=body.model_dump(),
        response_body=resp,
        response_status=200,
        latency_ms=int((time.time() - start) * 1000),
    )
    return resp


@router.post("/assemble", response_model=AssembledPizza)
async def assemble_pizza(
    body: AssembleRequest,
    api_key: str = Depends(verify_api_key),
    session_id: str = Depends(get_session_id),
):
    start = time.time()

    base_obj = get_object(session_id, body.base_id)
    if base_obj is None or base_obj.get("type") != "base":
        raise HTTPException(status_code=400, detail=f"Base {body.base_id} not found or not a base")

    sauce_obj = get_object(session_id, body.sauce_id)
    if sauce_obj is None or sauce_obj.get("type") not in ("sauce",):
        raise HTTPException(status_code=400, detail=f"Sauce {body.sauce_id} not found or not a sauce")

    assembly_quality = "optimal"
    if sauce_obj.get("sauce_quality") == "degraded":
        assembly_quality = "degraded"

    pizza_id = generate_id("pza_")

    # Build PizzaBase and Sauce from stored data
    base_data = {k: v for k, v in base_obj.items() if k != "type"}
    sauce_data = {k: v for k, v in sauce_obj.items() if k != "type"}

    assembled = AssembledPizza(
        id=pizza_id,
        base=PizzaBase(**base_data),
        sauce=Sauce(**sauce_data),
        toppings=body.toppings,
        status="assembled",
        assembly_quality=assembly_quality,
    )
    data = assembled.model_dump()
    data["type"] = "assembled"
    store_object(session_id, pizza_id, data)

    resp = assembled.model_dump()
    log_api_request(
        session_id=session_id,
        endpoint="/pizza/assemble",
        method="POST",
        request_body=body.model_dump(),
        response_body=resp,
        response_status=200,
        latency_ms=int((time.time() - start) * 1000),
    )
    return resp


@router.post("/bake", response_model=BakedPizza)
async def bake_pizza(
    body: BakeRequest,
    api_key: str = Depends(verify_api_key),
    session_id: str = Depends(get_session_id),
):
    start = time.time()

    pizza_obj = get_object(session_id, body.pizza_id)
    if pizza_obj is None or pizza_obj.get("type") != "assembled":
        raise HTTPException(status_code=400, detail=f"Pizza {body.pizza_id} not found or not assembled")

    quality = pizza_obj.get("assembly_quality", "optimal")
    overall = compute_final_score(quality)
    subs = compute_sub_scores(quality)

    baked_id = generate_id("bkd_")
    baking_params = {
        "temperature": body.temperature,
        "duration": body.duration,
        "rotation_frequency": body.rotation_frequency,
        "steam_injection": body.steam_injection,
        "crust_development": body.crust_development,
    }

    baked = BakedPizza(
        id=baked_id,
        pizza_id=body.pizza_id,
        baking_parameters=baking_params,
        quality_metrics=QualityMetrics(
            overall_score=overall,
            crust_crispness=subs["crust_crispness"],
            cheese_melt=subs["cheese_melt"],
            topping_distribution=subs["topping_distribution"],
            sauce_integration=subs["sauce_integration"],
        ),
    )
    data = baked.model_dump()
    data["type"] = "baked"
    store_object(session_id, baked_id, data)

    resp = baked.model_dump()
    log_api_request(
        session_id=session_id,
        endpoint="/pizza/bake",
        method="POST",
        request_body=body.model_dump(),
        response_body=resp,
        response_status=200,
        latency_ms=int((time.time() - start) * 1000),
    )
    return resp
