# -*- coding: utf-8 -*-
"""Assurance-loi inconnue -> le bloc (point 3 de l'Article 2) est CONSERVÉ avec les
champs vides. C'est ce que fait le règlement de RÉFÉRENCE (dossier AUTO VIRAGE,
comparé le 27/07/2026) : « 3. Verzekeringsmaatschappij … Benaming : ___ ».

Historique : une tentative de SUPPRESSION du bloc (27/07 matin) a été annulée
l'après-midi — elle laissait une ligne « Polisnummer » orpheline sur le point 2 et
cassait la numérotation, et surtout l'original garde le bloc. On verrouille ici le
bon comportement : le titre du point 3 est TOUJOURS présent (avec ou sans assureur).
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
def test_sans_assurance_le_bloc_reste(lang):
    # Pas d'assureur -> le bloc (titre point 3) est TOUJOURS là (comme l'original).
    txt = _texte(R.build_reglement({'reglement_langue': lang}, {'nom_societe': 'X'}, _tpl(lang)))
    assert TITRE[lang] in txt


@pytest.mark.parametrize('lang', ['FR', 'NL'])
def test_avec_assurance_formulaire_nom_present(lang):
    payload = {'reglement_langue': lang, 'assurance_loi': 'AXA Belgium'}
    txt = _texte(R.build_reglement(payload, {'nom_societe': 'X'}, _tpl(lang)))
    assert TITRE[lang] in txt
    assert 'AXA Belgium' in txt


@pytest.mark.parametrize('lang', ['FR', 'NL'])
def test_avec_assurance_prisma_nom_present(lang):
    payload = {'reglement_langue': lang,
               'institutions_prisma': [{'uc_id': 'ucArbeidsongevallen',
                                        'nom1': 'Ethias', 'rue': 'Rue des Croisiers',
                                        'numero': '24', 'code_postal': '4000',
                                        'localite': 'Liège'}]}
    txt = _texte(R.build_reglement(payload, {'nom_societe': 'X'}, _tpl(lang)))
    assert TITRE[lang] in txt
    assert 'Ethias' in txt
