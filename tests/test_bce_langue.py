# -*- coding: utf-8 -*-
"""BCE bilingue : `_bce_forme` reconnaît les libellés FR ET NL de la forme
juridique et rend la valeur DANS la langue demandée. (La lecture live de la
fiche BCE FR/NL est vérifiée en prod, pas en test — elle dépend du réseau.)

Contexte : un règlement NL sortait « SRL » / « Transport routier de fret » au lieu
de « Besloten Vennootschap » / « Goederenvervoer… » — la BCE était lue en FR en dur.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import app  # noqa: E402


def test_srl_fr():
    assert app._bce_forme('Société à responsabilité limitée', 'fr') == 'SRL'

def test_bv_nl():
    assert app._bce_forme('Besloten vennootschap', 'nl') == 'Besloten Vennootschap'

def test_sa_fr_et_nv_nl():
    assert app._bce_forme('Société anonyme', 'fr') == 'SA'
    assert app._bce_forme('Naamloze vennootschap', 'nl') == 'Naamloze Vennootschap'

def test_reconnait_les_deux_langues_dans_le_texte():
    # texte NL mais sortie FR demandée, et l'inverse
    assert app._bce_forme('besloten vennootschap', 'fr') == 'SRL'
    assert app._bce_forme('société à responsabilité limitée', 'nl') == 'Besloten Vennootschap'

def test_asbl_vzw():
    assert app._bce_forme('Association sans but lucratif', 'fr') == 'ASBL'
    assert app._bce_forme('Vereniging zonder winstoogmerk', 'nl') == 'VZW'

def test_inconnu_vide():
    assert app._bce_forme('Forme exotique', 'fr') == ''
    assert app._bce_forme('', 'nl') == ''
