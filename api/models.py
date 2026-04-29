"""Pydantic v2 models for the PizzaStack API."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


# --- Enums as Literal unions ---

TomatoVariety = Literal["San Marzano", "Roma", "Cherry", "Heirloom", "Beefsteak"]
SliceMethod = Literal["dice", "slice", "chop", "mince", "julienne"]
SliceSize = Literal["fine", "small", "medium", "large", "chunk"]
SliceConsistency = Literal["uniform", "rough", "fine", "coarse"]
StirringFrequency = Literal["constant", "frequent", "occasional", "rare"]
SauceQuality = Literal["optimal", "degraded"]
PizzaThickness = Literal["thin", "medium", "thick", "deep"]
PizzaSize = Literal[
    "8inch", "10inch", "12inch", "14inch", "16inch", "18inch"
]
PizzaStyle = Literal["neapolitan", "new_york", "chicago", "sicilian", "detroit"]
ToppingDistribution = Literal["even", "center", "edges", "random"]
CrustDevelopment = Literal["low", "medium", "high"]
AnalysisDepth = Literal["basic", "comprehensive"]
CompareMetric = Literal["sweetness", "acidity", "umami", "overall_score"]
AssemblyQuality = Literal["optimal", "degraded"]


# --- Tomato ---


class TomatoProperties(BaseModel):
    acidity: float
    sugar_content: float


class Tomato(BaseModel):
    id: str
    variety: TomatoVariety
    ripeness: float = Field(ge=0, le=1)
    weight: float
    type: Literal["raw"] = "raw"
    properties: TomatoProperties


class AcquireTomatoRequest(BaseModel):
    variety: TomatoVariety
    ripeness: float = Field(ge=0, le=1)
    weight: float


# --- Slice ---


class SliceRequest(BaseModel):
    tomato_ids: list[str]
    method: SliceMethod
    size: SliceSize
    consistency: SliceConsistency


class SlicePiece(BaseModel):
    id: str
    size: str
    weight: float


class SliceResult(BaseModel):
    id: str
    source_tomato_ids: list[str]
    method: SliceMethod
    size: SliceSize
    consistency: SliceConsistency
    type: Literal["sliced"] = "sliced"
    pieces: list[SlicePiece]


# --- Squeeze / Juice ---


class SqueezeRequest(BaseModel):
    tomato_ids: list[str]
    pressure: float = Field(ge=0, le=1)


class JuiceProperties(BaseModel):
    acidity: float
    viscosity: float


class JuiceResult(BaseModel):
    id: str
    volume: float
    concentration: float
    type: Literal["juice"] = "juice"
    properties: JuiceProperties


# --- Cooking ---


class Ingredient(BaseModel):
    id: str
    name: str
    amount: float
    unit: str


class SimmerRequest(BaseModel):
    ingredients: list[Ingredient]
    temperature: float
    duration: str
    stirring_frequency: Optional[StirringFrequency] = None


class RoastRequest(BaseModel):
    ingredients: list[Ingredient]
    temperature: float
    duration: str
    turning_frequency: Optional[str] = None


class SauceProperties(BaseModel):
    consistency: str
    volume: float


class Sauce(BaseModel):
    id: str
    name: str
    sauce_quality: SauceQuality
    degradation_reason: Optional[str] = None
    ingredients: list[Ingredient]
    temperature: float
    duration: str
    properties: SauceProperties


# --- Pizza Base ---


class PizzaBaseRequest(BaseModel):
    thickness: PizzaThickness
    size: PizzaSize
    style: PizzaStyle
    hydration: Optional[float] = None
    fermentation_time: Optional[str] = None
    flour_type: Optional[str] = None
    salt_content: Optional[float] = None


class PizzaBase(BaseModel):
    id: str
    thickness: PizzaThickness
    size: PizzaSize
    style: PizzaStyle
    hydration: Optional[float] = None
    fermentation_time: Optional[str] = None
    flour_type: Optional[str] = None
    salt_content: Optional[float] = None


# --- Assembly ---


class Topping(BaseModel):
    name: str
    amount: float
    unit: str
    distribution: ToppingDistribution


class AssembleRequest(BaseModel):
    base_id: str
    sauce_id: str
    toppings: list[Topping]


class AssembledPizza(BaseModel):
    id: str
    base: PizzaBase
    sauce: Sauce
    toppings: list[Topping]
    status: Literal["assembled"] = "assembled"
    assembly_quality: AssemblyQuality


# --- Bake ---


class BakeRequest(BaseModel):
    pizza_id: str
    temperature: float
    duration: str
    rotation_frequency: Optional[str] = None
    steam_injection: Optional[bool] = None
    crust_development: Optional[CrustDevelopment] = None


class QualityMetrics(BaseModel):
    overall_score: float
    crust_crispness: float
    cheese_melt: float
    topping_distribution: float
    sauce_integration: float


class BakedPizza(BaseModel):
    id: str
    pizza_id: str
    baking_parameters: dict
    quality_metrics: QualityMetrics


# --- Analysis ---


class AnalyzeRequest(BaseModel):
    dish_id: str
    depth: Optional[AnalysisDepth] = None
    include_aroma: Optional[bool] = None
    include_texture: Optional[bool] = None


class CompareRequest(BaseModel):
    dish_ids: list[str]
    metrics: list[CompareMetric]
