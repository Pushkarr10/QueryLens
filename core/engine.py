"""DuckDB execution engine with schema inspection and read-only validation."""

from __future__ import annotations
import io
import re
from typing import Any
import duckdb
import pandas as pd


class DuckDBEngine:
    """Manages an in-memory DuckDB connection, table loading, and safe query execution."""

    DISALLOWED_KEYWORDS = {
        "DROP", "DELETE", "UPDATE", "INSERT", "ALTER", "CREATE", "TRUNCATE",
        "REPLACE", "ATTACH", "DETACH", "COPY", "PRAGMA", "CALL", "EXPORT",
        "IMPORT", "GRANT", "REVOKE", "VACUUM", "INSTALL", "LOAD", "CHECKPOINT",
        "SET", "RESET"
    }

    def __init__(self):
        self.conn = duckdb.connect(database=":memory:")
        self.table_name = "data"
        self._is_loaded = False

    def load_csv(self, source: str | io.StringIO | io.BytesIO | pd.DataFrame | Any) -> dict[str, Any]:
        """Load CSV data into the in-memory 'data' table.

        Supports DataFrame, file path, file-like object, or raw CSV string.
        """
        if isinstance(source, pd.DataFrame):
            df = source
        elif isinstance(source, (io.StringIO, io.BytesIO)):
            source.seek(0)
            df = pd.read_csv(source)
        elif isinstance(source, str):
            if "\n" in source or "," in source:
                df = pd.read_csv(io.StringIO(source))
            else:
                df = pd.read_csv(source)
        elif hasattr(source, "read"):
            # Handle Streamlit UploadedFile
            if hasattr(source, "seek"):
                source.seek(0)
            df = pd.read_csv(source)
        else:
            raise ValueError(f"Unsupported data source type: {type(source)}")

        # Register and persist to DuckDB in-memory table 'data'
        self.conn.register("_temp_source_df", df)
        self.conn.execute(f"CREATE OR REPLACE TABLE {self.table_name} AS SELECT * FROM _temp_source_df")
        self.conn.unregister("_temp_source_df")
        self._is_loaded = True

        return self.get_schema()

    def is_loaded(self) -> bool:
        """Return True if a table has been loaded."""
        return self._is_loaded

    def get_schema(self) -> dict[str, Any]:
        """Inspect schema, column types, row count, and top 5 rows preview."""
        if not self._is_loaded:
            return {
                "columns": [],
                "types": {},
                "row_count": 0,
                "preview_df": pd.DataFrame(),
            }

        # Query DuckDB information_schema or pragma_table_info
        info_df = self.conn.execute(f"PRAGMA table_info('{self.table_name}')").df()
        columns = info_df["name"].tolist()
        types = dict(zip(info_df["name"], info_df["type"]))

        count_df = self.conn.execute(f"SELECT COUNT(*) as count FROM {self.table_name}").df()
        row_count = int(count_df["count"].iloc[0]) if not count_df.empty else 0

        preview_df = self.conn.execute(f"SELECT * FROM {self.table_name} LIMIT 5").df()

        return {
            "columns": columns,
            "types": types,
            "row_count": row_count,
            "preview_df": preview_df,
        }

    @classmethod
    def validate_query(cls, sql: str) -> tuple[bool, str]:
        """Strictly validate that the query is read-only (SELECT / WITH only).

        Rejects data-mutation keywords, multi-statement injection, and unpermitted operations.
        """
        if not sql or not sql.strip():
            return False, "Query is empty."

        # Remove line comments and block comments
        cleaned = re.sub(r"--[^\n]*", " ", sql)
        cleaned = re.sub(r"/\*.*?\*/", " ", cleaned, flags=re.DOTALL).strip()

        if not cleaned:
            return False, "Query consists only of comments or whitespace."

        # Check for multiple statements separated by semicolons (outside of quotes)
        # Split by semicolon and check non-empty statements
        statements = [s.strip() for s in re.split(r";(?=(?:[^']*'[^']*')*[^']*$)", cleaned) if s.strip()]
        if len(statements) > 1:
            return False, "Multiple SQL statements separated by semicolons are strictly prohibited."

        statement = statements[0]

        # Must start with SELECT or WITH
        first_word_match = re.match(r"^\s*([A-Za-z]+)", statement)
        if not first_word_match:
            return False, "Invalid SQL syntax: could not identify opening keyword."

        first_word = first_word_match.group(1).upper()
        if first_word not in {"SELECT", "WITH"}:
            return False, f"Permission denied: Query must begin with SELECT or WITH, but began with '{first_word}'."

        # Tokenize and scan for forbidden keywords as isolated words
        for keyword in cls.DISALLOWED_KEYWORDS:
            pattern = rf"\b{keyword}\b"
            if re.search(pattern, statement, flags=re.IGNORECASE):
                return False, f"Permission denied: Mutating or dangerous keyword '{keyword}' is blocked."

        return True, ""

    def execute_query(self, sql: str) -> pd.DataFrame:
        """Validate and execute a read-only SQL query against the loaded table."""
        if not self._is_loaded:
            raise RuntimeError("No dataset loaded. Please upload a CSV or load the sample dataset first.")

        is_valid, error_msg = self.validate_query(sql)
        if not is_valid:
            raise ValueError(error_msg)

        try:
            return self.conn.execute(sql).df()
        except Exception as e:
            raise RuntimeError(f"DuckDB Query Execution Error: {str(e)}") from e
