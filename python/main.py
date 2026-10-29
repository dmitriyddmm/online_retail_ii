import pandas as pd


DATA_PATH = ''
OUTPUT_DIR = 'info'


def load_and_clean_data(file_path) -> pd.DataFrame:
    """ Загружает данные из исходного датасета и возвращает датасет только со строками для расчётов """

    sheets = pd.read_excel(file_path, sheet_name=None)
    df = pd.concat(sheets.values(), ignore_index=True)
    df.columns = [str(column).strip().lower().replace(' ', '_') for column in df.columns]

    df['invoice'] = df['invoice'].astype('string').str.strip()
    df['invoice_date'] = pd.to_datetime(df['invoicedate'], errors='coerce')
    df['customer_id'] = pd.to_numeric(df['customer_id'], errors='coerce')
    df['quantity'] = pd.to_numeric(df['quantity'], errors='coerce')
    df['price'] = pd.to_numeric(df['price'], errors='coerce')
    df['line_revenue'] = df['quantity'] * df['price']
    df['is_cancelled'] = df['invoice'].str.upper().str.startswith('C', na=False)

    # исключить отменённые заказы, неположительные количества/цены и пустые даты
    sales = df.loc[
        (~df['is_cancelled'])
        & (df['quantity'] > 0)
        & (df['price'] > 0)
        & df['invoice_date'].notna()
    ].copy()
    sales['month'] = sales['invoice_date'].dt.to_period('M').astype(str)
    return sales


def calculate_monthly_kpis(sales: pd.DataFrame) -> pd.DataFrame:
    """ Рассчитывает показатели по месяцам """
    monthly = sales.groupby('month', as_index=False).agg(
        revenue=('line_revenue', 'sum'),  # выручка
        orders=('invoice', 'nunique'),  # количество заказов
        customers=('customer_id', 'nunique'),  # количество покупателей
        items_sold=('quantity', 'sum'),  # количество единиц товаров
    )
    monthly['avg_order_value'] = monthly['revenue'] / monthly['orders']  # средний чек
    return monthly


def calculate_customer_metrics(sales: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """ Рассчитывает показатели по покупателям """
    identified = sales.dropna(subset=['customer_id']).copy()
    orders = identified.groupby(['customer_id', 'invoice'], as_index=False).agg(
        order_date=('invoice_date', 'min'),  # дата совершения заказа
        order_revenue=('line_revenue', 'sum'),  # стоимость всего заказа
    )

    customer = orders.groupby('customer_id', as_index=False).agg(
        orders=('invoice', 'nunique'),  # количество заказов
        revenue=('order_revenue', 'sum'),  # общая выручка
        first_purchase=('order_date', 'min'),  # дата первой покупки
        last_purchase=('order_date', 'max'),  # дата последней покупки
    )

    snapshot_date = sales['invoice_date'].max().normalize()
    customer['recency_days'] = (
        snapshot_date - customer['last_purchase'].dt.normalize()
    ).dt.days  # количество прошедших дней с последней покупки
    customer['avg_order_value'] = customer['revenue'] / customer['orders']  # средний чек
    return orders, customer


def calculate_cohort_retention(orders: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Рассчитывает удержание по когортам и размеры когорт
    Когорта - пользователи с одинаковым месяцем первой покупки
    Удержание за месяц - доля покупателей когорты, совершивших покупку в данном месяце
    """
    cohort_orders = orders.copy()
    cohort_orders['month'] = cohort_orders['order_date'].dt.to_period('M')
    first_purchase_month = (
        cohort_orders.groupby('customer_id')['month'].min().rename('cohort_month')
    )
    cohort_orders = cohort_orders.join(first_purchase_month, on='customer_id')
    cohort_orders['cohort_index'] = (
        (cohort_orders['month'].dt.year - cohort_orders['cohort_month'].dt.year) * 12
        + cohort_orders['month'].dt.month
        - cohort_orders['cohort_month'].dt.month
    )  # номера когорт

    counts = (
        cohort_orders.groupby(['cohort_month', 'cohort_index'])['customer_id']
        .nunique()
        .rename('active_customers')
        .reset_index()
    )  # размеры когорт для каждого месяца (по месяцам и номерам)
    cohort_sizes = (
        cohort_orders.groupby('cohort_month')['customer_id']
        .nunique()
        .rename('cohort_size')
        .reset_index()
    )  # общие размеры когорт (по номерам)
    retention = counts.merge(cohort_sizes, on='cohort_month', how='left')
    retention['retention_rate'] = retention['active_customers'] / retention['cohort_size']  # удержание
    retention['cohort_month'] = retention['cohort_month'].astype(str)
    cohort_sizes['cohort_month'] = cohort_sizes['cohort_month'].astype(str)
    return retention.sort_values(['cohort_month', 'cohort_index']), cohort_sizes


def assign_rfm_segment(row: pd.Series) -> str:
    """ Разбивает покупателей на категории по RFM-оценкам """
    if row['R_score'] >= 4 and row['F_score'] >= 4 and row['M_score'] >= 4:
        return 'Самые активные сейчас'  # недавно покупали, часто покупают, дают высокую выручку
    if row['R_score'] >= 3 and row['F_score'] >= 4:
        return 'Активные сейчас'  # недавно покупали, часто покупают
    if row['R_score'] >= 4 and row['F_score'] <= 2:
        return 'Новые'  # недавно покупали, редко покупают
    if row['R_score'] <= 2 and row['F_score'] >= 3:
        return 'Активные ранее'  # давно покупали, часто покупали
    if row['R_score'] <= 2 and row['F_score'] <= 2:
        return 'Ушедшие'  # давно покупали, редко покупали
    return 'Смешанный профиль'


def calculate_rfm(customer: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """ Рассчитывает RFM-оценки и по каждой оценке делит покупателей на 5 равных категорий """
    rfm = customer[['customer_id', 'recency_days', 'orders', 'revenue']].rename(
        columns={'orders': 'frequency', 'revenue': 'monetary'}
    ).copy()

    # recency (давность) - как давно клиент совершил последнюю покупку; чем меньше, тем лучше
    rfm['R_score'] = pd.qcut(
        rfm['recency_days'].rank(method='first'),
        5,
        labels=[5, 4, 3, 2, 1],
    ).astype(int)

    # frequency (частота) - как часто клиент делает заказы; чем больше, тем лучше
    rfm['F_score'] = pd.qcut(
        rfm['frequency'].rank(method='first'),
        5,
        labels=[1, 2, 3, 4, 5],
    ).astype(int)

    # monetary (деньги) - сколько денег клиент потратил суммарно за период; чем больше, тем лучше
    rfm['M_score'] = pd.qcut(
        rfm['monetary'].rank(method='first'),
        5,
        labels=[1, 2, 3, 4, 5],
    ).astype(int)

    # ранжирование по RFM-оценкам
    rfm['segment'] = rfm.apply(assign_rfm_segment, axis=1)

    # общая информация по категориям покупателей
    segment_summary = (
        rfm.groupby('segment', as_index=False)
        .agg(
            customers=('customer_id', 'nunique'),  # количество покупателей
            revenue=('monetary', 'sum'),  # выручка
            avg_frequency=('frequency', 'mean'),  # средняя частота покупок
        )
        .sort_values('revenue', ascending=False)
    )
    return rfm, segment_summary


def calculate_country_summary(sales: pd.DataFrame) -> pd.DataFrame:
    """ Рассчитывает показатели по странам """
    summary = sales.groupby('country', as_index=False).agg(
        revenue=('line_revenue', 'sum'),  # выручка
        orders=('invoice', 'nunique'),  # количество заказов
        customers=('customer_id', 'nunique'),  # количество покупателей
        items_sold=('quantity', 'sum'),  # количество единиц товаров
    )
    total_revenue = summary['revenue'].sum()
    summary['revenue_share'] = summary['revenue'] / total_revenue
    return summary.sort_values('revenue', ascending=False)


def main():

    sales = load_and_clean_data(DATA_PATH)  # загрузить и очистить данные

    monthly = calculate_monthly_kpis(sales)
    country_summary = calculate_country_summary(sales)
    orders, customer = calculate_customer_metrics(sales)
    retention, cohort_sizes = calculate_cohort_retention(orders)
    rfm, segment_summary = calculate_rfm(customer)

    monthly.to_csv(OUTPUT_DIR + '/monthly_kpis.csv', index=False, encoding='utf-8-sig')  # показатели по месяцам: выручка, количество заказов, покупателей, единиц товаров
    customer.to_csv(OUTPUT_DIR + '/customer_summary.csv', index=False, encoding='utf-8-sig')   # показатели по покупателям: количество заказов, общая выручка, даты первой и последней покупки, дней после последней покупки, средний чек
    retention.to_csv(OUTPUT_DIR + '/cohort_retention.csv', index=False, encoding='utf-8-sig')  # удержание по когортам
    cohort_sizes.to_csv(OUTPUT_DIR + '/cohort_sizes.csv', index=False, encoding='utf-8-sig')  # размеры когорт
    rfm.to_csv(OUTPUT_DIR + '/customer_rfm.csv', index=False, encoding='utf-8-sig')  # RFM-оценки по покупателям
    segment_summary.to_csv(OUTPUT_DIR + '/rfm_segment_summary.csv', index=False, encoding='utf-8-sig')  # общие данные о категориях покупателей
    country_summary.to_csv(OUTPUT_DIR + '/country_summary.csv', index=False, encoding='utf-8-sig')  # показатели по странам: выручка, количество заказов, покупателей, единиц товаров

    # количество и доля покупателей с повторными покупками
    customer_orders = orders.groupby("customer_id")["invoice"].nunique()
    repeat_customers = customer_orders[customer_orders >= 2].index
    repeat_customers_count = len(repeat_customers)
    repeat_customers_share = repeat_customers_count / customer['customer_id'].nunique() if customer['customer_id'].nunique() > 0 else 0

    # месяц с наибольшей выручкой
    best_month = monthly.loc[monthly["revenue"].idxmax()]

    # медианное удержание в первый месяц после первой покупки
    first_month_retention = retention.loc[
        retention["cohort_index"] == 1, "retention_rate",
    ]
    median_first_month_retention = first_month_retention.median()

    # доля выручки от великобритании
    uk_revenue_share = country_summary.loc[
        country_summary["country"].str.strip().str.casefold() == "united kingdom", "revenue_share"
    ]

    print("Анализ выполнен")
    print(f"Выручка: {sales['line_revenue'].sum():.2f} £")
    print(f"Заказов: {sales['invoice'].nunique()}")
    print(f"Покупателей: {customer['customer_id'].nunique()}")
    print(f"Покупателей с повторными покупками: {repeat_customers_count}")
    print(f"Доля покупателей с повторными покупками: {repeat_customers_share:.2%}")
    print(f"Месяц с максимальной выручкой: {best_month['month']}")
    print(f"Выручка за этот месяц: {best_month['revenue']:.2f}")
    print(f"Доля выручки от Великобритании: {uk_revenue_share.iloc[0]:.2%}")
    print(f"Медианное удержание в первый месяц: {median_first_month_retention:.2%}")


if __name__ == '__main__':
    main()
