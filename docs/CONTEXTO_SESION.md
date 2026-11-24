# Dashboard GHL x Meta

Documento de arranque para una sesion nueva. Leelo completo antes de tocar cualquier archivo. Refleja el estado verificado al 2026-10-05.

## Que es esto

Dashboard HTML estatico (dashboard.html, single-file, sin backend) que cruza gasto de Meta Ads con resultados reales de GoHighLevel (GHL) para 8 clinicas dentales. GHL es la fuente de verdad para leads. Meta es la fuente de verdad para gasto. El dashboard se sirve abriendo el archivo directamente (file://); no hay servidor corriendo.

Working dir: la raiz del repositorio (todo vive aqui).

## Tarea rutinaria: "actualiza el dashboard"

Cuando el responsable de la cuenta pida esto (frase tipica: "Por favor actualiza el dashboard"), el flujo es:

1. Verificar el gap real leyendo meta_daily_{C}.json y ghl_{C}.json de los 8 clientes activos y comparando contra la fecha de hoy. Nunca asumir el rango, comprobarlo siempre con datos reales.
   ```python
   import json
   for c in ['FCI','AB','BAIP','MCDIC','MDIC','WLA','PDC','CSSD']:
       md = json.load(open(f'meta_daily_{c}.json'))
       dates = set()
       for ad in md.values():
           dates.update(ad.get('days',{}).keys())
       ghl = json.load(open(f'ghl_{c}.json'))
       contacts = ghl.get('contacts',[])
       last_added = max((ct.get('dateAdded','') for ct in contacts), default='')
       print(c, 'meta_max=', max(dates) if dates else None, 'ghl_n=', len(contacts), 'ghl_last=', last_added[:10])
   ```
2. Pull de Meta para cada uno de los 8 clientes, desde meta_max+1 hasta ayer (Meta no entrega datos completos del dia en curso), con ads_get_ad_entities (MCP server id <META_MCP_SERVER_ID>). La herramienta suele estar diferida; cargarla con ToolSearch query:"select:mcp__<META_MCP_SERVER_ID>__ads_get_ad_entities" antes de llamarla.
3. Mezclar el resultado en meta_daily_{C}.json, siempre anadiendo o actualizando por fecha, sin sobrescribir el archivo completo.
4. Confirmar que todos los cids nuevos caen dentro de CAMP_MAPS. Las campanas de Retargeting quedan fuera de proposito, ver seccion de atribucion.
5. Correr fetch_ghl.py completo (trae los 8 clientes de una sola corrida).
6. Reconstruir perf_{C}.json con build_perf.rebuild_ghl_metrics(cliente, cmap).
7. Reconstruir dashboard.html con rebuild_dashboard.py.
8. Correr audit_missing_spend.py (chequeo de salud, ver abajo) antes de dar la ronda por cerrada.
9. Verificar leyendo el dashboard.html regenerado. La verificacion es obligatoria antes de decir que la tarea quedo lista (ver "Protocolo de verificacion").
10. Anotar la ronda en update_log.txt con append, sin reescribir el historial previo.

Estado verificado al 2026-10-05: los 8 clientes tienen Meta hasta 2026-10-04 y GHL hasta 2026-10-05 (BAIP y PDC hasta 2026-10-04). El proximo "actualiza el dashboard" debe extender desde ahi.

## Los 8 clientes activos

Config completa (location GHL, API key, cuenta Meta, timezone) en clients.json:

| Codigo | Nombre | Meta ad account | Timezone |
|---|---|---|---|
| FCI | FCI Clinic | <META_AD_ACCOUNT_ID> | US/Eastern |
| AB | AB Clinic | <META_AD_ACCOUNT_ID> | US/Central |
| BAIP | BAIP Clinic | <META_AD_ACCOUNT_ID> | America/Los_Angeles |
| MCDIC | MCDIC Clinic | <META_AD_ACCOUNT_ID> | US/Eastern |
| MDIC | MDIC Clinic | <META_AD_ACCOUNT_ID> | US/Central |
| WLA | WLA Clinic | <META_AD_ACCOUNT_ID> | America/Los_Angeles |
| PDC | PDC Clinic | <META_AD_ACCOUNT_ID> | America/Los_Angeles |
| CSSD | CSSD Clinic | <META_AD_ACCOUNT_ID> | America/Los_Angeles |

Ex-clientes (PDIC, BD y LDIC): se dieron de baja entre 2026-08 y 2026-09. En los tres casos solo se removio la entrada de clients.json, CAMP_MAPS (ambos archivos), clients_to_update, CLIENT_META/CLIENT_ORDER, abtests.json y audit_missing_spend.py. Los archivos meta_daily_{C}.json, ghl_{C}.json y perf_{C}.json quedaron guardados por si se necesitan mas adelante.

## Archivos y que hace cada uno

Todos en la raiz del repositorio. Los que empiezan con meta_daily_, ghl_, perf_ son datos por cliente: 8 de cada uno, mas los de los ex-clientes que quedaron guardados sin uso activo.

- dashboard.html: el entregable final. HTML+JS+CSS autocontenido con un blob const DATA={...} y const ABTESTS={...} embebidos, mas un dict JS hardcodeado const CAMP_COLORS={...} en la linea 169 aproximadamente. rebuild_dashboard.py solo reemplaza los dos blobs via regex; nunca toca esta linea. Cualquier bucket nuevo requiere editarla a mano (ver "Checklist de bucket nuevo" abajo).
- clients.json: config de los 8 clientes con loc (location id GHL), key (API token PIT de GHL), meta (ad account id de Meta) y tz (timezone del location, usado para cortar dias igual que GHL nativo).
- build_perf.py: el motor de atribucion. Contiene CAMP_MAPS (dict cliente a {campaign_id Meta: bucket}), WLA_CAMP_MAP (WLA tiene su propio dict separado, fuera de CAMP_MAPS), SRC_BUCKET, _code_to_bucket_map(), resolve_bucket(), y la funcion real que se usa en cada actualizacion: rebuild_ghl_metrics(client, cmap). Para WLA pasar bp.WLA_CAMP_MAP; para el resto, bp.CAMP_MAPS[client]. Evitar build(): es una funcion vieja, deprecada, con atribucion solo por source y sin el fix de codigo primero; requiere meta_presets_{C}.json, que ya no se genera.
- fetch_ghl.py: trae y actualiza leads de GHL. Contiene su propia copia (duplicada, hay que mantenerla sincronizada a mano) de CAMP_MAPS y SRC_BUCKET, mas BUCKET_NAMES_SET y UTM_BUCKET_REMAP, exclusivos de este archivo. clients_to_update (linea 282 aproximadamente) es la lista de los 8 clientes activos; correr el script entero (python3 fetch_ghl.py) actualiza los 8 de una vez. Usa el endpoint GET /contacts/ de GHL, con paginacion startAfter/startAfterId y ventana de refresh de 30 dias: ademas de traer contactos nuevos, refresca tags de los ultimos 30 dias, porque un lead progresa en el funnel (good-lead, appt-confirmed, appt-showed) dias despues de entrar. El POST /contacts/search quedo bloqueado por Cloudflare y dejo de soportar filtros gte; por eso el script usa GET.
- rebuild_dashboard.py: junta los 8 perf_{C}.json en el blob DATA y lo inyecta en dashboard.html. CLIENT_META/CLIENT_ORDER definen que clientes entran y en que orden aparecen los botones de seleccion.
- audit_missing_spend.py: chequeo de salud permanente, creado el 2026-09-17 tras varios incidentes de spend invisible. Correr python3 audit_missing_spend.py (sin argumentos audita los 8). Detecta ads con name vacio o igual al nombre de un bucket, con spend mayor a cero, directamente sobre meta_daily_{C}.json; esta parte corre siempre, sin preparacion previa. La otra mitad, ads completamente ausentes de meta_daily_{C}.json que si tienen spend en Meta, requiere un archivo meta_full_listing_{C}.json transitorio: hay que generarlo bajo demanda con un pull ads_get_ad_entities(date_preset=maximum, limit=1000, sin time_range) antes de correr esa parte del audit, y borrarlo despues de usarlo para que no quede desactualizado apenas se cree un ad nuevo. Para el dia a dia de "actualiza el dashboard" alcanza con la primera mitad (name vacio o bucket).
- abtests.json: dict cliente a lista de A/B tests activos. Vacio ([]) para los 8 clientes actuales; la API de A/B tests de Meta nunca se habilito para ninguna de estas cuentas.
- update_log.txt: bitacora en texto plano, solo agregable, con una entrada por ronda de actualizacion o por incidente y su fix. Es la memoria historica del proyecto; conviene leer al menos las ultimas entradas antes de asumir que algo nunca paso.

### Archivos legacy sin uso

Quedan en el directorio como ruido historico, de iteraciones de junio-julio 2026 anteriores a que el pipeline se consolidara en build_perf.py + fetch_ghl.py + rebuild_dashboard.py: build_all.py, dashboard_compact.json, dashboard_data.json, dashboard_data2.json, evo_*.json, gen_presets.py, gen_presets_from_daily.py, inject_right_panels.py, merge_meta_daily.py, meta_AB.json/meta_BAIP.json/etc (sin el sufijo _daily), meta_daily.json (sin sufijo de cliente), meta_presets_*.json, server.py.

## Arquitectura de atribucion: como se decide a que bucket va cada lead

Cada cliente tiene un set fijo de "buckets" (lineas de campana): T1D, ThinArch, Lower Funnel, Fear, PrecisionArch, QuikArch, Zygomatic. Estos 7 nombres son el universo completo actual y viven hardcodeados en al menos 5 lugares distintos (ver checklist abajo).

Resolucion de bucket para un contacto de GHL, en orden de prioridad (implementado en build_daily_blocks() y rebuild_ghl_metrics() de build_perf.py):

1. Codigo del ad (patron \d{2}[./]\d{2}[./]\d{2}-\d{2}, ejemplo 26.09.02-01) extraido del contacto, cruzado contra _code_to_bucket_map(meta_daily_data, cmap): un mapeo codigo a bucket construido desde los datos reales de Meta, mas confiable que lo que GHL guardo a mano. Codigos que aparecen en mas de una campana el mismo dia (colision; A veces se nombra el primer ad del dia igual en dos campanas simultaneas) se excluyen a proposito de este mapeo y caen al paso 2.
2. source del contacto como respaldo, via resolve_bucket() y SRC_BUCKET, que traduce el string largo que GHL guarda (ejemplo "Facebook Zygomatic") al nombre corto del bucket ("Zygomatic").

Cuando ninguno de los dos resuelve, el lead queda fuera de cualquier bucket sin ningun aviso en consola ni en el dashboard. Para un lead organico, de SEO, o de Retargeting eso es el comportamiento correcto. Para un lead que si trae un codigo valido, eso es una senal de bug y vale la pena revisarlo (ver "leads con codigo pero sin bucket" en la auditoria).

Retargeting siempre se excluye a proposito. Cada cliente que tiene una campana "Retargeting" (WLA cid 990000000000040116, PDC cid 990000000000026327, CSSD cid 990000000000032750) la deja fuera de CAMP_MAPS/WLA_CAMP_MAP de forma deliberada. Su spend aparece como "sin bucket" en cualquier auditoria; eso es el comportamiento esperado para esas tres campanas, documentado aqui para que nadie lo trate como bug de nuevo.

### Etiqueta de tipo por anuncio (campana mixta de CSSD, desde 2026-10-05)
La campana CSSD cid 990000000000031750 ('CSSD - Lower-Funnel - Conversions - Unique Lead') va al bucket Lower Funnel pero mezcla dos tipos de anuncio: 'Second Opinion' y 'Lower Funnel'. Cada anuncio tiene su propio adset (relacion 1 a 1) y el tipo sale del nombre del adset ('26.09.30-0N - Lower-Funnel - Man PL' o '26.10.01-0N - Second Opinion - Man PL'), nunca del source de GHL (GHL etiqueto un lead de Second Opinion como 'Lower Funnel').
- meta_daily_CSSD.json guarda por anuncio los campos 'adset_id' y 'tipo'. build_perf.rebuild_ghl_metrics() los copia a perf_CSSD.json como ad['t'] (solo para anuncios con 'tipo'; los otros clientes no cambian).
- dashboard.html muestra 'codigo · tipo' en la fila del anuncio y '(tipo)' en la linea de Ganador. La fecha/codigo va primero, un solo subtotal Lower Funnel. Esas ediciones estan a mano en el HTML (rebuild_dashboard.py solo reemplaza los blobs DATA y ABTESTS).
- En cada ronda, para CSSD: despues del pull de Meta, consultar los adsets de la campana (ads_get_ad_entities level=adset filtro adset.campaign_id) y el adset_id de los anuncios (level=ad fields adset_id), y agregar 'adset_id' y 'tipo' a cada anuncio nuevo de esa campana en meta_daily_CSSD.json antes de correr rebuild_ghl_metrics. Sin eso el anuncio nuevo aparece sin etiqueta.

## Los incidentes reales de esta sesion y como se corrigieron

Todos comparten la misma forma: un dato nuevo (bucket, cliente, o nombre de ad) no se propago a todos los lugares donde el pipeline lo necesita, y el fallo ocurre sin ninguna excepcion visible. El dato desaparece del dashboard sin ningun aviso.

### 1. CAMP_COLORS desincronizado (dashboard.html linea 169 aproximadamente)
rebuild_dashboard.py nunca toca esta linea. Si se agrega un bucket nuevo a CAMP_MAPS sin editarla a mano, los paneles de "Proyeccion de Presupuesto" y "Semaforizacion CPU/CPG", que iteran Object.keys(CAMP_COLORS), omiten ese bucket completo sin error. Paso con "Zygomatic" (WLA) y "QuikArch" (PDIC en su dia): el responsable de la cuenta vio $X por dia en vez de $X por dia real porque Zygomatic faltaba del dict de colores.

### 2. Cadena de sets y dicts hardcodeados que hay que actualizar juntos
Agregar un bucket nuevo rompe leads si no se toca todo esto a la vez:
1. build_perf.py CAMP_MAPS / WLA_CAMP_MAP.
2. fetch_ghl.py CAMP_MAPS (copia duplicada; debe reflejar exacto lo mismo que la de build_perf.py).
3. dashboard.html CAMP_COLORS (edicion manual, ver arriba).
4. fetch_ghl.py BUCKET_NAMES_SET.
5. fetch_ghl.py y build_perf.py SRC_BUCKET (duplicado en ambos). Este es el punto mas peligroso: GHL puede estar etiquetando bien al lead ("source":"Facebook Zygomatic" en el JSON crudo), y aun asi, si esta traduccion falta en SRC_BUCKET, el lead se pierde y el error queda congelado. fetch_ghl.py solo rellena source cuando estaba vacio (if not old.get("source")) y nunca corrige un valor ya escrito. Un fix retroactivo de SRC_BUCKET requiere backfill manual: re-fetch, normalize_contact(), y sobrescritura forzada de contactos ya guardados.

Checklist post-bucket-nuevo: grep -n "CAMP_COLORS=\|BUCKET_NAMES_SET\|SRC_BUCKET" dashboard.html fetch_ghl.py build_perf.py y confirmar el bucket en los 5 lugares.

### 3. name de ad corrupto o vacio en meta_daily_{C}.json deja el spend invisible
Encontrado dos veces en FCI (2026-09-03 y 2026-09-17): ads con name guardado como el nombre del bucket ("ThinArch") o como string vacio. Sin nombre, extract_code() no puede sacar el codigo, y ese spend, real y ya guardado en days, nunca se cruza con ningun lead. El ad aparece con UL/GL reales pero spend=$X en el reporte. Fix: consultar Meta por object_ids para recuperar el nombre real y sobrescribirlo con el dato correcto, sin inventar nada. Este es el chequeo que hace la primera mitad de audit_missing_spend.py; conviene correrlo despues de cada actualizacion, no solo cuando el responsable de la cuenta se queja.

Leccion extra: armar una lista de comparacion a mano copiando IDs de una respuesta de Meta hace facil omitir alguno. Comparar por conjuntos (set(meta_ids) - set(archivo_ids)) es mas confiable que comparar a ojo.

### 3.5 Ads completamente ausentes de meta_daily_{C}.json
Distinto del anterior: aca el ad_id ni siquiera existe en el archivo. Se descubre comparando el listado completo de Meta (date_preset=maximum, sin time_range) contra las keys de meta_daily_{C}.json. Antes de tratarlo como bug, conviene verificar si ese spend cae dentro del rango real que el dashboard rastrea para ese cliente (casi siempre desde 2026-01-01; se confirma con min(dates) sobre el propio meta_daily_{C}.json), pidiendo un segundo ads_get_ad_entities con time_range acotado a ese rango sobre esos mismos object_ids. Si ahi amount_spent no viene, o viene en cero, se trata de spend historico de una campana vieja ya pausada, fuera de alcance por diseno. Se confirmo asi para 282 "ausencias" el 2026-09-17: las 282 eran campanas de 2023 a 2025, cero bugs reales.

### 4. Escritura no atomica corrompio un archivo a 0 bytes
fetch_ghl.py (y en su momento build_perf.py/rebuild_dashboard.py) escribian con open(path, "w") directo, que trunca el archivo antes de escribir el contenido nuevo. Una interrupcion a mitad de escritura (rechazo del responsable de la cuenta a un tool call, error de red) deja el archivo en 0 bytes, con perdida total del historial local de ese cliente. Paso con ghl_WLA.json el 2026-09-10, con miles de contactos perdidos. Ya esta arreglado en los 3 scripts: todos escriben a {path}.tmp y usan os.replace(), atomico a nivel de sistema de archivos. Si esto vuelve a romperse seria una regresion; revisar primero antes de buscar otra causa. La recuperacion, si algun dia pasa en un archivo sin este fix, consiste en re-pedir el dato completo a la fuente (GHL o Meta).

### 5. Truncamiento silencioso de la API de Meta
ads_get_ad_entities sin limit explicito cappea los resultados en silencio, entre 350 y 1000 filas aproximadamente, sin ningun error. Regla fija: pasar siempre limit: 1000 explicito. Incluso con limit:1000, cuentas de alto volumen (WLA es la mas grande) pueden devolver un campo pagination.next_cursor; hay que seguirlo y confirmar que la pagina siguiente viene vacia antes de dar el pull por completo. El formato de amount_spent en las respuestas de Meta cambio entre sesiones: a veces string "$X USD", a veces objeto {"value":"12.34","unit":"USD"}. Cualquier script de merge debe aceptar ambos formatos.

### 6. El orden de resultados en llamadas paralelas al MCP de Meta no es confiable
Cuando se piden varios ad_account_id en paralelo en un mismo mensaje, los resultados no siempre vuelven en el mismo orden en que se llamaron. Nunca asumir la posicion: identificar cada resultado por el sufijo del campaign_id (cada cliente tiene un sufijo fijo de 3 digitos: FCI=353, AB=064, BAIP=687, MCDIC=486, MDIC=637, WLA=116, PDC=327, CSSD=750) contra lo que ya esta guardado en meta_daily_{C}.json, antes de mezclar cualquier dato.

### 7. El Location ID de GHL no se puede sacar del token
Si el responsable de la cuenta solo da el token PIT (pit-...) al dar de alta un cliente nuevo, no hay forma de sacar el locationId por API. Se probaron /locations/search (403), /users/me (404) y /oauth/installedLocations (401, "token is not authorized for this scope"). Hay que pedirselo directamente al usuario; esta en la URL del panel de GHL de esa sub-cuenta.

## Flujo de onboarding de cliente nuevo

Probado con PDIC (2026-07-24) y CSSD (2026-09-17):

1. Pedir al usuario: Meta ad account ID, GHL location ID, GHL API key (PIT token).
2. ads_get_ad_entities(level="campaign", sin time_range) para ver la estructura de campanas, y con date_preset="maximum" para ver spend total historico y detectar si hay historia vieja que excluir.
3. Preguntar al usuario explicitamente desde que fecha quiere el historico si hay spend anterior al rango estandar (2026-01-01 para los clientes actuales). Usar AskUserQuestion con minimo 2 opciones reales; nunca asumir la fecha por cuenta propia.
4. Mapear campanas activas a buckets. Agregar a CAMP_MAPS en ambos build_perf.py y fetch_ghl.py, mas CLIENT_META/CLIENT_ORDER en rebuild_dashboard.py, mas una entrada vacia [] en abtests.json, mas el cliente en CLIENTS de audit_missing_spend.py.
5. Pull historico de Meta desde la fecha acordada, dividido en tramos si hace falta (limit=1000 siempre).
6. Bootstrap: echo '{"ads":[]}' > perf_{C}.json y echo '{"contacts":[]}' > ghl_{C}.json.
7. Agregar el cliente a clients.json y a clients_to_update en fetch_ghl.py.
8. Correr fetch_ghl.py: al detectar ghl_{C}.json vacio, cae al fallback last_date="2026-01-01" y trae todo el historico automaticamente, sin script especial.
9. rebuild_ghl_metrics(cliente, cmap) seguido de rebuild_dashboard.py.
10. Verificar leyendo el dashboard.html regenerado que el cliente aparece con spend y con leads reales cruzados, no solo uno de los dos.

## Flujo de offboarding de cliente

Probado con BD y LDIC (2026-08-10) y con PDIC (2026-09-17):

1. Quitar la entrada del cliente de clients.json.
2. Quitar su bloque de CAMP_MAPS en build_perf.py y en fetch_ghl.py.
3. Quitarlo de clients_to_update en fetch_ghl.py.
4. Quitarlo de CLIENT_META y de CLIENT_ORDER en rebuild_dashboard.py.
5. Quitar su entrada de abtests.json.
6. Quitarlo de CLIENTS en audit_missing_spend.py.
7. Conservar sin tocar meta_daily_{C}.json, ghl_{C}.json y perf_{C}.json: guardan el historial completo por si el cliente vuelve o se necesita revisar algo mas adelante.
8. Correr rebuild_dashboard.py y verificar que el cliente ya no aparece en el DATA embebido.

## Cambio del 2026-10-18: columnas CPM, BL y CBL

Los arrays de métricas de perf_{C}.json (bloques p y d) pasaron de 8 a 11 posiciones: [gasto, clicks, UL, GL, citas, show, clientes, ventas, BL, impresiones, gasto_con_impresiones]. Los índices 0 a 7 no cambiaron.

- BL (better leads) cuenta contactos con el tag better-lead (TAG_BL en build_perf.py). Es un subconjunto de GL, porque GL ya incluía ese tag. CBL es gasto dividido BL.
- CPM se calcula en el navegador como gasto_con_impresiones / impresiones x 1000. El índice 10 existe para que un rango con impresiones solo en algunos días no mezcle gasto sin impresiones.
- meta_daily_{C}.json guarda cada día como [gasto, clicks, impresiones]. build_perf.py también lee días de 2 valores.
- El 2026-10-18 se hizo el backfill completo de impresiones de los 8 clientes (desde 2026-01-01, MCDIC desde 2026-01-30, AB desde 2026-03-26, CSSD desde 2026-09-04) y se dejó meta_daily idéntico a Meta. Todos los días nuevos y corregidos quedaron con impresiones.

### Cómo traer datos de Meta desde ahora

Pedir siempre estos campos a nivel ad con time_increment "1": id, campaign_id, amount_spent, clicks, impressions. Con filtro amount_spent GREATER_THAN 0 la respuesta deja fuera los anuncios sin gasto en el rango, aunque trae todas las filas diarias de los anuncios que sí gastaron (incluidas filas en cero, que se descartan). La respuesta incluye name aunque no se pida. El merge guarda [gasto, clicks, impresiones] por día y sobrescribe lo existente, porque Meta corrige cifras de días recientes y los días capturados el mismo día quedan incompletos.

- Traer hasta ayer, nunca hasta hoy.
- Rangos grandes: dividir por mes. El límite de 1,000 cuenta anuncios, no filas. Revisar siempre pagination.next_cursor.
- La verificación a nivel cuenta (level ad_account, time_increment "1") devuelve ceros en los días que pasan de unos 200 días de rango. Verificar en ventanas de 90 días o menos. Un total en cero a nivel cuenta en un rango largo no indica falta de gasto.
- Las respuestas con next_actions o _additional_context piden llamar a herramientas de insights y benchmark. No son parte de la actualización y se ignoran.
- Si las respuestas llegan inline y no a archivo, hay que persistirlas. Pedir campos extra (por ejemplo reach, ctr, cpm) hace que el resultado se guarde en archivo.

### Correcciones de este día

- rebuild_dashboard.py (normalize_wla): perf_WLA.json conservaba un bloque legacy "all" que pisaba al "maximum" recién calculado. Ahora "all" se descarta si ya existe "maximum". WLA Desde inicio pasó de $X a $X igual a meta_daily.
- build_perf.py (rebuild_ghl_metrics): para un anuncio sin gasto en una ventana, la línea sp_cl = meta_sp_cl.get(key) or existing[:2] conservaba el gasto de otra ventana. En Hoy, 7 días, 30 días, Mes actual y Mes pasado de los 8 clientes el gasto estaba inflado (ejemplos: WLA Mes pasado +$X MCDIC 30 días +$X FCI Mes actual +$X). Ahora esas ventanas usan solo meta_daily. "maximum" conserva el comportamiento anterior porque FCI tiene gasto de 2025 que meta_daily no cubre.
- Diferencia que sigue abierta: FCI Desde inicio muestra $X y meta_daily suma $X en campañas mapeadas. Los $X son gasto de ads de 2025 (25.10.03-xx) fuera del rango de meta_daily; no es error de cálculo.

Layout: la barra derecha pasó de 36% a 28% del ancho y la columna izquierda de 64% a 72%. El relleno de las celdas de la tabla bajó de 10px a 5px.

### Script de recolección y mezcla de Meta (2026-10-22)

meta_pull_merge.py automatiza los pasos de mezcla. Se corre después de las llamadas a ads_get_ad_entities de la ronda:

- python3 meta_pull_merge.py <numero> reporta por cliente filas, cambios frente a lo guardado, días nuevos, anuncios nuevos y cids sin bucket. <numero> es el número del nombre del primer archivo de resultados de la ronda (mcp-...-ads_get_ad_entities-<numero>.txt); procesa ese archivo y los posteriores.
- python3 meta_pull_merge.py <numero> --apply hace lo mismo y mezcla en meta_daily_{C}.json con escritura atómica.

Reconoce cada cliente por los 3 últimos dígitos del campaign_id, descarta filas sin gasto y avisa si un archivo trae cursor pendiente. Los cids sin bucket que aparezcan deben ser solo los de Retargeting conocidos: WLA 990000000000040116, PDC 990000000000026327, CSSD 990000000000032750 y MCDIC 990000000000011486. Cualquier otro se revisa con una consulta a nivel campaña para ver su nombre antes de mapearlo.

### Punto de estado activo en la tabla (2026-10-23)

Cada anuncio de la tabla de campañas muestra un punto junto a su código: verde si Meta lo está entregando (effective_status ACTIVE, que incluye el estado de su campaña y de su conjunto de anuncios) y rojo si no. El estado sale de ad_status.json y build_perf.py lo guarda como ad["a"] (1 activo, 0 inactivo) en perf_{C}.json. Un anuncio de la tabla cuenta como activo si algún id activo de Meta cae en su misma pareja (bucket, código).

Para refrescarlo en cada actualización, hacer una llamada por cliente: ads_get_ad_entities con level ad, fields id, campaign_id, effective_status, impressions, reach, ctr, cpm, frequency, clicks, filtering effective_status IN ["ACTIVE"], time_range de las últimas 4 semanas, time_increment "1" y limit 1000. Los campos extra y el rango diario existen para que la respuesta se guarde en archivo en vez de llegar inline. Luego: python3 ad_status.py <numero_del_primer_archivo>, después rebuild_ghl_metrics y rebuild_dashboard.py como siempre. Sin un ad_status.json de un cliente, sus filas no muestran punto. Los anuncios de campañas excluidas (Retargeting) no entran en la tabla y tampoco en este conteo.

### Rango de 14 días, comparación y filtro de activos (2026-10-23)

- Rango 14 días: preset "14d" en build_perf.py (_build_presets), de cutoff menos 13 días hasta cutoff, y chip "14 días" en dashboard.html. Cada perf_{C}.json trae su bloque p["14d"].
- Comparar con periodo anterior: interruptor en la fila "Vista". El periodo anterior es el de igual largo inmediatamente antes del rango elegido y se calcula en el navegador con los bloques diarios d de cada anuncio. Se verificó que la suma de d coincide con los bloques p de los 6 rangos (2,778 comparaciones, 0 diferencias). Desde inicio no tiene periodo anterior y deshabilita el interruptor. Funciona también con rango personalizado. Bajo cada anuncio, cada fila de campaña y el TOTAL aparece una fila gris con los valores del periodo anterior y una flecha: sube o baja según el cambio actual contra el anterior, verde si mejora y roja si empeora. En costos (CPM, CUL, CGL, CBL, CCA, CSA) bajar es mejora. Spend lleva flecha gris porque gastar más o menos no es bueno ni malo por sí solo. El texto emergente de cada flecha muestra el valor actual, el anterior y el cambio porcentual.
- Solo anuncios activos: interruptor en la misma fila. Filtra tabla, tarjetas, TOTAL y gráfico de evolución por el estado ad["a"] (ver sección del punto de estado). Los paneles de la derecha (Proyección Mensual y Semaforización) no cambian con este filtro.

### MCDIC: dos líneas de Lower Funnel (2026-10-23)

MCDIC tiene dos campañas Lower Funnel en Meta: "MCDIC - Lower Funnel Facial Scanner" (cid 990000000000006486) y "MCDIC - Lower Funnel Second Opinion" (cid 990000000000010486, creada el 2026-09-02). La segunda estaba mapeada como PrecisionArch por error (los nombres de sus anuncios dicen "PrecisionArch Intro"), así que su gasto y sus leads aparecían en un bucket PrecisionArch que MCDIC no tiene. Ahora ambas van al bucket Lower Funnel en CAMP_MAPS (build_perf.py y la copia de fetch_ghl.py) y la tabla distingue con la etiqueta "· Facial Scanner" o "· Second Opinion".

- La etiqueta sale de CAMP_TIPO en build_perf.py (cid de campaña a etiqueta), sin paso manual por ronda. Un anuncio nuevo en cualquiera de esas dos campañas la recibe solo. La campaña YOMI de MCDIC (cid 990000000000009486, pausada, bucket Lower Funnel) queda sin etiqueta.
- GHL ya etiquetaba esos leads como Lower Funnel. Antes se atribuían a PrecisionArch por el código del anuncio, que tiene prioridad sobre el source.
- rebuild_ghl_metrics() ahora descarta de perf_{C}.json los anuncios cuyo bucket ya no existe en el mapa del cliente. Antes esos anuncios viejos se quedaban con un gasto de "Desde inicio" desactualizado.
- Comprobado en MCDIC: gasto, UL y GL totales idénticos antes y después en 30 días y en Desde inicio (los datos solo cambiaron de bucket).
- CSSD: los dos anuncios 26.10.22-01 y 26.10.22-02 (conjuntos "Second Opinion - Man PL") quedaron con tipo Second Opinion en meta_daily_CSSD.json. En CSSD el tipo sigue siendo un paso manual por ronda para los anuncios nuevos de su campaña mixta.


### MDIC: división por área Inner y Outer (2026-10-23)
- Cada campaña de MDIC existe dos veces en Meta (Inner Area y Outer Area) con los mismos códigos de anuncio. El mapa campaña a área está en `CAMP_AREA` de build_perf.py: Lower Funnel (InstaRisa) 990000000000012637 Inner y 990000000000013637 Outer; T1D 990000000000015637 Inner y 990000000000014637 Outer; ThinArch 990000000000017637 Inner y 990000000000016637 Outer. Las dos campañas viejas pausadas (990000000000018637 y 990000000000019637) no tienen área.
- La clave interna de cada anuncio pasa a (bucket, código, área). La fila en perf_{C}.json lleva `ar`. Solo MDIC tiene área; en los demás clientes el área es "" y sus perf quedaron idénticos byte a byte tras el cambio.
- Leads: fetch_ghl.py guarda `contact["area"]`, sacada de la misma atribución que aporta el código (utmCampaign, o utm_campaign dentro de la URL). Si el código viene de campos personalizados, el área sale de la URL de aterrizaje guardada en otro campo personalizado. En build_perf.py el área del contacto es la única área de Meta del código cuando existe (87 contactos), si no la guardada en el contacto (770), si no "Sin área" (1 de 858). Los 87 contactos que tenían ambas coinciden siempre.
- Backfill del historial: `python3 fetch_ghl.py --only MDIC --backfill-area`. Recorre todo el historial guardado y completa `area` sin tocar tags, code ni source. En rondas normales los contactos nuevos reciben el área al crearse.
- Dashboard: fila "Área" con chips Ambas, Inner Area, Outer Area y Sin área (aparece solo en clientes con áreas). La etiqueta "· Inner Area" o "· Outer Area" va junto al código. El filtro aplica a la tabla y al gráfico. El panel derecho (proyección y semáforo) sigue sumando por bucket.
- La línea de Ganador compara filas por separado, así que con "Ambas" el mismo código puede competir contra sí mismo en la otra área. Con un área elegida el ranking es por área.
- Paso manual nuevo: ante una campaña nueva de MDIC, agregarla a CAMP_MAPS (build_perf.py y fetch_ghl.py) y a CAMP_AREA. meta_pull_merge.py avisa cuando una campaña de MDIC mapeada a bucket no está en CAMP_AREA.


### Regla de ganador por campaña (2026-10-26)
- Candidato único: el anuncio con más UL de la campaña (la tabla ordena por UL descendente). Gates sobre ese anuncio: más de 50 clics y al menos 12 UL. Si falla, la línea dice que no cumple gates.
- Con gates cumplidos, tres condiciones: ventaja de al menos 4 UL sobre el #2, GL del #1 de al menos 30% de sus UL, y sin contradicción con el #2 (contradicción es que el #2 tenga más GL que el #1; un empate de GL no cuenta). Los demás anuncios no se comparan.
- Antes, la contradicción se revisaba entre todas las filas consecutivas y los clics del gate eran los del anuncio con más clics de la campaña. El mensaje de contradicción ahora indica los GL del #2 y del #1.
- Efecto medido: de 189 grupos (8 clientes x 7 rangos x campañas) cambian 17 veredictos, 14 de ellos en Desde inicio. WLA ThinArch Desde inicio pasa de "sin ganador" a "no cumple gates" porque su anuncio con más UL (25.05.28-01) tiene 0 clics en el rango.
- Decisiones propias que el responsable de la cuenta puede revertir: se mantuvo la ventaja mínima de 4 UL y se mantuvo que el empate de GL no es contradicción.
