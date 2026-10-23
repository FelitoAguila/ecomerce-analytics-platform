from ecommerce_db.helpers import seed_helpers


def test_schema_sql_loaded():
    # schema.sql is loaded from helpers package; ensure file exists and has tables
    from pathlib import Path

    sql_path = Path(seed_helpers.__file__).parent / "schema.sql"
    sql = sql_path.read_text()
    assert "CREATE TABLE" in sql
    assert "orders" in sql


def test_iter_csv_text_strips_utf8_bom():
    content = "product_category_name\tproduct_category_name_english\nbebes\tbaby\n".encode("utf-8-sig")

    class DummyBody:
        def __init__(self, data):
            self.data = data
            self.pos = 0

        def read(self, amt=8192):
            chunk = self.data[self.pos : self.pos + amt]
            self.pos += amt
            return chunk

    class DummyS3:
        def __init__(self, body):
            self.body = body

        def get_object(self, Bucket=None, Key=None):
            return {"Body": self.body}

    text = seed_helpers.iter_csv_text(DummyS3(DummyBody(content)), "b", "k")
    result = "".join(text)
    assert result.startswith("product_category_name")
    assert "baby" in result


def test_iter_csv_text_multibyte_split():
    content = "col1\tcol2\nhéllo\tworld\n".encode("utf-8")

    class DummyBody:
        def __init__(self, data):
            self.data = data
            self.pos = 0

        def read(self, amt=1):
            if self.pos >= len(self.data):
                return b""
            chunk = self.data[self.pos : self.pos + amt]
            self.pos += amt
            return chunk

    class DummyS3:
        def __init__(self, body):
            self.body = body

        def get_object(self, Bucket=None, Key=None):
            return {"Body": self.body}

    result = "".join(seed_helpers.iter_csv_text(DummyS3(DummyBody(content)), "b", "k"))
    assert "héllo" in result
