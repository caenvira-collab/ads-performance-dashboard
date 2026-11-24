#!/usr/bin/env python3
"""Regenera dashboard.html a partir de dashboard.template.html embebiendo los 8 perf files actualizados."""
import json, os, re
from pathlib import Path

BASE = Path(__file__).parent
HTML_PATH = BASE / "dashboard.html"                      # salida generada (no se versiona)
TEMPLATE_PATH = BASE / "dashboard.template.html"         # plantilla con DATA y ABTESTS vacios

CLIENT_META = {
    "FCI":{"name":"FCI Clinic"},"AB":{"name":"AB Clinic"},
    "BAIP":{"name":"BAIP Clinic"},
    "MCDIC":{"name":"MCDIC Clinic"},
    "MDIC":{"name":"MDIC Clinic"},"WLA":{"name":"WLA Clinic"},
    "PDC":{"name":"PDC Clinic"},"CSSD":{"name":"CSSD Clinic"},
}
CLIENT_ORDER = ["FCI","AB","BAIP","MCDIC","MDIC","WLA","PDC","CSSD"]

def normalize_wla(perf):
    new_presets = {}
    for k, v in perf.get("presets", {}).items():
        key = "maximum" if k == "all" else k
        new_presets[key] = {"start": v[0], "end": v[1]} if isinstance(v, list) else v
    perf["presets"] = new_presets
    for ad in perf.get("ads", []):
        if "all" in ad.get("p", {}):
            legacy = ad["p"].pop("all")
            ad["p"].setdefault("maximum", legacy)
    return perf

data = {}
for c in CLIENT_ORDER:
    ppath = BASE / f"perf_{c}.json"
    if not ppath.exists(): continue
    with open(ppath) as f:
        perf = json.load(f)
    if c == "WLA":
        perf = normalize_wla(perf)
    perf["name"] = CLIENT_META[c]["name"]
    data[c] = perf

data_json = json.dumps(data, separators=(',', ':'), ensure_ascii=False)

abtests_path = BASE / "abtests.json"
if abtests_path.exists():
    with open(abtests_path) as f:
        abtests = json.load(f)
else:
    abtests = {}
abtests_json = json.dumps(abtests, separators=(',', ':'), ensure_ascii=False)

with open(TEMPLATE_PATH, encoding="utf-8") as f:
    content = f.read()

new_content = re.sub(r'const DATA=\{.*?\};(?=\n)', f'const DATA={data_json};', content, count=1, flags=re.DOTALL)
new_content = re.sub(r'const ABTESTS=\{.*?\};(?=\n)', f'const ABTESTS={abtests_json};', new_content, count=1, flags=re.DOTALL)

tmp_path = str(HTML_PATH) + ".tmp"
with open(tmp_path, "w", encoding="utf-8") as f:
    f.write(new_content)
os.replace(tmp_path, HTML_PATH)

print(f"dashboard.html actualizado: {len(new_content)/1024:.1f}KB")
