-- строки без ошибок во входных данных
WITH clean_sales AS (
    SELECT
        invoice,
        customer_id,
        invoice_date,
        quantity * price AS line_revenue
    FROM
        online_retail_raw
    WHERE
        UPPER(TRIM(invoice)) NOT LIKE 'C%' AND
        quantity > 0 AND
        price > 0 AND
        invoice_date IS NOT NULL AND
        customer_id IS NOT NULL
),
-- заказы
orders AS (
    SELECT
        customer_id, -- покупатель
        invoice, -- номер заказа
        MIN(invoice_date) AS order_date, -- дата совершения
        SUM(line_revenue) AS order_revenue -- общая цена
    FROM
        clean_sales
    GROUP BY
        customer_id,
        invoice
)
-- заказы каждого покупателя
SELECT
    customer_id,
    (SELECT MAX(invoice_date)::date FROM clean_sales) - MAX(order_date)::date AS recency_days, -- число дней от последнего заказа покупателя до конца расчётного периода
    COUNT(DISTINCT invoice) AS frequency, -- количество заказов
    SUM(order_revenue) AS monetary, -- стоимость всех заказов
    MIN(order_date) AS first_purchase, -- дата первого заказа
    MAX(order_date) AS last_purchase -- дата последнего заказа
FROM
    orders
GROUP BY
    customer_id