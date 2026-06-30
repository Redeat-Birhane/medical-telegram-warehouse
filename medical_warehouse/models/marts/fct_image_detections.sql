with detections as (

    select * from {{ ref('stg_yolo_detections') }}

),

messages as (

    select * from {{ ref('fct_messages') }}

),

joined as (

    select
        d.message_id,
        m.channel_key,
        m.date_key,

        d.channel_name,
        d.image_path,
        d.detected_objects,
        d.object_count,
        d.avg_confidence,
        d.image_category,
        d.processed_at,

        -- Bring engagement metrics along for analysis
        m.view_count,
        m.forward_count

    from detections d

    inner join messages m
        on d.message_id = m.message_id
       and d.channel_name = m.channel_name

)

select * from joined