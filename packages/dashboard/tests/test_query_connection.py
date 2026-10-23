from dashboard import query


def test_tables_uses_settings():
    t = query.tables()
    assert "fct_orders" in t
    assert "dim_customers" in t
    assert "orders_snapshot" in t
    assert "geolocation" in t
    assert "order_items" in t


def test_query_module_has_kpis():
    assert callable(query.kpis)
    assert callable(query.monthly_metrics)
    assert callable(query.status_funnel)
    assert callable(query.geo_state_centroids)


def test_kpis_sql_uses_countif():
    # inspect source to catch regressions
    src = open(query.__file__).read()
    assert "countif" in src
    assert "filter (" not in src.lower() or "countif" in src
