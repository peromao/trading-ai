"""Domain models shared across the trading AI application."""

from __future__ import annotations

from pydantic import BaseModel, Field


class Order(BaseModel):
    ticker: str
    qty: int
    price: float = Field(..., ge=0.0)


class AiDecision(BaseModel):
    daily_summary: str
    orders: list[Order]
    explanation: str


class WeeklyResearch(BaseModel):
    research: str
    orders: list[Order]
