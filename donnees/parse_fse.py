"""Extrait la liste officielle des Fonds de sécurité d'existence (SPF Emploi, FR+NL) :
  - dénomination OFFICIELLE de chaque commission paritaire          -> règlement, point 9
  - fonds de sécurité d'existence : nom + adresse (+ tél/fax/mail)  -> règlement, point 4

Sortie : JSON {cp: {denomination, fonds: [{nom, adresse, tel, fax, mail, web}]}}

Pièges de la page source, tous rencontrés pour de vrai :
  - les CP 110 et 216 sont balisées <h3> alors que toutes les autres sont <h2>
    -> on classe par le TEXTE du titre, jamais par son niveau ;
  - « 102.02 & 102.04 ... » : un titre peut couvrir plusieurs CP ;
  - la CP 140 (transport) est découpée en sous-secteurs qui ont CHACUN leur fonds
    (« Sous-secteur des entreprises de taxis (140.06) ») -> les fonds qui suivent
    appartiennent à ces numéros-là, pas à 140. Une CP ainsi découpée est ambiguë
    telle quelle : on lui laisse sa dénomination mais AUCUN fonds, pour ne jamais
    imprimer le fonds d'un autre sous-secteur dans le règlement.
"""
import json
import re
import sys
from html import unescape

SRC, DEST = sys.argv[1], sys.argv[2]
h = open(SRC, encoding='utf-8', errors='replace').read()
mcorps = re.search(r'(<h2\b.*?)(?:<footer|<nav\b|</article>)', h, re.S)
corps = mcorps.group(1) if mcorps else h

RE_CP = re.compile(
    r'^((?:\d{1,3}(?:\.\d{2})?)(?:\s*(?:&|et|en|,)\s*\d{1,3}(?:\.\d{2})?)*)\s+(.+)$')
RE_FONDS_NUM = re.compile(r'^\d+\.\s')
RE_EST_CP = re.compile(r'commission\s+paritaire|paritair\s+(?:comit|subcomit)', re.I)
RE_SOUS = re.compile(r'^(?:sous-secteur|subsector)', re.I)


def txt(s):
    return re.sub(r'\s+', ' ', unescape(re.sub(r'<[^>]+>', ' ', s))
                  .replace('\xa0', ' ')).strip()


def infos(bloc):
    items = [txt(x) for x in re.findall(r'<(?:li|p)\b[^>]*>(.*?)</(?:li|p)>', bloc, re.S)]
    mm = re.search(r'mailto:([^"\'>\s?]+)', bloc)
    wm = re.search(r'href="(https?://[^"]+)"', bloc)
    tel = fax = adresse = ''
    for it in filter(None, items):
        if re.match(r'^T[ée]l', it, re.I):
            tel = re.sub(r'^T[ée]l\.?\s*:?\s*', '', it, flags=re.I).strip()
        elif re.match(r'^Fax', it, re.I):
            fax = re.sub(r'^Fax\.?\s*:?\s*', '', it, flags=re.I).strip()
        elif re.match(r'^(Mail\s*to|E-?mail)', it, re.I):
            continue
        elif re.search(r'\b\d{4}\s+[A-ZÀ-Ÿ]', it) and not adresse:
            adresse = it
    return {'adresse': adresse, 'tel': tel, 'fax': fax,
            'mail': unescape(mm.group(1)).strip() if mm else '',
            'web': wm.group(1).strip() if wm else ''}


titres = list(re.finditer(r'<h[23]\b[^>]*>(.*?)</h[23]>', corps, re.S))
data = {}
parents, cibles, ambigus = [], [], set()
for k, m in enumerate(titres):
    t = txt(m.group(1))
    if not t:
        continue
    suite = corps[m.end(): titres[k + 1].start() if k + 1 < len(titres) else len(corps)]
    # FR : « Sous-secteur ... (140.06) » ; NL : « 1. Subsector ... (140.01) » -> on
    # retire la numérotation AVANT de tester, sinon le NL passe pour un fonds.
    sans_num = re.sub(r'^\d+\.\s*', '', t).strip()
    mcp = RE_CP.match(t)
    if mcp and not RE_FONDS_NUM.match(t) and RE_EST_CP.search(mcp.group(2)):
        parents = re.findall(r'\d{1,3}(?:\.\d{2})?', mcp.group(1))
        cibles = list(parents)
        denom = mcp.group(2).strip(' :;.')
        for n in parents:
            data.setdefault(n, {'denomination': denom, 'fonds': []})
            data[n]['denomination'] = denom
    elif RE_SOUS.match(sans_num):
        # « Sous-secteur ... (140.06) » -> les fonds suivants sont à 140.06
        nums = re.findall(r'\((\d{1,3}\.\d{2})\)', t)
        if nums:
            cibles = nums
            ambigus.update(parents)          # la CP mère ne suffit plus à trancher
            for n in nums:
                data.setdefault(n, {'denomination': '', 'fonds': []})
                if not data[n]['denomination'] and parents:
                    data[n]['denomination'] = data[parents[0]]['denomination']
        else:
            cibles = list(parents)           # sous-secteur sans numéro -> reste sur la CP
    elif cibles:
        nom = sans_num
        if nom:
            f = dict({'nom': nom}, **infos(suite))
            for n in cibles:
                data[n]['fonds'].append(f)

for n in ambigus:
    data[n]['fonds'] = []                    # ex. CP 140 seule : on n'invente pas

json.dump(data, open(DEST, 'w', encoding='utf-8'), ensure_ascii=False, indent=1,
          sort_keys=True)
avec = sum(1 for v in data.values() if any(f['adresse'] for f in v['fonds']))
print(f'{len(data)} CP -> {DEST} | {avec} avec un fonds adressable | '
      f'{len(ambigus)} CP mères ambiguës (sous-secteurs) : {sorted(ambigus)}')
