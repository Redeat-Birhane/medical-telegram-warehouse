-- tests/assert_positive_views.sql
-- Must return 0 rows to pass
-- Fails if any message has a negative view count

select
    message_id,
    channel_name,
    views
from {{ ref('stg_telegram_messages') }}
where views < 0