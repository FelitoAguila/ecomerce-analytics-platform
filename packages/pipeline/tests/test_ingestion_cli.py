from pipeline import ingestion


def test_to_naive_utc_parses_offset():
    from datetime import datetime

    dt = ingestion.to_naive_utc(datetime.fromisoformat("2026-01-01T05:00:00+05:00"))
    assert dt.tzinfo is None
    assert dt.hour == 0


def test_to_naive_utc_passthrough_naive():
    from datetime import datetime

    dt = ingestion.to_naive_utc(datetime(2026, 1, 1, 10, 0, 0))
    assert dt.hour == 10


def test_primary_keys_present():
    assert "orders" in ingestion.PRIMARY_KEYS
    assert ingestion.PRIMARY_KEYS["orders"] == "order_id"
    assert ingestion.PRIMARY_KEYS["order_items"] == ("order_id", "order_item_id")
    assert ingestion.PRIMARY_KEYS["geolocation"] == "geolocation_id"
