# Historial de pruebas: cómo actualizarlo

Carpeta: `pruebas/`. La página es `pruebas/index.html` y se abre desde la pestaña "Historial de pruebas" del dashboard.

Se usa cuando el responsable de la cuenta escribe "actualiza las pruebas", "actualiza este testeo" o pega un texto que empieza con "Actualiza las pruebas de {CLIENTE}, campaña {CAMPAÑA}:" (lo genera el botón "Copiar para Claude" de la página).

## Archivos

- `notas_originales.csv`: texto literal de cada nota, una por línea con el formato `clave|nota`. Los saltos de línea dentro de una nota van como `\n`. La clave sigue el patrón `CLIENTE-CAMPAÑA-NN` (LF, T1, TA, PA, ZY). El texto original de cada nota se copia tal cual, sin corregirlo.
- `registros.json`: la clasificación. Cada registro tiene cliente, campana, area (solo MDIC: Inner, Outer o Ambas), nid (la clave de la nota), cre (creativo con el que se probó), cond (condición extra), gana y pierde (listas de `[tipo, etiqueta]`), r y conf.
  - `r`: `comp` (gana contra pierde), `mejor` (solo gana), `malo` (solo pierde), `inconcluso`, `obs` (observación sin variable), `regla` (no usar nunca).
  - `conf`: `firme` o `debil` (pocos números, "seems", "slightly", "appears").
  - Tipos: `hl`, `callout`, `boton`, `loc`, `pb`, `ps`, `badge`, `intro`, `precio`, `formato`, `cre`.
  - Para `hl` la etiqueta es el id del catálogo `hls` dentro de `registros.json`. Si el headline no existe, se agrega al catálogo con su texto exacto.
- `construir.py`: arma `datos.js` y revisa las alertas. `reconstruir.py` lo corre en cada actualización del dashboard.
- `semilla_notas_2026-11-14.py`: carga inicial. No se vuelve a correr porque sobrescribiría `registros.json`.

## Pasos

1. Leer el texto que pegó el responsable de la cuenta y separar cada nota. Si no dice cliente o campaña, preguntar.
2. Agregar cada nota a `notas_originales.csv` con una clave nueva, sin cambiarle una letra.
3. Agregar los registros a `registros.json` con un script `python3 -`: ids `P` correlativos, `origen` con la fecha del día. Usar las mismas etiquetas que ya existen (revisar las de ese cliente antes de inventar una). Una nota que compara dos cosas distintas se parte en dos registros con el mismo `nid`.
4. Correr `python3 pruebas/construir.py` y revisar que no haya error y que las alertas tengan sentido.
5. Abrir la página y confirmar que las notas nuevas aparecen en "Notas originales" de su campaña.
6. Reportar al responsable de la cuenta cuántas notas entraron, cómo quedó clasificada cada una y cualquier contradicción nueva.

## Sección "Qué probar después" (por campaña)

La calcula la página sola, con las mismas notas y con el bloque `rinde_hoy` que `construir.py` saca de `perf_{C}.json` (anuncios con gasto en los últimos 30 días, ordenados por good leads). Cambia cada vez que entran notas nuevas o se actualiza el dashboard, sin editarla a mano.

- Combinación base: lo mejor de cada variable en la campaña; a falta de notas ahí, lo mejor del cliente sin resultados en contra. El creativo y la intro solo salen de la propia campaña. Cuando las notas callan el creativo, la base toma el anuncio activo con más good leads.
- Cada propuesta cambia una sola variable sobre la base. Prioridad alta: headlines que ganaron en otra campaña del cliente sin perder nunca, y desempates de headlines. Baja: lo que solo tiene notas débiles, headlines de otros clientes y headlines que en otros clientes perdieron más de lo que ganaron.
- Quedan fuera: variantes que perdieron sin ningún resultado a favor, reglas de "no usar", el callout de Keep Your Gums fuera de ThinArch, headlines sin texto, etiquetas genéricas ("Con price badge") y Formato y diseño, que va pegado al creativo. "$251/mo" y "$251+/mo" cuentan como la misma variante.

## Reglas del responsable de la cuenta (2026-11-14)

- Todo es intercambiable entre campañas del mismo cliente, menos el creativo.
- El callout "Get All New Teeth & Keep Your Gums!" solo se usa en ThinArch. Si aparece en otra campaña (en Meta o en una nota), se avisa.
- Callouts, botones, badges y precios funcionan o no según el creativo con el que van. Siempre registrar el creativo (`cre`) cuando la nota lo dice.
- El headline es la única variable que no depende del creativo. Un headline que gana en una nota y pierde en otra es una contradicción real.
- Las notas salen tras dos semanas o más de análisis. La fecha no hace falta.
- En CSSD, Second Opinion cuenta como Lower Funnel. Las notas de PrecisionArch de CSSD quedaron fuera por ahora (el bloque que llegó era copia de Lower Funnel).
- HL4, HL4 Receive, Receive Price y ONLY HL todavía no tienen texto. el responsable de la cuenta lo pasará más adelante; entonces se actualiza el catálogo `hls`.
- GT1D, GANTI1D y GAYTI1D son "Get All New Teeth in 1 Day".
