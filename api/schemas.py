from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field


# ─── Top Products ──────────────────────────────────────────────────────────────

class TopProduct(BaseModel):
    term: str = Field(..., description="The mentioned word/term")
    mentions: int = Field(..., description="Number of times mentioned across all channels")


class TopProductsResponse(BaseModel):
    limit: int
    results: list[TopProduct]


# ─── Channel Activity ──────────────────────────────────────────────────────────

class DailyActivity(BaseModel):
    post_date: date
    message_count: int
    avg_views: float
    avg_forwards: float


class ChannelActivityResponse(BaseModel):
    channel_name: str
    channel_title: Optional[str] = None
    channel_type: Optional[str] = None
    total_posts: int
    avg_views: float
    first_post_date: Optional[datetime] = None
    last_post_date: Optional[datetime] = None
    daily_activity: list[DailyActivity]


# ─── Message Search ─────────────────────────────────────────────────────────────

class MessageResult(BaseModel):
    message_id: int
    channel_name: str
    message_text: str
    message_date: datetime
    view_count: int
    forward_count: int
    has_image: bool


class MessageSearchResponse(BaseModel):
    query: str
    limit: int
    result_count: int
    results: list[MessageResult]


# ─── Visual Content Stats ───────────────────────────────────────────────────────

class ChannelVisualStats(BaseModel):
    channel_name: str
    total_posts: int
    images_detected: int
    pct_with_image: float
    promotional_count: int
    product_display_count: int
    lifestyle_count: int
    other_count: int


class VisualContentResponse(BaseModel):
    channels: list[ChannelVisualStats]


# ─── Error Response ──────────────────────────────────────────────────────────────

class ErrorResponse(BaseModel):
    detail: str