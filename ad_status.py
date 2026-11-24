#!/usr/bin/env python3
"""Guarda en ad_status.json los ids de anuncios ACTIVOS de cada cliente, a partir de resultados guardados de
ads_get_ad_entities (level ad, filtro effective_status IN [ACTIVE]).

Uso: python3 ad_status.py <timestamp_minimo>
<timestamp_minimo>: numero del nombre del primer archivo de resultados de esta consulta
(mcp-...-ads_get_ad_entities-<numero>.txt). Se procesan ese archivo y los posteriores.

effective_status ACTIVE significa que el anuncio se esta entregando: incluye el estado de su campana y de su
conjunto de anuncios. Un anuncio que no aparece en la lista se considera inactivo.
"""
import glob, json, os, re, sys, datetime

BASE = os.path.dirname(os.path.abspath(__file__))
SUF = {"353": "FCI", "064": "AB", "687": "BAIP", "486": "MCDIC", "637": "MDIC", "116": "WLA", "327": "PDC", "750": "CSSD"}
# Cualquier carpeta de proyecto: una sesion programada puede tener otro directorio de trabajo y guarda ahi sus resultados
# META_RESULTS_GLOB reemplaza la ruta por defecto: cualquier carpeta con archivos de la misma forma
# (JSON con "ad_entities" y el numero de ronda en el nombre, ver README).
TR_GLOB = os.environ.get("META_RESULTS_GLOB") or os.path.expanduser(
    "~/.claude/projects/*/*/tool-results/mcp-*-ads_get_ad_entities-*.txt")


def main():
    min_ts = int(sys.argv[1])
    files = [f for f in glob.glob(TR_GLOB) if int(re.search(r"entities-(\d+)(?:-[a-z0-9]+)?\.txt$", f).group(1)) >= min_ts]
    active = {}
    for f in sorted(files):
        d = json.load(open(f))
        rows = [r for r in json.loads(d["ad_entities"]) if r.get("id") and r.get("campaign_id")]
        sufs = {SUF.get(r["campaign_id"][-3:], "??") for r in rows}
        if len(sufs) != 1 or "??" in sufs:
            print("archivo omitido (cliente no identificado):", os.path.basename(f), sufs)
            continue
        c = next(iter(sufs))
        if d.get("pagination", {}).get("next_cursor"):
            print(f"{c}: CURSOR PENDIENTE, la lista de activos esta incompleta")
        for r in rows:
            if r.get("effective_status") == "ACTIVE":
                active.setdefault(c, set()).add(r["id"])
    out = {}
    for c in SUF.values():
        if c not in active:
            print(f"{c}: SIN DATOS de estado en esta ronda (se conserva el estado anterior si existia)")
            continue
        md = json.load(open(f"{BASE}/meta_daily_{c}.json"))
        sin_historia = [a for a in active[c] if a not in md]
        out[c] = {"asof": str(datetime.date.today()), "active": sorted(active[c])}
        print(f"{c}: {len(active[c])} activos | sin gasto aun en meta_daily: {len(sin_historia)}")
    path = f"{BASE}/ad_status.json"
    prev = json.load(open(path)) if os.path.exists(path) else {}
    prev.update(out)
    tmp = path + ".tmp"
    json.dump(prev, open(tmp, "w"))
    os.replace(tmp, path)


if __name__ == "__main__":
    main()
