"""Sample e-commerce sales dataset generator."""

import random
from datetime import date, timedelta
import io
import pandas as pd


def generate_sample_sales_df(num_rows: int = 200, seed: int = 42) -> pd.DataFrame:
    """Generate a clean synthetic e-commerce sales dataset."""
    random.seed(seed)

    regions = ["North America", "Europe", "Asia Pacific", "Latin America"]
    catalog = {
        "Electronics": [
            ("Wireless Noise-Canceling Headphones", 120.0, 0.28),
            ("Ultra-Wide 4K Monitor", 399.0, 0.32),
            ("Mechanical Ergonomic Keyboard", 85.0, 0.25),
            ("Smart Fitness Watch", 149.0, 0.35),
            ("USB-C Thunderbolt Dock", 110.0, 0.30),
        ],
        "Office Supplies": [
            ("Ergonomic Mesh Chair", 240.0, 0.35),
            ("Standing Desk Converter", 180.0, 0.30),
            ("Premium Fountain Pen Set", 45.0, 0.40),
            ("A4 Heavy-Duty Paper Ream (5x)", 35.0, 0.18),
            ("Acoustic Desk Privacy Panel", 95.0, 0.28),
        ],
        "Furniture": [
            ("Solid Oak Coffee Table", 320.0, 0.38),
            ("Minimalist Bookshelf Unit", 175.0, 0.33),
            ("Adjustable Floor Lamp", 65.0, 0.26),
            ("Velvet Accent Armchair", 290.0, 0.42),
            ("Modular Storage Ottoman", 80.0, 0.27),
        ],
        "Apparel": [
            ("Waterproof Trail Jacket", 130.0, 0.45),
            ("Merino Wool Crewneck", 90.0, 0.40),
            ("Performance Running Shoes", 115.0, 0.35),
            ("Breathable Canvas Backpack", 60.0, 0.38),
            ("Thermal Compression Tights", 45.0, 0.32),
        ],
    }

    start_date = date(2024, 1, 1)
    end_date = date(2024, 12, 31)
    delta_days = (end_date - start_date).days

    records = []
    categories = list(catalog.keys())

    for _ in range(num_rows):
        cat = random.choice(categories)
        product_info = random.choice(catalog[cat])
        product_name, base_price, profit_margin = product_info

        order_dt = start_date + timedelta(days=random.randint(0, delta_days))
        region = random.choice(regions)

        # Variations in volume and slight price discounts/premiums
        units_sold = random.randint(1, 18)
        price_multiplier = random.uniform(0.92, 1.08)
        unit_price = round(base_price * price_multiplier, 2)
        revenue = round(units_sold * unit_price, 2)

        # Margin with slight variance
        effective_margin = max(0.08, min(0.60, profit_margin + random.uniform(-0.06, 0.06)))
        profit = round(revenue * effective_margin, 2)

        records.append({
            "order_date": order_dt.isoformat(),
            "region": region,
            "category": cat,
            "product": product_name,
            "units_sold": units_sold,
            "revenue": revenue,
            "profit": profit,
        })

    # Sort deterministically by date
    records.sort(key=lambda x: x["order_date"])
    return pd.DataFrame(records)


def generate_sample_sales_csv(num_rows: int = 200, seed: int = 42) -> str:
    """Generate sample sales data as CSV string."""
    df = generate_sample_sales_df(num_rows=num_rows, seed=seed)
    return df.to_csv(index=False)
