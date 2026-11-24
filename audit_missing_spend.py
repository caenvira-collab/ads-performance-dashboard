#!/usr/bin/env python3
"""Auditoria permanente: compara el listado COMPLETO de ads de Meta (via MCP, pre-guardado en un
archivo JSON por cliente) contra meta_daily_{C}.json para detectar:
  1. Ads con spend real en Meta que no existen en absoluto en meta_daily_{C}.json.
  2. Ads presentes en meta_daily_{C}.json con name vacio o name==nombre_de_bucket y spend > 0.
No hace llamadas a Meta por si mismo (evita duplicar el MCP) -- lee un snapshot ya descargado.
Uso: primero descargar el listado completo de cada cliente con ads_get_ad_entities
(date_preset=maximum, limit=1000, sin time_range) y guardarlo en
meta_full_listing_{C}.json (lista de dicts con al menos id, campaign_id, amount_spent opcional).
Luego correr: python3 audit_missing_spend.py [CLIENTE ...]
"""
import json, os, sys, re

BASE = os.path.dirname(os.path.abspath(__file__))
BUCKETS = {"T1D", "ThinArch", "Lower Funnel", "Fear", "PrecisionArch", "QuikArch", "Zygomatic"}
CLIENTS = ["FCI", "AB", "BAIP", "MCDIC", "MDIC", "WLA", "PDC", "CSSD"]


def parse_spend(s):
    if s is None:
        return 0.0
    return float(str(s).replace(" USD", "").replace("USD", "").replace("\xa0", "").replace("$", "").replace(",", "").strip() or 0)


def audit_client(client):
    md_path = f"{BASE}/meta_daily_{client}.json"
    full_path = f"{BASE}/meta_full_listing_{client}.json"

    with open(md_path) as f:
        md = json.load(f)

    findings = {"bad_name": [], "missing_ads": []}

    for aid, ad in md.items():
        name = (ad.get("name") or "").strip()
        spend = sum(v[0] for v in ad.get("days", {}).values())
        if (name == "" or name in BUCKETS) and spend > 0:
            findings["bad_name"].append((aid, name, round(spend, 2)))

    if os.path.exists(full_path):
        with open(full_path) as f:
            full_listing = json.load(f)
        existing_ids = set(md.keys())
        for e in full_listing:
            aid = e["id"]
            if aid in existing_ids:
                continue
            spend = parse_spend(e.get("amount_spent"))
            if spend > 0:
                findings["missing_ads"].append((aid, e.get("name", "")[:60], round(spend, 2)))
    else:
        findings["no_full_listing"] = True

    return findings


def main():
    clients = sys.argv[1:] or CLIENTS
    any_issue = False
    for c in clients:
        f = audit_client(c)
        if f.get("no_full_listing"):
            print(f"{c}: SIN meta_full_listing_{c}.json -- solo se revisó name vacío/bucket, no ads totalmente ausentes.")
        if f["bad_name"]:
            any_issue = True
            print(f"{c}: BAD NAME ({len(f['bad_name'])}):")
            for aid, name, spend in f["bad_name"]:
                print(f"    {aid}  name={name!r}  spend=${spend}")
        if f["missing_ads"]:
            any_issue = True
            print(f"{c}: ADS AUSENTES CON SPEND REAL ({len(f['missing_ads'])}):")
            for aid, name, spend in f["missing_ads"]:
                print(f"    {aid}  {name}  spend=${spend}")
        if not f["bad_name"] and not f["missing_ads"] and not f.get("no_full_listing"):
            print(f"{c}: OK")
    if not any_issue:
        print("\n=== Sin hallazgos nuevos en los clientes auditados ===")


if __name__ == "__main__":
    main()
