"""PizzaStack API — TomatoPy's pizza-making API."""

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes.tomato import router as tomato_router
from api.routes.cook import router as cook_router
from api.routes.pizza import router as pizza_router
from api.routes.taste import router as taste_router
from api.routes.session import router as session_router

app = FastAPI(
    title="PizzaStack API",
    version="1.0.0",
    description="TomatoPy's pizza-making API. Virtually acquire, prepare, cook, and assemble pizzas programmatically.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(tomato_router, prefix="/v1")
app.include_router(cook_router, prefix="/v1")
app.include_router(pizza_router, prefix="/v1")
app.include_router(taste_router, prefix="/v1")
app.include_router(session_router, prefix="/v1")


DATA_DIR = os.environ.get("PIZZASTACK_DATA_DIR", "data")
os.makedirs(os.path.join(DATA_DIR, "logs"), exist_ok=True)


@app.get("/")
async def root():
    return {"name": "PizzaStack API", "version": "1.0.0", "by": "TomatoPy"}


@app.get("/health")
async def health():
    return {"status": "ok"}
