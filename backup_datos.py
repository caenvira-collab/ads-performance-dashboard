#!/usr/bin/env python3
"""Respaldo de los datos del dashboard antes de cada actualizacion, y restauracion.

Uso:
  python3 backup_datos.py                    # crea backups/AAAA-MM-DD_HHMM/ y conserva los ultimos 8
  python3 backup_datos.py --list             # lista los respaldos disponibles
  python3 backup_datos.py --restore <nombre> # restaura ese respaldo (antes guarda el estado actual como antes_de_restaurar_...)

Se respaldan dashboard.html, perf_*, meta_daily_*, ghl_* de los 8 clientes activos, ad_status.json, abtests.json
y update_log.txt. El codigo (.py) y clients.json no se tocan en una actualizacion y quedan fuera.
"""
import datetime, os, shutil, sys

BASE = os.path.dirname(os.path.abspath(__file__))
DEST = os.path.join(BASE, "backups")
CLIENTES = ["FCI", "AB", "BAIP", "MCDIC", "MDIC", "WLA", "PDC", "CSSD"]
ARCHIVOS = (["dashboard.html", "ad_status.json", "abtests.json", "update_log.txt"]
            + [f"{p}_{c}.json" for p in ("perf", "meta_daily", "ghl") for c in CLIENTES])
CONSERVAR = 8


def copiar(origen_dir, destino_dir):
    os.makedirs(destino_dir, exist_ok=True)
    n = faltan = 0
    for f in ARCHIVOS:
        src = os.path.join(origen_dir, f)
        if not os.path.exists(src):
            faltan += 1
            print("  falta:", f)
            continue
        shutil.copyfile(src, os.path.join(destino_dir, f))  # el disco exFAT agrega por su cuenta un archivo ._ por cada archivo; es ruido del volumen
        n += 1
    return n, faltan


def listar():
    if not os.path.isdir(DEST):
        return []
    return sorted(d for d in os.listdir(DEST) if os.path.isdir(os.path.join(DEST, d)) and not d.startswith("antes_de_restaurar"))


def main():
    if "--list" in sys.argv:
        for d in listar():
            print(d)
        return
    if "--restore" in sys.argv:
        nombre = sys.argv[sys.argv.index("--restore") + 1]
        origen = os.path.join(DEST, nombre)
        if not os.path.isdir(origen):
            sys.exit(f"No existe el respaldo {nombre}. Disponibles: {listar()}")
        previo = os.path.join(DEST, "antes_de_restaurar_" + datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S"))
        copiar(BASE, previo)
        n, faltan = copiar(origen, BASE)
        print(f"Restaurados {n} archivos desde {nombre} ({faltan} ausentes). Estado anterior guardado en {previo}")
        return
    nombre = datetime.datetime.now().strftime("%Y-%m-%d_%H%M")
    destino = os.path.join(DEST, nombre)
    n, faltan = copiar(BASE, destino)
    if faltan:
        sys.exit(f"Respaldo incompleto en {destino}: faltan {faltan} archivos")
    for viejo in listar()[:-CONSERVAR]:
        shutil.rmtree(os.path.join(DEST, viejo))
    print(f"Respaldo {nombre}: {n} archivos, {sum(os.path.getsize(os.path.join(destino, f)) for f in ARCHIVOS) / 1e6:.1f} MB. Respaldos guardados: {len(listar())}")


if __name__ == "__main__":
    main()
