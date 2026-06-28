-- models/staging/stg_telegram_messages.sql
-- Cleans and standardizes raw.telegram_messages
-- Casts types, renames columns, filters bad records, adds calculated fields

with source as (

    select * from {{ source('raw', 'telegram_messages') }}

),

cleaned as (

    select
        -- IDs
        message_id,
        channel_name,
        channel_title,

        -- Timestamps
        cast(message_date as timestamptz)   as message_date,
        cast(scraped_at  as timestamptz)    as scraped_at,

        -- Text
        trim(message_text)                  as message_text,
        length(trim(message_text))          as message_length,

        -- Media flags
        cast(has_media as boolean)          as has_media,
        case
            when image_path is not null
             and image_path != ''
            then true
            else false
        end                                 as has_image,

        image_path,

        -- Engagement
        coalesce(cast(views    as integer), 0) as views,
        coalesce(cast(forwards as integer), 0) as forwards,

        -- Channel type classification based on channel name
        case
            when lower(channel_name) like '%chemed%'
                then 'Medical'
            when lower(channel_name) like '%lobelia%'
                then 'Cosmetics'
            when lower(channel_name) like '%tikvah%'
                then 'Pharmaceutical'
            else 'Unknown'
        end                                 as channel_type,

        -- Date parts (useful for joining to dim_dates later)
        cast(message_date as date)          as message_date_only,
        extract(year  from message_date)    as message_year,
        extract(month from message_date)    as message_month,
        extract(dow   from message_date)    as message_day_of_week

    from source

    where
        -- Remove records with no meaningful content
        message_id   is not null
        and channel_name is not null
        and (
            (message_text is not null and trim(message_text) != '')
            or has_media = true
        )
        -- Remove any future-dated messages (data quality check)
        and message_date <= now()

)

select * from cleaned