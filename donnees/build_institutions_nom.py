"""Construit donnees/institutions_nommees.json : caisse de vacances + SEPPT agréés.

Sources officielles :
  - ONVA / RJV      : https://www.onva.fgov.be/fr/contact  et  https://www.rjv.fgov.be/nl/contact
  - SEPPT agréés    : https://emploi.belgique.be/fr/agrements/agrement-services-externes-pour-la-
                      prevention-et-la-protection-au-travail-seppt   (+ sa version NL)

Usage : python3 build_institutions_nom.py seppt_liste.json seppt_liste_nl.json
"""
import json
import re
import sys

FR_P, NL_P = sys.argv[1], sys.argv[2]

# Clés de reconnaissance : la gestionnaire tape « Mensura », « Securex »… On réutilise
# la même logique que _pdc_du_seppt (sous-chaîne sur un nom court et distinctif).
CLES = ('clb', 'attentia', 'cesi', 'cohezio', 'idewe', 'liantis', 'mediwet',
        'mensura', 'premed', 'securex')

CAISSE = {
    'fr': {'nom': 'Office National des Vacances Annuelles',
           'rue': 'Rue Montagne aux Herbes Potagères', 'no': '48',
           'cp': '1000', 'localite': 'BRUXELLES'},
    'nl': {'nom': 'Rijksdienst voor Jaarlijkse Vakantie',
           'rue': 'Warmoesberg', 'no': '48', 'cp': '1000', 'localite': 'Brussel'},
}


def coupe(rue):
    """« Avenue du Boulevard 21 boîte 9 » -> (« Avenue du Boulevard », « 21 boîte 9 »)."""
    m = re.match(r'^(.*?[^\d\s])\s+(\d.*)$', (rue or '').strip())
    return (m.group(1).strip(), m.group(2).strip()) if m else ((rue or '').strip(), '')


def cle_de(nom):
    n = (nom or '').lower()
    return next((c for c in CLES if c in n), None)


fr = {cle_de(d['nom']): d for d in json.load(open(FR_P, encoding='utf-8')) if cle_de(d['nom'])}
nl = {cle_de(d['nom']): d for d in json.load(open(NL_P, encoding='utf-8')) if cle_de(d['nom'])}

manquants = [c for c in CLES if c not in fr or c not in nl]
assert not manquants, f'SEPPT non reconnus dans la liste officielle : {manquants}'

seppt = []
for c in CLES:
    a, b = fr[c], nl[c]
    # garde-fou de concordance, comme pour les services de contrôle : si les 2 pages ne
    # désignent pas le même immeuble, c'est qu'une des deux est périmée -> le FR fait foi.
    if a['cp'] != b['cp']:
        print(f"  ! {c} : CP FR {a['cp']} != NL {b['cp']} -> on garde le FR des deux côtés")
        b = a
    ra, na_ = coupe(a['rue'])
    rb, nb_ = coupe(b['rue'])
    seppt.append({
        'cle': c,
        'fr': {'nom': a['nom'], 'rue': ra, 'no': na_, 'cp': a['cp'], 'localite': a['localite']},
        'nl': {'nom': b['nom'], 'rue': rb, 'no': nb_, 'cp': b['cp'], 'localite': b['localite']},
    })

data = {'caisse_vacances': CAISSE, 'seppt': seppt}
json.dump(data, open('institutions_nommees.json', 'w', encoding='utf-8'),
          ensure_ascii=False, indent=1, sort_keys=True)
print(f'{len(seppt)} SEPPT + la caisse de vacances -> institutions_nommees.json')
