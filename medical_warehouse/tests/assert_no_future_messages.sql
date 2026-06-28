-- tests/assert_no_future_messages.sql
-- Must return 0 rows to pass
-- Fails if any message has a date in the future

select
    message_id,
    channel_name,
    message_date
from {{ ref('stg_telegram_messages') }}
where message_date > now()