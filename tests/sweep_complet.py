# -*- coding: utf-8 -*-
"""CONTRÔLE MANUEL DE PROFONDEUR (non collecté par pytest — lancer : python3 tests/sweep_complet.py)

Balayage de profondeur : UN règlement par CP et par langue (128 × 2 = 256 documents
réels), avec invariants stricts sur chacun. But : qu'aucune CP ne soit « la seule mal
ordonnée » qu'on découvre chez un client — le mécanisme du bug des fonds de pension.

Invariants par document :
  I1  la génération n'explose pas ;
  I2  aucun jeton {{...}} du modèle ne survit ;
  I3  la dénomination OFFICIELLE de la CP (dans la bonne langue) est imprimée ;
  I4  le point 4 ne cite JAMAIS un fonds de pension (pensio/pilier/pijler) ;
  I5  si la CP a un fonds social -> son nom est imprimé ; sinon -> blanc (…………) ;
  I6  l'article 66 porte une adresse (code postal à 4 chiffres) ;
  I7  aucun « None » littéral n'apparaît ;
  I8  le renvoi de l'article 4 vise l'annexe 11 (FR) / bijlage 11 (NL).
"""
import io
import json
import re
import sys
import zipfile
from html import unescape

import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import reglement_gen as R

BUNDLE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '_reglement_bundle')
TPL = {L: open(f'{BUNDLE}/reglement_{L}.docx', 'rb').read() for L in ('FR', 'NL')}
IDENT = {'nom_societe': 'SWEEP TEST SRL', 'forme_juridique': 'SRL',
         'adresse_siege_social_1': 'Rue du Test 1', 'adresse_siege_social_2': '1000 Bruxelles'}
RE_PENSION = R.RE_FONDS_PENSION

def texte(b):
    x = zipfile.ZipFile(io.BytesIO(b)).read('word/document.xml').decode('utf-8')
    t = re.sub(r'<[^>]+>', '', x)
    t = re.sub(r'MERGEFIELD [A-Za-zÀ-ÿ0-9_]+ ', '', t)
    return re.sub(r'\s+', ' ', unescape(t))

fr = R._donnees('fse_fr')
echecs, faits = [], 0
for lang in ('FR', 'NL'):
    data = R._donnees('fse_nl' if lang == 'NL' else 'fse_fr')
    ancre = ('Fonds de sécurité d’existence ou Fonds socialDénomination :'
             if lang == 'FR' else 'Fondsen voor bestaanszekerheid of Sociaal FondsBenaming :')
    ancre_plate = re.sub(r'\s+', ' ', ancre)
    for cp in sorted(fr):
        faits += 1
        ctx = f'{lang} CP {cp}'
        try:
            b = R.build_reglement(
                {'reglement_langue': lang, 'num_entreprise': '0999999999',
                 'regimes': [{'cp': cp}], 'seppt': 'Mensura'}, IDENT, TPL[lang])   # I1
        except Exception as e:
            echecs.append(f'{ctx} I1 EXPLOSION : {e}'); continue
        t = texte(b)
        if re.search(r'\{\{[A-Za-z]', t):
            m = re.search(r'\{\{[^}]{0,40}', t)
            echecs.append(f'{ctx} I2 jeton survivant : {m.group(0)!r}')
        denom = (data.get(cp) or {}).get('denomination', '')
        if denom and denom[:60] not in t:
            echecs.append(f'{ctx} I3 dénomination absente : {denom[:50]!r}')
        i = t.find('Fonds de sécurité' if lang == 'FR' else 'Fondsen voor bestaanszekerheid')
        zone = t[i:i + 260] if i >= 0 else ''
        if not zone:
            echecs.append(f'{ctx} I4 ancre du point 4 introuvable'); continue
        if RE_PENSION.search(zone.split('Adresse')[0].split('Adres')[0]):
            echecs.append(f'{ctx} I4 FONDS DE PENSION au point 4 : {zone[:90]!r}')
        fonds = R._fonds_principal(cp, lang)
        if fonds and fonds['nom'][:45] not in t:
            echecs.append(f'{ctx} I5 fonds attendu absent : {fonds["nom"][:45]!r}')
        if not fonds and not ('…' in zone):
            echecs.append(f'{ctx} I5 pas de fonds mais pas de blanc : {zone[:80]!r}')
        art66 = ('Contrôle des lois sociales' if lang == 'FR' else 'Inspectie van de sociale wetten')
        j = t.find(art66)
        if j < 0 or not re.search(r'\b\d{4}\b', t[j:j + 130]):
            echecs.append(f'{ctx} I6 article 66 sans adresse')
        if re.search(r'\bNone\b', t):
            echecs.append(f'{ctx} I7 « None » littéral')
        renvoi_ok = ('(annexe n° 11)' in t) if lang == 'FR' else ('bijlage nr. 11' in t)
        if not renvoi_ok:
            echecs.append(f'{ctx} I8 renvoi annexe 11 absent')

print(f'{faits} documents générés ({len(fr)} CP × 2 langues)')
if echecs:
    print(f'\n{len(echecs)} VIOLATION(S) :')
    for e in echecs[:40]:
        print('  ✗', e)
    sys.exit(1)
print('TOUS INVARIANTS RESPECTÉS (I1..I8)')
