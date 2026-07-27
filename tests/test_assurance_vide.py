# -*- coding: utf-8 -*-
"""Assurance-loi inconnue -> le point 3 de l'Article 2 est SUPPRIMÉ (décision Dims
27/07/2026, alignée sur la pratique de la gestionnaire), au lieu de pointillés.

Ce qu'on verrouille, en FR ET en NL :
- sans assurance : plus de titre « Assurance-loi / Verzekeringsmaatschappij » ;
- les points voisins (2. caisse, 4. fonds) restent intacts — on ne supprime QUE lui ;
- avec assurance (formulaire) : le bloc reste et porte le nom saisi ;
- avec assurance via institutions Prisma : le bloc reste (la couche la plus forte).
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
TPL = {'FR': os.path.join(BUNDLE, 'reglement_FR.docx'),
       'NL': os.path.join(BUNDLE, 'reglement_NL.docx')}
TITRE = {'FR': 'Assurance-loi accidents du travail',
         'NL': 'Verzekeringsmaatschappij tegen arbeidsongevallen'}
# NB : le modèle FR écrit « d'existence » avec l'apostrophe TYPOGRAPHIQUE (U+2019) ;
# on s'ancre sur un fragment sans apostrophe pour ne pas dépendre du glyphe.
VOISINS = {'FR': ('Caisse de vacances annuelles', 'Fonds de sécurité'),
           'NL': ('Kas voor jaarlijkse vakantie', 'Fondsen voor bestaanszekerheid')}


def _tpl(lang):
    p = TPL[lang]
    if not os.path.exists(p):
        pytest.skip(f"modèle absent : {p}")
    with open(p, 'rb') as f:
        return f.read()


def _texte(docx_bytes):
    x = zipfile.ZipFile(io.BytesIO(docx_bytes)).read('word/document.xml').decode('utf-8')
    return re.sub(r'<[^>]+>', '', x)


@pytest.mark.parametrize('lang', ['FR', 'NL'])
def test_sans_assurance_le_bloc_disparait(lang):
    txt = _texte(R.build_reglement({'reglement_langue': lang}, {'nom_societe': 'X'}, _tpl(lang)))
    assert TITRE[lang] not in txt


@pytest.mark.parametrize('lang', ['FR', 'NL'])
def test_sans_assurance_les_voisins_restent(lang):
    txt = _texte(R.build_reglement({'reglement_langue': lang}, {'nom_societe': 'X'}, _tpl(lang)))
    for voisin in VOISINS[lang]:
        assert voisin in txt, f"le point voisin « {voisin} » a disparu avec l'assurance"


@pytest.mark.parametrize('lang', ['FR', 'NL'])
def test_avec_assurance_formulaire_le_bloc_reste(lang):
    payload = {'reglement_langue': lang, 'assurance_loi': 'AXA Belgium'}
    txt = _texte(R.build_reglement(payload, {'nom_societe': 'X'}, _tpl(lang)))
    assert TITRE[lang] in txt
    assert 'AXA Belgium' in txt


@pytest.mark.parametrize('lang', ['FR', 'NL'])
def test_avec_assurance_prisma_le_bloc_reste(lang):
    payload = {'reglement_langue': lang,
               'institutions_prisma': [{'uc_id': 'ucArbeidsongevallen',
                                        'nom1': 'Ethias', 'rue': 'Rue des Croisiers',
                                        'numero': '24', 'code_postal': '4000',
                                        'localite': 'Liège'}]}
    txt = _texte(R.build_reglement(payload, {'nom_societe': 'X'}, _tpl(lang)))
    assert TITRE[lang] in txt
    assert 'Ethias' in txt
