import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest
import pandas as pd
from core.sample_data import generate_sample_sales_df, generate_sample_sales_csv
from core.engine import DuckDBEngine
from core.nl2sql import NL2SQLTranslator


def test_sample_data_generation():
    df = generate_sample_sales_df(num_rows=200)
    assert len(df) == 200
    expected_cols = ["order_date", "region", "category", "product", "units_sold", "revenue", "profit"]
    assert list(df.columns) == expected_cols
    assert (df["revenue"] >= 0).all()
    assert (df["units_sold"] > 0).all()

    csv_data = generate_sample_sales_csv(num_rows=50)
    assert "order_date,region,category" in csv_data


def test_engine_load_and_schema():
    engine = DuckDBEngine()
    df = generate_sample_sales_df(num_rows=100)
    schema = engine.load_csv(df)

    assert engine.is_loaded() is True
    assert schema["row_count"] == 100
    assert "revenue" in schema["columns"]
    assert len(schema["preview_df"]) == 5


def test_engine_query_validation():
    # Allowed
    valid_queries = [
        "SELECT * FROM data",
        "select count(*) from data",
        "WITH summary AS (SELECT region, SUM(revenue) AS rev FROM data GROUP BY region) SELECT * FROM summary",
        "SELECT region, profit FROM data WHERE region = 'North America'",
    ]
    for q in valid_queries:
        is_valid, msg = DuckDBEngine.validate_query(q)
        assert is_valid, f"Expected valid for '{q}', got error: {msg}"

    # Blocked
    invalid_queries = [
        ("DROP TABLE data", "must begin with SELECT or WITH"),
        ("DELETE FROM data WHERE 1=1", "must begin with SELECT or WITH"),
        ("UPDATE data SET revenue = 0", "must begin with SELECT or WITH"),
        ("INSERT INTO data VALUES ('2024-01-01', 'A', 'B', 'C', 1, 10, 2)", "must begin with SELECT or WITH"),
        ("ALTER TABLE data ADD COLUMN x INT", "must begin with SELECT or WITH"),
        ("WITH t AS (UPDATE data SET revenue = 0) SELECT * FROM t", "blocked"),
        ("SELECT * FROM data; DROP TABLE data;", "Multiple SQL statements"),
        ("SELECT 1; SELECT 2;", "Multiple SQL statements"),
        ("", "empty"),
        ("   ", "empty"),
        ("SELECT * FROM data WHERE region = 'North'; DELETE FROM data", "Multiple SQL statements"),
        ("SELECT * FROM (SELECT 1) data; ATTACH 'malicious.db'", "Multiple SQL statements"),
    ]
    for q, expected_substr in invalid_queries:
        is_valid, msg = DuckDBEngine.validate_query(q)
        assert not is_valid, f"Expected '{q}' to be blocked, but it passed!"
        assert expected_substr.lower() in msg.lower(), f"Expected '{expected_substr}' in '{msg}'"


def test_nl2sql_offline_patterns():
    translator = NL2SQLTranslator()
    engine = DuckDBEngine()
    df = generate_sample_sales_df(num_rows=200)
    schema = engine.load_csv(df)

    test_cases = [
        ("Total revenue by region", "region", "revenue", "GROUP BY"),
        ("Top 5 products by profit", "product", "profit", "LIMIT 5"),
        ("Average units sold per category", "category", "units_sold", "AVG"),
        ("Revenue trend over time", "order_date", "revenue", "ORDER BY"),
        ("How many orders", "COUNT", "", ""),
    ]

    for prompt, expected_token1, expected_token2, expected_token3 in test_cases:
        sql, mode = translator.translate(prompt, schema, mode="offline")
        assert "Offline Demo Mode" in mode
        assert "FROM DATA" in sql.upper()
        if expected_token1:
            assert expected_token1.lower() in sql.lower(), f"'{expected_token1}' missing in {sql}"
        if expected_token2:
            assert expected_token2.lower() in sql.lower(), f"'{expected_token2}' missing in {sql}"
        if expected_token3:
            assert expected_token3.lower() in sql.lower(), f"'{expected_token3}' missing in {sql}"

        # Ensure execution succeeds without error!
        result_df = engine.execute_query(sql)
        assert not result_df.empty, f"Query '{sql}' returned empty dataframe!"


if __name__ == "__main__":
    test_sample_data_generation()
    test_engine_load_and_schema()
    test_engine_query_validation()
    test_nl2sql_offline_patterns()
    print("All tests passed successfully!")
