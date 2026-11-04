from __future__ import annotations

import math
from numbers import Real
from decimal import Decimal

import pandas as pd

import config
from data import quality_report


def analyze(df: pd.DataFrame) -> dict:
    """Return presentation-independent summaries for rows suitable for analysis.

    Invalid rows are reported by their Excel row numbers and excluded as whole rows;
    no cell values are coerced and no invalid observations are hidden.
    """
    report = quality_report(df)
    frame = df.copy()
    numeric_columns = [key for key in config.NUMERIC_COLUMNS if key in frame.columns]
    usable_positions: list[int] = []
    if numeric_columns:
        for position, (_, row) in enumerate(frame.iterrows()):
            good = True
            for key in numeric_columns:
                value = row[key]
                low, high = config.HISTORY_RANGES[key]
                if (isinstance(value, bool) or not isinstance(value, (Real, Decimal))
                        or not math.isfinite(float(value)) or float(value) < low
                        or (high is not None and float(value) > high)):
                    good = False
                    break
            if good and ("product" not in frame.columns or pd.isna(row["product"])):
                good = False
            if good:
                usable_positions.append(position)
    usable = frame.iloc[usable_positions].copy() if usable_positions else frame.iloc[:0].copy()
    excluded_rows = sorted(set(int(value) for value in frame.index) -
                           {int(frame.index[position]) for position in usable_positions})

    numeric = usable[numeric_columns] if numeric_columns else pd.DataFrame(dtype="float64")
    description = numeric.describe(percentiles=[.25, .5, .75]).T if not numeric.empty else pd.DataFrame(
        columns=["count", "mean", "std", "min", "25%", "50%", "75%", "max"])
    if not numeric.empty:
        description.insert(1, "median", numeric.median())
        description = description[["count", "mean", "median", "std", "min", "25%", "50%", "75%", "max"]]

    if "product" in usable.columns and "actual" in usable.columns:
        product_stats = (usable.groupby("product", dropna=False)["actual"]
                         .agg(observations="count", mean="mean", median="median")
                         .reset_index().sort_values("mean", ascending=False, kind="stable"))
    else:
        product_stats = pd.DataFrame(columns=["product", "observations", "mean", "median"])
    correlation = numeric.corr() if not numeric.empty else pd.DataFrame(
        index=numeric_columns, columns=numeric_columns, dtype="float64")
    distributions = {key: numeric[key].astype(float).tolist() for key in numeric_columns
                     if key in numeric.columns}
    return {
        "overview": {
            "rows": int(len(frame)),
            "products": int(frame["product"].nunique(dropna=True)) if "product" in frame else 0,
            "analyzed_rows": int(len(usable)),
            "excluded_rows": excluded_rows,
        },
        "description": description,
        "distributions": distributions,
        "correlation": correlation,
        "product_stats": product_stats,
        "quality": report,
    }
