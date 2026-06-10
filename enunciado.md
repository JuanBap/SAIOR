# Caso Técnico: Sistema de Análisis Inteligente para Operaciones Rappi

**Rol:** AI Engineer

**Tiempo para la entrega:** 2 días calendario

**Formato de presentación:** 30 minutos (20 min presentación + 10 min Q&A)

---

## 1. Contexto del Problema

Rappi opera en 9 países con cientos de zonas geográficas, cada una con sus propias dinámicas operacionales. Los equipos de Strategy, Planning & Analytics (SP&A) y Operations necesitan tomar decisiones data-driven constantemente, pero enfrentan dos desafíos principales:

1. **Acceso fragmentado a insights:** Los datos están disponibles, pero requiere conocimiento técnico (SQL, Python) para extraer respuestas a preguntas de negocio.
2. **Análisis manual repetitivo:** Cada semana los equipos dedican horas a identificar zonas con problemas, oportunidades de crecimiento y anomalías operacionales.

**Tu misión** es construir un sistema basado en IA que democratice el acceso a estos datos y automatice la generación de insights accionables.

---

## 2. Entregables Requeridos

### 2.1 Bot Conversacional de Datos (70% del peso)

Desarrolla un chatbot que permita a usuarios no técnicos hacer preguntas en lenguaje natural sobre las métricas operacionales y recibir respuestas precisas.

**Requisitos mínimos:**

✅ **Capacidad de respuesta a queries complejas** (al menos estos casos de uso):

- Preguntas de filtrado: *"¿Cuáles son las 5 zonas con mayor % Lead Penetration esta semana?"*
- Comparaciones: *"Compara el Perfect Order entre zonas Wealthy y Non Wealthy en México"*
- Tendencias temporales: *"Muestra la evolución de Gross Profit UE en Chapinero últimas 8 semanas"*
- Agregaciones: *"¿Cuál es el promedio de Lead Penetration por país?"*
- Análisis multivariable: *"¿Qué zonas tienen alto Lead Penetration pero bajo Perfect Order?"*
- Preguntas de inferencia: *¿Cuáles son las zonas que más crecen en órdenes en las últimas 5 semanas y qué podría explicar el crecimiento?*

✅ **Manejo de contexto:** El bot debe entender el contexto de negocio (ejemplo: si preguntan por "zonas problemáticas", debe inferir que son aquellas con métricas deterioradas).

✅ **Sugerencias** proactivas de análisis.

✅ **Memoria conversacional** (seguimiento de diálogo).

**Bonus (no obligatorio):**

- **Visualización de datos:** Genera gráficos cuando la pregunta lo amerite (líneas para tendencias, barras para comparaciones, etc.)
- Exportación de resultados (CSV, PDF)

---

### 2.2 Sistema de Insights Automáticos (30% del peso)

Construye un sistema que analice automáticamente los datos y genere un reporte ejecutivo con los insights más relevantes.

**Requisitos mínimos:**

✅ **Identificación automática de insights** en al menos estas categorías:

- **Anomalías:** Zonas con cambios drásticos semana a semana (>10% deterioro/mejora).
- **Tendencias preocupantes:** Métricas en deterioro consistente (3+ semanas seguidas).
- **Benchmarking:** Comparación de zonas similares (mismo país/tipo) con performance divergente.
- **Correlaciones:** Relaciones entre métricas (ej: zonas con bajo Lead Penetration también tienen bajo Conversion).
- Oportunidades en general.

✅ **Reporte ejecutivo estructurado** que incluya:

- Resumen ejecutivo (top 3–5 hallazgos críticos)
- Detalle por categoría de insight
- Recomendaciones accionables para cada hallazgo

✅ **Formato de salida:** Markdown, HTML o PDF (elige el más apropiado)

**Bonus (no obligatorio):**

- Sistema de envío automático por email.

---

## 3. Datos Proporcionados

Recibirás 2 datasets en formato CSV:

### Dataset 1: Métricas Input (métricas operacionales por zona)

| Columna | Tipo | Descripción |
|---|---|---|
| COUNTRY | string | Código de país (AR, BR, CL, CO, CR, EC, MX, PE, UY) |
| CITY | string | Nombre de la ciudad |
| ZONE | string | Zona operacional o barrio |
| ZONE_TYPE | string | Segmentación por riqueza (Wealthy / Non Wealthy) |
| ZONE_PRIORITIZATION | string | Priorización estratégica (High Priority / Prioritized / Not Prioritized) |
| METRIC | string | Nombre de la métrica medida |
| L8W_VALUE a L0W_VALUE | float | Valor de la métrica en cada una de las últimas 8 semanas (L8W = hace 8 semanas, L0W = semana actual) |

### Dataset 2: Órdenes (volumen de órdenes por zona)

| Columna | Descripción |
|---|---|
| COUNTRY, CITY, ZONE | Identificadores geográficos |
| METRIC | Siempre "Orders" |
| L8W a L0W | Número de órdenes en cada semana |

### Diccionario de Métricas

| Métrica | Descripción |
|---|---|
| % PRO Users Who Breakeven | Usuarios con suscripción Pro cuyo valor generado para la empresa (a través de compras, comisiones, etc.) ha cubierto el costo total de su membresía / Total de usuarios suscripción Pro |
| % Restaurants Sessions With Optimal Assortment | Sesiones con un mínimo de 40 restaurantes / Total de sesiones |
| Gross Profit UE | Margen bruto de ganancia / Total de órdenes |
| Lead Penetration | Tiendas habilitadas en Rappi / (Tiendas previamente identificadas como prospectos (leads) + Tiendas habilitadas + Tiendas que salieron de Rappi) |
| MLTV Top Verticals Adoption | Usuarios con órdenes en diferentes verticales (restaurantes, super, pharmacy, liquors) / Total usuarios |
| Non-Pro PTC > OP | Conversión de usuarios No Pro en "Proceed to Checkout" a "Order Placed" |
| Perfect Orders | Orders sin cancelaciones o defectos o demora / Total de órdenes |
| Pro Adoption | Usuarios suscripción Pro / Total usuarios de Rappi |
| Restaurants Markdowns / GMV | Descuentos totales en órdenes de restaurantes / Total Gross Merchandise Value Restaurantes |
| Restaurants SS > ATC CVR | Conversión en restaurantes de "Select Store" a "Add to Cart" |
| Restaurants SST > SS CVR | Porcentaje de usuarios que, después de seleccionar un Restaurante o "Supermercados", proceden a seleccionar una tienda en particular de la lista que se les presenta |
| Retail SST > SS CVR | Porcentaje de usuarios que, después de seleccionar un Supermercados, proceden a seleccionar una tienda en particular de la lista que se les presenta |
| Turbo Adoption | Total de usuarios que compran en Turbo (Servicio fast de Rappi) / Total de usuarios de Rappi con tiendas de turbo disponible |

---

## 4. Requisitos Técnicos

### Stack Tecnológico

**Libertad total de herramientas:**

- **LLMs:** OpenAI (GPT-4, GPT-3.5), Anthropic (Claude), Google (Gemini), modelos open-source (Llama, Mistral), etc.
- **Plataformas no-code/low-code:** Make, n8n, Zapier, etc.
- **Lenguajes:** Python, JavaScript, TypeScript, o cualquier otro
- **Frameworks:** Streamlit, Gradio, Flask, FastAPI, Next.js, React, o lo que prefieras
- Si usas APIs pagas, **documenta el costo estimado** por uso (ej: "~$0.50 por sesión de 10 preguntas")

### Código y Reproducibilidad

✅ Incluye un **README** con:

- Instrucciones de cómo funciona tu solución

✅ **Organización:** Estructura tu solución de la manera que consideres más clara

> **Nota:** Si usas plataformas como Make o n8n, exporta los workflows/blueprints e incluye instrucciones de importación.

---

## 5. Criterios de Evaluación

Tu solución será evaluada según la siguiente rúbrica (100 puntos):

| Criterio | Peso | Qué evaluamos |
|---|---|---|
| Arquitectura y Diseño Técnico | 15% | Elección de componentes, patrones de diseño, escalabilidad, justificación de decisiones |
| Calidad del Bot | 35% | Precisión en respuestas, capacidad de manejar queries complejas, experiencia de usuario |
| Calidad de Insights | 30% | Relevancia, profundidad, accionabilidad de los insights generados automáticamente |
| Código y Documentación | 5% | Limpieza de código, reproducibilidad, claridad de documentación |
| Presentación y Comunicación | 20% | Claridad en la demo, capacidad de explicar decisiones técnicas |

**Lo que buscamos en un candidato excepcional:**

- **Pensamiento estratégico:** No solo resolver el problema, sino proponer mejoras y extensiones futuras
- **Balance técnico-negocio:** Entender que el objetivo es generar valor, no solo código elegante
- **Creatividad:** Soluciones innovadoras a los desafíos del caso
- **Atención al detalle:** Manejo de edge cases, validaciones, experiencia de usuario

---

## 6. Formato de Entrega

### Repositorio

Sube tu solución a un repositorio Git (GitHub, GitLab, etc.) y comparte el link. Asegúrate de que sea **público** o danos acceso.

### Presentación (30 minutos)

Estructura sugerida:

1. **Contexto y approach** (3 min): ¿Cómo interpretaste el problema?
2. **Demo del bot** (10 min): Muestra el bot respondiendo al menos 5 preguntas de diferente complejidad
3. **Insights automáticos** (5 min): Muestra el reporte generado y explica los hallazgos
4. **Decisiones técnicas** (5 min): Arquitectura, elección de LLM, trade-offs principales
5. **Limitaciones y próximos pasos** (2 min): ¿Qué mejorarías con más tiempo?
6. **Q&A** (10 min)

> **Importante:** Realiza una **demo en vivo**, no un video grabado. Queremos ver el sistema funcionando en tiempo real.

---

## 7. Preguntas Frecuentes

**¿Puedo usar librerías de third-party para gráficos/análisis?**

Sí, usa lo que necesites (plotly, matplotlib, seaborn, pandas, numpy, scikit-learn, etc.)

**¿Qué pasa si no completo todos los bonus?**

Los bonus no son obligatorios. Un caso resuelto sólidamente sin bonus es mejor que uno con bonus pero implementación mediocre.

**¿Puedo hacer preguntas durante el caso?**

Si tienes dudas **conceptuales** sobre métricas de negocio, puedes escribir a daniel.chain@rappi.com.

**¿Necesito deployment en la nube?**

No es obligatorio. Con que funcione localmente (localhost) es suficiente. Si haces deployment (Streamlit Cloud, Render, Railway, etc.) es un plus.

**¿Qué tan sofisticado debe ser el sistema de insights?**

Prioriza **relevancia sobre complejidad**. 5 insights bien fundamentados y accionables valen más que 20 insights superficiales.

---

## 8. Datos de Contacto y Timeline

**Envío de materiales:** Recibirás los CSVs junto con este brief

**Fecha límite de entrega:** 2025/10/13

**Fecha de presentación:** [A coordinar después de entrega]

**Contacto para dudas:** daniel.chain@rappi.com

---

## 9. Consejos Finales

✨ **Empieza simple:** Un bot básico que funcione bien es mejor que uno ambicioso que falla

✨ **Documenta tus decisiones:** Explica por qué elegiste X framework o Y modelo

✨ **Piensa en el usuario final:** ¿Realmente un Operational Manager usaría esto?

✨ **Gestiona tu tiempo:** 2 días suenan como mucho, pero pasan rápido. Prioriza los requisitos obligatorios

---

**¡Mucha suerte! Estamos emocionados de ver tu solución.**

> *Nota: Los datos han sido anonimizados y randomizados, por lo que no representan un país ni período específico.*