# -*- coding: utf-8 -*-
"""Bugs trouvés en comparant au règlement de RÉFÉRENCE (AUTO VIRAGE, CP 140.03, NL)
le 27/07/2026 — le banc « portail vs original » de Dims.

1. Fonds de la CP 140.03 : le SPF liste les fonds autobus/autocars (140.01) sur la
   page commune « CP 140 » -> ils polluaient toutes les sous-commissions. Le vrai
   fonds du 140.03 est le SFTL (correction nommée dans donnees/reconcilier_fse.py).
2. Point 7 « Sociaal Kantoor » : le n° d'affiliation doit être le n° de dossier
   PersoProject (numero_employeur, ex. 2493), PAS le n° ONSS.
"""
import io
import os
import re
import sys
import zipfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import reglement_gen as R  # noqa: E402

BUNDLE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..',
                      '_reglement_bundle')


def _tpl(lang):
    p = os.path.join(BUNDLE, f'reglement_{lang}.docx')
    if not os.path.exists(p):
        pytest.skip(f'modèle absent : {p}')
    with open(p, 'rb') as f:
        return f.read()


def _texte(b):
    return re.sub(r'<[^>]+>', '',
                  zipfile.ZipFile(io.BytesIO(b)).read('word/document.xml').decode('utf-8'))


# ---------- 1. fonds 140.03 ----------

def test_fonds_140_03_nl_est_le_sftl():
    fonds = R._fonds_principal('140.03', 'NL')
    assert fonds and fonds.get('nom') == 'Sociaal Fonds Transport en Logistiek'

def test_fonds_140_03_fr_est_le_fstl():
    fonds = R._fonds_principal('140.03', 'FR')
    assert fonds and fonds.get('nom') == 'Fonds Social Transport et Logistique'

def test_reglement_nl_140_03_imprime_le_sftl():
    payload = {'reglement_langue': 'NL', 'regimes': [{'cp': '140.03'}]}
    txt = _texte(R.build_reglement(payload, {'nom_societe': 'X'}, _tpl('NL')))
    assert 'Sociaal Fonds Transport en Logistiek' in txt
    assert 'autocardiensten' not in txt   # les fonds 140.01 ne fuient plus

def test_fonds_140_01_reste_autobus():
    # La correction ne touche QUE la 140.03 : le 140.01 garde ses fonds autocars.
    fonds = R._fonds_principal('140.01', 'NL')
    assert fonds and 'autocardiensten' in fonds.get('nom', '')


# ---------- 2. n° de dossier PersoProject (point 7) ----------

def test_no_employeur_est_le_numero_de_dossier():
    v = R._valeurs({'numero_employeur': '2493', 'num_onss': '1485505-52'}, {}, None)
    assert v['No_employeur_Em'] == '2493'

def test_no_employeur_sans_dossier_reste_blanc_pas_onss():
    # Sans n° de dossier, on laisse un blanc à compléter — on n'imprime JAMAIS
    # le n° ONSS à la place (bug AUTO VIRAGE : 1485505-52 au lieu de 2493).
    v = R._valeurs({'num_onss': '1485505-52'}, {}, None)
    assert v['No_employeur_Em'] == R.BLANK

def test_reglement_imprime_le_numero_de_dossier():
    payload = {'reglement_langue': 'NL', 'numero_employeur': '2493'}
    txt = _texte(R.build_reglement(payload, {'nom_societe': 'X'}, _tpl('NL')))
    assert '2493' in txt


# ---------- 3. point « contributions directes » : team perception par langue ----------
# Source : finances.belgium.be (Déclaration au précompte professionnel, 27/07/2026) —
# le bureau dépend de la LANGUE de la déclaration, pas du secteur. Les 2 règlements
# de référence (transport) écrivaient un générique « Team Perception Précompte Prof. ».

def test_contributions_fr_team_namur():
    txt = _texte(R.build_reglement({'reglement_langue': 'FR'}, {'nom_societe': 'X'}, _tpl('FR')))
    assert 'Team Précompte Professionnel Namur' in txt

def test_contributions_nl_team_mechelen():
    txt = _texte(R.build_reglement({'reglement_langue': 'NL'}, {'nom_societe': 'X'}, _tpl('NL')))
    assert 'Team Bedrijfsvoorheffing Mechelen' in txt

def test_contributions_fr_pas_le_seppt():
    # Le défaut ne doit pas écraser la protection anti-doublon SEPPT/point 8.
    txt = _texte(R.build_reglement({'reglement_langue': 'FR', 'seppt': 'Mensura'},
                                   {'nom_societe': 'X'}, _tpl('FR')))
    import re as _re
    m = _re.search(r'Bureau des contributions directesDénomination\s*:\s*(.{0,40})', txt)
    assert m and 'Mensura' not in m.group(1)
    assert m and 'Team Précompte Professionnel Namur' in m.group(1) + txt[txt.find('Bureau des contributions'):][:120]
