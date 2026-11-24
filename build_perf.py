#!/usr/bin/env python3
"""Build perf_{C}.json from meta_presets_{C}.json + ghl_{C}.json + meta_daily_{C}.json"""
import json, re, os
from datetime import datetime, date

BASE = os.path.dirname(os.path.abspath(__file__))

CAMP_MAPS = {
    "AB":    {"990000000000001064":"T1D","990000000000002064":"ThinArch"},
    "BAIP":  {"990000000000003687":"T1D","990000000000004687":"Lower Funnel","990000000000005687":"ThinArch"},
    "MCDIC": {"990000000000006486":"Lower Funnel","990000000000007486":"ThinArch","990000000000008486":"T1D","990000000000009486":"Lower Funnel","990000000000010486":"Lower Funnel"},
    # MCDIC: 990000000000011486 ("MCDIC - Retargeting", creada 2026-10-19) excluido a proposito, mismo criterio que el resto
    "MDIC":  {"990000000000012637":"Lower Funnel","990000000000013637":"Lower Funnel","990000000000014637":"T1D","990000000000015637":"T1D","990000000000016637":"ThinArch","990000000000017637":"ThinArch","990000000000018637":"Lower Funnel","990000000000019637":"T1D"},
    "FCI":   {"990000000000020353":"ThinArch","990000000000021353":"T1D","990000000000022353":"Lower Funnel"},
    "PDC":   {"990000000000023327":"ThinArch","990000000000024327":"Lower Funnel","990000000000025327":"T1D"},
    # PDC: 990000000000026327 ("[PDC] - Retargeting") excluido a propósito
    # PDC: 990000000000027327 ("Event: ...") pausada, sin precedente de bucket, excluida
    "CSSD":  {"990000000000028750":"PrecisionArch","990000000000029750":"T1D","990000000000030750":"ThinArch","990000000000031750":"Lower Funnel"},
    # CSSD: 990000000000032750 ("[CSSD] - Retargeting") excluido a propósito, mismo criterio que el resto
    # CSSD: campañas viejas pausadas (RayFace, InstaRisa, T1D antiguo, desde jul-2024) excluidas por
    #   decisión del usuario 2026-09-17. Dashboard rastrea CSSD solo desde 2026-01-01
}

# Etiqueta de tipo por campana cuando una linea (bucket) agrupa campanas distintas: ad["t"] en el dashboard.
# MCDIC: campanas "Lower Funnel Facial Scanner" y "Lower Funnel Second Opinion" van ambas al bucket Lower Funnel.
CAMP_TIPO = {
    "MCDIC": {"990000000000006486": "Facial Scanner", "990000000000010486": "Second Opinion"},
    # WLA: Lower Funnel agrupa la campana de Yomi y la de Second Opinion (decision del responsable de la cuenta, 2026-11-16).
    "WLA": {"990000000000033116": "Yomi", "990000000000034116": "Second Opinion"},
}
# Division por area (Inner/Outer) dentro de un cliente: MDIC duplica cada campana por area con los MISMOS codigos
# de anuncio. La clave interna de cada anuncio es (bucket, code, area); area == "" en los clientes sin division.
# En perf_{C}.json la fila lleva ad["ar"] y el dashboard la muestra y la filtra.
CAMP_AREA = {
    "MDIC": {
        "990000000000012637": "Inner Area", "990000000000013637": "Outer Area",   # InstaRisa -> Lower Funnel
        "990000000000015637": "Inner Area", "990000000000014637": "Outer Area",   # T1D
        "990000000000017637": "Inner Area", "990000000000016637": "Outer Area",   # ThinArch
    },
}
SIN_AREA = "Sin área"

WLA_CAMP_MAP = {
    "990000000000035116": "ThinArch",
    "990000000000036116": "T1D",
    "990000000000033116": "Lower Funnel",
    "990000000000037116": "Fear",
    "990000000000038116": "PrecisionArch",
    "990000000000039116": "Zygomatic",
    "990000000000034116": "Lower Funnel",  # WLA - Second Opinion, desde 2026-11-14 (decision del responsable de la cuenta: cuenta como Lower Funnel, igual que en CSSD)
    # 990000000000040116 ("WLA - Retargeting") excluido a propósito, igual que el resto de RT/Retargeting
}

SRC_BUCKET = {
    "Facebook T1D":"T1D","Facebook ThinArch":"ThinArch",
    "Facebook Fear":"Fear","Facebook PrecisionArch":"PrecisionArch",
    "Facebook Lower-Funnel":"Lower Funnel","Facebook Lower Funnel":"Lower Funnel",
    "Facebook Reveals":"Lower Funnel","Facebook Reveal":"Lower Funnel",
    "Facebook QuikArch":"QuikArch","Facebook Zygomatic":"Zygomatic",
}

TAG_UL  = {"lead","temp-active-unique-lead"}
TAG_GL  = {"good-lead","better-lead","great-lead","temp-active-good-lead"}
TAG_BL  = {"better-lead"}
TAG_CIT = {"appt-confirmed"}
TAG_SHO = {"appt-showed"}
TAG_CLI = {"client","client-assigned"}

CODE_RE = re.compile(r'\b(\d{2}[./]\d{2}[./]\d{2}-\d{2})\b')

def _normalize_code(raw):
    """PDC usa '/' como separador en vez de '.' en algunos ads — normaliza a '.' para
    que el agrupamiento por código sea consistente con el resto de clientes."""
    return raw.replace('/', '.') if raw else raw

def _get_code(contact):
    """Returns ad code from top-level field (old format) or attribution data (GET endpoint raw format).
    Search order: attributionSource / lastAttributionSource → attributions[] → customFields → whole JSON."""
    code = contact.get("code")
    if code:
        return code
    sources = [contact.get("attributionSource") or {}, contact.get("lastAttributionSource") or {}]
    sources += list(contact.get("attributions") or [])
    for att in sources:
        for field in ("utmContent", "utmKeyword", "pageUrl", "url"):
            m = CODE_RE.search(str(att.get(field) or ""))
            if m:
                return _normalize_code(m.group(1))
    for cf in contact.get("customFields") or []:
        m = CODE_RE.search(str(cf.get("value") or ""))
        if m:
            return _normalize_code(m.group(1))
    m = CODE_RE.search(json.dumps(contact))
    return _normalize_code(m.group(1)) if m else None

def area_of_cid(client, cid):
    """Area de una campana Meta. "" si el cliente no se divide por area; SIN_AREA si la campana no esta en CAMP_AREA."""
    if client not in CAMP_AREA:
        return ""
    return CAMP_AREA[client].get(cid, SIN_AREA)

def _code_to_area_map(client, meta_daily_data, cmap):
    """Codigo -> area cuando el codigo existe en una sola area de Meta. Los codigos que viven en Inner y Outer
    (los mismos anuncios duplicados) quedan fuera: ahi decide el area que trae el contacto (contact["area"])."""
    if client not in CAMP_AREA or not meta_daily_data:
        return {}
    seen = {}
    for ad in meta_daily_data.values():
        if not cmap.get(ad.get('cid')): continue
        code = extract_code(ad.get('name', ''))
        area = CAMP_AREA[client].get(ad.get('cid'))
        if code and area:
            seen.setdefault(code, set()).add(area)
    return {c: next(iter(a)) for c, a in seen.items() if len(a) == 1}

def contact_area(client, contact, code, code_area):
    """Area de un contacto: la unica area de Meta del codigo si existe; si no, la guardada desde la atribucion de GHL."""
    if client not in CAMP_AREA:
        return ""
    return code_area.get(code) or contact.get("area") or SIN_AREA

def _ad_key(ad):
    return (ad["c"], ad["k"], ad.get("ar", ""))

def _new_ad(key, p):
    ad = {"c": key[0], "k": key[1], "p": p}
    if key[2]:
        ad["ar"] = key[2]
    return ad

def _detect_cutoff():
    """Detecta el último día con datos en meta_daily_*.json para anclar los presets."""
    import glob
    latest = None
    for path in glob.glob(f"{BASE}/meta_daily_*.json"):
        try:
            with open(path) as f: d = json.load(f)
            for ad in d.values():
                for dt in ad.get("days", {}).keys():
                    if latest is None or dt > latest:
                        latest = dt
        except Exception:
            pass
    return date.fromisoformat(latest) if latest else date.today()

def _build_presets(cutoff=None):
    from datetime import timedelta
    cutoff = cutoff or _detect_cutoff()
    seven_ago   = cutoff - timedelta(days=6)
    fourteen_ago = cutoff - timedelta(days=13)
    twentyone_ago = cutoff - timedelta(days=20)
    thirty_ago  = cutoff - timedelta(days=29)
    tmonth_start = cutoff.replace(day=1)
    lmonth_end  = tmonth_start - timedelta(days=1)
    lmonth_start = lmonth_end.replace(day=1)
    return [
        ("today",   cutoff,        cutoff),
        ("7d",      seven_ago,     cutoff),
        ("14d",     fourteen_ago,  cutoff),
        ("21d",     twentyone_ago, cutoff),
        ("30d",     thirty_ago,    cutoff),
        ("tmonth",  tmonth_start,  cutoff),
        ("lmonth",  lmonth_start,  lmonth_end),
        ("maximum", date(2000,1,1), cutoff),
    ]

PRESETS = _build_presets()

def resolve_bucket(raw_src, cmap):
    """Resuelve el source string de GHL al nombre de bucket de campaña.
    Acepta tanto 'Facebook PrecisionArch' (forma larga) como 'PrecisionArch' (forma corta).
    Retorna None si el source no corresponde a ninguna campaña Meta conocida.
    """
    bucket_names = set(cmap.values())
    return raw_src if raw_src in bucket_names else SRC_BUCKET.get(raw_src)

def parse_sp(s):
    if not s or s == "Not available": return 0.0
    return float(re.sub(r'[^\d.]','',str(s)) or 0)

def parse_cl(s):
    if not s or s == "Not available": return 0
    try: return int(str(s).replace(',',''))
    except: return 0

_TZ_CACHE = {}
def _client_tz(client):
    """Timezone del location GHL del cliente (clients.json key 'tz'). None = UTC."""
    if client not in _TZ_CACHE:
        tz = None
        try:
            with open(f"{BASE}/clients.json") as f:
                cfg = json.load(f)
            tz = (cfg.get(client) or {}).get("tz")
        except Exception:
            pass
        _TZ_CACHE[client] = tz
    return _TZ_CACHE[client]

def contact_date(c, tz=None):
    """Fecha del contacto en el timezone del location GHL (para igualar los cortes de fecha de GHL)."""
    d = c.get("dateAdded","")
    if not d: return None
    try:
        dt = datetime.fromisoformat(d.replace("Z","+00:00"))
        if dt.tzinfo is None:
            from datetime import timezone as _tzu
            dt = dt.replace(tzinfo=_tzu.utc)
        if tz:
            from zoneinfo import ZoneInfo
            dt = dt.astimezone(ZoneInfo(tz))
        return dt.date()
    except:
        try: return datetime.strptime(d[:10],"%Y-%m-%d").date()
        except: return None

def extract_code(name):
    m = CODE_RE.search(name or "")
    return _normalize_code(m.group(1)) if m else None


def _code_to_bucket_map(meta_daily_data, cmap):
    """Mapea código de anuncio -> bucket usando meta_daily (dato de Meta, más confiable que
    el 'source' de GHL, que puede venir vacío o mal etiquetado a mano -- ver caso WLA/Zygomatic
    2026-08-12: leads con source='PrecisionArch' cuyo código real era de un ad de Zygomatic).
    Códigos reciclados entre campañas distintas (colisión, ej. mismo código fecha+secuencia
    usado en dos campañas el mismo día) se excluyen del mapa -- quedan ambiguos a propósito,
    y en ese caso el 'source' de GHL sigue siendo el único desempate disponible."""
    if not meta_daily_data:
        return {}
    seen, ambiguous = {}, set()
    for ad in meta_daily_data.values():
        bucket = cmap.get(ad.get('cid'))
        if not bucket: continue
        code = extract_code(ad.get('name', ''))
        if not code: continue
        if code in seen and seen[code] != bucket:
            ambiguous.add(code)
        else:
            seen[code] = bucket
    return {c: b for c, b in seen.items() if c not in ambiguous}


def build_daily_blocks(client, pairs, cmap, meta_daily_data, ghl_data):
    """Build {(bucket,code,area): {date: [sp,cl,ul,gl,cit,sho,cli,won,bl,imp,sp_imp]}} from daily Meta + GHL."""

    # GHL daily counts + won revenue per (bucket, code, date)
    ghl_daily = {}
    if ghl_data:
        # Map contactId → won revenue
        opp_won = {}
        for o in ghl_data.get("opps", []):
            if o.get("status") == "won":
                cid = o.get("contactId")
                if cid:
                    opp_won[cid] = opp_won.get(cid, 0) + float(o.get("monetaryValue") or 0)

        tz = _client_tz(client)
        code_to_bucket = _code_to_bucket_map(meta_daily_data, cmap)
        code_area = _code_to_area_map(client, meta_daily_data, cmap)
        for contact in ghl_data.get("contacts", []):
            d = contact_date(contact, tz)
            if d is None: continue
            code = _get_code(contact)
            raw_src = (contact.get("source") or "").strip()
            bucket = code_to_bucket.get(code) if code else None
            if not bucket:
                bucket = resolve_bucket(raw_src, cmap)
            if not bucket or not code: continue
            tags = set(contact.get("tags") or [])
            key = (bucket, code, contact_area(client, contact, code, code_area))
            dt_str = str(d)
            # [ul, gl, cit, sho, cli, won, bl]
            m = ghl_daily.setdefault(key, {}).setdefault(dt_str, [0,0,0,0,0,0.0,0])
            if tags & TAG_UL:  m[0] += 1
            if tags & TAG_GL:  m[1] += 1
            if tags & TAG_CIT: m[2] += 1
            if tags & TAG_SHO: m[3] += 1
            if tags & TAG_CLI: m[4] += 1
            if tags & TAG_BL:  m[6] += 1
            won = opp_won.get(contact.get("id"), 0)
            if won:
                m[5] = round(m[5] + won, 2)

    # Meta daily sp/cl/imp per (bucket, code)
    meta_daily_by_pair = {}
    if meta_daily_data:
        for aid, a in meta_daily_data.items():
            cid = a.get('cid')
            bucket = cmap.get(cid)
            if not bucket: continue
            code = extract_code(a.get('name',''))
            if not code: continue
            key = (bucket, code, area_of_cid(client, cid))
            for dt, v in a.get('days', {}).items():
                row = meta_daily_by_pair.setdefault(key, {}).setdefault(dt, [0.0, 0, 0, 0.0])
                row[0] = round(row[0] + v[0], 2)
                row[1] += v[1]
                if len(v) > 2:
                    row[2] += v[2]
                    row[3] = round(row[3] + v[0], 2)

    # Combine per pair
    d_blocks = {}
    all_keys = set(meta_daily_by_pair.keys()) | set(ghl_daily.keys())
    for key in all_keys:
        if key not in pairs:
            continue
        all_dates = set(meta_daily_by_pair.get(key, {}).keys()) | set(ghl_daily.get(key, {}).keys())
        d_block = {}
        for dt in sorted(all_dates):
            meta = meta_daily_by_pair.get(key, {}).get(dt, [0.0, 0, 0, 0.0])
            ghl  = ghl_daily.get(key, {}).get(dt, [0,0,0,0,0,0.0,0])
            d_block[dt] = [round(meta[0], 2), meta[1]] + ghl + [meta[2], round(meta[3], 2)]  # [sp,cl,ul,gl,cit,sho,cli,won,bl,imp,sp_con_imp]
        if d_block:
            d_blocks[key] = d_block

    return d_blocks


def build(client):
    mpath = f"{BASE}/meta_presets_{client}.json"
    gpath = f"{BASE}/ghl_{client}.json"
    dpath = f"{BASE}/meta_daily_{client}.json"

    has_presets = os.path.exists(mpath)
    has_ghl = os.path.exists(gpath)
    has_daily = os.path.exists(dpath)

    if not has_presets:
        print(f"SKIP {client}: no meta_presets")
        return
    if not has_ghl:
        print(f"SKIP {client}: no ghl")
        return

    with open(mpath) as f: meta = json.load(f)
    with open(gpath) as f: ghl_data = json.load(f)
    meta_daily_data = None
    if has_daily:
        with open(dpath) as f: meta_daily_data = json.load(f)

    cmap = CAMP_MAPS.get(client, {})

    # Build ad catalog from maximum preset
    catalog = {}
    max_ads = meta.get("maximum", {}).get("ads", [])
    for ad in max_ads:
        cid = ad.get("cid","")
        bucket = cmap.get(cid)
        if not bucket: continue
        code = ad.get("code") or extract_code(ad.get("name",""))
        if code:
            catalog[ad["id"]] = {"b": bucket, "k": code, "ar": area_of_cid(client, cid)}

    # Spend/clicks per preset
    psp = {}
    for (pname,_,_) in PRESETS:
        psp[pname] = {}
        for ad in meta.get(pname, {}).get("ads", []):
            psp[pname][ad["id"]] = [
                parse_sp(ad.get("sp", ad.get("amount_spent", 0))),
                parse_cl(ad.get("cl", ad.get("clicks", 0)))
            ]

    # GHL won opportunities
    opp_won = {}
    for o in ghl_data.get("opps", []):
        if o.get("status") == "won":
            cid = o.get("contactId")
            if cid:
                opp_won[cid] = opp_won.get(cid, 0) + float(o.get("monetaryValue") or 0)

    # GHL metrics per preset
    gm = {pname:{} for (pname,_,_) in PRESETS}
    tz = _client_tz(client)
    code_area = _code_to_area_map(client, meta_daily_data, cmap)
    for contact in ghl_data.get("contacts", []):
        d = contact_date(contact, tz)
        if d is None: continue
        raw_src = (contact.get("source") or "").strip()
        bucket = resolve_bucket(raw_src, cmap)
        if not bucket: continue
        code = _get_code(contact)
        if not code: continue
        tags = set(contact.get("tags") or [])
        flags = [bool(tags & TAG_UL), bool(tags & TAG_GL), bool(tags & TAG_CIT), bool(tags & TAG_SHO), bool(tags & TAG_CLI)]
        won = opp_won.get(contact.get("id"), 0)
        key = (bucket, code, contact_area(client, contact, code, code_area))
        for (pname, pstart, pend) in PRESETS:
            if pstart <= d <= pend:
                m = gm[pname].setdefault(key, [0,0,0,0,0,0])
                for i, f in enumerate(flags):
                    if f: m[i] += 1
                m[5] += won

    # Unique (bucket, code) pairs from Meta catalog
    pairs = {}
    for aid, info in catalog.items():
        key = (info["b"], info["k"], info["ar"])
        pairs.setdefault(key, []).append(aid)

    # Add phantom pairs: GHL contacts from old/inactive ads not in Meta catalog
    # These are correctly-attributed contacts whose ads stopped spending before
    # the current window — build() would otherwise silently drop them.
    all_ghl_keys = set()
    for pname_gm in gm.values():
        all_ghl_keys.update(pname_gm.keys())
    for key in all_ghl_keys:
        if key not in pairs:
            pairs[key] = []  # phantom: sp=cl=0, GHL metrics only

    # Find overall start date
    max_start = None
    for ad in max_ads:
        ds = ad.get("date_start","")
        if ds and (max_start is None or ds < max_start):
            max_start = ds
    max_start = max_start or "2020-01-01"

    # Build daily blocks
    d_blocks = build_daily_blocks(client, pairs, cmap, meta_daily_data, ghl_data)

    # Build output ads list
    ads_out = []
    for (bucket, code, area), aids in sorted(pairs.items()):
        p_out = {}
        for (pname, pstart, pend) in PRESETS:
            sp_t, cl_t = 0.0, 0
            for aid in aids:
                d = psp.get(pname, {}).get(aid, [0,0])
                sp_t += d[0]; cl_t += d[1]
            g = gm[pname].get((bucket, code, area), [0,0,0,0,0,0])
            p_out[pname] = [round(sp_t,2), cl_t] + g
        ad_obj = _new_ad((bucket, code, area), p_out)
        if (bucket, code, area) in d_blocks:
            ad_obj["d"] = d_blocks[(bucket, code, area)]
        ads_out.append(ad_obj)

    prange = {}
    for (pname, pstart, pend) in PRESETS:
        prange[pname] = {"start": str(pstart), "end": str(pend)}
    prange["maximum"]["start"] = max_start

    out = {"client": client, "gen": "2026-06-19", "start": max_start, "presets": prange, "ads": ads_out}
    opath = f"{BASE}/perf_{client}.json"
    tmp_path = opath + ".tmp"
    with open(tmp_path, "w") as f:
        json.dump(out, f, separators=(',', ':'))
    os.replace(tmp_path, opath)

    ads_with_d = sum(1 for a in ads_out if "d" in a)
    total_sp = sum(a["p"]["maximum"][0] for a in ads_out)
    print(f"OK {client}: {len(ads_out)} ads ({ads_with_d} with daily 'd' block), ${total_sp:,.0f} max spend → {opath}")


def rebuild_ghl_metrics(client, cmap):
    """Rebuild GHL metrics (ul/gl/cit/sho/cli/won) in p blocks + rebuild d blocks.
    Keeps existing sp/cl from Meta unchanged. Used for clients without meta_presets file."""
    ppath = f"{BASE}/perf_{client}.json"
    dpath = f"{BASE}/meta_daily_{client}.json"
    gpath = f"{BASE}/ghl_{client}.json"

    if not os.path.exists(ppath): print(f"SKIP {client}: no perf file"); return
    if not os.path.exists(gpath): print(f"SKIP {client}: no ghl file"); return

    with open(ppath) as f: perf = json.load(f)
    with open(gpath) as f: ghl_data = json.load(f)
    meta_daily_data = None
    if os.path.exists(dpath):
        with open(dpath) as f: meta_daily_data = json.load(f)

    # Descartar anuncios de buckets que ya no existen para este cliente (p. ej. tras remapear una campana)
    valid_buckets = set(cmap.values())
    perf["ads"] = [ad for ad in perf.get("ads", []) if ad["c"] in valid_buckets]
    # Clientes divididos por area: las filas viejas sin area (una por codigo, Inner+Outer mezclados) se descartan
    # y se regeneran por (bucket, code, area) mas abajo desde meta_daily y GHL.
    if client in CAMP_AREA:
        perf["ads"] = [ad for ad in perf["ads"] if ad.get("ar")]

    # Build pairs from existing ads
    pairs = {_ad_key(ad): [] for ad in perf.get("ads", [])}

    # Won opps by contactId
    opp_won = {}
    for o in ghl_data.get("opps", []):
        if o.get("status") == "won":
            cid = o.get("contactId")
            if cid:
                opp_won[cid] = opp_won.get(cid, 0) + float(o.get("monetaryValue") or 0)

    # GHL metrics per preset per (bucket, code)
    gm = {pname: {} for (pname, _, _) in PRESETS}
    tz = _client_tz(client)
    code_to_bucket = _code_to_bucket_map(meta_daily_data, cmap)
    code_area = _code_to_area_map(client, meta_daily_data, cmap)
    for contact in ghl_data.get("contacts", []):
        d = contact_date(contact, tz)
        if d is None: continue
        # bucket: preferir el código de anuncio (dato de Meta, ground truth) sobre el
        # 'source' de GHL (texto editable a mano, puede venir vacío o mal etiquetado)
        code = _get_code(contact)
        raw_src = (contact.get("source") or "").strip()
        bucket = code_to_bucket.get(code) if code else None
        if not bucket:
            bucket = resolve_bucket(raw_src, cmap)
        if not bucket or not code: continue
        tags = set(contact.get("tags") or [])
        flags = [bool(tags & TAG_UL), bool(tags & TAG_GL), bool(tags & TAG_CIT),
                 bool(tags & TAG_SHO), bool(tags & TAG_CLI)]
        won = opp_won.get(contact.get("id"), 0)
        key = (bucket, code, contact_area(client, contact, code, code_area))
        for (pname, pstart, pend) in PRESETS:
            if pstart <= d <= pend:
                m = gm[pname].setdefault(key, [0, 0, 0, 0, 0, 0.0, 0])
                for i, f in enumerate(flags):
                    if f: m[i] += 1
                m[5] = round(m[5] + won, 2)
                if tags & TAG_BL: m[6] += 1

    # Add phantom ads: GHL contacts from codes not in existing perf ads
    existing_keys = set(pairs.keys())
    all_ghl_keys = set()
    for pname_gm in gm.values():
        all_ghl_keys.update(pname_gm.keys())
    for key in all_ghl_keys:
        if key not in existing_keys:
            pairs[key] = []
            phantom_p = {}
            for (pname, _, _) in PRESETS:
                ghl = gm[pname].get(key, [0, 0, 0, 0, 0, 0.0, 0])
                phantom_p[pname] = [0.0, 0] + ghl + [0, 0]
            perf["ads"].append(_new_ad(key, phantom_p))

    # sp/cl per preset from meta_daily (used when existing p blocks have sp=0)
    meta_sp_cl = {pname: {} for (pname, _, _) in PRESETS}
    if meta_daily_data:
        for aid, a in meta_daily_data.items():
            bucket = cmap.get(a.get('cid'))
            if not bucket: continue
            code = extract_code(a.get('name', ''))
            if not code: continue
            key = (bucket, code, area_of_cid(client, a.get('cid')))
            for pname, pstart, pend in PRESETS:
                ps, pe = str(pstart), str(pend)
                for dt, v in a.get('days', {}).items():
                    if ps <= dt <= pe:
                        row = meta_sp_cl[pname].setdefault(key, [0.0, 0, 0, 0.0])
                        row[0] = round(row[0] + v[0], 2)
                        row[1] += v[1]
                        if len(v) > 2:
                            row[2] += v[2]
                            row[3] = round(row[3] + v[0], 2)

    # Add phantom ads: meta_daily ads with spend but no perf entry and no GHL leads
    existing_keys = {_ad_key(ad) for ad in perf["ads"]}
    all_meta_keys = set()
    for pname_msc in meta_sp_cl.values():
        all_meta_keys.update(pname_msc.keys())
    for key in all_meta_keys:
        if key not in existing_keys:
            pairs[key] = []
            perf["ads"].append(_new_ad(key, {}))

    # Update p blocks: always prefer meta_sp_cl (computed from current date ranges)
    for ad in perf["ads"]:
        key = _ad_key(ad)
        for (pname, _, _) in PRESETS:
            existing = ad["p"].get(pname, [0, 0, 0, 0, 0, 0, 0, 0])
            m = meta_sp_cl[pname].get(key)
            if m:
                sp_cl, imp = m[:2], [m[2], round(m[3], 2)]
            elif meta_daily_data and pname != "maximum":
                sp_cl, imp = [0.0, 0], [0, 0]
            else:
                sp_cl, imp = existing[:2], [0, 0]
            ghl = gm[pname].get(key, [0, 0, 0, 0, 0, 0.0, 0])
            ad["p"][pname] = sp_cl + ghl + imp

    # Rebuild d blocks
    d_blocks = build_daily_blocks(client, pairs, cmap, meta_daily_data, ghl_data)
    updated_d = 0
    for ad in perf["ads"]:
        key = _ad_key(ad)
        if key in d_blocks:
            ad["d"] = d_blocks[key]
            updated_d += 1
        elif client in CAMP_AREA:
            # Al repartir por area, una fila que ya no genera datos diarios no puede conservar el bloque viejo:
            # seguiria sumando en graficos y comparaciones. (Los demas clientes lo conservan: comportamiento previo.)
            ad.pop("d", None)

    # Filas "Sin área" que ya no tienen ningun dato (p. ej. leads reasignados a su area): se descartan
    if client in CAMP_AREA:
        perf["ads"] = [ad for ad in perf["ads"]
                       if ad.get("ar") != SIN_AREA or ad.get("d") or any(any(v) for v in ad["p"].values())]

    # Etiqueta de tipo por anuncio (campo 'tipo' en meta_daily, tomado del adset) -> ad["t"]
    if meta_daily_data:
        code_tipo = {}
        for a in meta_daily_data.values():
            bucket = cmap.get(a.get('cid'))
            code = extract_code(a.get('name', ''))
            tipo = a.get('tipo') or CAMP_TIPO.get(client, {}).get(a.get('cid'))
            if bucket and code and tipo:
                code_tipo[(bucket, code)] = tipo
        for ad in perf["ads"]:
            t = code_tipo.get((ad["c"], ad["k"]))
            if t: ad["t"] = t

    # Estado activo por anuncio (ad_status.json) -> ad["a"] = 1 activo, 0 inactivo
    spath = f"{BASE}/ad_status.json"
    if meta_daily_data and os.path.exists(spath):
        st = json.load(open(spath)).get(client)
        if st:
            act = set(st["active"])
            active_keys = set()
            for aid, a in meta_daily_data.items():
                if aid in act:
                    b = cmap.get(a.get('cid'))
                    code = extract_code(a.get('name', ''))
                    if b and code:
                        active_keys.add((b, code, area_of_cid(client, a.get('cid'))))
            for ad in perf["ads"]:
                ad["a"] = 1 if _ad_key(ad) in active_keys else 0

    # Update presets date ranges and gen timestamp
    perf["gen"] = str(date.today())
    existing_presets = perf.get("presets", {})
    perf["presets"] = {}
    for (pname, pstart, pend) in PRESETS:
        if pname == "maximum":
            # Keep the historical start date (first actual data day), only update end
            hist_start = existing_presets.get("maximum", {}).get("start", str(pstart))
            perf["presets"][pname] = {"start": hist_start, "end": str(pend)}
        else:
            perf["presets"][pname] = {"start": str(pstart), "end": str(pend)}

    tmp_path = ppath + ".tmp"
    with open(tmp_path, "w") as f:
        json.dump(perf, f, separators=(',', ':'))
    os.replace(tmp_path, ppath)

    won_total = sum(ad["p"].get("maximum", [0]*8)[7] for ad in perf["ads"])
    print(f"OK {client}: p blocks rebuilt, {updated_d}/{len(perf['ads'])} ads with d, won(max)=${won_total:,.0f} → {ppath}")


def add_daily_to_existing(client, cmap):
    """Add 'd' blocks to an existing perf file that wasn't generated by build()."""
    ppath = f"{BASE}/perf_{client}.json"
    dpath = f"{BASE}/meta_daily_{client}.json"
    gpath = f"{BASE}/ghl_{client}.json"

    if not os.path.exists(ppath):
        print(f"SKIP {client}: no perf file"); return

    with open(ppath) as f: perf = json.load(f)

    meta_daily_data = None
    if os.path.exists(dpath):
        with open(dpath) as f: meta_daily_data = json.load(f)

    ghl_data = None
    if os.path.exists(gpath):
        with open(gpath) as f: ghl_data = json.load(f)

    # Build pairs dict from existing ads
    pairs = {}
    for ad in perf.get("ads", []):
        pairs.setdefault(_ad_key(ad), [])

    d_blocks = build_daily_blocks(client, pairs, cmap, meta_daily_data, ghl_data)

    # Inject 'd' into each ad
    updated = 0
    for ad in perf["ads"]:
        key = _ad_key(ad)
        if key in d_blocks:
            ad["d"] = d_blocks[key]
            updated += 1

    tmp_path = ppath + ".tmp"
    with open(tmp_path, "w") as f:
        json.dump(perf, f, separators=(',', ':'))
    os.replace(tmp_path, ppath)

    print(f"OK {client}: {updated}/{len(perf['ads'])} ads updated with 'd' block → {ppath}")


if __name__ == "__main__":
    import sys
    clients = sys.argv[1:] or ["AB","BAIP","MCDIC","MDIC","FCI","WLA","PDC","CSSD"]
    for c in clients:
        print(f"\nProcessing {c}...")
        if c == "FCI":
            # FCI has no meta_presets: rebuild GHL p blocks + d blocks from meta_daily
            rebuild_ghl_metrics("FCI", CAMP_MAPS["FCI"])
        elif c == "WLA":
            rebuild_ghl_metrics("WLA", WLA_CAMP_MAP)
        else:
            build(c)
    print("\nDone!")
