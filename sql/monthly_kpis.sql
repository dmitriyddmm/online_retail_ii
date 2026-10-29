-- строки без ошибок в исходных данных
WITH clean_sales AS (
    SELECT
        invoice,
        stockcode,
        description,
        quantity,
        invoice_date,
        price,
        customer_id,
        country,
        quantity * price AS line_revenue,
        DATE_TRUNC('month', invoice_date)::date AS month
    FROM
        online_retail_raw
    WHERE
        UPPER(TRIM(invoice)) NOT LIKE 'C%' AND
        quantity > 0 AND
        price > 0 AND
        invoice_date IS NOT NULL
)
-- ежемесячные KPI
SELECT
    month, -- месяц
    SUM(line_revenue) AS revenue, -- выручка
    COUNT(DISTINCT invoice) AS orders, -- количество заказов
    SUM(quantity) AS items_sold, -- количество единиц товаров
    COUNT(DISTINCT customer_id) AS identified_customers, -- количество уникальных покупателей
    SUM(line_revenue) / NULLIF(COUNT(DISTINCT invoice), 0) AS avg_order_value -- средняя цена заказа
FROM
    clean_sales
GROUP BY
    month
ORDER BY
    month