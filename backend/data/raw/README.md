# Raw data

Coloca aquí el Excel original:

```
Sistema_de_Análisis_Inteligente_para_Operaciones_Rappi_-_Dummy_Data.xlsx
```

Hojas esperadas: `RAW_INPUT_METRICS`, `RAW_ORDERS`.

Luego regenera los parquet (desde `backend/`):

```bash
python src/prepare_data.py data/raw/<archivo>.xlsx
```

Los parquet en `../processed/` ya vienen generados, así que este paso solo es
necesario si cambian los datos o quieres reproducir la ingesta desde cero.
