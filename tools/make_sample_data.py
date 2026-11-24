#!/usr/bin/env python3
"""Generate SYNTHETIC data so the whole pipeline can run without any real account.

Nothing here comes from a real client. Every number is produced by a seeded random generator, so two
runs give the same files. The script writes into the repository root (the files below are listed in
.gitignore, so they never reach version control):

  meta_daily_{C}.json   daily spend / clicks / impressions per ad
  ghl_{C}.json          contacts with tags, source bucket and ad code
  perf_{C}.json         empty seed (the pipeline fills it)
  ad_status.json        ids of the ads that are active on the last stored day
  abtests.json, update_log.txt
  clients.json          copy of clients.example.json, only if clients.json does not exist yet
  pruebas/registros.json, pruebas/notas_originales.csv   a few fictional test notes

With --pull it also writes meta_results/*.txt: simulated answers of the Meta tool `ads_get_ad_entities`
in the shape that meta_pull_merge.py and ad_status.py read (see README.md, "Demo run").

Usage:
  python3 tools/make_sample_data.py [--pull]
"""
import json
import os
import random
import shutil
import sys
from datetime import date, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import build_perf as bp  # noqa: E402  (needs ROOT on sys.path first)

CLIENTS = ["FCI", "AB", "BAIP", "MCDIC", "MDIC", "WLA", "PDC", "CSSD"]
START = date(2026, 10, 1)
END = date(2026, 11, 19)                       # last day stored in meta_daily
PULL_SINCE, PULL_UNTIL = date(2026, 11, 14), date(2026, 11, 22)
rng = random.Random(42)


def daterange(a, b):
    d = a
    while d <= b:
        yield d
        d += timedelta(days=1)


def write_json(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, separators=(",", ":"))


def day_numbers():
    spend = round(rng.uniform(6, 45), 2)
    return [spend, int(spend * rng.uniform(0.8, 2.0)), int(spend * rng.uniform(60, 140))]


def build_client(ci, c):
    """Return (meta_daily, ghl contacts) for one client, using the campaign map in build_perf.py."""
    cmap = bp.WLA_CAMP_MAP if c == "WLA" else bp.CAMP_MAPS[c]
    meta_daily, contacts = {}, []
    for k, (cid, bucket) in enumerate(sorted(cmap.items())):
        area = bp.CAMP_AREA.get(c, {}).get(cid)
        for j in range(3):
            launch = START + timedelta(days=5 * k + 4 * j)
            stop = END if j < 2 else END - timedelta(days=9)    # third ad of each campaign is paused
            if launch > stop:
                continue
            ad_id = f"98{ci:02d}{k:02d}{j:02d}" + "0" * 10        # 18 digits, clearly fake
            code = f"{launch:%y.%m.%d}-{j + 1:02d}"               # YY.MM.DD-NN, the ad code convention
            ad = {"name": f"{code} - {bucket} - Sample ad {k + 1}.{j + 1}", "cid": cid,
                  "days": {d.isoformat(): day_numbers() for d in daterange(launch, stop)}}
            if c == "CSSD" and bucket == "Lower Funnel":          # shows the adset 'tipo' label
                ad["adset_id"] = f"9{ci}00{k}{j}"
                ad["tipo"] = "Second Opinion" if j == 1 else "Lower Funnel"
            meta_daily[ad_id] = ad
            for day, (spend, _clicks, _imp) in ad["days"].items():
                for _ in range(int(spend // rng.uniform(14, 30))):
                    tags = ["lead"]
                    if rng.random() < 0.45:
                        tags.append("good-lead")
                        if rng.random() < 0.4:
                            tags.append("better-lead")
                        if rng.random() < 0.5:
                            tags.append("appt-confirmed")
                            if rng.random() < 0.6:
                                tags.append("appt-showed")
                                if rng.random() < 0.4:
                                    tags.append("client")
                    ct = {"id": f"sample-{c}-{len(contacts) + 1:05d}",
                          "dateAdded": f"{day}T{rng.randint(12, 23):02d}:{rng.randint(0, 59):02d}:00.000Z",
                          "tags": tags, "source": bucket, "code": code}
                    if area:
                        ct["area"] = area
                    contacts.append(ct)
    return meta_daily, contacts


def write_pruebas():
    folder = os.path.join(ROOT, "pruebas")
    os.makedirs(folder, exist_ok=True)
    hls = {"S-HL1": {"texto": "Sample headline one"}, "S-HL2": {"texto": "Sample headline two"},
           "S-HL3": {"texto": "Sample headline three"}}
    base = {"area": None, "cre": None, "cond": "", "conf": "firme", "origen": "2026-11-14"}
    registros = [
        dict(base, cliente="FCI", campana="ThinArch", nid="FCI-TA-01", gana=[["hl", "S-HL1"]],
             pierde=[["hl", "S-HL2"]], r="comp", id="P001"),
        dict(base, cliente="FCI", campana="T1D", nid="FCI-T1-01", gana=[["hl", "S-HL3"]],
             pierde=[], r="mejor", id="P002"),
        dict(base, cliente="AB", campana="ThinArch", nid="AB-TA-01", gana=[],
             pierde=[["hl", "S-HL2"]], r="malo", id="P003", conf="debil"),
    ]
    write_json(os.path.join(folder, "registros.json"), {"hls": hls, "registros": registros})
    notes = ["clave|nota",
             "FCI-TA-01|Sample note: headline one beat headline two after two weeks.",
             "FCI-T1-01|Sample note: headline three looks better than the control.",
             "AB-TA-01|Sample note: headline two did not work."]
    with open(os.path.join(folder, "notas_originales.csv"), "w", encoding="utf-8") as f:
        f.write("\n".join(notes) + "\n")


def write_pull(all_meta):
    """Simulated ads_get_ad_entities answers: one spend file and one status file per client."""
    out = os.path.join(ROOT, "meta_results")
    shutil.rmtree(out, ignore_errors=True)
    os.makedirs(out)
    for ci, c in enumerate(CLIENTS):
        rows, status, revised = [], [], False
        for ad_id, ad in all_meta[c].items():
            running_at_end = END.isoformat() in ad["days"]
            for d in daterange(PULL_SINCE, PULL_UNTIL):
                v = ad["days"].get(d.isoformat())
                if v is None and d > END and running_at_end:
                    v = day_numbers()                              # a day that is new for the dashboard
                elif v is not None and not revised:
                    v, revised = [round(v[0] + 0.37, 2), v[1], v[2]], True   # Meta corrected one old figure
                if v is None:
                    continue
                rows.append({"id": ad_id, "campaign_id": ad["cid"], "name": ad["name"],
                             "amount_spent": {"value": f"{v[0]:.2f}", "unit": "USD"},
                             "clicks": str(v[1]), "impressions": str(v[2]),
                             "date_start": d.isoformat(), "date_stop": d.isoformat()})
            if running_at_end:
                status.append({"id": ad_id, "campaign_id": ad["cid"], "effective_status": "ACTIVE",
                               "date_start": PULL_UNTIL.isoformat(), "date_stop": PULL_UNTIL.isoformat()})
        for number, payload in ((1000 + ci, rows), (2000 + ci, status)):
            path = os.path.join(out, f"mcp-sample-ads_get_ad_entities-{number}.txt")
            write_json(path, {"ad_entities": json.dumps(payload), "client_conversation_id": "sample"})


def main():
    all_meta = {}
    active = {}
    for ci, c in enumerate(CLIENTS):
        meta_daily, contacts = build_client(ci, c)
        all_meta[c] = meta_daily
        write_json(os.path.join(ROOT, f"meta_daily_{c}.json"), meta_daily)
        write_json(os.path.join(ROOT, f"ghl_{c}.json"), {"contacts": contacts})
        write_json(os.path.join(ROOT, f"perf_{c}.json"),
                   {"client": c, "start": START.isoformat(), "presets": {}, "ads": []})
        active[c] = {"asof": END.isoformat(),
                     "active": sorted(a for a, ad in meta_daily.items() if END.isoformat() in ad["days"])}
        print(f"{c}: {len(meta_daily)} ads, {len(contacts)} contacts")
    write_json(os.path.join(ROOT, "ad_status.json"), active)
    write_json(os.path.join(ROOT, "abtests.json"), {})
    with open(os.path.join(ROOT, "update_log.txt"), "w", encoding="utf-8") as f:
        f.write("=== sample data generated by tools/make_sample_data.py ===\n")
    if not os.path.exists(os.path.join(ROOT, "clients.json")):
        shutil.copyfile(os.path.join(ROOT, "clients.example.json"), os.path.join(ROOT, "clients.json"))
        print("clients.json created from clients.example.json (placeholders only)")
    write_pruebas()
    if "--pull" in sys.argv:
        write_pull(all_meta)
        print("meta_results/ written (simulated Meta answers)")


if __name__ == "__main__":
    main()
