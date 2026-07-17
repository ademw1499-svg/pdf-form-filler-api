"""Offre de collaboration 2026-2027 : le calque doit être VISIBLE, pas seulement présent.

Le bug qu'on garde : les templates exportés depuis Word/Pages laissent un clip ouvert
(le filet de bas de page, 455 x 3,4 pt) et la page « contrat de mandat » a un q non
refermé. Avec merge_page(), notre texte était dessiné DANS cette bande minuscule :
présent dans le fichier et extractible par pdfplumber, mais invisible à l'écran —
donc indétectable par un test qui se contente de chercher le texte.

On vérifie ici les invariants qui rendent ce bug impossible : template et calque sont
chacun dans un Form XObject (l'opérateur Do sauvegarde/restaure l'état graphique) et
les ressources du calque résolvent réellement.
"""
import io
import os
import re
import sys

import pdfplumber
import pytest
from pypdf import PdfReader
from pypdf.generic import ArrayObject, IndirectObject, NameObject

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import app  # noqa: E402

DONNEES = {
    'nom_societe': 'BOULANGERIE TEST SRL', 'adresse_1': 'Rue du Pain 12',
    'adresse_2': '1000 Bruxelles', 'num_tva': 'BE 0555.123.456',
    'represente_par': 'Jean Dupont', 'nom_soussigne': 'Jean Dupont',
    'niss': '85.01.01-123.45', 'qualite': 'Gérant', 'date_signature': '17/07/2026',
    'date_fait': '17/07/2026', 'date_entree_jour': '01', 'date_entree_mois': '08',
    'date_entree_annee': '2026',
}

LANGUES = ['fr', 'nl']


@pytest.fixture(scope='module')
def offres():
    cwd = os.getcwd()
    os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    try:
        return {lg: app.fill_offre_pdf(DONNEES, lg) for lg in LANGUES}
    finally:
        os.chdir(cwd)


def _pages_a_champs(lang):
    return app.OFFRE_LAYOUT[lang]['pages'].items()


def _contenu(page):
    c = page.get(NameObject('/Contents')).get_object()
    if isinstance(c, ArrayObject):
        return b'\n'.join(s.get_object().get_data() for s in c)
    return c.get_data()


@pytest.mark.parametrize('lang', LANGUES)
def test_pages_attendues(offres, lang):
    """FR 20 pages / NL 21 pages : les 2 documents n'ont pas la même pagination."""
    attendu = {'fr': 20, 'nl': 21}[lang]
    assert len(PdfReader(io.BytesIO(offres[lang])).pages) == attendu


@pytest.mark.parametrize('lang', LANGUES)
def test_calque_isole_dans_un_form_xobject(offres, lang):
    """Sans cette isolation, un clip du template masque tout notre texte."""
    rd = PdfReader(io.BytesIO(offres[lang]))
    for nom, idx in _pages_a_champs(lang):
        page = rd.pages[idx]
        assert _contenu(page).split() == [b'q', b'/__tpl', b'Do', b'Q',
                                          b'q', b'/__ovl', b'Do', b'Q'], \
            f'{lang}/{nom} : le flux de page doit se limiter aux deux Do isolés'
        xo = page['/Resources']['/XObject']
        for cle in ('/__tpl', '/__ovl'):
            form = xo[cle].get_object()
            assert form['/Subtype'] == '/Form', f'{lang}/{nom}{cle} pas un Form'
            bbox = [float(v) for v in form['/BBox']]
            mb = page.mediabox
            assert bbox[2] - bbox[0] >= float(mb.width) - 1, \
                f'{lang}/{nom}{cle} : BBox plus étroite que la page -> texte rogné'
            assert bbox[3] - bbox[1] >= float(mb.height) - 1, \
                f'{lang}/{nom}{cle} : BBox plus basse que la page -> texte rogné'


@pytest.mark.parametrize('lang', LANGUES)
def test_polices_du_calque_resolvent(offres, lang):
    """Le calque vient d'un autre document : sans clone() dans le writer, ses
    polices pointent dans le vide et rien ne s'affiche (template intact, texte absent)."""
    rd = PdfReader(io.BytesIO(offres[lang]))
    for nom, idx in _pages_a_champs(lang):
        form = rd.pages[idx]['/Resources']['/XObject']['/__ovl'].get_object()
        # pypdf 3.17 (prod) ne déréférence pas tout seul, pypdf 6 (local) si.
        res = form['/Resources'].get_object()
        polices = res.get('/Font')
        polices = polices.get_object() if polices is not None else None
        assert polices, f'{lang}/{nom} : calque sans police'
        utilisees = set(re.findall(rb'(/[A-Za-z0-9#+.-]+)\s+[\d.]+\s+Tf',
                                   form.get_data()))
        assert utilisees, f'{lang}/{nom} : aucun Tf dans le calque'
        for u in utilisees:
            nom_police = u.decode('latin-1')
            assert nom_police in polices, \
                f'{lang}/{nom} : {nom_police} utilisée mais absente des ressources'
            ref = polices.raw_get(nom_police)
            if isinstance(ref, IndirectObject):
                assert ref.get_object() is not None, \
                    f'{lang}/{nom} : {nom_police} est une référence morte'


def _sans_pointilles(s):
    """Les « ……… » du template s'intercalent dans le texte extrait."""
    return re.sub(r'[\s.…]', '', s or '')


@pytest.mark.parametrize('lang', LANGUES)
def test_valeurs_sur_les_bonnes_pages(offres, lang):
    attendu = {
        'cover': ['BOULANGERIETESTSRL', 'RueduPain12', '1000Bruxelles', 'JeanDupont'],
        'cond': ['BOULANGERIETESTSRL', 'BE0555123456', 'JeanDupont', '17/07/2026'],
        'proc': ['BOULANGERIETESTSRL', 'JeanDupont', '850101-12345', 'Gérant'],
        'mandat': ['BOULANGERIETESTSRL', 'JeanDupont', '850101-12345', 'Gérant'],
    }
    with pdfplumber.open(io.BytesIO(offres[lang])) as pdf:
        for nom, idx in _pages_a_champs(lang):
            texte = _sans_pointilles(pdf.pages[idx].extract_text())
            for v in attendu[nom]:
                assert _sans_pointilles(v) in texte, \
                    f'{lang}/{nom} (p{idx}) : « {v} » absent'


@pytest.mark.parametrize('lang', LANGUES)
def test_pages_sans_champ_intactes(offres, lang):
    """Les pages statiques (conditions générales, annexes) ne doivent pas bouger."""
    cwd = os.getcwd()
    os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    try:
        tpl = app.TEMPLATES['offre_nl' if lang == 'nl' else 'offre_fr']
        src = PdfReader(tpl)
        out = PdfReader(io.BytesIO(offres[lang]))
        touchees = set(app.OFFRE_LAYOUT[lang]['pages'].values())
        for i in range(len(src.pages)):
            if i in touchees:
                continue
            assert (src.pages[i].extract_text() or '') == \
                   (out.pages[i].extract_text() or ''), f'{lang} : page {i} altérée'
    finally:
        os.chdir(cwd)


def test_champ_vide_nimprime_rien(offres):
    """Un champ absent des données ne doit pas écrire « None » sur le document."""
    cwd = os.getcwd()
    os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    try:
        b = app.fill_offre_pdf({'nom_societe': 'SEULE SRL'}, 'fr')
    finally:
        os.chdir(cwd)
    with pdfplumber.open(io.BytesIO(b)) as pdf:
        for idx in app.OFFRE_LAYOUT['fr']['pages'].values():
            t = pdf.pages[idx].extract_text() or ''
            assert 'None' not in t, f'page {idx} : « None » imprimé'
