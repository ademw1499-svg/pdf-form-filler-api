#!/usr/bin/env python3
"""Récupère les modèles Word du règlement depuis Supabase Storage vers le dossier
local `../_reglement_bundle/` — celui que les tests attendent (voir tests/conftest.py).

Pourquoi : les modèles Word (reglement_FR.docx / reglement_NL.docx) ne sont PAS dans
le dépôt (il est PUBLIC, ce sont des documents PersoProject). La production les lit
depuis le bucket Supabase `reglement`. Ce script les télécharge du MÊME bucket : les
tests testent donc EXACTEMENT le document utilisé en prod.

À lancer une fois sur une nouvelle machine (ex. le PC 06), avant `pytest` :

    SUPABASE_URL="https://zjqhlnitvyyktuxykmbr.supabase.co" \
    SUPABASE_KEY="<clé service_role ou anon — variables Railway>" \
    python3 fetch_bundle.py

N'utilise que la bibliothèque standard. Si un modèle Word change un jour, ré-uploade-le
sur Supabase (upload_supabase.py) : prod ET tests resteront alignés.
"""
import os
import ssl
import sys
import urllib.request

URL = os.environ.get('SUPABASE_URL', '').rstrip('/')
KEY = os.environ.get('SUPABASE_KEY') or os.environ.get('SUPABASE_SERVICE_KEY') \
    or os.environ.get('SUPABASE_ANON_KEY')
if not URL or not KEY:
    sys.exit("Manque SUPABASE_URL et/ou SUPABASE_KEY (variables d'environnement). "
             "Les clés sont dans les variables du service Railway.")

BUCKET = 'reglement'
FICHIERS = ('reglement_FR.docx', 'reglement_NL.docx')
DEST = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '_reglement_bundle')
os.makedirs(DEST, exist_ok=True)

ctx = ssl.create_default_context()
ok = 0
for nom in FICHIERS:
    req = urllib.request.Request(
        f"{URL}/storage/v1/object/{BUCKET}/{nom}",
        headers={'apikey': KEY, 'Authorization': f'Bearer {KEY}'})
    try:
        with urllib.request.urlopen(req, timeout=30, context=ctx) as r:
            data = r.read()
    except Exception as e:
        print(f"  ✗ {nom} : {e}")
        continue
    # Un .docx est un zip PK — garde-fou contre un JSON d'erreur enregistré par erreur.
    if data[:2] != b'PK':
        print(f"  ✗ {nom} : réponse inattendue ({data[:80]!r}) — bucket/clé corrects ?")
        continue
    cible = os.path.join(DEST, nom)
    with open(cible, 'wb') as f:
        f.write(data)
    print(f"  ✓ {nom} -> {os.path.normpath(cible)} ({len(data)} octets)")
    ok += 1

if ok == len(FICHIERS):
    print(f"\n{ok}/{len(FICHIERS)} modèles récupérés. `python3 -m pytest tests/ -q` peut tourner.")
else:
    sys.exit(f"\n{ok}/{len(FICHIERS)} récupérés — corrige la clé/le bucket avant de lancer les tests.")
