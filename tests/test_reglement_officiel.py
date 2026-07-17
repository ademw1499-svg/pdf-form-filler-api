# -*- coding: utf-8 -*-
"""Données officielles du règlement de travail (demandes du 2026-07-17) :

  point 9   : dénomination OFFICIELLE de la CP (et non le libellé libre de l'écran)
  point 4   : fonds de sécurité d'existence de la CP (nom + adresse)
  article 4 : le renvoi vise l'annexe 11 (accusé de réception), pas la 10
  article 66: services de contrôle compétents pour la province du client
  annexe 5  : pas de siège d'exploitation en construction (124) ni en transport (140)

Source des données : liste des Fonds de sécurité d'existence + directions régionales
du SPF Emploi (dossier donnees/).
"""
import io
import os
import re
import sys
import zipfile
from html import unescape

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import reglement_gen as R  # noqa: E402

BUNDLE = os.path.join(os.path.dirname(__file__), '..', '..', '_reglement_bundle')


def _tpl(lang):
    p = os.path.join(BUNDLE, f'reglement_{lang}.docx')
    if not os.path.exists(p):
        pytest.skip(f'modèle absent : {p}')
    with open(p, 'rb') as f:
        return f.read()


def _texte(b):
    x = zipfile.ZipFile(io.BytesIO(b)).read('word/document.xml').decode('utf-8')
    t = re.sub(r'<[^>]+>', '', x)
    t = re.sub(r'MERGEFIELD [A-Za-zÀ-ÿ0-9_]+ ', '', t)
    return re.sub(r'\s+', ' ', unescape(t))


IDENT = {'nom_societe': 'CARWASH TEST SRL', 'adresse_siege_social_1': 'Rue Haute 12',
         'adresse_siege_social_2': '1880 Kapelle-op-den-Bos',   # -> Brabant flamand
         'sieges_exploitation': 'Rue du Dépôt 8 — 1000 Bruxelles'}


def gen(lang, cps, **extra):
    payload = {'reglement_langue': lang, 'num_entreprise': '0754615359',
               'regimes': [{'cp': c} for c in cps]}
    payload.update(extra)
    return _texte(R.build_reglement(payload, IDENT, _tpl(lang)))


# --------------------------------------------------------------- données embarquées
def test_fse_les_deux_langues_couvrent_les_memes_cp():
    fr, nl = R._donnees('fse_fr'), R._donnees('fse_nl')
    assert fr and nl
    assert set(fr) == set(nl), 'FR et NL doivent lister les mêmes commissions paritaires'


@pytest.mark.parametrize('cp,lang,attendu', [
    ('112', 'FR', 'Commission paritaire des entreprises de garage'),
    ('121', 'FR', 'Commission paritaire pour le nettoyage'),
    ('124', 'FR', 'Commission paritaire de la construction'),
    ('112', 'NL', 'Paritair Comité voor het garagebedrijf'),
    ('121', 'NL', 'Paritair Comité voor de schoonmaak'),
    ('112.00', 'FR', 'Commission paritaire des entreprises de garage'),   # « .00 » toléré
])
def test_denomination_officielle(cp, lang, attendu):
    assert R._fse_info(cp, lang).get('denomination') == attendu


def test_fonds_principal_est_le_fonds_social_pas_le_2e_pilier():
    """La CP 112 a un fonds social ET un fonds pension « 2e pilier » : le point 4
    vise le premier."""
    f = R._fonds_principal('112', 'FR')
    assert f['nom'] == 'Fonds social des entreprises de garage'
    assert f['adresse'] and re.search(r'\d{4}', f['adresse'])


def test_fonds_cp_107_conforme_a_la_source():
    """Contrôle bout en bout sur l'exemple de la liste officielle."""
    f = R._fonds_principal('107', 'FR')
    assert f['nom'] == 'Fonds commun pour vêtements sur mesure et couture dames'
    assert f['adresse'] == 'Quai de Willebroeck 37, 1000 BRUXELLES'
    assert f['tel'] == '02/238.06.51' and f['mail'] == 'pascal.cillis@unizo.be'


def test_cp140_nue_na_pas_de_fonds_mais_ses_sous_secteurs_si():
    """Chaque sous-secteur du transport a SON fonds : sur « 140 » seule on ne peut pas
    trancher, et il vaut mieux un blanc qu'un fonds faux."""
    assert R._fonds_principal('140', 'FR') is None
    assert R._fonds_principal('140.03', 'FR')['nom'].startswith('Fonds social pour les ouvriers')
    assert R._fonds_principal('140.04', 'FR')['nom'] == 'Fonds social Transport et Logistique'
    assert R._fonds_principal('140.06', 'NL')['nom'].startswith('Sociaal Fonds voor Taxi')


@pytest.mark.parametrize('adr,attendu', [
    ('Quai de Willebroeck 37, 1000 BRUXELLES', ('Quai de Willebroeck', '37', '1000', 'BRUXELLES')),
    ('Rue de Birmingham 225, 1070 Anderlecht', ('Rue de Birmingham', '225', '1070', 'Anderlecht')),
    ('Marlylaan 15 bus 8, 1120 NEDER-OVER-HEEMBEEK',
     ('Marlylaan', '15 bus 8', '1120', 'NEDER-OVER-HEEMBEEK')),
    ('', ('', '', '', '')),
])
def test_decoupe_adresse_plate(adr, attendu):
    assert R._decoupe_adresse_plate(adr) == attendu


def test_services_de_controle_couvrent_les_11_provinces():
    d = R._donnees('institutions_controle')
    provinces = {'Anvers', 'Brabant wallon', 'Brabant flamand', 'Bruxelles',
                 'Flandre occidentale', 'Flandre orientale', 'Hainaut', 'Liège',
                 'Limbourg', 'Luxembourg', 'Namur'}
    for svc in ('controle_lois', 'controle_bienetre'):
        assert set(d[svc]) == provinces, f'{svc} : provinces manquantes'
        for prov, v in d[svc].items():
            for lg in ('fr', 'nl'):
                assert v[lg]['rue'] and v[lg]['cp'] and v[lg]['localite'], f'{svc}/{prov}/{lg}'


def test_adresse_liege_est_celle_apres_demenagement():
    """La page NL du SPF affiche encore l'ancienne adresse (Rue Natalis 49, 4020) avec
    un avis de déménagement au 15/01/2024 ; c'est la FR (Rue de Fragnée, 4000) qui vaut."""
    v = R._donnees('institutions_controle')['controle_lois']['Liège']
    for lg in ('fr', 'nl'):
        assert v[lg]['cp'] == '4000', 'adresse de Liège périmée (page NL du SPF)'
        assert 'Natalis' not in v[lg]['rue']


# ------------------------------------------------------ jetons : FR et NL diffèrent !
def test_les_tables_de_jetons_fr_et_nl_different():
    """Garde-fou : les 2 modèles Word ne numérotent pas les jetons pareil. Une table
    unique écrivait la caisse de vacances dans la case assurance-loi en NL."""
    assert R.INST_TOKENS_FR['caisse']['nom'] == 'Nom_1_institution_Inst_v1'
    assert R.INST_TOKENS_NL['caisse']['nom'] == 'Nom_1_institution_Inst'
    assert R.INST_TOKENS_FR['fonds']['nom'] == 'Nom_1_institution_Inst_v4'
    assert R.INST_TOKENS_NL['fonds']['nom'] == 'Nom_1_institution_Inst_v2'
    assert R.INST_TOKENS_FR['controle_lois']['rue'] == 'Rue_institution_Inst_v2'
    assert R.INST_TOKENS_NL['controle_lois']['rue'] == 'Rue_institution_Inst_v5'
    # aucune institution ne doit partager un jeton de nom avec une autre, par langue
    for tbl, nom in ((R.INST_TOKENS_FR, 'FR'), (R.INST_TOKENS_NL, 'NL')):
        noms = [v['nom'] for v in tbl.values() if v.get('nom')]
        assert len(noms) == len(set(noms)), f'{nom} : deux institutions, même jeton de nom'


def test_sans_siege_exploitation():
    assert R._sans_siege_exploitation(['124'])
    assert R._sans_siege_exploitation(['124.01'])
    assert R._sans_siege_exploitation(['140.03'])
    assert R._sans_siege_exploitation(['121', '124'])      # une seule suffit
    assert not R._sans_siege_exploitation(['112', '121'])
    assert not R._sans_siege_exploitation([])


# --------------------------------------------------------------- document FR / NL
@pytest.mark.parametrize('lang,attendus', [
    ('FR', ['Commission paritaire des entreprises de garage',
            'Commission paritaire pour le nettoyage']),
    ('NL', ['Paritair Comité voor het garagebedrijf',
            'Paritair Comité voor de schoonmaak']),
])
def test_point9_denomination_officielle_dans_le_document(lang, attendus):
    t = gen(lang, ['112', '121'])
    for a in attendus:
        assert a in t, f'{lang} : « {a} » absent du point 9'


def test_point9_nutilise_pas_le_libelle_libre():
    """« Libellé » de l'écran (« Car-wash ») est un surnom interne : il ne doit PAS
    servir de dénomination légale."""
    t = _texte(R.build_reglement(
        {'reglement_langue': 'FR', 'num_entreprise': '0754615359',
         'regimes': [{'cp': '112', 'label': 'Car-wash'}]}, IDENT, _tpl('FR')))
    m = re.search(r'Commission paritaire pour ouvrier n°\s*112\s*Dénomination\s*:\s*(.{0,46})', t)
    assert m and m.group(1).startswith('Commission paritaire des entreprises de garage')
    assert 'Dénomination : Car-wash' not in t


@pytest.mark.parametrize('lang,ancre,fonds,ville', [
    ('FR', 'Fonds de sécurité d’existence ou Fonds socialDénomination :',
     'Fonds social des entreprises de garage', 'NEDER-OVER-HEEMBEEK'),
    ('NL', 'Fondsen voor bestaanszekerheid of Sociaal FondsBenaming :',
     'Sociaal fonds voor het garagebedrijf', 'NEDER-OVER-HEEMBEEK'),
])
def test_point4_fonds_nom_et_adresse(lang, ancre, fonds, ville):
    """On ancre sur le libellé du point 4 : vérifier que le nom du fonds est présent
    QUELQUE PART ne prouve rien — avec les jetons de l'autre langue il l'est aussi,
    mais dans la case du bureau des contributions."""
    t = gen(lang, ['112'])
    i = t.find(ancre)
    assert i >= 0, f'{lang} : libellé du point 4 introuvable'
    suite = t[i + len(ancre): i + len(ancre) + 130]
    assert suite.lstrip().startswith(fonds), f'{lang} : point 4 = {suite[:70]!r}'
    assert ville in suite, f'{lang} : adresse du fonds absente du point 4'


@pytest.mark.parametrize('lang', ['FR', 'NL'])
def test_article66_selon_la_province(lang):
    """Client à Kapelle-op-den-Bos (1880) -> Brabant flamand : lois sociales à Hasselt,
    bien-être à Louvain."""
    t = gen(lang, ['112'])
    ancre_lois = 'Contrôle des lois sociales :' if lang == 'FR' else 'Inspectie van de sociale wetten :'
    ancre_be = 'Contrôle du bien être au travail :' if lang == 'FR' else 'Medische inspectie :'
    m = re.search(re.escape(ancre_lois) + r'\s*(.{0,44})', t)
    assert m and 'Voorstraat 43 bus 03 02 3500 Hasselt' in m.group(1), f'{lang} lois : {m and m.group(1)}'
    m = re.search(re.escape(ancre_be) + r'\s*(.{0,44})', t)
    assert m and 'Philipssite 3A - bus 8 3001 Leuven' in m.group(1), f'{lang} bien-être : {m and m.group(1)}'


def test_article66_change_avec_la_province():
    ident = dict(IDENT, adresse_siege_social_2='4000 Liège')
    t = _texte(R.build_reglement(
        {'reglement_langue': 'FR', 'num_entreprise': '0754615359',
         'regimes': [{'cp': '112'}]}, ident, _tpl('FR')))
    assert 'Rue de Fragnée' in t and 'Hasselt' not in t


@pytest.mark.parametrize('lang,attendu,interdit', [
    ('FR', '(annexe n° 11)', '(annexe n° 10)'),
    ('NL', '(zie bijlage nr. 11)', '(zie bijlage nr. 10)'),
])
def test_article4_renvoie_a_lannexe_11(lang, attendu, interdit):
    """L'annexe 11 est l'accusé de réception ; l'annexe 10 est la politique de
    maintien du contact. Le titre et la table des matières de l'annexe 10 (sans
    parenthèses) ne doivent PAS être touchés."""
    t = gen(lang, ['112'])
    assert attendu in t
    assert interdit not in t
    titre = 'Annexe n°10' if lang == 'FR' else 'Bijlage nr.10'
    assert titre in t, 'le titre de l’annexe 10 a été modifié par erreur'


@pytest.mark.parametrize('lang', ['FR', 'NL'])
@pytest.mark.parametrize('cps,attendu', [
    (['112'], True), (['124'], False), (['140.03'], False), (['124', '121'], False),
])
def test_siege_exploitation_sauf_construction_et_transport(lang, cps, attendu):
    t = gen(lang, cps)
    assert ('Rue du Dépôt' in t) is attendu


def test_numero_de_cp_avec_sous_numero_sinscrit_entier():
    """« 140.03 » s'imprimait « 14003 » (les non-chiffres étaient supprimés)."""
    t = gen('FR', ['140.03'])
    # (?!\d) et pas \b : le document colle « 140.03Dénomination », sans espace.
    assert re.search(r'ouvrier n°\s*140\.03(?!\d)', t)
    assert '14003' not in t


@pytest.mark.parametrize('lang,ancre_avant,ancre_apres', [
    ('FR', 'Caisse de vacances annuellesDénomination :', 'Assurance-loi'),
    ('NL', 'Kas voor jaarlijkse vakantieBenaming :', 'Verzekeringsmaatschappij'),
])
def test_chaque_institution_dans_sa_case(lang, ancre_avant, ancre_apres):
    """Le nom saisi pour la caisse de vacances doit suivre le libellé « caisse de
    vacances » — en NL il atterrissait dans la case assurance-loi."""
    t = gen(lang, ['112'], assurance_loi='AXA', caisse_vacances='ACERTA', seppt='Mensura')
    # le document ne met pas d'espace après la valeur (« ACERTAAdres ») -> on ancre
    # sur le libellé suivant plutôt que sur une frontière de mot.
    m = re.search(re.escape(ancre_avant) + r'\s*(.{0,10}?)\s*(?:Adresse|Adres)\s*:', t)
    assert m and m.group(1) == 'ACERTA', f'{lang} : caisse = {m and m.group(1)!r}'
    i = t.index(ancre_apres)
    suite = t[i:i + 140]
    assert 'AXA' in suite, f'{lang} : assurance-loi mal placée -> {suite[:90]!r}'
    assert 'ACERTA' not in suite, f'{lang} : la caisse s’imprime dans la case assurance-loi'


def test_fr_bureau_des_contributions_nest_pas_le_seppt():
    """Le modèle FR réutilise {{Nom_1_institution_Inst}} au point 6 (SEPPT) ET au
    point 8 : sans remplacement positionnel, « Mensura » s'imprimait comme bureau
    des contributions directes."""
    t = gen('FR', ['112'], seppt='Mensura')
    m = re.search(r'Bureau des contributions directesDénomination\s*:\s*(.{0,14})', t)
    assert m and 'Mensura' not in m.group(1), f'point 8 = {m and m.group(1)!r}'
    assert re.search(r'Protection au travailDénomination\s*:\s*Mensura', t), 'SEPPT perdu au point 6'
