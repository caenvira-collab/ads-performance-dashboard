#!/usr/bin/env python3
"""Recolecta los resultados guardados de ads_get_ad_entities (nivel ad, time_increment 1) y los mezcla en
meta_daily_{C}.json.

Uso:
  python3 meta_pull_merge.py <timestamp_minimo>            # solo reporta
  python3 meta_pull_merge.py <timestamp_minimo> --apply    # reporta y mezcla

<timestamp_minimo>: numero del nombre de archivo (mcp-...-ads_get_ad_entities-<numero>.txt) del primer
resultado de esta ronda; se procesan los archivos con numero mayor o igual.

Cada cliente se identifica por los 3 ultimos digitos del campaign_id. Se descartan filas sin id y filas con
gasto 0 y clicks 0. Cada dia se guarda como [gasto, clicks, impresiones] y sobrescribe lo existente.
"""
import glob, json, os, re, sys, collections

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
import build_perf as bp

SUF = {"353": "FCI", "064": "AB", "687": "BAIP", "486": "MCDIC", "637": "MDIC", "116": "WLA", "327": "PDC", "750": "CSSD"}
# Cualquier carpeta de proyecto: una sesion programada puede tener otro directorio de trabajo y guarda ahi sus resultados
# META_RESULTS_GLOB reemplaza la ruta por defecto: cualquier carpeta con archivos de la misma forma
# (JSON con "ad_entities" y el numero de ronda en el nombre, ver README).
TR_GLOB = os.environ.get("META_RESULTS_GLOB") or os.path.expanduser(
    "~/.claude/projects/*/*/tool-results/mcp-*-ads_get_ad_entities-*.txt")


def num(x):
    if x is None:
        return 0.0
    if isinstance(x, dict):
        x = x.get("value")
    return float(str(x).replace(",", "") or 0)


def load(min_ts):
    data, report = {}, []
    files = [f for f in glob.glob(TR_GLOB) if int(re.search(r"entities-(\d+)(?:-[a-z0-9]+)?\.txt$", f).group(1)) >= min_ts]
    for f in sorted(files, key=lambda p: int(re.search(r"entities-(\d+)(?:-[a-z0-9]+)?\.txt$", p).group(1))):
        d = json.load(open(f))
        entities = json.loads(d["ad_entities"])
        # Solo filas con gasto: los archivos de estado de activos (effective_status) no traen amount_spent y se ignoran
        rows = [r for r in entities if r.get("id") and r.get("campaign_id") and "amount_spent" in r]
        sufs = {SUF.get(r["campaign_id"][-3:], "??" + r["campaign_id"][-3:]) for r in rows}
        dates = sorted({r["date_start"] for r in entities})
        cursor = bool(d.get("pagination", {}).get("next_cursor"))
        report.append((sorted(sufs), dates[0] if dates else None, dates[-1] if dates else None, len(entities), cursor))
        if len(sufs) != 1:
            continue
        c = next(iter(sufs))
        for r in rows:
            data.setdefault(c, {})[(r["id"], r["date_start"])] = (
                num(r["amount_spent"]), int(num(r.get("clicks"))), int(num(r.get("impressions"))),
                r["campaign_id"], r.get("name", ""))
    return data, report


def main():
    min_ts = int(sys.argv[1])
    apply = "--apply" in sys.argv
    data, report = load(min_ts)
    for r in report:
        print(r[0], r[1], r[2], r[3], "CURSOR PENDIENTE" if r[4] else "")
    for c in SUF.values():
        if c not in data:
            print(f"{c}: SIN DATOS en esta ronda")
            continue
        cmap = bp.WLA_CAMP_MAP if c == "WLA" else bp.CAMP_MAPS[c]
        p = f"{BASE}/meta_daily_{c}.json"
        md = json.load(open(p))
        old = {(a, dt): v for a, ad in md.items() for dt, v in ad["days"].items()}
        new = {k: v for k, v in data[c].items() if v[0] > 0 or v[1] > 0}
        changed = [k for k in new if k in old and (abs(old[k][0] - new[k][0]) > 0.011 or old[k][1] != new[k][1])]
        added = [k for k in new if k not in old]
        new_ads = {}
        unmapped = collections.Counter()
        for k, v in new.items():
            if k[0] not in md:
                new_ads[k[0]] = (v[3], v[4][:60])
            if v[3] not in cmap:
                unmapped[v[3]] += v[0]
        fechas = sorted({k[1] for k in added})
        print(f"{c}: filas {len(new)} | cambiadas {len(changed)} (neto ${sum(new[k][0] - old[k][0] for k in changed):+.2f})"
              f" | nuevas {len(added)} ${sum(new[k][0] for k in added):.2f} {fechas[:1]}..{fechas[-1:]}"
              f" | ads nuevos {len(new_ads)} | cids sin bucket {dict((k, round(v, 2)) for k, v in unmapped.items())}")
        if c in bp.CAMP_AREA:
            sin_area = {v[3] for v in new.values() if v[3] in cmap and v[3] not in bp.CAMP_AREA[c]}
            if sin_area:
                print(f"      CAMPANAS SIN AREA en CAMP_AREA[{c}] (sus anuncios saldran como 'Sin area'): {sorted(sin_area)}")
        for aid, (cid, nm) in new_ads.items():
            print(f"      ad nuevo {aid} cid {cid} {nm}")
        if apply:
            for (aid, dt), (s, k, i, cid, nm) in new.items():
                if aid not in md:
                    md[aid] = {"name": nm, "cid": cid, "days": {}}
                elif nm and not md[aid].get("name"):
                    md[aid]["name"] = nm
                md[aid]["days"][dt] = [round(s, 2), k, i]
            tmp = p + ".tmp"
            json.dump(md, open(tmp, "w"))
            os.replace(tmp, p)
            mx = max(d for a in md.values() for d in a["days"])
            sin_imp = sum(1 for a in md.values() for v in a["days"].values() if len(v) < 3)
            print(f"      mezclado: max fecha {mx}, filas sin impresiones {sin_imp}")


if __name__ == "__main__":
    main()
