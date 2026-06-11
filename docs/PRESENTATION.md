# Guion de presentación — 30 min (20 demo + 10 Q&A)

> Checklist previo (5 min antes): backend arriba (`uvicorn api:app --port 8000`),
> frontend arriba (`pnpm dev`), punto verde "API" en el header, una pestaña en `/` y otra
> en `/insights`, `pytest` corrido esa mañana (en verde), API key con créditos.
> **Plan B si falla la red/API:** los 13 tests pytest corren sin API y el reporte de
> insights es 100% determinista — la mitad de la demo sobrevive sin LLM.

---

## 1. Contexto y approach (3 min)

**Mensaje central (decirlo en los primeros 60 segundos):**

> "Los equipos de SP&A necesitan respuestas precisas, y los LLMs son maquinas de sonar
> convincentes. Mi decisión de diseño fue una sola: **el LLM nunca calcula — traduce,
> orquesta y narra; Python calcula**. La única parte probabilística del sistema es traducir
> la pregunta a una llamada de función tipada, y esa traducción la mido con tests."

- El problema: acceso fragmentado (requiere SQL/Python) + análisis manual repetitivo.
- La solución: bot conversacional (70%) + insights automáticos (30%), mismos cimientos:
  un query engine determinista sobre parquet tidy + un catálogo semántico de 13 métricas.
- Mencionar 1 hallazgo de perfilado como gancho de rigor: "el dataset traía Lead
  Penetration de hasta 393% — ratios imposibles. Los detecto en la ingesta contra el
  `valid_range` del catálogo y jamás llegan a un ranking."

## 2. Demo del bot (10 min) — 5 preguntas en vivo

Usar las tarjetas clickeables (suben la velocidad de la demo). Orden y qué señalar:

| # | Pregunta | Qué señalar mientras responde |
|---|----------|-------------------------------|
| 1 | *¿Cuáles son las 5 zonas con mayor % Lead Penetration esta semana?* (chip Filtrado) | El chip de herramienta con parámetros (`query_metrics · Lead Penetration · 5`): "esto es lo ÚNICO que decide el LLM". El gráfico y la tabla salen del cálculo, no del modelo. La nota de calidad: 32 zonas excluidas por diseño. |
| 2 | *¿Y cuáles son las 5 peores en esa misma métrica?* (escribirla) | **Memoria conversacional**: resolvió "esa misma métrica" del turno anterior y usó orden ascendente. |
| 3 | *Compara el Perfect Order entre zonas Wealthy y Non Wealthy en México* (chip Comparación) | Brecha de ~3.8 pp a favor de Wealthy; el bot da el "so what", no repite la tabla. Costo visible: ~$0.01–0.02 por pregunta. |
| 4 | *¿Qué zonas problemáticas hay en Colombia?* (escribirla) | **Contexto de negocio**: "problemática" tiene definición operativa en el catálogo; el agente orquesta varias herramientas solo (en el ensayo usó 2 con 7 visualizaciones). |
| 5 | *¿Cuáles son las zonas que más crecen en órdenes en las últimas 5 semanas y qué podría explicar el crecimiento?* (chip Inferencia) | Centro de Cuenca +47%, Sabaneta +37% — y los drivers presentados **como hipótesis, no causalidad** (la nota viene del propio engine). |

Cerrar la sección: "cada respuesta costó ~2 centavos de dólar y está anclada a un JSON
calculado que puedo auditar."

## 3. Insights automáticos (5 min)

Abrir `/insights` y recorrer de arriba a abajo:

1. **Stats**: ~4k hallazgos detectados en segundos, sin LLM en el cálculo.
2. **Hallazgos críticos**: explicar el ranking — `impacto = severidad × (1 + ln(1+órdenes))`.
   "Una caída del 15% en una zona de 20k órdenes importa más que en una de 200; eso es
   pensar en plata, no en porcentajes."
3. Click en **Síntesis IA**: "el LLM solo redacta sobre números ya calculados — miren cómo
   conecta hallazgos: detectó que dos zonas peruanas se voltearon a pérdida la misma semana
   y sugiere un evento sistémico de país."
4. **Heatmap** país×métrica (normalizado por dirección de la métrica) — vista gerencial.
5. Banner de **calidad de datos**: "la calidad del dato es un insight en sí mismo."
6. Botones **Markdown / PDF**: el reporte ejecutivo entregable.

## 4. Decisiones técnicas (5 min)

Apoyarse en `docs/ARCHITECTURE.md` (compartir pantalla del diagrama §1 y la tabla §2):

- **Las 7 defensas contra el no-determinismo** (recitar 3: schemas tipados, narración
  anclada + visuales deterministas, golden tests). Frase clave:
  > "La precisión no la afirmo: la mido. 13 tests de regresión congelan los 6 casos del
  > brief, y un runner pasa las preguntas reales por el agente — última corrida 8/8 por
  > $0.17."
- **Por qué no n8n/Zapier** (tabla §4): "la unidad de diseño de esas plataformas es el
  flujo; la de este problema es el dato." Admitir cuándo sí usarlas (integraciones simples)
  — balance técnico-negocio.
- **Stack**: FastAPI+SSE (streaming), Next.js+shadcn (UX de producto), Sonnet 4.6
  (tool-use robusto en español, ~$0.15–0.20 por sesión de 10 preguntas), parquet tidy (ms).

## 5. Limitaciones y próximos pasos (2 min)

Decirlas proactivamente (genera confianza):

1. Memoria conversacional en proceso → Redis con TTL en producción.
2. Los hallazgos críticos los domina GP UE (moneda vs ratios acotados) → normalizar
   severidad por volatilidad histórica de cada métrica.
3. Dataset estático de 8 semanas → el diseño ya soporta ingesta incremental semanal;
   siguiente paso natural: insights programados con alertas a Slack/email.
4. Visión: mismas herramientas expuestas como API interna para que otros equipos
   construyan encima (el engine es la plataforma, el bot es solo el primer cliente).

---

## Q&A — preguntas probables y respuestas cortas

**"¿Cómo garantizas que no alucina números?"**
No puede: no tiene acceso a los datos. Solo emite parámetros validados contra schemas; los
números vienen de pandas y la instrucción es narrar únicamente desde ese JSON. Si citara
algo fuera del resultado, los golden tests en vivo lo detectan.

**"¿Qué pasa si pregunto algo que las herramientas no cubren?"**
El agente lo dice y sugiere lo más cercano que sí puede responder (los errores
estructurados traen sugerencias). Extender = 1 función Python + 1 schema (~30 líneas).

**"¿Por qué Claude y no GPT/open-source?"**
Tool-use confiable y excelente español; la arquitectura es agnóstica — cambiar de proveedor
es reescribir `stream_agent`, no el sistema. Con temperature 0 y herramientas tipadas, el
modelo es un traductor: elegí el mejor traductor por costo ($3/$15 por millón).

**"¿Escala a millones de filas?"**
El patrón sí: las herramientas son agregaciones — se reimplementan sobre
DuckDB/BigQuery/Snowflake sin tocar agente ni frontend. Parquet en memoria fue la elección
correcta para 104k filas (consultas en ms).

**"¿Por qué los promedios por país no están ponderados por órdenes?"**
Ambos existen: `aggregate_metric` acepta `weighted_by_orders=true` y el agente lo usa si lo
pides ("promedio ponderado..."). El default simple replica el número que el equipo
calcularía a mano; está testeado que difieren.

**"¿Los datos salen de la empresa?"**
Solo los agregados que responde cada consulta viajan al LLM (filas del resultado), nunca el
dataset. Con Bedrock/Vertex el mismo diseño corre dentro del perímetro cloud propio.

**"¿Cuánto costó construirlo y operarlo?"**
Operación: ~$0.15–0.20 por sesión de 10 preguntas; el reporte de insights es gratis (sin
LLM) salvo la síntesis (~$0.01). Construcción: 2 días del caso.

**"¿Cómo sé que los insights no son ruido estadístico?"**
Umbrales explícitos y declarados en el propio reporte (±10% WoW con piso de base, 3+
semanas, 1.5σ con peer mínimo, |ρ|≥0.35 con n≥50), winsorización de outliers y exclusión de
flags. La metodología viaja con el reporte — es auditable.
