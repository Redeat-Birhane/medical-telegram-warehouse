-- models/marts/dim_dates.sql
-- Date dimension generated from the range of dates in the data

with date_spine as (

    select
        generate_series(
            (select min(cast(message_date as date)) from {{ ref('stg_telegram_messages') }}),
            (select max(cast(message_date as date)) from {{ ref('stg_telegram_messages') }}),
            interval '1 day'
        )::date as full_date

),

enriched as (

    select
        full_date,

        -- Keys and parts
        to_char(full_date, 'YYYYMMDD')::integer         as date_key,
        extract(dow   from full_date)::integer          as day_of_week,
        to_char(full_date, 'Day')                       as day_name,
        extract(week  from full_date)::integer          as week_of_year,
        extract(month from full_date)::integer          as month,
        to_char(full_date, 'Month')                     as month_name,
        extract(quarter from full_date)::integer        as quarter,
        extract(year  from full_date)::integer          as year,

        -- Weekend flag (0=Sunday, 6=Saturday)
        case
            when extract(dow from full_date) in (0, 6)
            then true
            else false
        end                                             as is_weekend

    from date_spine

)

select * from enriched
order by full_date