"""Ingesta y normalización del dataset Rappi.
Ejecutar: python src/prepare_data.py <ruta_excel_o_csvs>
Produce parquet tidy en data/processed/ con flags de calidad.
"""
import sys
from pathlib import Path
import pandas as pd
import numpy as np

OUT = Path(__file__).resolve().parents[1] / "data" / "processed"

def load(source: str):
    p = Path(source)
    if p.suffix == ".xlsx":
        m = pd.read_excel(p, sheet_name="RAW_INPUT_METRICS")
        o = pd.read_excel(p, sheet_name="RAW_ORDERS")
    else:  # directorio con CSVs
        m = pd.read_csv(p / "metrics.csv")
        o = pd.read_csv(p / "orders.csv")
    return m, o

def prepare(m: pd.DataFrame, o: pd.DataFrame):
    report = {}
    # 1. Dedupe exacto (GP UE viene duplicado con valores idénticos)
    before = len(m)
    m = m.drop_duplicates(["COUNTRY", "CITY", "ZONE", "METRIC"], keep="first")
    report["duplicates_removed"] = before - len(m)

    # 2. Tidy: una fila = zona + métrica + semana (-8..0)
    wk_m = {f"L{i}W_ROLL": -i for i in range(9)}
    ml = m.melt(
        id_vars=["COUNTRY", "CITY", "ZONE", "ZONE_TYPE", "ZONE_PRIORITIZATION", "METRIC"],
        value_vars=list(wk_m), var_name="WC", value_name="VALUE")
    ml["WEEK"] = ml.WC.map(wk_m)
    ml = ml.drop(columns="WC")

    # 3. Flags de calidad
    ml["QUALITY_FLAG"] = "OK"
    bad_lp = (ml.METRIC == "Lead Penetration") & (ml.VALUE > 1.5)
    ml.loc[bad_lp, "QUALITY_FLAG"] = "OUT_OF_RANGE"
    report["out_of_range_flags"] = int(bad_lp.sum())

    wk_o = {f"L{i}W": -i for i in range(9)}
    ol = o.melt(id_vars=["COUNTRY", "CITY", "ZONE", "METRIC"],
                value_vars=list(wk_o), var_name="WC", value_name="VALUE")
    ol["WEEK"] = ol.WC.map(wk_o)
    ol = ol.drop(columns=["WC", "METRIC"])

    OUT.mkdir(parents=True, exist_ok=True)
    ml.to_parquet(OUT / "metrics_long.parquet", index=False)
    ol.to_parquet(OUT / "orders_long.parquet", index=False)
    m.to_parquet(OUT / "metrics_wide.parquet", index=False)
    o.to_parquet(OUT / "orders_wide.parquet", index=False)
    report["zones_metrics"] = int(m[["COUNTRY", "CITY", "ZONE"]].drop_duplicates().shape[0])
    report["zones_orders"] = int(o[["COUNTRY", "CITY", "ZONE"]].drop_duplicates().shape[0])
    return report

if __name__ == "__main__":
    src = sys.argv[1] if len(sys.argv) > 1 else "data/raw"
    m, o = load(src)
    print(prepare(m, o))
