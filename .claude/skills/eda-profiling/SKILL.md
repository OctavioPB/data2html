---
name: eda-profiling
description: Usar al implementar o mejorar el perfilado EDA (backend/src/data2html/profiling/): estadísticas por columna, histogramas, correlaciones, outliers y avisos de calidad de datos.
---

# Perfilado EDA

## Por columna
- Base: `SUMMARIZE <tabla>` de DuckDB (min, max, aprox. distintos, nulos, cuantiles).
- Numéricas: histograma con bins de Freedman-Diaconis (máx. 50), outliers por IQR (1.5×).
- Categóricas: top-20 + "otros". Temporales: rango y conteo por periodo.

## Avisos (cada uno con umbral configurable)
| Aviso | Regla por defecto |
|---|---|
| Posible ID | distintos ≥ 95% de filas no nulas |
| Alta cardinalidad | categórica con > 1000 distintos |
| Nulos | > 20% |
| Constante | 1 valor distinto |
| Numérico como texto | ≥ 95% de valores parsean como número |

## Fuentes remotas
Nunca perfiles completo una tabla de Teradata. Muestra (`SAMPLE 100000`) y marca el
resultado con `sampled: true` y el tamaño. La UI debe mostrarlo.

## Correlaciones
Pearson y Spearman entre numéricas, solo si hay ≤ 50 columnas numéricas; reporta `n` usado.
No infieras causalidad en los textos de la UI.
