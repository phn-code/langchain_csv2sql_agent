"""Reject queries the model should rewrite, with a message it can act on.

This is not the security boundary. The reader role's privileges and the read-only transaction are. The guard
exists so the model gets a precise reason ("unknown table `customers`; available: ...") instead of a vaguer
Postgres error, and so obvious misuse never reaches the database.
"""

from collections.abc import Collection

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

_WRITES = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Merge,
    exp.Create,
    exp.Drop,
    exp.Alter,
    exp.TruncateTable,
    exp.Command,
    exp.Copy,
    exp.Into,
    exp.Lock,
    exp.Set,
    exp.Grant,
)
_DENIED_FUNCTIONS = frozenset(
    {"current_setting", "set_config", "dblink", "query_to_xml", "query_to_xml_and_xmlschema"}
)
_DENIED_PREFIXES = ("pg_", "lo_", "dblink_", "txid_")


class RejectedQuery(ValueError):
    pass


def check_query(statement: str, tables: Collection[str], schema: str = "analytics") -> str:
    """Return the statement without trailing semicolons, or raise RejectedQuery."""
    statement = statement.strip().rstrip(";").strip()
    try:
        parsed = [s for s in sqlglot.parse(statement, read="postgres") if s is not None]
    except ParseError as error:
        raise RejectedQuery(f"Could not parse the SQL: {error.errors[0]['description']}") from error
    if len(parsed) != 1:
        raise RejectedQuery(f"Write exactly one statement; found {len(parsed)}.")
    (tree,) = parsed
    if not isinstance(tree, exp.Query):
        raise RejectedQuery("Only SELECT queries are allowed.")
    if write := next(tree.find_all(*_WRITES), None):
        raise RejectedQuery(f"Only read-only SELECT queries are allowed; found {write.key.upper()}.")

    ctes = {cte.alias_or_name for cte in tree.find_all(exp.CTE)}
    for table in tree.find_all(exp.Table):
        if table.db and table.db != schema:
            raise RejectedQuery(f"Only tables in the {schema} schema are available, not `{table.db}.{table.name}`.")
        if table.name and table.name not in ctes and table.name not in tables:
            raise RejectedQuery(f"Unknown table `{table.name}`. Available tables: {', '.join(sorted(tables))}.")

    for function in tree.find_all(exp.Func):
        name = (function.sql_name() if not isinstance(function, exp.Anonymous) else function.name).lower()
        if name in _DENIED_FUNCTIONS or name.startswith(_DENIED_PREFIXES):
            raise RejectedQuery(f"The function `{name}` is not available.")
    return statement
