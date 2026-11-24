#!/usr/bin/env python3
"""Fetch/refresh GHL contacts for all clients into ghl_{C}.json.

- Usa el endpoint GET /contacts/ (el POST /contacts/search fue bloqueado por
  Cloudflare y dejó de soportar filtros gte sobre dateAdded).
- Ventana de refresh de 30 días: además de agregar contactos nuevos, refresca
  los tags de los ya guardados (los leads progresan en el funnel días después
  de entrar: good-lead, appt-confirmed, appt-showed, client).
"""
import json, os, re, time
from datetime import datetime, timedelta, timezone
from urllib.request import urlopen, Request
from urllib.parse import urlparse, parse_qs, urlencode, unquote
from urllib.error import URLError
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
GHL_URL = "https://services.leadconnectorhq.com/contacts/"
REFRESH_DAYS = 30
BACKFILL_AREA = "--backfill-area" in sys.argv
# --desde AAAA-MM-DD: amplia la ventana de refresco (tags y codigos) hasta esa fecha. Uso puntual.
DESDE = sys.argv[sys.argv.index("--desde") + 1] if "--desde" in sys.argv else None
HEADERS_BASE = {
    "Version": "2021-07-28",
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}

CODE_RE = re.compile(r'\b(\d{2}[./]\d{2}[./]\d{2}-\d{2})\b')

# From build_perf.py
CAMP_MAPS = {
    "AB":    {"990000000000001064":"T1D","990000000000002064":"ThinArch"},
    "BAIP":  {"990000000000003687":"T1D","990000000000004687":"Lower Funnel","990000000000005687":"ThinArch"},
    "MCDIC": {"990000000000006486":"Lower Funnel","990000000000007486":"ThinArch","990000000000008486":"T1D","990000000000009486":"Lower Funnel","990000000000010486":"Lower Funnel"},
    "MDIC":  {"990000000000012637":"Lower Funnel","990000000000013637":"Lower Funnel","990000000000014637":"T1D","990000000000015637":"T1D","990000000000016637":"ThinArch","990000000000017637":"ThinArch","990000000000018637":"Lower Funnel","990000000000019637":"T1D"},
    "FCI":   {"990000000000020353":"ThinArch","990000000000021353":"T1D","990000000000022353":"Lower Funnel"},
    "WLA":   {"990000000000035116":"ThinArch","990000000000036116":"T1D","990000000000033116":"Lower Funnel","990000000000037116":"Fear","990000000000038116":"PrecisionArch","990000000000039116":"Zygomatic","990000000000034116":"Lower Funnel"},
    "PDC":   {"990000000000023327":"ThinArch","990000000000024327":"Lower Funnel","990000000000025327":"T1D"},
    "CSSD":  {"990000000000028750":"PrecisionArch","990000000000029750":"T1D","990000000000030750":"ThinArch","990000000000031750":"Lower Funnel"},
}
SRC_BUCKET = {
    "Facebook T1D":"T1D","Facebook ThinArch":"ThinArch",
    "Facebook Fear":"Fear","Facebook PrecisionArch":"PrecisionArch",
    "Facebook Lower-Funnel":"Lower Funnel","Facebook Lower Funnel":"Lower Funnel",
    "Facebook Reveals":"Lower Funnel","Facebook Reveal":"Lower Funnel",
    "Facebook QuikArch":"QuikArch","Facebook Zygomatic":"Zygomatic",
}

def extract_code(text):
    m = CODE_RE.search(text or "")
    return m.group(1).replace('/', '.') if m else None

# Campo personalizado "UTM Content" del contacto: guarda el anuncio del ULTIMO formulario
# ("26.11.04-02 - ThinArch - Man PL/..."). Los dashboards nativos de GHL agrupan por este campo.
# Un contacto que entro por un anuncio viejo y volvio a llenar el formulario desde otro anuncio
# conserva el primer toque en attributions, pero GHL lo cuenta en el anuncio nuevo
# (caso real 2026-11-13: BAIP ThinArch 26.11.04-02 y 26.07.17-01 con good-lead y cita).
UTM_CF_RE = re.compile(r'^\s*(\d{2}[./]\d{2}[./]\d{2}-\d{2})\s+-\s')

def code_from_utm_field(contact):
    for cf in contact.get("customFields") or []:
        m = UTM_CF_RE.match(str(cf.get("value") or ""))
        if m:
            return m.group(1).replace('/', '.')
    return None

BUCKET_NAMES_SET = {"T1D", "ThinArch", "Lower Funnel", "Fear", "PrecisionArch", "QuikArch", "Zygomatic"}

# Clientes donde el UTM Content usa un nombre distinto al bucket interno del perf
UTM_BUCKET_REMAP = {
    "MDIC": {"InstaRisa": "Lower Funnel", "YOMI": "Lower Funnel"},
    "MCDIC": {"InstaRisa": "Lower Funnel", "YOMI": "Lower Funnel"},
    "FCI": {"InstaRisa": "Lower Funnel"},
}

def extract_bucket_from_utm(utm_content):
    """Extrae el bucket del UTM Content. Formato: 'CODE - BUCKET - ...' o 'CODE - BUCKET - .../...'"""
    # El UTM Content puede tener formato "26.05.27-03 - PrecisionArch - WLA Geo ..."
    # a veces con un "/" separando el nombre del ad del nombre del ad set
    text = (utm_content or "").split("/")[0].strip()
    parts = [p.strip() for p in text.split(" - ")]
    # parts[0] = code, parts[1] = bucket (si existe)
    if len(parts) >= 2 and parts[1] in BUCKET_NAMES_SET:
        return parts[1]
    return None

# Clientes cuyas campanas se duplican por area (Inner/Outer) con los mismos codigos de anuncio.
# Se guarda contact["area"] ("Inner Area"/"Outer Area") para repartir los leads por area en build_perf.py.
AREA_CLIENTS = {"MDIC"}
AREA_RE = re.compile(r'\b(Inner|Outer)[\s+]+Area\b', re.I)

def area_from_text(text):
    t = unquote(str(text or ""))
    m = AREA_RE.search(t)
    return f"{m.group(1).title()} Area" if m else None

def extract_area(contact):
    """Area (Inner/Outer) de la MISMA atribucion que aporta el codigo del anuncio (primera entrada con codigo,
    igual que normalize_contact). Un contacto con varios toques (primer y ultimo) conserva el area del primero.
    El nombre de campana viene en utmCampaign o en utm_campaign dentro de la URL.
    Si el codigo sale del campo UTM Content (ultimo formulario), el area sale de los campos
    personalizados de ese mismo formulario."""
    if code_from_utm_field(contact):
        for cf in contact.get("customFields") or []:
            a = area_from_text(cf.get("value"))
            if a:
                return a
    entries = [contact.get("attributionSource") or {}, contact.get("lastAttributionSource") or {}]
    entries += list(contact.get("attributions") or [])
    for att in entries:
        if not any(extract_code(str(att.get(f) or "")) for f in ("utmContent", "utmKeyword", "pageUrl", "url")):
            continue
        for f in ("utmCampaign", "pageUrl", "url", "utmContent"):
            a = area_from_text(att.get(f))
            if a:
                return a
        return None
    # Sin codigo en la atribucion: el codigo sale de los campos personalizados (formulario), y la URL de aterrizaje
    # con utm_campaign esta en otro campo personalizado del mismo contacto.
    for cf in contact.get("customFields") or []:
        a = area_from_text(cf.get("value"))
        if a:
            return a
    return None

def normalize_contact(contact, cmap, utm_remap=None):
    """Extract source bucket and ad code from a raw GHL contact.
    Priority: UTM Content bucket > source string > utm_campaign ID.
    UTM Content is set at ad creation and is more reliable than source string,
    which can be overwritten by GHL automations.
    """
    bucket = None
    code = code_from_utm_field(contact)  # 0. Ultimo formulario: mismo criterio que GHL
    bucket_names = set(cmap.values())

    # 1. Extract code AND bucket from UTM Content (most reliable source)
    for attr_key in ["attributionSource", "lastAttributionSource"]:
        attr = contact.get(attr_key) or {}
        for field in ["utmContent", "utmKeyword", "url"]:
            val = attr.get(field) or ""
            if not code:
                c = extract_code(val)
                if c:
                    code = c
            if not bucket and field == "utmContent":
                b = extract_bucket_from_utm(val)
                if b:
                    # Remap cliente-específico (ej: InstaRisa → Lower Funnel para MDIC)
                    if utm_remap:
                        b = utm_remap.get(b, b)
                    # Solo aceptar si es campaña válida para este cliente
                    if b in bucket_names:
                        bucket = b
        if code and bucket:
            break

    # 2. Fallback bucket from source string
    if not bucket:
        raw_src = (contact.get("source") or "").strip()
        bucket = raw_src if raw_src in set(cmap.values()) else SRC_BUCKET.get(raw_src)

    # 3. Fallback bucket from utm_campaign ID in URL
    if not bucket:
        for attr_key in ["attributionSource", "lastAttributionSource"]:
            attr = contact.get(attr_key) or {}
            url_str = attr.get("url") or ""
            if url_str and "utm_campaign=" in url_str:
                try:
                    from urllib.parse import urlparse, parse_qs
                    params = parse_qs(urlparse(url_str).query)
                    camp_id = params.get("utm_campaign", [None])[0]
                    if camp_id:
                        bucket = cmap.get(camp_id)
                except:
                    pass
            if bucket:
                break

    # 4. Fallback code/bucket from attributions array (GET endpoint format — attributionSource is empty)
    if not code or not bucket:
        for att in (contact.get("attributions") or []):
            for field in ["utmContent", "utmKeyword", "pageUrl", "url"]:
                val = str(att.get(field) or "")
                if not code:
                    c = extract_code(val)
                    if c:
                        code = c
                if not bucket and field == "utmContent":
                    b = extract_bucket_from_utm(val)
                    if b:
                        if utm_remap:
                            b = utm_remap.get(b, b)
                        if b in bucket_names:
                            bucket = b
            if code and bucket:
                break

    # 5. Fallback code from custom fields
    if not code:
        for cf in contact.get("customFields") or []:
            val = str(cf.get("value") or "")
            c = extract_code(val)
            if c:
                code = c
                break

    # 6. Last resort: search entire contact JSON for an ad code
    if not code:
        c = extract_code(json.dumps(contact))
        if c:
            code = c

    return bucket, code

def ghl_fetch_contacts(loc, key, since_date):
    """Fetch contacts added after since_date from GHL GET endpoint (newest first, stop at old contacts)."""
    headers = dict(HEADERS_BASE)
    headers["Authorization"] = f"Bearer {key}"

    all_contacts = []
    start_after = None
    start_after_id = None
    page = 0

    while True:
        params = {"locationId": loc, "limit": 100, "sortBy": "date_added"}
        if start_after:
            params["startAfter"] = start_after
        if start_after_id:
            params["startAfterId"] = start_after_id

        req = Request(GHL_URL + "?" + urlencode(params), headers=headers)
        try:
            with urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read())
        except URLError as e:
            print(f"    ERROR: {e}")
            break

        contacts = result.get("contacts", [])
        if not contacts:
            break

        page += 1
        # Contacts come newest first; stop when we hit contacts older than since_date
        new_in_page = 0
        for ct in contacts:
            ct_date = (ct.get("dateAdded") or "")[:10]
            if ct_date < since_date:
                print(f"    page {page}: {new_in_page} in window | reached {ct_date} < {since_date}, stopping")
                return all_contacts
            all_contacts.append(ct)
            new_in_page += 1

        print(f"    page {page}: {new_in_page} contacts >= {since_date} (total: {len(all_contacts)})")

        if len(contacts) < 100:
            break
        next_url = result.get("meta", {}).get("nextPageUrl", "")
        if not next_url:
            break
        qp = parse_qs(urlparse(next_url).query)
        start_after = qp.get("startAfter", [None])[0]
        start_after_id = qp.get("startAfterId", [None])[0]
        if not start_after:
            break
        time.sleep(0.2)

    return all_contacts

def process_client(client, clients_cfg):
    cfg = clients_cfg.get(client)
    if not cfg:
        print(f"  {client}: no config"); return

    loc = cfg["loc"]
    key = cfg["key"]
    cmap = CAMP_MAPS.get(client, {})
    utm_remap = UTM_BUCKET_REMAP.get(client, {})
    ghl_path = f"{BASE}/ghl_{client}.json"

    # Load existing
    existing = json.load(open(ghl_path)) if os.path.exists(ghl_path) else {"contacts": []}
    by_id = {c["id"]: c for c in existing.get("contacts", [])}
    existing_dates = [c.get("dateAdded","")[:10] for c in existing.get("contacts", []) if c.get("dateAdded")]
    last_date = max(existing_dates) if existing_dates else "2026-01-01"

    # Ventana: 30 días atrás (refresh de tags) o desde el último contacto si es más antiguo
    refresh_cutoff = (datetime.now(timezone.utc) - timedelta(days=REFRESH_DAYS)).strftime("%Y-%m-%d")
    since_date = min(last_date, refresh_cutoff)
    if DESDE:
        since_date = min(since_date, DESDE)
    if BACKFILL_AREA:
        since_date = min(existing_dates) if existing_dates else since_date

    print(f"  {client}: last date={last_date}, existing={len(by_id)} contacts")
    print(f"    Fetching contacts >= {since_date} (refresh window {REFRESH_DAYS}d)...")

    raw_contacts = ghl_fetch_contacts(loc, key, since_date)

    n_new = n_tags = n_area = n_code = 0
    for ct in raw_contacts:
        ct_id = ct.get("id")
        if ct_id in by_id:
            old = by_id[ct_id]
            if client in AREA_CLIENTS and not old.get("area"):
                area = extract_area(ct)
                if area:
                    old["area"] = area
                    n_area += 1
            if BACKFILL_AREA:
                continue  # el backfill solo completa area; no toca tags, code ni source de contactos viejos
            # Refresh: tags evolucionan después de la captura (GL/citas/shows/client)
            new_tags = ct.get("tags") or []
            if sorted(old.get("tags") or []) != sorted(new_tags):
                old["tags"] = new_tags
                n_tags += 1
            # El codigo se recalcula siempre: cambia si el contacto vuelve a llenar el formulario
            # desde otro anuncio (GHL lo cuenta en el anuncio nuevo).
            _, code = normalize_contact(ct, cmap, utm_remap)
            if code and code != old.get("code"):
                old["code"] = code
                n_code += 1
                if client in AREA_CLIENTS:
                    area = extract_area(ct)
                    if area:
                        old["area"] = area
            if not old.get("source"):
                bucket, _ = normalize_contact(ct, cmap, utm_remap)
                if bucket:
                    old["source"] = bucket
        else:
            bucket, code = normalize_contact(ct, cmap, utm_remap)
            new_c = {
                "id": ct_id,
                "dateAdded": ct.get("dateAdded"),
                "tags": ct.get("tags") or [],
                "source": bucket,
                "code": code,
            }
            if client in AREA_CLIENTS:
                area = extract_area(ct)
                if area:
                    new_c["area"] = area
                    n_area += 1
            existing["contacts"].append(new_c)
            by_id[ct_id] = new_c
            n_new += 1

    tmp_path = ghl_path + ".tmp"
    with open(tmp_path, "w") as f:
        json.dump(existing, f, separators=(',', ':'))
    os.replace(tmp_path, ghl_path)

    extra = f" | area asignada a {n_area}" if client in AREA_CLIENTS else ""
    print(f"    +{n_new} new contacts, {n_tags} tags refreshed, {n_code} codigos corregidos{extra} | total: {len(existing['contacts'])}")
    return n_new

# Load clients config
clients_cfg = json.load(open(f"{BASE}/clients.json"))
clients_to_update = ["FCI", "AB", "BAIP", "MCDIC", "MDIC", "WLA", "PDC", "CSSD"]
# Uso: python3 fetch_ghl.py [--only MDIC,CSSD] [--backfill-area]
#   --only: procesa solo esos clientes.
#   --backfill-area: recorre todo el historial guardado y completa contact["area"] (solo AREA_CLIENTS),
#   sin refrescar tags ni code/source de contactos ya guardados.
if "--only" in sys.argv:
    clients_to_update = [c for c in sys.argv[sys.argv.index("--only") + 1].split(",") if c in clients_to_update]
if BACKFILL_AREA:
    clients_to_update = [c for c in clients_to_update if c in AREA_CLIENTS]

print("=== GHL Contact Fetch ===")
total_new = 0
for c in clients_to_update:
    print(f"\n[{c}]")
    n = process_client(c, clients_cfg)
    if n:
        total_new += n

print(f"\n=== DONE: {total_new} new contacts added total ===")

# Verify last dates
print("\n--- Last dates after GHL update ---")
for client in clients_to_update:
    path = f"{BASE}/ghl_{client}.json"
    if os.path.exists(path):
        data = json.load(open(path))
        contacts = data.get('contacts', [])
        dates = [c.get('dateAdded','')[:10] for c in contacts if c.get('dateAdded')]
        last = max(dates) if dates else 'sin datos'
        print(f"  {client}: {len(contacts)} total, último = {last}")
