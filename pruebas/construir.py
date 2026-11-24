#!/usr/bin/env python3
"""Arma pruebas/datos.js para la pagina Historial de pruebas.

Lee registros.json (clasificacion de cada nota) y notas_originales.csv (texto literal), y revisa los
nombres de los anuncios en meta_daily_{C}.json buscando callouts exclusivos (hoy: Keep Your Gums, solo ThinArch)
en campanas que no corresponden. reconstruir.py lo llama al final de cada actualizacion del dashboard.

Uso: python3 pruebas/construir.py
"""
import json, os, re, sys
from datetime import date

BASE = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(BASE)
sys.path.insert(0, RAIZ)

CLIENTES = ["FCI", "AB", "BAIP", "MCDIC", "MDIC", "WLA", "PDC", "CSSD"]
NOMBRES = {
    "FCI": "FCI Clinic", "AB": "AB Clinic", "BAIP": "BAIP Clinic",
    "MCDIC": "MCDIC Clinic", "MDIC": "MDIC Clinic",
    "WLA": "WLA Clinic", "PDC": "PDC Clinic", "CSSD": "CSSD Clinic",
}
TIPOS = {
    "hl": "Headline", "callout": "Callout (texto de imagen)", "boton": "Fake button",
    "loc": "Location badge", "pb": "Price badge", "ps": "Price strip",
    "badge": "Otros badges", "intro": "Intro y copy", "precio": "Precio en copy o URL",
    "formato": "Formato y diseño", "cre": "Creativo",
}
# Unico callout que no se puede usar fuera de su campana.
EXCLUSIVOS = [{"tipo": "callout", "etiqueta": "Get All New Teeth & Keep Your Gums!",
               "patron": r"keep\s*(your|their)?\s*gums", "solo_en": "ThinArch"}]


def leer_notas():
    notas = {}
    with open(os.path.join(BASE, "notas_originales.csv"), encoding="utf-8") as f:
        next(f)
        for linea in f:
            linea = linea.rstrip("\n")
            if linea:
                clave, texto = linea.split("|", 1)
                notas[clave] = texto.replace("\\n", "\n")
    return notas


def mapas_campana():
    import build_perf as bp
    return {c: (bp.WLA_CAMP_MAP if c == "WLA" else bp.CAMP_MAPS[c]) for c in CLIENTES}


def alertas_meta(mapas):
    try:
        estado = json.load(open(os.path.join(RAIZ, "ad_status.json")))
    except Exception:
        estado = {}
    salida = []
    for c in CLIENTES:
        ruta = os.path.join(RAIZ, f"meta_daily_{c}.json")
        if not os.path.exists(ruta):
            continue
        md = json.load(open(ruta))
        activos = set((estado.get(c) or {}).get("active") or [])
        for ex in EXCLUSIVOS:
            pat = re.compile(ex["patron"], re.I)
            for aid, a in md.items():
                nombre = a.get("name") or ""
                if not pat.search(nombre):
                    continue
                bucket = mapas[c].get(a.get("cid"))
                if bucket == ex["solo_en"]:
                    continue
                dias = {d: v for d, v in (a.get("days") or {}).items() if v and v[0] > 0}
                salida.append({
                    "fuente": "Meta", "cliente": c, "campana": bucket or "Campaña sin bucket en el dashboard",
                    "cid": a.get("cid"), "ad_id": aid, "nombre": nombre, "texto": ex["etiqueta"],
                    "solo_en": ex["solo_en"], "activo": aid in activos,
                    "desde": min(dias) if dias else None, "hasta": max(dias) if dias else None,
                    "gasto": round(sum(v[0] for v in dias.values()), 2),
                })
    return salida


COD_RE = re.compile(r"\s*(\d{2}[./]\d{2}[./]\d{2}-\d{2})")


def rinde_hoy(mapas, top=5):
    """Por cliente y campana: anuncios con gasto en los ultimos 30 dias del dashboard, ordenados por good leads.
    Indices del bloque p de perf: 0 gasto, 2 unique leads, 3 good leads, 4 citas."""
    salida = {}
    for c in CLIENTES:
        rp, rm = os.path.join(RAIZ, f"perf_{c}.json"), os.path.join(RAIZ, f"meta_daily_{c}.json")
        if not (os.path.exists(rp) and os.path.exists(rm)):
            continue
        perf, md = json.load(open(rp)), json.load(open(rm))
        nombres = {}
        for a in md.values():
            m = COD_RE.match(a.get("name") or "")
            b = mapas[c].get(a.get("cid"))
            if not m or not b:
                continue
            gasto = sum(v[0] for v in (a.get("days") or {}).values() if v)
            k = (b, m.group(1).replace("/", "."))
            if k not in nombres or gasto > nombres[k][1]:
                nombres[k] = (a.get("name"), gasto)
        rango = perf.get("presets", {}).get("30d", {})
        por = {}
        for ad in perf.get("ads", []):
            b30 = (ad.get("p") or {}).get("30d") or []
            if len(b30) < 5 or not b30[0]:
                continue
            por.setdefault(ad["c"], []).append({
                "cod": ad["k"], "nombre": nombres.get((ad["c"], ad["k"]), ("", 0))[0],
                "activo": bool(ad.get("a")), "gasto": round(b30[0], 2), "ul": b30[2], "gl": b30[3], "citas": b30[4]})
        salida[c] = {"rango": rango, "campanas": {k: sorted(v, key=lambda x: (-x["gl"], -x["citas"], -x["ul"]))[:top]
                                                  for k, v in por.items()}}
    return salida


def alertas_notas(registros):
    salida = []
    for ex in EXCLUSIVOS:
        for r in registros:
            for t, v in r["gana"] + r["pierde"]:
                if t == ex["tipo"] and v == ex["etiqueta"] and r["campana"] != ex["solo_en"]:
                    salida.append({"fuente": "Notas", "cliente": r["cliente"], "campana": r["campana"],
                                   "nid": r["nid"], "texto": ex["etiqueta"], "solo_en": ex["solo_en"]})
    return salida


def main():
    base = json.load(open(os.path.join(BASE, "registros.json"), encoding="utf-8"))
    notas = leer_notas()
    faltan = sorted({r["nid"] for r in base["registros"]} - set(notas))
    if faltan:
        sys.exit(f"ERROR: registros sin nota en notas_originales.csv: {faltan}")
    mapas = mapas_campana()
    campanas = {c: sorted(set(mapas[c].values())) for c in CLIENTES}
    am = alertas_meta(mapas)
    an = alertas_notas(base["registros"])
    datos = {
        "generado": date.today().isoformat(), "clientes": CLIENTES, "nombres": NOMBRES,
        "tipos": TIPOS, "no_intercambiable": ["cre"], "excepcion_creativo": ["hl"],
        "exclusivos": [{k: v for k, v in e.items() if k != "patron"} for e in EXCLUSIVOS],
        "campanas": campanas, "hls": base["hls"], "notas": notas,
        "registros": base["registros"], "alertas": am + an,
        "rinde_hoy": rinde_hoy(mapas),
    }
    with open(os.path.join(BASE, "datos.js"), "w", encoding="utf-8") as f:
        f.write("window.PRUEBAS=" + json.dumps(datos, ensure_ascii=False, separators=(",", ":")) + ";\n")
    print(f"pruebas/datos.js actualizado: {len(base['registros'])} registros, {len(notas)} notas")
    act = sum(1 for a in am if a["activo"])
    print(f"ALERTAS Keep Your Gums fuera de ThinArch: {len(am)} anuncios en Meta ({act} activos), {len(an)} en notas")
    for a in am:
        print(f"  {a['cliente']} | {a['campana']} | {'ACTIVO' if a['activo'] else 'inactivo'} | "
              f"{a['desde']} a {a['hasta']} | ${a['gasto']:,.2f} | {a['ad_id']} | {a['nombre'][:90]}")
    for a in an:
        print(f"  NOTA {a['cliente']} | {a['campana']} | {a['nid']}")


if __name__ == "__main__":
    main()
