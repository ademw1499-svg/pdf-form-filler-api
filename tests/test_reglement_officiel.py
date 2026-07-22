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


# Les CP où la page du SPF liste le fonds de pension AVANT le fonds social. Se fier au
# rang (« le 1er fonds adressable ») imprimait donc le fonds de pension au point 4.
# Ne PAS réduire cette liste à un seul cas : la CP 112, seule testée au départ, est
# ordonnée favorablement par hasard — d'où une suite verte sur un code faux.
@pytest.mark.parametrize('cp,lang,attendu', [
    ('220', 'FR', "Fonds social et de garantie des employés de l'industrie alimentaire"),
    ('327.01', 'FR', "Fonds de sécurité d'existence des ateliers sociaux"),
    ('329.01', 'FR', 'Fonds social pour le secteur socio-culturel de la Communauté flamande'),
    ('118', 'NL', 'Waarborg- en Sociaal Fonds voor de voedingsnijverheid'),
    ('220', 'NL', 'Waarborg- en Sociaal Fonds voor de bedienden uit de voedingsnijverheid'),
    ('329.01', 'NL', 'Sociaal Fonds voor het Sociaal-Cultureel Werk van de Vlaamse Gemeenschap'),
])
def test_fonds_pension_liste_en_premier_est_ecarte(cp, lang, attendu):
    f = R._fonds_principal(cp, lang)
    assert f, f'{lang} CP {cp} : aucun fonds'
    assert f['nom'].startswith(attendu), f'{lang} CP {cp} -> {f["nom"]!r}'
    assert not R.RE_FONDS_PENSION.search(f['nom'])


@pytest.mark.parametrize('cp', ['102.01', '102.09'])
@pytest.mark.parametrize('lang', ['FR', 'NL'])
def test_cp_sans_fonds_social_reste_blanche(cp, lang):
    """Le SPF ne liste qu'un fonds « 2e pilier » pour ces sous-commissions : mieux vaut
    un blanc à compléter que le fonds de pension au point 4."""
    assert R._fonds_principal(cp, lang) is None


def test_aucune_cp_nimprime_un_fonds_de_pension():
    """Balayage des 128 CP dans les 2 langues : le point 4 ne doit JAMAIS citer un
    fonds de pension complémentaire."""
    fautes = []
    for lang in ('FR', 'NL'):
        for cp in R._donnees('fse_fr' if lang == 'FR' else 'fse_nl'):
            f = R._fonds_principal(cp, lang)
            if f and R.RE_FONDS_PENSION.search(f['nom']):
                fautes.append(f'{lang} {cp} -> {f["nom"]}')
    assert not fautes, fautes


def test_fr_et_nl_citent_le_meme_fonds():
    """Les listes FR et NL du SPF ne sont pas ordonnées pareil : la même CP donnait un
    fonds différent (et une adresse différente) selon la langue du règlement."""
    ecarts = []
    for cp in R._donnees('fse_fr'):
        a, b = R._fonds_principal(cp, 'FR'), R._fonds_principal(cp, 'NL')
        if bool(a) != bool(b):
            ecarts.append(f'{cp} : FR={bool(a)} NL={bool(b)}')
        elif a and b:
            # le nom est traduit, mais le code postal doit désigner le même organisme
            cpa, cpb = re.search(r'\b\d{4}\b', a['adresse']), re.search(r'\b\d{4}\b', b['adresse'])
            if cpa and cpb and cpa.group() != cpb.group():
                ecarts.append(f'{cp} : FR={a["nom"][:40]} ({cpa.group()}) / '
                              f'NL={b["nom"][:40]} ({cpb.group()})')
    assert not ecarts, ecarts


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


def test_article66_fr_et_nl_prennent_bien_LEUR_adresse():
    """Bruxelles est la seule province où les 2 langues donnent des libellés différents
    (« Rue Ernest Blerot » / « Ernest Blerotstraat »). Sans ce cas, le paramétrage
    FR/NL des autres tests ne prouve rien : leurs données FR et NL sont identiques,
    donc la mutation `cle = 'fr'` passait inaperçue."""
    ident = dict(IDENT, adresse_siege_social_2='1070 Bruxelles')
    payload = {'num_entreprise': '0754615359', 'regimes': [{'cp': '112'}]}
    fr = _texte(R.build_reglement(dict(payload, reglement_langue='FR'), ident, _tpl('FR')))
    nl = _texte(R.build_reglement(dict(payload, reglement_langue='NL'), ident, _tpl('NL')))
    m = re.search(r'Contrôle des lois sociales\s*:\s*(.{0,40})', fr)
    assert m and 'Rue Ernest Blerot' in m.group(1), f'FR -> {m and m.group(1)!r}'
    m = re.search(r'Inspectie van de sociale wetten\s*:\s*(.{0,40})', nl)
    assert m and 'Ernest Blerotstraat' in m.group(1), f'NL -> {m and m.group(1)!r}'
    assert 'Ernest Blerotstraat' not in fr, 'le FR a pris l’adresse néerlandaise'
    assert 'Rue Ernest Blerot' not in nl, 'le NL a pris l’adresse française'


def test_le_repertoire_est_prioritaire_sur_les_donnees_officielles():
    """Exigence : « le répertoire Supabase, s'il est rempli, reste PRIORITAIRE »."""
    repertoire = [{'type': 'controle_lois', 'province': 'Brabant flamand',
                   'nom': 'CLS test', 'rue': 'Rue Saisie', 'numero': '99',
                   'code_postal': '9999', 'localite': 'VILLE SAISIE'}]
    t = _texte(R.build_reglement(
        {'reglement_langue': 'FR', 'num_entreprise': '0754615359',
         'regimes': [{'cp': '112'}]}, IDENT, _tpl('FR'), repertoire=repertoire))
    m = re.search(r'Contrôle des lois sociales\s*:\s*(.{0,44})', t)
    assert m and 'Rue Saisie 99 9999 VILLE SAISIE' in m.group(1), f'-> {m and m.group(1)!r}'
    assert 'Voorstraat' not in t, "l'adresse officielle a écrasé la saisie"


def test_repertoire_sans_adresse_ne_produit_pas_un_hybride():
    """Un fonds saisi sans adresse ne doit PAS hériter de l'adresse officielle d'un
    autre organisme : nom de A + adresse de B est pire que l'un ou l'autre."""
    repertoire = [{'type': 'fonds', 'nom': 'Fonds saisi à la main'}]
    t = _texte(R.build_reglement(
        {'reglement_langue': 'FR', 'num_entreprise': '0754615359',
         'regimes': [{'cp': '112'}]}, IDENT, _tpl('FR'), repertoire=repertoire))
    ancre = 'Fonds de sécurité d’existence ou Fonds socialDénomination :'
    i = t.index(ancre)
    bloc = t[i + len(ancre): i + len(ancre) + 120]
    assert bloc.lstrip().startswith('Fonds saisi à la main'), bloc[:60]
    assert 'NEDER-OVER-HEEMBEEK' not in bloc, f'adresse officielle conservée : {bloc[:90]!r}'


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


@pytest.mark.parametrize('lang,nom,rue', [
    ('FR', 'Office National des Vacances Annuelles', 'Rue Montagne aux Herbes Potagères'),
    ('NL', 'Rijksdienst voor Jaarlijkse Vakantie', 'Warmoesberg'),
])
def test_point2_caisse_vacances_auto(lang, nom, rue):
    """Point 2 : ONVA (FR) / RJV (NL) rempli d'office, sans saisie."""
    t = gen(lang, ['124'])
    ancre = ('Caisse de vacances annuellesDénomination :' if lang == 'FR'
             else 'Kas voor jaarlijkse vakantieBenaming :')
    i = t.find(ancre)
    suite = t[i + len(ancre): i + len(ancre) + 120]
    assert nom in suite, f'{lang} : nom de la caisse absent -> {suite[:60]!r}'
    assert rue in suite, f'{lang} : adresse de la caisse absente'


def test_caisse_saisie_reste_prioritaire():
    """Un nom saisi au formulaire l'emporte sur l'ONVA par défaut."""
    t = gen('FR', ['124'], caisse_vacances='Ma Caisse SRL')
    i = t.find('Caisse de vacances annuellesDénomination :')
    suite = t[i:i + 90]
    assert 'Ma Caisse SRL' in suite
    assert 'Office National des Vacances' not in suite


@pytest.mark.parametrize('lang,seppt,rue', [
    ('FR', 'Mensura', 'Avenue du Boulevard'),
    ('NL', 'Mensura', 'Bolwerklaan'),
    ('FR', 'Securex', 'Avenue de Tervueren'),
    ('FR', 'Cesi', 'Avenue Konrad Adenauer'),
])
def test_point6_seppt_adresse_auto(lang, seppt, rue):
    """Point 6 : la gestionnaire tape « Mensura », l'adresse suit — c'était le
    « j'ai mis mensura et y a rien »."""
    t = gen(lang, ['124'], seppt=seppt)
    ancre = ('Protection au travailDénomination :' if lang == 'FR'
             else 'Bescherming op het werkBenaming :')
    i = t.find(ancre)
    suite = t[i + len(ancre): i + len(ancre) + 120]
    assert seppt in suite, f'{lang} : le nom saisi doit rester ({suite[:50]!r})'
    assert rue in suite, f'{lang} {seppt} : adresse absente -> {suite[:70]!r}'


def test_onss_adresse_dans_la_langue():
    """L'ONSS était figé en français : « Place Victor Horta » dans un document NL."""
    fr = gen('FR', ['124'])
    nl = gen('NL', ['124'])
    assert 'Place Victor Horta 11 1060 Bruxelles' in fr
    assert 'Victor Hortaplein 11 1060 Brussel' in nl
    assert 'Place Victor Horta' not in nl, 'adresse française dans le document NL'


def test_cp200_denomination_sans_coquille():
    """La page FR du SPF écrit « employers » (anglais) : corrigé en « employés »."""
    assert R._fse_info('200', 'FR')['denomination'] == \
        'Commission paritaire auxiliaire pour les employés'
    assert 'employers' not in gen('FR', ['200'])


@pytest.mark.parametrize('lang,attendu_nom', [
    ('FR', 'Fonds social de la commission paritaire pour les employés du commerce '
           'international, du transport et de la logistique'),
    ('NL', 'Sociaal Fonds van het Paritair Comité voor de bedienden uit de '
           'internationale handel'),
])
def test_point4_deux_fonds_ouvrier_et_employe(lang, attendu_nom):
    """Société ouvriers + employés (KNS : 140.03 + 226) : le point 4 doit montrer les
    DEUX fonds. Le modèle n'a qu'un emplacement -> le fonds employé est injecté.
    Sans ça il était perdu (constaté sur le vrai document rempli à la main)."""
    t = gen(lang, ['140.03', '226'])
    # le fonds ouvrier (140.03) est dans l'emplacement du point 4
    assert ('Fonds social pour les ouvriers des entreprises des services publics'
            in t if lang == 'FR' else
            'Sociaal Fonds voor werklieden van de ondernemingen' in t)
    # le fonds employé (226) est injecté, avec son adresse
    label = 'pour les employés :' if lang == 'FR' else 'voor de bedienden :'
    i = t.find(label)
    assert i >= 0, f'{lang} : fonds employé non injecté'
    suite = t[i:i + 180]
    assert attendu_nom[:50] in suite, f'{lang} : mauvais fonds employé -> {suite[:90]!r}'
    assert 'ANTWERPEN' in suite or 'Antwerpen' in suite, f'{lang} : adresse du fonds employé absente'


def test_point4_une_seule_cp_pas_de_second_fonds():
    """Une société à une seule CP ne doit pas voir de ligne « fonds employé »."""
    t = gen('FR', ['124'])
    assert 'pour les employés :' not in t


def test_point4_deux_cp_meme_fonds_pas_de_doublon():
    """Deux régimes qui partagent le même fonds (ex. deux sous-CP du même secteur) :
    on n'injecte pas un doublon."""
    t = gen('FR', ['112', '112'])
    assert t.count('Fonds social des entreprises de garage') == 1
    assert 'pour les employés :' not in t


# Une CP représentante de chaque FAMILLE de piège rencontré (le balayage complet des
# 128 CP × 2 langues vit dans tests/sweep_complet.py, à lancer avant toute release) :
#   112 = normale multi-fonds · 329.01 = pension listé en premier (FR) ·
#   118 = pension en premier côté NL seulement · 102.01 = AUCUN fonds social ·
#   140.03 = sous-secteur transport · 102.02 = titre partagé entre 2 CP ·
#   110 = balisée <h3> sur la page SPF · 200 = coquille « employers » corrigée ·
#   124 = construction (sans siège d'exploitation) · 302 = horeca (fonds « 2e pilier » homonyme)
FAMILLES_CP = ['112', '329.01', '118', '102.01', '140.03', '102.02', '110', '200', '124', '302']


@pytest.mark.parametrize('lang', ['FR', 'NL'])
def test_invariants_par_famille_de_cp(lang):
    """Mêmes invariants que le balayage complet, sur un représentant par famille."""
    data = R._donnees('fse_nl' if lang == 'NL' else 'fse_fr')
    for cp in FAMILLES_CP:
        t = gen(lang, [cp])
        assert not re.search(r'\{\{[A-Za-z]', t), f'{lang} {cp} : jeton survivant'
        assert not re.search(r'\bNone\b', t), f'{lang} {cp} : None littéral'
        denom = (data.get(cp) or {}).get('denomination', '')
        assert denom[:60] in t, f'{lang} {cp} : dénomination absente'
        i = t.find('Fonds de sécurité' if lang == 'FR' else 'Fondsen voor bestaanszekerheid')
        zone = t[i:i + 220].split('Adresse')[0].split('Adres')[0]
        assert not R.RE_FONDS_PENSION.search(zone), f'{lang} {cp} : fonds de pension au point 4'
        fonds = R._fonds_principal(cp, lang)
        if fonds:
            assert fonds['nom'][:45] in t, f'{lang} {cp} : fonds attendu absent'
        renvoi = '(annexe n° 11)' if lang == 'FR' else 'bijlage nr. 11'
        assert renvoi in t, f'{lang} {cp} : renvoi annexe 11 absent'


def test_fr_bureau_des_contributions_nest_pas_le_seppt():
    """Le modèle FR réutilise {{Nom_1_institution_Inst}} au point 6 (SEPPT) ET au
    point 8 : sans remplacement positionnel, « Mensura » s'imprimait comme bureau
    des contributions directes."""
    t = gen('FR', ['112'], seppt='Mensura')
    m = re.search(r'Bureau des contributions directesDénomination\s*:\s*(.{0,14})', t)
    assert m and 'Mensura' not in m.group(1), f'point 8 = {m and m.group(1)!r}'
    assert re.search(r'Protection au travailDénomination\s*:\s*Mensura', t), 'SEPPT perdu au point 6'


# --- Institutions du dossier Prisma (colonne employeurs.institutions, robot PC 06) ---
# Échantillon RÉEL lu par le PC 06 dans Prisma le 22/07/2026 (dossier 2905).
INST_PRISMA = [
    {"type": "Caisse congés payés", "uc_id": "ucVakantiekas", "nom1": "RJV",
     "rue": "Warmoesberg", "numero": "48", "code_postal": "1000", "localite": "Bruxelles",
     "num_affiliation": "", "langue": "N"},
    {"type": "Accident travail", "uc_id": "ucArbeidsongevallen", "nom1": "ASSUBEL",
     "rue": "Rue de Laeken", "numero": "35", "code_postal": "1000",
     "localite": "Bruxelles ville", "num_affiliation": "", "langue": "F"},
    {"type": "Service médical", "uc_id": "ucArbeidsgeneeskundige", "nom1": "MSR FAMEDI",
     "rue": "Quai aux Pierres de taille", "numero": "16", "boite": "3",
     "code_postal": "1000", "localite": "Bruxelles ville",
     "num_affiliation": "2905/77", "langue": "F"},
    {"type": "ONEM", "uc_id": "ucRVA", "nom1": "O.N.E.M.", "rue": "Rue Molitor",
     "numero": "8 a", "code_postal": "6700", "localite": "Arlon"},   # pas de case -> ignoré
]


def test_prisma_institutions_remplissent_les_bonnes_cases():
    """Le dossier Prisma du client (robot PC 06) remplit caisse / assurance / SEPPT,
    n° d'affiliation compris — et l'emporte sur le nom saisi au formulaire."""
    t = _texte(R.build_reglement(
        {'reglement_langue': 'FR', 'num_entreprise': '0754615359',
         'seppt': 'Mensura',                       # saisi -> doit perdre contre Prisma
         'institutions_prisma': INST_PRISMA,
         'regimes': [{'cp': '112'}]}, IDENT, _tpl('FR')))
    i = t.index('Caisse de vacances annuelles')
    bloc = t[i:i + 220]
    assert 'RJV' in bloc and 'Warmoesberg 48 1000 Bruxelles' in re.sub(r'\s+', ' ', bloc), bloc[:120]
    i = t.index('Assurance-loi accidents du travail')
    bloc = re.sub(r'\s+', ' ', t[i:i + 220])
    assert 'ASSUBEL' in bloc and 'Rue de Laeken 35 1000' in bloc, bloc[:120]
    i = t.index('Service externe pour la Prévention')
    bloc = re.sub(r'\s+', ' ', t[i:i + 260])
    assert 'MSR FAMEDI' in bloc and 'Quai aux Pierres de taille 16 bte 3' in bloc, bloc[:150]
    assert '2905/77' in bloc, 'le n° d’affiliation SEPPT du client n’est pas repris'
    assert 'Mensura' not in bloc, 'la saisie formulaire a écrasé le dossier Prisma'
    assert 'O.N.E.M' not in t or 'Arlon' not in t[:t.index('Article 3')], \
        'une institution sans case (ONEM) a fui dans le document'


def test_prisma_bloc_entier_sans_hybride():
    """Une institution Prisma sans adresse donne des blancs — jamais le nom Prisma
    collé à l'adresse d'une autre source (règle anti-hybride)."""
    t = _texte(R.build_reglement(
        {'reglement_langue': 'FR', 'num_entreprise': '0754615359',
         'institutions_prisma': [{'uc_id': 'ucArbeidsongevallen', 'nom1': 'ASSUBEL'}],
         'regimes': [{'cp': '112'}]}, IDENT, _tpl('FR')))
    i = t.index('Assurance-loi accidents du travail')
    bloc = re.sub(r'\s+', ' ', t[i:i + 200])
    assert 'ASSUBEL' in bloc
    assert 'Rue de Laeken' not in bloc and 'Warmoesberg' not in bloc, bloc[:140]


def test_prisma_absent_ou_malforme_sans_effet():
    """Pas de colonne, liste vide, ou entrées malformées : le règlement sort comme avant."""
    base = {'reglement_langue': 'FR', 'num_entreprise': '0754615359',
            'seppt': 'Mensura', 'regimes': [{'cp': '112'}]}
    ref = _texte(R.build_reglement(dict(base), IDENT, _tpl('FR')))
    for inst in (None, [], [None, 42, {'uc_id': 'ucInconnu', 'nom1': 'X'}]):
        t = _texte(R.build_reglement(dict(base, institutions_prisma=inst), IDENT, _tpl('FR')))
        assert t == ref, f'institutions_prisma={inst!r} a modifié le document'
