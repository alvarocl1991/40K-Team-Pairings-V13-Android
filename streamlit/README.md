# 40K Team Pairings V13 — Data-Driven

## Puesta en marcha

```bash
python -m pip install -r requirements.txt
python -m streamlit run streamlit_app.py
```

## Datos estadísticos

La aplicación descarga los win rates desde MiniHeadQuarters (formato Individual/Solo) y usa, por defecto, una ventana móvil de 12 semanas. El menú lateral permite seleccionar 1, 2, 4, 8, 12 o 26 semanas y forzar una actualización. Los datos se guardan en caché durante 6 horas para evitar consultas innecesarias.

- Estadísticas: https://miniheadquarters.com/meta/solo/warhammer-40000/stats/
- Metodología: https://miniheadquarters.com/meta/warhammer-40000/methodology/

El sitio muestra el win rate global por facción, los resultados de cada matchup, el número de partidas y rangos de confianza del 95%. Los emparejamientos directos con pocas partidas se suavizan hacia una estimación basada en los win rates globales. Si no hay datos para una facción, la aplicación no inventa una tasa: usa un prior neutral cuando no se pueda estimar y lo indica.

## Cómo se combina facción y disposición

1. Se utiliza el win rate directo facción contra facción cuando existe. Si falta, se calcula una estimación atenuada a partir de los win rates globales.
2. Se toma el win rate empírico de la disposición propia contra la rival y se compara con lo esperado a partir de los win rates globales de ambas disposiciones.
3. Ese efecto específico se aplica como un ajuste ponderado en log-odds a la probabilidad de facción.
4. El optimizador evalúa las 720 permutaciones con estas probabilidades, calcula victorias esperadas y probabilidades de 3+, 4+ y 5+ victorias. El asistente de pairing usa el mismo motor.

**Limitación importante:** MiniHeadQuarters no publica una estadística conjunta por cada combinación exacta de facción propia, facción rival y dos disposiciones. Por tanto, la probabilidad final es una estimación combinada a partir de dos tablas empíricas, no una tasa histórica observada para esa combinación completa. La app muestra las muestras de facción/disposición que alimentan cada estimación.

Algunas selecciones de la lista original pueden no tener datos competitivos 40K claros (por ejemplo, Adeptus Titanicus) o tener una muestra reciente muy pequeña. Se mantienen las opciones en la interfaz, se indica la falta de datos y no se inventan resultados.

## Equipo

Se mantiene la opción de guardar/cargar tu equipo propio como archivo JSON. La descarga se realiza en el dispositivo donde abras la app.
