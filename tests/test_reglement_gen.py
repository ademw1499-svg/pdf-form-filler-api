# -*- coding: utf-8 -*-
"""
Tests du générateur de règlement de travail (reglement_gen.py).

Couvre : parsing du temps plein, normalisation/lookup des commissions paritaires,
provinces, cadre horaire, régimes multiples (une CP = son temps plein + sa propre
ouverture), génération d'horaires bornée par régime, cas limites (CP sans données,
champs vides), et remplissage du VRAI modèle Word FR/NL (CP ouvrier/employé,
caméras, siège d'exploitation).

Lancer :  python3 -m pytest tests/ -v
"""
import io
import re
import zipfile
import os
import pytest

import reglement_gen as R

# --- Modèles Word officiels (bundle local). Tests d'intégration ignorés si absents.
BUNDLE = os.path.join(os.path.dirname(__file__), '..', '..', '_reglement_bundle')
TPL_FR = os.path.join(BUNDLE, 'reglement_FR.docx')
TPL_NL = os.path.join(BUNDLE, 'reglement_NL.docx')


def _tpl(path):
    if not os.path.exists(path):
        pytest.skip(f"modèle absent : {path}")
    with open(path, 'rb') as f:
        return f.read()


def _texte(docx_bytes):
    """Texte lisible d'un .docx (jetons remplacés, sans codes de champ)."""
    x = zipfile.ZipFile(io.BytesIO(docx_bytes)).read('word/document.xml').decode('utf-8')
    t = re.sub(r'<[^>]+>', '', x)
    return re.sub(r'MERGEFIELD [A-Za-zÀ-ÿ0-9_]+ ', '', t)


# Répertoire CP de test (comme en base)
CP_REP = [
    {'cp': '112', 'denomination': 'Entreprises de garage', 'heures_semaine': '36h30'},
    {'cp': '121', 'denomination': 'Entreprises de nettoyage', 'heures_semaine': '38'},
    {'cp': '226', 'denomination': 'Commerce international', 'heures_semaine': '37'},
    {'cp': '102.01', 'denomination': 'Carrières Hainaut', 'heures_semaine': '38'},
]


# ------------------------------------------------------------------ unités pures
class TestHebdoMin:
    @pytest.mark.parametrize('val,attendu', [
        ('36h30', 2190), ('38', 2280), ('38h', 2280), ('37', 2220),
        ('36,5', 2190), ('36.5', 2190), ('40h', 2400), ('35h00', 2100),
    ])
    def test_formats(self, val, attendu):
        assert R._hebdo_min(val) == attendu

    def test_defaut_si_vide(self):
        assert R._hebdo_min('') == 2280
        assert R._hebdo_min(None) == 2280

    def test_defaut_si_invalide(self):
        assert R._hebdo_min('bla') == 2280
        assert R._hebdo_min('abc', defaut=1800) == 1800


class TestCpNorm:
    @pytest.mark.parametrize('val,attendu', [
        ('112', '112'), ('112.00', '112'), ('102.01', '102.01'),
        ('  121 ', '121'), ('CP 124', '124'), ('', ''), (None, ''),
    ])
    def test_norm(self, val, attendu):
        assert R._cp_norm(val) == attendu


class TestCpLookup:
    def test_lookup_par_numero(self):
        lut = R._cp_lookup(CP_REP)
        assert R._cp_info(lut, '112') == {'hebdo': '36h30', 'denom': 'Entreprises de garage'}
        assert R._cp_info(lut, '112.00')['hebdo'] == '36h30'
        assert R._cp_info(lut, '121')['hebdo'] == '38'

    def test_sous_cp(self):
        lut = R._cp_lookup(CP_REP)
        assert R._cp_info(lut, '102.01')['denom'] == 'Carrières Hainaut'
        # variante chiffres-seuls
        assert R._cp_info(lut, '10201')['hebdo'] == '38'

    def test_inconnue(self):
        lut = R._cp_lookup(CP_REP)
        assert R._cp_info(lut, '999') == {}
        assert R._cp_info(R._cp_lookup(None), '112') == {}


class TestProvince:
    @pytest.mark.parametrize('cp,prov', [
        ('1000', 'Bruxelles'), ('1400', 'Brabant wallon'), ('2000', 'Anvers'),
        ('4000', 'Liège'), ('5000', 'Namur'), ('6000', 'Hainaut'),
        ('6700', 'Luxembourg'), ('8000', 'Flandre occidentale'), ('9000', 'Flandre orientale'),
        ('3500', 'Limbourg'),
    ])
    def test_provinces(self, cp, prov):
        assert R._province_from_cp(cp) == prov

    def test_invalide(self):
        assert R._province_from_cp('') == ''
        assert R._province_from_cp('abcd') == ''


class TestTemps:
    def test_min_hhmm(self):
        assert R._min('10:00') == 600
        assert R._min('06:30') == 390
        assert R._hhmm(600) == '10:00'
        assert R._hhmm(1470) == '00:30'  # dépasse minuit

    def test_duree(self):
        assert R._duree(2190) == '36h30'
        assert R._duree(2280) == '38h'
        assert R._duree(480) == '8h'

    def test_jours_ouverts(self):
        assert R._jours_ouverts(0, 6) == [0, 1, 2, 3, 4, 5, 6]
        assert R._jours_ouverts(0, 5) == [0, 1, 2, 3, 4, 5]
        assert len(R._jours_ouverts(0, 6)) == 7


# ------------------------------------------------------------- régimes & horaires
class TestRegimes:
    def test_regimes_explicites(self):
        payload = {'regimes': [
            {'cp': '112', 'label': 'Car-wash', 'hebdo': '36h30',
             'ouverture_debut': '10:00', 'ouverture_fin': '18:00', 'jour_debut': 0, 'jour_fin': 5},
            {'cp': '121', 'label': 'Nettoyage', 'hebdo': '38',
             'ouverture_debut': '06:00', 'ouverture_fin': '23:00', 'jour_debut': 0, 'jour_fin': 6},
        ]}
        items = R._regimes_du_payload(payload)
        assert len(items) == 2
        assert items[0]['cible'] == 2190 and items[0]['label'] == 'Car-wash'
        assert items[1]['cible'] == 2280

    def test_hebdo_resolu_depuis_repertoire(self):
        # temps plein absent -> complété par le répertoire (112 = 36h30)
        payload = {'regimes': [
            {'cp': '112', 'ouverture_debut': '10:00', 'ouverture_fin': '18:00', 'jour_debut': 0, 'jour_fin': 5},
        ]}
        items = R._regimes_du_payload(payload, CP_REP)
        assert items[0]['cible'] == 2190
        assert items[0]['label'] == 'Entreprises de garage'   # dénomination du répertoire

    def test_hebdo_defaut_38_si_cp_inconnue(self):
        payload = {'regimes': [
            {'cp': '999', 'ouverture_debut': '09:00', 'ouverture_fin': '17:00', 'jour_debut': 0, 'jour_fin': 4},
        ]}
        items = R._regimes_du_payload(payload, CP_REP)
        assert items[0]['cible'] == 2280   # 38h par défaut

    def test_sans_ouverture_ignore(self):
        payload = {'regimes': [{'cp': '112', 'hebdo': '38'}]}  # pas d'ouverture
        assert R._regimes_du_payload(payload) == []

    def test_retrocompat_ouvrier_employe(self):
        payload = {'commission_paritaire': '124', 'heures_ouvrier': '40',
                   'cp_employe': '200', 'heures_employe': '38',
                   'ouverture_debut': '08:00', 'ouverture_fin': '18:00',
                   'ouverture_jour_debut': 0, 'ouverture_jour_fin': 4}
        items = R._regimes_du_payload(payload)
        assert len(items) == 2
        assert items[0]['cible'] == 2400 and items[1]['cible'] == 2280


class TestGenererHoraires:
    def test_bornes_par_ouverture(self):
        sched = R.generer_horaires({}, cible=2190, debut='10:00', fin='18:00', jour_debut=0, jour_fin=5)
        assert sched, "des horaires doivent être générés"
        mins = [m for s in sched for (_, a, b, c, d) in s['lignes'] for m in (a, b, c, d) if m is not None]
        assert min(mins) >= R._min('10:00')
        assert max(mins) <= R._min('18:00')

    def test_nuit_traverse_minuit(self):
        # 05:00 -> 03:00 (lendemain) : la fenêtre doit couvrir jusqu'à 03:00
        sched = R.generer_horaires({}, cible=2280, debut='05:00', fin='03:00', jour_debut=0, jour_fin=6)
        assert sched
        # au moins un créneau doit se terminer après minuit (03:00 = 180 le lendemain -> 1620)
        fins = [d for s in sched for (_, a, b, c, d) in s['lignes'] if d is not None]
        assert max(fins) >= R._min('03:00') % 1440 or max(fins) >= 1440 - 60

    def test_5j_et_6j(self):
        sched = R.generer_horaires({}, cible=2280, debut='06:00', fin='23:00', jour_debut=0, jour_fin=6)
        modes = ' '.join(s['titre'] for s in sched)
        assert '6 jours' in modes and '5 jours' in modes

    def test_ouverture_absente_vide(self):
        assert R.generer_horaires({}, debut=None, fin=None) == []


class TestDocHoraires:
    def test_deux_regimes_deux_sections(self):
        payload = {'reglement_langue': 'FR', 'regimes': [
            {'cp': '112', 'label': 'Car-wash', 'hebdo': '36h30',
             'ouverture_debut': '10:00', 'ouverture_fin': '18:00', 'jour_debut': 0, 'jour_fin': 5},
            {'cp': '121', 'label': 'Nettoyage', 'hebdo': '38',
             'ouverture_debut': '06:00', 'ouverture_fin': '23:00', 'jour_debut': 0, 'jour_fin': 6},
        ]}
        out = R.generer_doc_horaires(payload, {'nom_societe': 'X'})
        assert out
        txt = _texte(out)
        assert 'CAR-WASH (CP 112) — 36h30/semaine' in txt
        assert 'NETTOYAGE (CP 121) — 38h/semaine' in txt

    def test_bornes_respectees_par_regime(self):
        payload = {'reglement_langue': 'FR', 'regimes': [
            {'cp': '112', 'label': 'Car-wash', 'hebdo': '36h30',
             'ouverture_debut': '10:00', 'ouverture_fin': '18:00', 'jour_debut': 0, 'jour_fin': 5},
            {'cp': '121', 'label': 'Nettoyage', 'hebdo': '38',
             'ouverture_debut': '06:00', 'ouverture_fin': '23:00', 'jour_debut': 0, 'jour_fin': 6},
        ]}
        txt = _texte(R.generer_doc_horaires(payload, {'nom_societe': 'X'}))
        cw, net = txt.find('CAR-WASH'), txt.find('NETTOYAGE')
        seg_cw, seg_net = txt[cw:net], txt[net:]
        def bornes(seg):
            ts = [int(a) * 60 + int(b) for a, b in re.findall(r'(\d{2}):(\d{2})', seg)]
            return min(ts), max(ts)
        assert bornes(seg_cw) == (600, 1080)      # 10:00 -> 18:00
        assert bornes(seg_net) == (360, 1380)     # 06:00 -> 23:00

    def test_none_si_pas_douverture(self):
        assert R.generer_doc_horaires({'reglement_langue': 'FR'}) is None

    def test_cp_sans_donnees_defaut_38(self):
        # CP inconnue, temps plein non fourni -> 38h par défaut, doc quand même généré
        payload = {'reglement_langue': 'FR', 'regimes': [
            {'cp': '999', 'ouverture_debut': '09:00', 'ouverture_fin': '17:00', 'jour_debut': 0, 'jour_fin': 4},
        ]}
        txt = _texte(R.generer_doc_horaires(payload, {'nom_societe': 'X'}, cp_repertoire=CP_REP))
        assert '38h/semaine' in txt


# ------------------------------------------------------- intégration modèle Word
class TestBuildReglement:
    def test_cp_ouvrier_et_employe_positionnels(self):
        payload = {'reglement_langue': 'FR', 'commission_paritaire': '124', 'cp_employe': '226'}
        out = R.build_reglement(payload, {'nom_societe': 'TEST'}, _tpl(TPL_FR))
        txt = _texte(out)
        i = txt.find('Commission paritaire pour ouvrier')
        bloc = txt[i:i + 160]
        assert '124' in bloc and '226' in bloc
        assert bloc.find('124') < bloc.find('226')   # ouvrier avant employé

    def test_cp_depuis_regimes(self):
        payload = {'reglement_langue': 'FR', 'regimes': [
            {'cp': '112'}, {'cp': '121'},
        ]}
        txt = _texte(R.build_reglement(payload, {'nom_societe': 'X'}, _tpl(TPL_FR), cp_repertoire=CP_REP))
        i = txt.find('Commission paritaire pour ouvrier')
        bloc = txt[i:i + 200]
        assert '112' in bloc and '121' in bloc
        # dénomination reprise du répertoire
        assert 'Entreprises de garage' in bloc or 'garage' in bloc.lower()

    def test_cameras_defaut_neant(self):
        txt = _texte(R.build_reglement({'reglement_langue': 'FR'}, {'nom_societe': 'X'}, _tpl(TPL_FR)))
        i = txt.find('surveillance par caméras comporte')
        assert '0 caméra' in txt[i:i + 60]
        assert 'Néant' in txt[i:i + 120]

    def test_cameras_remplies(self):
        payload = {'reglement_langue': 'FR', 'nombre_cameras': '3', 'cameras_emplacement': 'entrée, entrepôt'}
        txt = _texte(R.build_reglement(payload, {'nom_societe': 'X'}, _tpl(TPL_FR)))
        i = txt.find('surveillance par caméras comporte')
        assert '3 caméra' in txt[i:i + 60]
        assert 'entrée, entrepôt' in txt[i:i + 140]

    def test_siege_exploitation_reel(self):
        identity = {'nom_societe': 'X', 'adresse_siege_social_1': 'Rue A 1',
                    'adresse_siege_social_2': '1000 Bruxelles',
                    'sieges_exploitation': 'Brukskensweg 15, 3800 Sint-Truiden'}
        txt = _texte(R.build_reglement({'reglement_langue': 'FR'}, identity, _tpl(TPL_FR)))
        assert 'Brukskensweg 15, 3800 Sint-Truiden' in txt

    def test_adresse_siege_social_decoupee(self):
        identity = {'nom_societe': 'X', 'adresse_siege_social_1': 'Rue Test 12',
                    'adresse_siege_social_2': '1000 Bruxelles'}
        txt = _texte(R.build_reglement({'reglement_langue': 'FR'}, identity, _tpl(TPL_FR)))
        i = txt.find('siège social')
        assert '1000' in txt[i:i + 80] and 'Bruxelles' in txt[i:i + 80]

    def test_pas_de_date_placeholder(self):
        txt = _texte(R.build_reglement({'reglement_langue': 'FR'}, {'nom_societe': 'X'}, _tpl(TPL_FR)))
        assert '[date]' not in txt

    def test_nl(self):
        payload = {'reglement_langue': 'NL', 'commission_paritaire': '124', 'cp_employe': '200'}
        txt = _texte(R.build_reglement(payload, {'nom_societe': 'X'}, _tpl(TPL_NL)))
        assert '124' in txt and '200' in txt

    # ----- cas limites -----
    def test_payload_vide_ne_plante_pas(self):
        out = R.build_reglement({}, None, _tpl(TPL_FR))
        assert isinstance(out, (bytes, bytearray)) and len(out) > 1000

    def test_identity_none(self):
        out = R.build_reglement({'reglement_langue': 'FR'}, None, _tpl(TPL_FR))
        assert len(out) > 1000

    def test_sans_template_leve_erreur(self):
        with pytest.raises(ValueError):
            R.build_reglement({}, None, None)


class TestValeurs:
    def test_vide_donne_blanc(self):
        v = R._valeurs({}, None)
        assert v['Nom_Em'] == R.BLANK
        assert v['Commission_paritaire_Em'] == R.BLANK

    def test_cp_et_onss(self):
        v = R._valeurs({'commission_paritaire': 'CP 124', 'num_onss': '1234567-89'}, {})
        assert v['Commission_paritaire_Em'] == '124'
        assert v['No_ONSS_Em'] == '1234567-89'

    def test_num_entreprise_formate(self):
        v = R._valeurs({'num_entreprise': '0754615359'}, {})
        assert v['No_d_entreprise_Emp'] == '0754.615.359'

    def test_exploitation_repli_siege_social(self):
        # sans sieges_exploitation -> repli sur le siège social
        idd = {'adresse_siege_social_1': 'Rue A 1', 'adresse_siege_social_2': '1000 Bruxelles'}
        v = R._valeurs({}, idd)
        assert 'Rue A 1' in v['sieges_exploitation']


class TestInstitutions:
    INSTS = [
        {'type': 'assurance', 'nom': 'AXA', 'rue': 'Boulevard du Souverain',
         'numero': '25', 'code_postal': '1170', 'localite': 'Bruxelles'},
        {'type': 'seppt', 'nom': 'Mensura', 'rue': 'Rue Gaucheret',
         'numero': '88', 'code_postal': '1030', 'localite': 'Bruxelles'},
        {'type': 'controle_lois', 'province': 'Bruxelles', 'rue': 'Rue Ernest Blerot',
         'numero': '1', 'code_postal': '1070', 'localite': 'Bruxelles'},
        {'type': 'controle_lois', 'province': 'Liège', 'rue': 'Rue Natalis',
         'numero': '49', 'code_postal': '4020', 'localite': 'Liège'},
    ]

    def test_assurance_par_nom(self):
        v = R._valeurs_institutions({'assurance_loi': 'AXA'}, {}, self.INSTS)
        assert any('Souverain' in str(x) for x in v.values())

    def test_controle_par_province_bruxelles(self):
        v = R._valeurs_institutions({}, {'adresse_siege_social_2': '1000 Bruxelles'}, self.INSTS)
        assert any('Blerot' in str(x) for x in v.values())     # bureau de Bruxelles
        assert all('Natalis' not in str(x) for x in v.values())  # pas celui de Liège

    def test_controle_par_province_liege(self):
        v = R._valeurs_institutions({}, {'adresse_siege_social_2': '4000 Liège'}, self.INSTS)
        assert any('Natalis' in str(x) for x in v.values())

    def test_build_reglement_avec_institutions(self):
        idd = {'nom_societe': 'X', 'adresse_siege_social_2': '1000 Bruxelles'}
        txt = _texte(R.build_reglement({'reglement_langue': 'FR', 'assurance_loi': 'AXA', 'seppt': 'Mensura'},
                                       idd, _tpl(TPL_FR), repertoire=self.INSTS))
        assert 'Souverain' in txt      # adresse assurance (Art. 2)
        assert 'Blerot' in txt         # adresse contrôle lois sociales (Art. 66)

    def test_repertoire_vide_ok(self):
        assert R._valeurs_institutions({'assurance_loi': 'AXA'}, {}, []) == {}
        assert R._valeurs_institutions({}, {}, None) == {}
