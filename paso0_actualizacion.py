#!/usr/bin/env python3
"""Paso 0 de la actualizacion del dashboard en un solo comando y sin argumentos.

Revisa que clients.json exista, crea el respaldo con backup_datos.py y muestra
la ultima fecha guardada de Meta y de GHL por cliente, junto con el rango de Meta que toca traer hoy:
since es la fecha mas antigua guardada menos 6 dias y until es ayer.

Uso: python3 paso0_actualizacion.py
"""
import datetime, json, os, subprocess, sys

BASE = os.path.dirname(os.path.abspath(__file__))
CLIENTES = ["FCI", "AB", "BAIP", "MCDIC", "MDIC", "WLA", "PDC", "CSSD"]


def main():
    if not os.path.exists(os.path.join(BASE, "clients.json")):
        sys.exit("ERROR: no se encuentra clients.json. Copia clients.example.json a clients.json y completa los valores.")

    r = subprocess.run([sys.executable, os.path.join(BASE, "backup_datos.py")], capture_output=True, text=True)
    print((r.stdout + r.stderr).strip())
    if r.returncode != 0:
        sys.exit("ERROR: el respaldo termino con error, la actualizacion debe suspenderse.")

    ultimas = {}
    for c in CLIENTES:
        with open(os.path.join(BASE, f"meta_daily_{c}.json")) as f:
            md = json.load(f)
        meta = max(d for a in md.values() for d in a["days"])
        with open(os.path.join(BASE, f"ghl_{c}.json")) as f:
            ghl = max(x["dateAdded"][:10] for x in json.load(f)["contacts"] if x.get("dateAdded"))
        ultimas[c] = meta
        print(f"{c}: Meta hasta {meta} | GHL hasta {ghl}")

    mas_antigua = min(ultimas.values())
    since = datetime.date.fromisoformat(mas_antigua) - datetime.timedelta(days=6)
    until = datetime.date.today() - datetime.timedelta(days=1)
    print(f"RANGO DE META A TRAER: since {since} until {until} (hoy es {datetime.date.today()})")
    if until < datetime.date.fromisoformat(mas_antigua):
        print("AVISO: ayer es anterior a la ultima fecha guardada, no hay dias nuevos de Meta.")


if __name__ == "__main__":
    main()
