"""Extrait les directions régionales du SPF Emploi (Contrôle des lois sociales et
Contrôle du bien-être au travail) : ressort + adresse POSTALE principale.

La page de chaque direction distingue « Bureau principal et adresse postale pour
l'ensemble de ... » des « Bureaux locaux (sur rendez-vous uniquement - pas d'envoi
postal à ces bureaux) ». Le règlement doit porter l'adresse postale -> on ne garde
que le bureau principal, soit UNE adresse par ressort.
"""
import glob
import json
import re
import sys
from html import unescape

MOTIF, DEST = sys.argv[1], sys.argv[2]


def lignes_de(f):
    h = open(f, encoding='utf-8', errors='replace').read()
    m = re.search(r'<h1', h)
    h = h[m.start():] if m else h
    fin = re.search(r'(<footer|Cartes et accessibilit|Lettre d.informa|Kaarten en |Nieuwsbrief)', h)
    if fin:
        h = h[:fin.start()]
    t = unescape(re.sub(r'<[^>]+>', '\n', h))
    return [re.sub(r'\s+', ' ', l).strip() for l in t.split('\n') if l.strip()]


def section(lignes, titres, stop):
    """Lignes situées entre un titre de `titres` et le prochain titre de `stop`."""
    for i, l in enumerate(lignes):
        if l.lower().rstrip(' :') in titres:
            out = []
            for j in range(i + 1, len(lignes)):
                if lignes[j].lower().rstrip(' :') in stop:
                    break
                out.append(lignes[j])
            return out
    return []


STOP = {'adresse', 'ressort', 'contact', 'adres', 'ambtsgebied', 'renseignements pratiques',
        'praktische inlichtingen', 'cartes et accessibilité', 'inspecteur du travail – directeur',
        'inspecteur du travail - directeur', 'arbeidsinspecteur – directeur',
        'arbeidsinspecteur - directeur', 'bureaux locaux', 'lokale kantoren'}

res = []
for f in sorted(glob.glob(MOTIF)):
    L = lignes_de(f)
    titre = L[0] if L else '?'
    bloc_ressort = section(L, {'ressort', 'ambtsgebied'}, STOP)
    bloc = section(L, {'adresse', 'adres'}, {'cartes et accessibilité', 'kaarten'})
    # Certaines pages (bien-être Liège) n'ont PAS de titre « Adresse » : l'adresse
    # suit directement le ressort. On la récupère là, et le ressort s'arrête avant.
    if not bloc:
        i = next((k for k, l in enumerate(bloc_ressort) if re.match(r'^\d{4}\s+\S', l)), None)
        if i is not None and i >= 1:
            bloc, bloc_ressort = bloc_ressort[i - 1:i + 1], bloc_ressort[:i - 1]
    ressort = ' '.join(bloc_ressort)
    # on coupe dès les bureaux locaux : ils ne reçoivent pas de courrier
    coupe = next((i for i, l in enumerate(bloc)
                  if re.search(r'bureaux locaux|lokale kantoren', l, re.I)), len(bloc))
    bloc = bloc[:coupe]
    bloc = [l for l in bloc if not re.match(
        r'^(bureau principal|hoofdkantoor|adresse postale)', l, re.I)]
    iloc = next((i for i, l in enumerate(bloc) if re.match(r'^\d{4}\s+\S', l)), None)
    rue = no = cp = loc = ''
    if iloc is not None:
        mloc = re.match(r'^(\d{4})\s+(.+)$', bloc[iloc])
        cp, loc = mloc.group(1), mloc.group(2).strip()
        avant = [l for l in bloc[:iloc] if l]
        if avant:
            voie = avant[-1]                       # la dernière ligne avant « CP Localité »
            mv = re.match(r'^(.*?[^\d\s])\s+(\d.*)$', voie)   # « Voorstraat 43 bus 03 02 »
            rue, no = (mv.group(1).strip(), mv.group(2).strip()) if mv else (voie, '')
    res.append({'fichier': f, 'direction': titre, 'ressort': ressort,
                'rue': rue, 'no': no, 'cp': cp, 'localite': loc})

json.dump(res, open(DEST, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
for r in res:
    print(f"{r['direction'][:56]:58s}")
    print(f"    ressort : {r['ressort'][:88]}")
    print(f"    adresse : {r['rue']} | {r['no']} | {r['cp']} | {r['localite']}")
