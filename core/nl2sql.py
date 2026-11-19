"""Natural language to DuckDB SQL translator supporting Offline Demo Mode and OpenAI/OpenRouter."""

from __future__ import annotations
import re
from typing import Any
import openai


class NL2SQLTranslator:
    """Translates natural language questions into safe DuckDB SQL queries."""

    def __init__(self):
        pass

    def translate(
        self,
        prompt: str,
        schema: dict[str, Any],
        mode: str = "offline",
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ) -> tuple[str, str]:
        """Translate natural language to SQL.

        Returns tuple of (sql_query, mode_description).
        """
        prompt = prompt.strip()
        if not prompt:
            return "SELECT * FROM data LIMIT 10", "Default preview"

        if mode.lower() in {"openai", "openrouter"} and api_key:
            try:
                sql = self._translate_llm(
                    prompt=prompt,
                    schema=schema,
                    api_key=api_key,
                    base_url=base_url,
                    model=model or "gpt-4o-mini",
                )
                return sql, f"LLM ({model or 'gpt-4o-mini'})"
            except Exception as e:
                # Fallback to offline generator with explanatory flag
                offline_sql = self._translate_offline(prompt, schema)
                return offline_sql, f"Offline Fallback (LLM error: {str(e)[:60]}...)"

        # Default: Offline Demo Mode
        sql = self._translate_offline(prompt, schema)
        return sql, "Offline Demo Mode"

    def _translate_llm(
        self,
        prompt: str,
        schema: dict[str, Any],
        api_key: str,
        base_url: str | None = None,
        model: str = "gpt-4o-mini",
    ) -> str:
        """Query LLM via OpenAI-compatible client."""
        client_kwargs: dict[str, Any] = {"api_key": api_key}
        if base_url and base_url.strip():
            client_kwargs["base_url"] = base_url.strip()

        client = openai.OpenAI(**client_kwargs)

        col_defs = ", ".join([f"{col} ({dtype})" for col, dtype in schema.get("types", {}).items()])
        sample_preview = ""
        if "preview_df" in schema and not schema["preview_df"].empty:
            sample_preview = f"\nSample rows:\n{schema['preview_df'].head(2).to_dict(orient='records')}"

        system_prompt = (
            "You are an expert DuckDB SQL data analyst. Generate ONLY a single, valid DuckDB SQL query "
            "for the table named 'data'.\n"
            f"Table Schema: data({col_defs})\n"
            f"{sample_preview}\n"
            "CRITICAL RULES:\n"
            "1. Output ONLY the raw SQL statement. No explanations, no markdown ticks, no commentary.\n"
            "2. Read-only: Query MUST start with SELECT or WITH. Never mutate data.\n"
            "3. Use exact column names from the schema.\n"
            "4. Round numeric aggregates to 2 decimal places where appropriate."
        )

        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
            max_tokens=300,
        )

        raw_sql = response.choices[0].message.content or ""
        # Clean markdown code blocks if the model wrapped it
        raw_sql = re.sub(r"^```(?:sql)?\s*", "", raw_sql.strip(), flags=re.IGNORECASE)
        raw_sql = re.sub(r"\s*```$", "", raw_sql.strip())
        return raw_sql.strip()

    def _translate_offline(self, prompt: str, schema: dict[str, Any]) -> str:
        """Reliable rule-based SQL generator that inspects the actual table schema."""
        columns = schema.get("columns", [])
        types = schema.get("types", {})
        lower_prompt = prompt.lower().strip()

        if not columns:
            return "SELECT * FROM data LIMIT 10"

        # Categorize available columns
        num_cols = []
        date_cols = []
        cat_cols = []

        for col in columns:
            dtype = str(types.get(col, "")).upper()
            clower = col.lower()
            if any(t in dtype for t in ["INT", "FLOAT", "DOUBLE", "DECIMAL", "NUMERIC", "REAL"]) or clower in {
                "revenue", "profit", "units_sold", "sales", "amount", "price", "quantity", "cost", "margin"
            }:
                num_cols.append(col)
            elif any(t in dtype for t in ["DATE", "TIME", "TIMESTAMP"]) or "date" in clower or "time" in clower:
                date_cols.append(col)
            else:
                cat_cols.append(col)

        # Helper to find closest column match in query
        def find_mentioned_column(col_list: list[str]) -> str | None:
            for col in col_list:
                # check exact word or parts
                col_words = col.lower().replace("_", " ").split()
                if col.lower() in lower_prompt or all(w in lower_prompt for w in col_words):
                    return col
            return None

        # Helper to find target metric
        def find_metric() -> str:
            matched = find_mentioned_column(num_cols)
            if matched:
                return matched
            # Common synonyms
            if "sale" in lower_prompt or "turnover" in lower_prompt or "revenue" in lower_prompt:
                for col in num_cols:
                    if "rev" in col.lower() or "sale" in col.lower():
                        return col
            if "profit" in lower_prompt or "margin" in lower_prompt or "earning" in lower_prompt:
                for col in num_cols:
                    if "profit" in col.lower() or "margin" in col.lower():
                        return col
            if "unit" in lower_prompt or "qty" in lower_prompt or "volume" in lower_prompt or "quantity" in lower_prompt:
                for col in num_cols:
                    if "unit" in col.lower() or "qty" in col.lower() or "quant" in col.lower():
                        return col
            return num_cols[0] if num_cols else "*"

        # Helper to find target dimension
        def find_dimension() -> str:
            matched = find_mentioned_column(cat_cols)
            if matched:
                return matched
            # Common synonyms
            if "region" in lower_prompt or "country" in lower_prompt or "territory" in lower_prompt:
                for col in cat_cols:
                    if "reg" in col.lower() or "loc" in col.lower() or "countr" in col.lower():
                        return col
            if "product" in lower_prompt or "item" in lower_prompt:
                for col in cat_cols:
                    if "prod" in col.lower() or "item" in col.lower():
                        return col
            if "category" in lower_prompt or "department" in lower_prompt:
                for col in cat_cols:
                    if "cat" in col.lower() or "dept" in col.lower():
                        return col
            return cat_cols[0] if cat_cols else columns[0]

        # 1. Total counts / row counts
        if re.search(r"\b(how many|count|number of rows|total rows|row count|total records)\b", lower_prompt):
            if "unique" in lower_prompt or "distinct" in lower_prompt:
                dim = find_mentioned_column(columns) or (cat_cols[0] if cat_cols else columns[0])
                return f"SELECT COUNT(DISTINCT {dim}) AS unique_{dim}_count FROM data"
            return "SELECT COUNT(*) AS total_records FROM data"

        # 2. Time-series / trend queries
        if any(w in lower_prompt for w in ["trend", "over time", "monthly", "daily", "by month", "by date", "per day"]) or (
            date_cols and any(d.lower() in lower_prompt for d in date_cols)
        ):
            date_col = date_cols[0] if date_cols else "order_date"
            metric = find_metric()
            agg = "AVG" if "avg" in lower_prompt or "average" in lower_prompt else "SUM"
            alias = f"{agg.lower()}_{metric}" if metric != "*" else "metric_val"
            return (
                f"SELECT {date_col}, ROUND({agg}({metric}), 2) AS {alias} "
                f"FROM data GROUP BY {date_col} ORDER BY {date_col} ASC"
            )

        # 3. Top / Bottom N queries
        top_match = re.search(r"\b(top|bottom|highest|lowest|best|worst)\s*(\d+)?\b", lower_prompt)
        if top_match:
            keyword = top_match.group(1).lower()
            limit_str = top_match.group(2)
            limit = int(limit_str) if limit_str else 5

            order_dir = "ASC" if keyword in {"bottom", "lowest", "worst"} else "DESC"
            dim = find_dimension()
            metric = find_metric()
            agg = "AVG" if "avg" in lower_prompt or "average" in lower_prompt else "SUM"
            alias = f"{agg.lower()}_{metric}" if metric != "*" else "metric_val"

            return (
                f"SELECT {dim}, ROUND({agg}({metric}), 2) AS {alias} "
                f"FROM data GROUP BY {dim} ORDER BY {alias} {order_dir} LIMIT {limit}"
            )

        # 4. Group by Aggregation: "Total/Average <metric> by/per <dimension>"
        if any(w in lower_prompt for w in [" by ", " per ", " each ", " across "]):
            dim = find_dimension()
            metric = find_metric()
            agg = "AVG" if "avg" in lower_prompt or "average" in lower_prompt or "mean" in lower_prompt else "SUM"
            alias = f"{agg.lower()}_{metric}" if metric != "*" else "metric_val"

            # Check if second dimension is requested: e.g. "by region and category"
            dim2 = None
            for col in cat_cols:
                if col != dim and (col.lower() in lower_prompt):
                    dim2 = col
                    break

            if dim2:
                return (
                    f"SELECT {dim}, {dim2}, ROUND({agg}({metric}), 2) AS {alias} "
                    f"FROM data GROUP BY {dim}, {dim2} ORDER BY {alias} DESC LIMIT 50"
                )

            return (
                f"SELECT {dim}, ROUND({agg}({metric}), 2) AS {alias} "
                f"FROM data GROUP BY {dim} ORDER BY {alias} DESC"
            )

        # 5. Standalone Aggregate (e.g., "total revenue", "average profit")
        if any(w in lower_prompt for w in ["total", "sum", "average", "avg", "max", "maximum", "min", "minimum"]):
            metric = find_metric()
            agg = "AVG" if "avg" in lower_prompt or "average" in lower_prompt else "SUM"
            if "max" in lower_prompt:
                agg = "MAX"
            elif "min" in lower_prompt:
                agg = "MIN"
            alias = f"{agg.lower()}_{metric}"
            return f"SELECT ROUND({agg}({metric}), 2) AS {alias} FROM data"

        # 6. Fallback: Filter or general sample
        # Check if user mentioned a specific filter value
        for col in cat_cols:
            distinct_check = f"SELECT DISTINCT {col} FROM data LIMIT 20"
            # If prompt mentions column name directly
            if col.lower() in lower_prompt:
                metric = find_metric()
                return f"SELECT {col}, ROUND(SUM({metric}), 2) AS total_{metric} FROM data GROUP BY {col} ORDER BY total_{metric} DESC"

        # Default fallback
        return "SELECT * FROM data LIMIT 20"
