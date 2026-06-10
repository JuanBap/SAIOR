"""Ingesta y normalización del dataset Rappi.

Ejecutar:
    python src/prepare_data.py <ruta_excel_o_dir_csvs>   # ingesta completa desde el raw
    python src/prepare_data.py --reflag                   # recalcula QUALITY_FLAG sobre
                                                          # data/processed (sin el raw)
Produce parquet tidy en data/processed/ con flags de calidad.

Los flags NO usan umbrales ad-hoc: se derivan del `valid_range` declarado por
métrica en metrics_catalog.json (la capa semántica es la fuente de verdad).
"""
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "processed"
CATALOG = json.loads((Path(__file__).parent / "metrics_catalog.json").read_text())


def load(source: str):
    p = Path(source)
    if p.suffix == ".xlsx":
        m = pd.read_excel(p, sheet_name="RAW_INPUT_METRICS")
        o = pd.read_excel(p, sheet_name="RAW_ORDERS")
    else:  # directorio con CSVs
        m = pd.read_csv(p / "metrics.csv")
        o = pd.read_csv(p / "orders.csv")
    return m, o


def apply_quality_flags(ml: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Marca OUT_OF_RANGE todo valor fuera del valid_range del catálogo de su métrica.
    Ej.: Lead Penetration es un ratio [0,1] — un 110% es imposible por definición."""
    ml = ml.copy()
    ml["QUALITY_FLAG"] = "OK"
    total = 0
    for metric, spec in CATALOG["metrics"].items():
        vr = spec.get("valid_range")
        if not vr:
            continue
        lo, hi = vr
        in_metric = (ml.METRIC == metric) & ml.VALUE.notna()
        bad = pd.Series(False, index=ml.index)
        if lo is not None:
            bad |= in_metric & (ml.VALUE < lo)
        if hi is not None:
            bad |= in_metric & (ml.VALUE > hi)
        ml.loc[bad, "QUALITY_FLAG"] = "OUT_OF_RANGE"
        total += int(bad.sum())
    return ml, total


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

    # 3. Flags de calidad por valid_range del catálogo
    ml, n_flags = apply_quality_flags(ml)
    report["out_of_range_flags"] = n_flags

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


def reflag():
    """Recalcula los flags sobre el parquet procesado (útil si cambia el catálogo
    o no se dispone del Excel original)."""
    ml = pd.read_parquet(OUT / "metrics_long.parquet").drop(columns=["QUALITY_FLAG"])
    ml, n = apply_quality_flags(ml)
    ml.to_parquet(OUT / "metrics_long.parquet", index=False)
    return {"out_of_range_flags": n, "rows": len(ml)}


if __name__ == "__main__":
    if sys.argv[1:] == ["--reflag"]:
        print(reflag())
    else:
        src = sys.argv[1] if len(sys.argv) > 1 else "data/raw"
        m, o = load(src)
        print(prepare(m, o))
