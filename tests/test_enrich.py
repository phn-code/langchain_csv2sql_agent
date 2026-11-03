from pathlib import Path

from csv2sql.ingest.enrich import ColumnNote, Enrichment, Proposal, TableNote, enrich
from csv2sql.ingest.keys import ForeignKey, infer_keys
from csv2sql.ingest.pipeline import read_directory

from .scripted import ScriptedModel


def test_ai_proposals_are_kept_only_when_the_data_proves_them(tmp_path: Path) -> None:
    (tmp_path / "stores.csv").write_text("store_id,city,manager_email\n1,Paris,a@x.com\n2,Rome,b@x.com\n")
    (tmp_path / "sales.csv").write_text("sale_id,shop,amount,region\n10,1,5,1\n11,2,7,9\n")
    tables = read_directory(tmp_path)
    keys = infer_keys(tables)
    assert keys.foreign == ()  # `shop` is not named after `stores`, so the name rules cannot see it

    model = ScriptedModel(
        script=[
            Enrichment(
                tables=[
                    TableNote(
                        name="sales", description="One sale.", columns=[ColumnNote(name="shop", description="Store.")]
                    ),
                    TableNote(name="ghost", description="Not a table.", columns=[]),
                ],
                relationships=[
                    Proposal(table="sales", column="shop", parent_table="stores", parent_column="store_id"),
                    Proposal(table="sales", column="region", parent_table="stores", parent_column="store_id"),
                    Proposal(table="sales", column="amount", parent_table="stores", parent_column="city"),
                ],
            )
        ]
    )
    keys, descriptions = enrich(model, tables, keys)

    assert keys.foreign == (ForeignKey("sales", "shop", "stores", "store_id", origin="ai"),)
    assert [r.reason for r in keys.rejected] == [
        "AI suggestion rejected: values do not match",
        "AI suggestion rejected: city is not the primary key of stores",
    ]
    assert descriptions.tables == {"sales": "One sale."}
    assert descriptions.columns == {("sales", "shop"): "Store."}
    assert "a@x.com" not in model.prompts[0]  # personal data never leaves the machine
    assert '"personal_data": "email address"' in model.prompts[0]
