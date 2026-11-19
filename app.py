"""QueryLens DuckDB: In-Memory NL2SQL CSV Explorer & Visualizer."""

from __future__ import annotations
import io
import time
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from core.engine import DuckDBEngine
from core.nl2sql import NL2SQLTranslator
from core.sample_data import generate_sample_sales_df, generate_sample_sales_csv

# Page configuration
st.set_page_config(
    page_title="QueryLens DuckDB - Instant NL2SQL & Visuals",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom Styling
st.markdown(
    """
    <style>
    .main-header {
        font-size: 2.2rem;
        font-weight: 800;
        background: linear-gradient(90deg, #2563EB, #7C3AED, #DB2777);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.2rem;
    }
    .sub-header {
        font-size: 1.05rem;
        color: #64748B;
        margin-bottom: 1.2rem;
    }
    .badge {
        display: inline-block;
        padding: 0.25rem 0.6rem;
        font-size: 0.78rem;
        font-weight: 600;
        border-radius: 9999px;
        background-color: #EEF2FF;
        color: #4F46E5;
        margin-right: 0.4rem;
    }
    .badge-green {
        background-color: #ECFDF5;
        color: #059669;
    }
    .stCodeBlock {
        border-radius: 8px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def get_engine() -> DuckDBEngine:
    """Retrieve or initialize DuckDB engine in session state."""
    if "engine" not in st.session_state:
        engine = DuckDBEngine()
        # Default load sample dataset so app is 100% interactive immediately
        sample_df = generate_sample_sales_df(num_rows=200)
        engine.load_csv(sample_df)
        st.session_state["engine"] = engine
        st.session_state["dataset_name"] = "Sample E-Commerce Sales (200 rows)"
    return st.session_state["engine"]


def get_translator() -> NL2SQLTranslator:
    """Retrieve or initialize NL2SQL translator in session state."""
    if "translator" not in st.session_state:
        st.session_state["translator"] = NL2SQLTranslator()
    return st.session_state["translator"]


def auto_visualize(df: pd.DataFrame) -> go.Figure | None:
    """Intelligently infer and generate an optimal Plotly visualization."""
    if df.empty or len(df.columns) == 0:
        return None

    # Scalar check: 1 row, 1 column handled outside via st.metric
    if df.shape == (1, 1):
        return None

    cols = list(df.columns)
    num_cols = []
    date_cols = []
    cat_cols = []

    for col in cols:
        series = df[col]
        # Check date
        if pd.api.types.is_datetime64_any_dtype(series):
            date_cols.append(col)
        elif "date" in col.lower() or "time" in col.lower() or "day" in col.lower():
            try:
                pd.to_datetime(series.dropna().head(10))
                date_cols.append(col)
            except Exception:
                cat_cols.append(col)
        elif pd.api.types.is_numeric_dtype(series):
            num_cols.append(col)
        else:
            cat_cols.append(col)

    # Heuristic 1: Date + 1 Numeric => Line Chart
    if date_cols and num_cols:
        dcol = date_cols[0]
        ncol = num_cols[0]
        sorted_df = df.sort_values(by=dcol)
        fig = px.line(
            sorted_df,
            x=dcol,
            y=ncol,
            markers=True,
            title=f"Trend of {ncol} over {dcol}",
            color_discrete_sequence=["#2563EB"],
        )
        fig.update_layout(
            hovermode="x unified",
            xaxis_title=dcol.replace("_", " ").title(),
            yaxis_title=ncol.replace("_", " ").title(),
            margin=dict(l=20, r=20, t=50, b=20),
            template="plotly_white",
        )
        return fig

    # Heuristic 2: 1 Categorical + 1 Numeric => Bar Chart
    if cat_cols and num_cols:
        ccol = cat_cols[0]
        ncol = num_cols[0]
        # If many categories (> 15), show horizontal bar sorted
        if len(df) > 8:
            sorted_df = df.sort_values(by=ncol, ascending=True)
            fig = px.bar(
                sorted_df,
                x=ncol,
                y=ccol,
                orientation="h",
                text=ncol,
                title=f"{ncol.replace('_', ' ').title()} by {ccol.replace('_', ' ').title()}",
                color=ncol,
                color_continuous_scale="Blues",
            )
            fig.update_traces(texttemplate="%{text:.2s}", textposition="outside")
            fig.update_layout(
                yaxis=dict(categoryorder="total ascending"),
                margin=dict(l=20, r=20, t=50, b=20),
                template="plotly_white",
            )
        else:
            sorted_df = df.sort_values(by=ncol, ascending=False)
            fig = px.bar(
                sorted_df,
                x=ccol,
                y=ncol,
                text=ncol,
                title=f"{ncol.replace('_', ' ').title()} by {ccol.replace('_', ' ').title()}",
                color=ncol,
                color_continuous_scale="Viridis",
            )
            fig.update_traces(texttemplate="%{text:.2s}", textposition="outside")
            fig.update_layout(
                margin=dict(l=20, r=20, t=50, b=20),
                template="plotly_white",
            )
        return fig

    # Heuristic 3: 2 Numeric Columns => Scatter Plot
    if len(num_cols) >= 2:
        x_col, y_col = num_cols[0], num_cols[1]
        fig = px.scatter(
            df,
            x=x_col,
            y=y_col,
            title=f"{y_col.replace('_', ' ').title()} vs {x_col.replace('_', ' ').title()}",
            color_discrete_sequence=["#7C3AED"],
            opacity=0.85,
        )
        fig.update_layout(
            margin=dict(l=20, r=20, t=50, b=20),
            template="plotly_white",
        )
        return fig

    # Heuristic 4: Single Numeric Column (Multiple rows) => Histogram
    if len(num_cols) == 1 and not cat_cols:
        ncol = num_cols[0]
        fig = px.histogram(
            df,
            x=ncol,
            title=f"Distribution of {ncol.replace('_', ' ').title()}",
            color_discrete_sequence=["#059669"],
        )
        fig.update_layout(margin=dict(l=20, r=20, t=50, b=20), template="plotly_white")
        return fig

    return None


def main():
    engine = get_engine()
    translator = get_translator()

    # --- SIDEBAR ---
    with st.sidebar:
        st.header("⚙️ Configuration")

        st.subheader("1. Data Source")
        uploaded_file = st.file_uploader("Upload CSV File", type=["csv"])
        if uploaded_file is not None:
            # Check if this is a newly uploaded file
            if st.session_state.get("_last_uploaded") != uploaded_file.name:
                try:
                    engine.load_csv(uploaded_file)
                    st.session_state["dataset_name"] = uploaded_file.name
                    st.session_state["_last_uploaded"] = uploaded_file.name
                    st.toast(f"✅ Loaded '{uploaded_file.name}' into DuckDB!", icon="🚀")
                except Exception as e:
                    st.error(f"Failed to load CSV: {e}")

        if st.button("🔄 Reload Sample Sales Data", use_container_width=True):
            sample_df = generate_sample_sales_df(num_rows=200)
            engine.load_csv(sample_df)
            st.session_state["dataset_name"] = "Sample E-Commerce Sales (200 rows)"
            st.session_state["_last_uploaded"] = None
            st.toast("✅ Sample sales dataset reloaded!", icon="📦")

        st.markdown("---")
        st.subheader("2. Translation Engine")
        engine_mode = st.radio(
            "Engine Mode",
            options=["Offline Demo Mode (No Key Required)", "OpenAI / OpenRouter API"],
            index=0,
            help="Offline Demo Mode operates 100% locally with zero external API calls.",
        )

        api_key = None
        base_url = None
        model_name = "gpt-4o-mini"

        if "OpenAI" in engine_mode:
            api_key = st.text_input("API Key", type="password", placeholder="sk-...")
            provider = st.selectbox("Provider", ["OpenAI", "OpenRouter", "Custom URL"])
            if provider == "OpenRouter":
                base_url = "https://openrouter.ai/api/v1"
                model_name = st.text_input("Model ID", value="openai/gpt-4o-mini")
            elif provider == "Custom URL":
                base_url = st.text_input("Base URL", placeholder="http://localhost:11434/v1")
                model_name = st.text_input("Model Name", value="llama3")
            else:
                model_name = st.selectbox("OpenAI Model", ["gpt-4o-mini", "gpt-4o", "gpt-3.5-turbo"])

        st.markdown("---")
        schema = engine.get_schema()
        st.markdown(f"**Current Dataset**: `{st.session_state.get('dataset_name', 'None')}`")
        st.markdown(f"**Rows**: `{schema['row_count']}` | **Columns**: `{len(schema['columns'])}`")

        # Download sample dataset option
        sample_csv = generate_sample_sales_csv(200)
        st.download_button(
            label="📥 Download Sample CSV",
            data=sample_csv,
            file_name="sample_sales_data.csv",
            mime="text/csv",
            use_container_width=True,
        )

    # --- MAIN VIEW ---
    st.markdown('<div class="main-header">⚡ QueryLens DuckDB</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="sub-header">Zero-setup natural language analytics for CSVs powered by in-memory DuckDB and instant Plotly charts.</div>',
        unsafe_allow_html=True,
    )

    col_b1, col_b2, col_b3 = st.columns([1, 1, 1])
    with col_b1:
        st.markdown('<span class="badge">🦆 In-Memory DuckDB: Table `data`</span>', unsafe_allow_html=True)
    with col_b2:
        st.markdown('<span class="badge badge-green">🛡️ Strict Read-Only Guardrails</span>', unsafe_allow_html=True)
    with col_b3:
        mode_badge = "Offline Mode Active" if "Offline" in engine_mode else "API Mode Active"
        st.markdown(f'<span class="badge">{mode_badge}</span>', unsafe_allow_html=True)

    st.markdown("")

    # --- SCHEMA EXPANDER ---
    schema = engine.get_schema()
    with st.expander("📋 Table Schema & Preview (Table: `data`)", expanded=False):
        c1, c2 = st.columns([1, 2])
        with c1:
            schema_df = pd.DataFrame(
                list(schema["types"].items()),
                columns=["Column Name", "DuckDB Type"],
            )
            st.dataframe(schema_df, use_container_width=True, hide_index=True)
        with c2:
            st.markdown(f"**First 5 Rows of {schema['row_count']} total records:**")
            st.dataframe(schema["preview_df"], use_container_width=True, hide_index=True)

    # --- EXAMPLE PROMPT BUTTONS ---
    st.markdown("##### 💡 Example Queries (Click to test):")
    p_col1, p_col2, p_col3, p_col4 = st.columns(4)

    clicked_prompt = None
    with p_col1:
        if st.button("📊 Total revenue by region", use_container_width=True):
            clicked_prompt = "Total revenue by region"
    with p_col2:
        if st.button("🏆 Top 5 products by profit", use_container_width=True):
            clicked_prompt = "Top 5 products by profit"
    with p_col3:
        if st.button("📦 Avg units sold per category", use_container_width=True):
            clicked_prompt = "Average units sold per category"
    with p_col4:
        if st.button("📈 Revenue trend over time", use_container_width=True):
            clicked_prompt = "Revenue trend over time"

    # Default query handling
    if clicked_prompt:
        st.session_state["query_input"] = clicked_prompt

    user_query = st.text_input(
        "Ask a question about your data in plain English:",
        value=st.session_state.get("query_input", "Total revenue by region"),
        key="query_text_box",
        placeholder="e.g., Top 5 products by profit, Total revenue by region...",
    )

    run_query = st.button("🚀 Run Query", type="primary")

    # If example clicked or Run pressed or initial load
    should_run = run_query or clicked_prompt or ("last_run_query" not in st.session_state)

    if should_run and user_query.strip():
        st.session_state["last_run_query"] = user_query.strip()
        with st.spinner("Translating natural language to DuckDB SQL..."):
            t_start = time.perf_counter()
            mode_arg = "openai" if "OpenAI" in engine_mode else "offline"
            sql_query, mode_used = translator.translate(
                prompt=user_query,
                schema=schema,
                mode=mode_arg,
                api_key=api_key,
                base_url=base_url,
                model=model_name,
            )
            translate_time = time.perf_counter() - t_start

        st.session_state["generated_sql"] = sql_query
        st.session_state["mode_used"] = mode_used
        st.session_state["translate_time"] = translate_time

        # Validate and Execute
        try:
            e_start = time.perf_counter()
            result_df = engine.execute_query(sql_query)
            exec_time = time.perf_counter() - e_start
            st.session_state["query_error"] = None
            st.session_state["result_df"] = result_df
            st.session_state["exec_time"] = exec_time
        except Exception as e:
            st.session_state["query_error"] = str(e)
            st.session_state["result_df"] = None

    # --- DISPLAY RESULTS ---
    if "generated_sql" in st.session_state:
        st.markdown("---")
        h_col1, h_col2 = st.columns([3, 1])
        with h_col1:
            st.markdown(f"**Generated DuckDB SQL** (`{st.session_state.get('mode_used', 'Offline')}`)")
        with h_col2:
            if "exec_time" in st.session_state:
                st.caption(f"⏱️ Translation: {st.session_state.get('translate_time', 0):.3f}s | Query: {st.session_state.get('exec_time', 0):.3f}s")

        st.code(st.session_state["generated_sql"], language="sql")

        if st.session_state.get("query_error"):
            st.error(f"❌ {st.session_state['query_error']}")
        else:
            result_df: pd.DataFrame = st.session_state.get("result_df")
            if result_df is not None:
                if result_df.empty:
                    st.warning("Query returned zero rows.")
                elif result_df.shape == (1, 1):
                    # Single metric scalar result
                    metric_col = result_df.columns[0]
                    val = result_df.iloc[0, 0]
                    formatted_val = f"{val:,.2f}" if isinstance(val, (int, float)) else str(val)
                    st.metric(label=metric_col.replace("_", " ").title(), value=formatted_val)
                else:
                    tab_vis, tab_data = st.tabs(["📊 Auto Visualization", f"📄 Data Table ({len(result_df)} rows)"])

                    with tab_vis:
                        fig = auto_visualize(result_df)
                        if fig is not None:
                            st.plotly_chart(fig, use_container_width=True)
                        else:
                            st.info("No single 2D auto-chart inferred for this column combination. Inspect results in the Data Table tab below.")
                            st.dataframe(result_df, use_container_width=True)

                    with tab_data:
                        st.dataframe(result_df, use_container_width=True)

                    # Download button
                    csv_buffer = io.StringIO()
                    result_df.to_csv(csv_buffer, index=False)
                    st.download_button(
                        label="📥 Download Results (CSV)",
                        data=csv_buffer.getvalue(),
                        file_name="querylens_results.csv",
                        mime="text/csv",
                    )


if __name__ == "__main__":
    main()
