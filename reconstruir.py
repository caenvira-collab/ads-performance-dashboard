#!/usr/bin/env python3
"""Paso 6 de la actualizacion en un solo comando y sin argumentos: reconstruye los perf de los 8 clientes
con rebuild_ghl_metrics y regenera dashboard.html con rebuild_dashboard.py.

Uso: python3 reconstruir.py
"""
import os, subprocess, sys

BASE = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE)
sys.path.insert(0, BASE)

import build_perf as bp

CLIENTES = ["FCI", "AB", "BAIP", "MCDIC", "MDIC", "WLA", "PDC", "CSSD"]

for c in CLIENTES:
    bp.rebuild_ghl_metrics(c, bp.WLA_CAMP_MAP if c == "WLA" else bp.CAMP_MAPS[c])

r = subprocess.run([sys.executable, os.path.join(BASE, "rebuild_dashboard.py")])

# Historial de pruebas: rearma pruebas/datos.js y revisa el callout Keep Your Gums fuera de ThinArch.
# Si falla, el dashboard ya quedo regenerado; el error se informa y no cambia el codigo de salida.
p = subprocess.run([sys.executable, os.path.join(BASE, "pruebas", "construir.py")])
if p.returncode != 0:
    print(f"AVISO: pruebas/construir.py termino con error {p.returncode}; el dashboard si se regenero")
sys.exit(r.returncode)
