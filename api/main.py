import re
from collections import Counter
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from api.database import get_db, MARTS_SCHEMA
from api.schemas import (
    TopProduct, TopProductsResponse,
    DailyActivity, ChannelActivityResponse,
    MessageResult, MessageSearchResponse,
    ChannelVisualStats, VisualContentResponse,
)

app = FastAPI(
    title="Ethiopian Medical Telegram Analytics API",
    description=(
        "Analytical API exposing insights from Ethiopian medical and "
        "pharmaceutical Telegram channels — built on a dbt star schema "
        "warehouse (CheMed123, Lobelia Cosmetics, Tikvah Pharma)."
    ),
    version="1.0.0",
)

# Common stopwords to exclude from "top products" word frequency analysis
STOPWORDS = {
    "the", "and", "for", "with", "from", "this", "that", "your", "you",
    "are", "have", "has", "will", "our", "all", "can", "more", "now",
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
    "open", "until", "midnight", "infront", "school", "address", "adress",
    "delivery", "price", "pharmacy", "location", "call", "contact", "available",
    "free", "shop", "store", "ground", "floor", "plaza",
}


# ─── Endpoint 1: Top Products ───────────────────────────────────────────────────

@app.get(
    "/api/reports/top-products",
    response_model=TopProductsResponse,
    summary="Top mentioned products/terms",
    description=(
        "Returns the most frequently mentioned terms across all channel messages. "
        "Common stopwords and operational/logistics terms (delivery, hours, address) "
        "are filtered out to surface more product-relevant terms."
    ),
    tags=["Reports"],
)
def get_top_products(
    limit: int = Query(10, ge=1, le=100, description="Number of top terms to return"),
    db: Session = Depends(get_db),
):
    try:
        sql = text(f"""
            select message_text
            from {MARTS_SCHEMA}.fct_messages
            where message_text is not null and length(trim(message_text)) > 0
        """)
        rows = db.execute(sql).fetchall()

        counter = Counter()
        for (text_content,) in rows:
            words = re.findall(r"[a-zA-Z]{4,}", text_content.lower())
            for w in words:
                if w not in STOPWORDS:
                    counter[w] += 1

        top = counter.most_common(limit)

        return TopProductsResponse(
            limit=limit,
            results=[TopProduct(term=term, mentions=count) for term, count in top],
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to compute top products: {e}")


# ─── Endpoint 2: Channel Activity ───────────────────────────────────────────────

@app.get(
    "/api/channels/{channel_name}/activity",
    response_model=ChannelActivityResponse,
    summary="Channel posting activity and trends",
    description="Returns posting volume, engagement stats, and daily activity trend for a specific channel.",
    tags=["Channels"],
    responses={404: {"description": "Channel not found"}},
)
def get_channel_activity(
    channel_name: str,
    days: int = Query(30, ge=1, le=365, description="Number of recent days of daily activity to return"),
    db: Session = Depends(get_db),
):
    try:
        channel_sql = text(f"""
            select
                channel_name, channel_title, channel_type,
                total_posts, avg_views, first_post_date, last_post_date
            from {MARTS_SCHEMA}.dim_channels
            where channel_name = :channel_name
        """)
        channel_row = db.execute(channel_sql, {"channel_name": channel_name}).fetchone()

        if channel_row is None:
            raise HTTPException(
                status_code=404,
                detail=f"Channel '{channel_name}' not found. Check available channels via /api/reports/visual-content.",
            )

        daily_sql = text(f"""
            select
                d.full_date           as post_date,
                count(f.message_id)   as message_count,
                coalesce(round(avg(f.view_count), 1), 0)    as avg_views,
                coalesce(round(avg(f.forward_count), 1), 0) as avg_forwards
            from {MARTS_SCHEMA}.dim_dates d
            left join {MARTS_SCHEMA}.fct_messages f
                on d.date_key = f.date_key
               and f.channel_name = :channel_name
            where d.full_date >= (current_date - (:days || ' days')::interval)
            group by d.full_date
            order by d.full_date desc
        """)
        daily_rows = db.execute(daily_sql, {"channel_name": channel_name, "days": days}).fetchall()

        return ChannelActivityResponse(
            channel_name=channel_row.channel_name,
            channel_title=channel_row.channel_title,
            channel_type=channel_row.channel_type,
            total_posts=channel_row.total_posts,
            avg_views=float(channel_row.avg_views or 0),
            first_post_date=channel_row.first_post_date,
            last_post_date=channel_row.last_post_date,
            daily_activity=[
                DailyActivity(
                    post_date=row.post_date,
                    message_count=row.message_count,
                    avg_views=float(row.avg_views or 0),
                    avg_forwards=float(row.avg_forwards or 0),
                )
                for row in daily_rows
            ],
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch channel activity: {e}")


# ─── Endpoint 3: Message Search ─────────────────────────────────────────────────

@app.get(
    "/api/search/messages",
    response_model=MessageSearchResponse,
    summary="Search messages by keyword",
    description="Searches message text for a keyword (case-insensitive, partial match) across all channels.",
    tags=["Search"],
)
def search_messages(
    query: str = Query(..., min_length=1, description="Keyword to search for in message text"),
    limit: int = Query(20, ge=1, le=100, description="Max number of results to return"),
    channel_name: Optional[str] = Query(None, description="Optionally filter by a specific channel"),
    db: Session = Depends(get_db),
):
    try:
        sql_parts = [f"""
            select message_id, channel_name, message_text, message_date,
                   view_count, forward_count, has_image
            from {MARTS_SCHEMA}.fct_messages
            where message_text ilike :pattern
        """]
        params = {"pattern": f"%{query}%", "limit": limit}

        if channel_name:
            sql_parts.append("and channel_name = :channel_name")
            params["channel_name"] = channel_name

        sql_parts.append("order by message_date desc limit :limit")
        sql = text(" ".join(sql_parts))

        rows = db.execute(sql, params).fetchall()

        return MessageSearchResponse(
            query=query,
            limit=limit,
            result_count=len(rows),
            results=[
                MessageResult(
                    message_id=row.message_id,
                    channel_name=row.channel_name,
                    message_text=row.message_text,
                    message_date=row.message_date,
                    view_count=row.view_count,
                    forward_count=row.forward_count,
                    has_image=row.has_image,
                )
                for row in rows
            ],
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {e}")


# ─── Endpoint 4: Visual Content Stats ───────────────────────────────────────────

@app.get(
    "/api/reports/visual-content",
    response_model=VisualContentResponse,
    summary="Visual content statistics by channel",
    description="Returns image usage and YOLO-classified content category breakdown for each channel.",
    tags=["Reports"],
)
def get_visual_content_stats(db: Session = Depends(get_db)):
    try:
        sql = text(f"""
            select
                c.channel_name,
                c.total_posts,
                count(d.message_id)                                          as images_detected,
                coalesce(round(100.0 * count(d.message_id) / nullif(c.total_posts, 0), 1), 0) as pct_with_image,
                count(*) filter (where d.image_category = 'promotional')      as promotional_count,
                count(*) filter (where d.image_category = 'product_display')  as product_display_count,
                count(*) filter (where d.image_category = 'lifestyle')        as lifestyle_count,
                count(*) filter (where d.image_category = 'other')            as other_count
            from {MARTS_SCHEMA}.dim_channels c
            left join {MARTS_SCHEMA}.fct_image_detections d
                on c.channel_name = d.channel_name
            group by c.channel_name, c.total_posts
            order by pct_with_image desc
        """)
        rows = db.execute(sql).fetchall()

        return VisualContentResponse(
            channels=[
                ChannelVisualStats(
                    channel_name=row.channel_name,
                    total_posts=row.total_posts,
                    images_detected=row.images_detected,
                    pct_with_image=float(row.pct_with_image or 0),
                    promotional_count=row.promotional_count,
                    product_display_count=row.product_display_count,
                    lifestyle_count=row.lifestyle_count,
                    other_count=row.other_count,
                )
                for row in rows
            ]
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch visual content stats: {e}")


# ─── Health check ────────────────────────────────────────────────────────────────

@app.get("/health", tags=["Meta"], summary="Health check")
def health_check():
    return {"status": "ok"}


@app.get("/", tags=["Meta"], include_in_schema=False)
def root():
    return {
        "message": "Ethiopian Medical Telegram Analytics API",
        "docs": "/docs",
    }