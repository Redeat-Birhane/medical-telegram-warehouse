with source as (

    select * from {{ source('raw', 'yolo_detections') }}

),

cleaned as (

    select
        message_id,
        channel_name,
        image_path,

        trim(detected_objects)              as detected_objects,
        coalesce(object_count, 0)           as object_count,
        coalesce(avg_confidence, 0)         as avg_confidence,

        case
            when image_category in (
                'promotional', 'product_display', 'lifestyle', 'other'
            )
            then image_category
            else 'other'
        end                                  as image_category,

        cast(processed_at as timestamptz)   as processed_at

    from source

    where message_id is not null
      and channel_name is not null

)

select * from cleaned