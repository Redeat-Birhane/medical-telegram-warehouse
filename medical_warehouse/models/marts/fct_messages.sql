-- models/marts/fct_messages.sql
-- Central fact table joining messages to channel and date dimensions

with messages as (

    select * from {{ ref('stg_telegram_messages') }}

),

channels as (

    select * from {{ ref('dim_channels') }}

),

dates as (

    select * from {{ ref('dim_dates') }}

),

fact as (

    select
        -- Natural key
        m.message_id,

        -- Foreign keys
        c.channel_key,
        d.date_key,

        -- Message content
        m.message_text,
        m.message_length,
        m.channel_name,
        m.message_date,

        -- Engagement metrics
        m.views         as view_count,
        m.forwards      as forward_count,

        -- Media flags
        m.has_media,
        m.has_image,
        m.image_path

    from messages m

    left join channels c
        on m.channel_name = c.channel_name

    left join dates d
        on m.message_date_only = d.full_date

)

select * from fact