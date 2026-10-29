-- проверка качества данных
SELECT
    -- количества строк
    COUNT(*) AS rows_total, -- общее
    COUNT(*) FILTER (WHERE customer_id IS NULL) AS missing_customer_id, -- с пропущенным покупателем
    COUNT(*) FILTER (WHERE quantity <= 0) AS nonpositive_quantity, -- с неположительным количеством товара
    COUNT(*) FILTER (WHERE price <= 0) AS nonpositive_price, -- с неположительной ценой
    COUNT(*) FILTER (WHERE UPPER(invoice) LIKE 'C%') AS cancellation_rows, -- отмена транзакции
    COUNT(*) FILTER (WHERE invoice_date IS NULL) AS missing_invoice_date -- с пропущенной датой транзакции
FROM
    online_retail_raw