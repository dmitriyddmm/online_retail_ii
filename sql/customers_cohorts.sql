-- строки без ошибок во входных данных
WITH clean_sales AS (
    SELECT
        invoice,
        customer_id,
        invoice_date
    FROM
        online_retail_raw
    WHERE
        UPPER(TRIM(invoice)) NOT LIKE 'C%' AND
        quantity > 0 AND
        price > 0 AND
        invoice_date IS NOT NULL AND
        customer_id IS NOT NULL
),
-- месяцы совершения заказов
customer_months AS (
    SELECT DISTINCT
        customer_id,
        DATE_TRUNC('month', invoice_date)::date AS order_month
    FROM
        clean_sales
),
-- когорты покупателей (по месяцу совершения первой покупки)
cohorts AS (
    SELECT
        customer_id,
        MIN(order_month) AS cohort_month
    FROM
        customer_months
    GROUP BY
        customer_id
),
activity AS (
    SELECT
        cm.customer_id, -- покупатель
        cm.order_month, -- месяц совершения текущей покупок
        c.cohort_month, -- месяц совершения первой покупки
        (EXTRACT(YEAR FROM cm.order_month) - EXTRACT(YEAR FROM c.cohort_month)) * 12
            + EXTRACT(MONTH FROM cm.order_month)
            - EXTRACT(MONTH FROM c.cohort_month) AS cohort_index
            -- номер когорты, к которой относится покупатель + месяц относительно первой покупки
    FROM
        customer_months cm
        JOIN
            cohorts c
        USING (customer_id)
)
-- количество покупателей каждой когорты для каждого месяца
SELECT
    cohort_month,
    cohort_index,
    COUNT(DISTINCT customer_id) AS active_customers
FROM
    activity
GROUP BY
    cohort_month,
    cohort_index
ORDER BY
    cohort_month,
    cohort_index