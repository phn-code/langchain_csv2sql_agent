from pathlib import Path

from csv2sql.ingest.keys import ForeignKey, infer_keys
from csv2sql.ingest.pipeline import read_directory
from csv2sql.ingest.profile import read_table

from .conftest import SAMPLE


def test_sample_keys() -> None:
    keys = infer_keys(read_directory(SAMPLE))
    assert keys.primary == {
        "media_customer_reviews": "new_id",
        "sales_customers": "customer_id",
        "sales_franchises": "franchise_id",
        "sales_suppliers": "supplier_id",
        "sales_transactions": "transaction_id",
    }
    assert set(keys.foreign) == {
        ForeignKey("media_customer_reviews", "franchise_id", "sales_franchises", "franchise_id"),
        ForeignKey("media_gold_reviews_chunked", "franchise_id", "sales_franchises", "franchise_id"),
        ForeignKey("sales_franchises", "supplier_id", "sales_suppliers", "supplier_id"),
        ForeignKey("sales_transactions", "customer_id", "sales_customers", "customer_id", offset=1_000_000),
        ForeignKey("sales_transactions", "franchise_id", "sales_franchises", "franchise_id"),
    }
    assert keys.rejected == ()


def test_value_overlap_without_a_name_match_is_not_a_key() -> None:
    """Every customer id is also a transaction id. Values alone would link the tables; names must propose it."""
    tables = {t.name: t for t in read_directory(SAMPLE)}
    customers = set(tables["sales_customers"].values("customer_id"))
    assert customers <= set(tables["sales_transactions"].values("transaction_id"))
    keys = infer_keys(list(tables.values()))
    assert all(f.parent_table != "sales_transactions" for f in keys.foreign)


def test_unmatched_values_are_rejected_with_a_reason(tmp_path: Path) -> None:
    (tmp_path / "customers.csv").write_text("customer_id\n1\n2\n3\n")
    (tmp_path / "orders.csv").write_text("order_id,customer_id\n10,1\n11,7\n12,40\n")
    keys = infer_keys([read_table(tmp_path / "customers.csv"), read_table(tmp_path / "orders.csv")])
    assert keys.foreign == ()
    assert [r.reason for r in keys.rejected] == ["2 of 3 values have no match, even after shifting"]


def test_generic_id_primary_key_is_matched_by_entity_name(tmp_path: Path) -> None:
    (tmp_path / "categories.csv").write_text("id,label\n1,a\n2,b\n")
    (tmp_path / "products.csv").write_text("id,category_id\n1,2\n2,2\n")
    keys = infer_keys([read_table(tmp_path / "categories.csv"), read_table(tmp_path / "products.csv")])
    assert keys.foreign == (ForeignKey("products", "category_id", "categories", "id"),)
