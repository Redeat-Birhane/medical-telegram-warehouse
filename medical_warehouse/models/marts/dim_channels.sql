-- models/marts/dim_channels.sql
-- Channel dimension — one row per unique channel

with channel_stats as (

    select
        channel_name,
        channel_title,
        channel_type,

        min(message_date)   as first_post_date,
        max(message_date)   as last_post_date,
        count(*)            as total_posts,
        avg(views)          as avg_views,
        sum(case when has_image then 1 else 0 end) as total_images

    from {{ ref('stg_telegram_messages') }}
    group by channel_name, channel_title, channel_type

)

select
    -- Surrogate key
    row_number() over (order by channel_name) as channel_key,

    channel_name,
    channel_title,
    channel_type,
    first_post_date,
    last_post_date,
    total_posts,
    round(cast(avg_views as numeric), 2)      as avg_views,
    total_images

from channel_stats