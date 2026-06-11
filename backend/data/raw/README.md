# Raw data

`dummydata.xlsx` — el Excel original del caso (datos anonimizados/randomizados, según la
nota del brief). Hojas: `RAW_INPUT_METRICS`, `RAW_ORDERS`, `RAW_SUMMARY`.

Regenerar los parquet de `../processed/` desde cero (desde `backend/`):

```bash
.venv/bin/python src/prepare_data.py data/raw/dummydata.xlsx
```

Recalcular solo los flags de calidad (si cambia el catálogo):

```bash
.venv/bin/python src/prepare_data.py --reflag
```

Reproducibilidad verificada: la ingesta completa desde este Excel reproduce exactamente los
valores congelados en `tests/test_golden_queries.py` (963 duplicados removidos, 253 flags
OUT_OF_RANGE, 980 zonas de métricas, 1.242 de órdenes).
