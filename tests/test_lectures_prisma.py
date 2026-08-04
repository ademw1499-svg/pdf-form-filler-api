# -*- coding: utf-8 -*-
"""Lectures Prisma (consultation LECTURE SEULE du serveur .101).

Le portail demande la lecture d'une fiche (POST /lectures/demande), le lecteur
sur le serveur la prend (GET /lectures/a-faire, prise atomique pending->running),
renvoie le dump (POST /lectures/resultat), et le portail récupère des champs
prêts à préremplir un règlement de travail (GET /lectures/etat).

Ce qu'on verrouille ici :
- auth : demande/etat = utilisateur portail connecté ; a-faire/resultat = jeton machine ;
- le backend n'enfile QUE des 'lecture_fiche' (jamais un deploy/cli par ce chemin) ;
- numero et id strictement numériques (interpolés dans l'URL PostgREST) ;
- le mapping dump -> champs règlement (CP, langue, heures/sem, adresse, SEPPT,
  assurance-loi) ne renvoie QUE ce qui a été trouvé.

Supabase est simulé (monkeypatch de requests.*) : on teste NOTRE logique.
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import app  # noqa: E402

JETON = 'jeton-lecteur-de-test-suffisamment-long'


class FauxSupabase:
    def __init__(self):
        self.appels = []
        self.get_corps = []          # réponses successives pour get()

    def _rep(self, corps, status=200):
        class R:
            status_code = status
            text = '' if status < 300 else 'erreur supabase'
            def json(self):
                return corps
        return R()

    def get(self, url, **kw):
        self.appels.append(('GET', url, kw))
        corps = self.get_corps.pop(0) if self.get_corps else []
        return self._rep(corps)

    def patch(self, url, **kw):
        self.appels.append(('PATCH', url, kw))
        return self._rep([{'id': 7, 'commande': 'lecture_fiche',
                           'args': {'numero': '2948'}, 'statut': 'running'}])

    def post(self, url, **kw):
        self.appels.append(('POST', url, kw))
        return self._rep([{'id': 7}])


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv('PRESTATIONS_TOKEN', JETON)
    monkeypatch.setattr(app, 'SUPABASE_URL', 'https://fake.supabase.co')
    monkeypatch.setattr(app, 'SUPABASE_KEY', 'sk-fake')
    faux = FauxSupabase()
    monkeypatch.setattr(app.requests, 'get', faux.get)
    monkeypatch.setattr(app.requests, 'patch', faux.patch)
    monkeypatch.setattr(app.requests, 'post', faux.post)
    # utilisateur portail « connecté » par défaut ; les tests 401 le débranchent
    monkeypatch.setattr(app, 'verify_user_token', lambda req: 'gest@test.be')
    c = app.app.test_client()
    c.faux = faux
    return c


H = {'X-Prestations-Token': JETON}


# ---------- refus ----------

def test_demande_sans_login_401(client, monkeypatch):
    monkeypatch.setattr(app, 'verify_user_token', lambda req: None)
    assert client.post('/lectures/demande', json={'numero': '2948'}).status_code == 401

def test_etat_sans_login_401(client, monkeypatch):
    monkeypatch.setattr(app, 'verify_user_token', lambda req: None)
    assert client.get('/lectures/etat?id=7').status_code == 401

def test_a_faire_sans_jeton_401(client):
    assert client.get('/lectures/a-faire').status_code == 401

def test_resultat_sans_jeton_401(client):
    assert client.post('/lectures/resultat', json={'id': 7, 'ok': True}).status_code == 401

def test_demande_numero_invalide_400(client):
    # lettres, injection PostgREST, vide : tout est refusé avant d'atteindre Supabase
    for mauvais in ('abc', '1&statut=eq.pending', '', '12345678'):
        r = client.post('/lectures/demande', json={'numero': mauvais})
        assert r.status_code == 400, mauvais
    assert not any(m == 'POST' for m, _, _ in client.faux.appels)

def test_resultat_id_invalide_400(client):
    r = client.post('/lectures/resultat', headers=H,
                    json={'id': '7&statut=eq.pending', 'ok': True, 'dump': {}})
    assert r.status_code == 400


# ---------- flux nominal ----------

def test_demande_enfile_une_lecture_fiche(client):
    r = client.post('/lectures/demande', json={'numero': '2948'})
    assert r.status_code == 201
    assert r.get_json()['id'] == 7
    methode, url, kw = client.faux.appels[-1]
    assert methode == 'POST' and '/rest/v1/commandes' in url
    corps = kw['json']
    assert corps['commande'] == 'lecture_fiche'          # JAMAIS autre chose
    assert corps['args'] == {'numero': '2948'}
    assert corps['statut'] == 'pending'

def test_a_faire_prend_atomiquement(client):
    r = client.get('/lectures/a-faire', headers=H)
    assert r.status_code == 200
    rows = r.get_json()
    assert rows and rows[0]['args']['numero'] == '2948'
    methode, url, kw = client.faux.appels[-1]
    # la « prise » est un PATCH filtré pending->running (atomique côté PostgREST)
    assert methode == 'PATCH'
    assert 'commande=eq.lecture_fiche' in url and 'statut=eq.pending' in url
    assert kw['json'] == {'statut': 'running'}

def test_resultat_ok_ecrit_done(client):
    r = client.post('/lectures/resultat', headers=H,
                    json={'id': 7, 'ok': True, 'dump': {'general': {'Nom': 'ACME'}}})
    assert r.status_code == 200
    methode, url, kw = client.faux.appels[-1]
    assert methode == 'PATCH' and 'id=eq.7' in url
    assert kw['json']['statut'] == 'done'
    assert 'ACME' in kw['json']['resultat']

def test_resultat_erreur_ecrit_erreur(client):
    client.post('/lectures/resultat', headers=H,
                json={'id': 7, 'ok': False, 'erreur': 'fiche verrouillée'})
    _, _, kw = client.faux.appels[-1]
    assert kw['json']['statut'] == 'erreur'
    assert 'fiche verrouill' in kw['json']['resultat']

def test_etat_en_cours_puis_done(client):
    client.faux.get_corps = [[{'id': 7, 'statut': 'running', 'resultat': None}]]
    r = client.get('/lectures/etat?id=7')
    assert r.get_json() == {'statut': 'running'}

    dump = {'general': {'Nom': 'ACME', 'Comm. paritaire': '200 (Français)'},
            'institutions': []}
    client.faux.get_corps = [[{'id': 7, 'statut': 'done',
                               'resultat': json.dumps(dump)}]]
    r = client.get('/lectures/etat?id=7')
    d = r.get_json()
    assert d['statut'] == 'done'
    assert d['champs']['commission_paritaire'] == '200'
    assert d['champs']['reglement_langue'] == 'FR'

def test_etat_erreur_remonte_au_portail(client):
    client.faux.get_corps = [[{'id': 7, 'statut': 'erreur',
                               'resultat': json.dumps({'erreur': 'Prisma fermé'})}]]
    d = client.get('/lectures/etat?id=7').get_json()
    assert d['statut'] == 'erreur' and 'Prisma' in d['erreur']

def test_etat_introuvable_404(client):
    client.faux.get_corps = [[]]
    assert client.get('/lectures/etat?id=99').status_code == 404


# ---------- cache 24 h ----------

def _ts_il_y_a(heures):
    from datetime import datetime, timedelta, timezone
    return (datetime.now(timezone.utc) - timedelta(hours=heures)).isoformat()

def test_demande_cache_fiche_lue_recemment(client):
    # une lecture done de la même fiche il y a 2 h -> résultat instantané,
    # AUCUNE nouvelle ligne enfilée (Prisma pas re-sollicité)
    client.faux.get_corps = [[{'id': 42, 'traite_at': _ts_il_y_a(2)}]]
    r = client.post('/lectures/demande', json={'numero': '2948'})
    assert r.status_code == 200
    assert r.get_json() == {'id': 42, 'cache': True}
    assert not any(m == 'POST' for m, _, _ in client.faux.appels)

def test_demande_cache_perime_relit(client):
    client.faux.get_corps = [[{'id': 42, 'traite_at': _ts_il_y_a(30)}]]
    r = client.post('/lectures/demande', json={'numero': '2948'})
    assert r.status_code == 201                    # > 24 h -> vraie lecture
    assert client.faux.appels[-1][0] == 'POST'

def test_demande_forcer_ignore_le_cache(client):
    client.faux.get_corps = [[{'id': 42, 'traite_at': _ts_il_y_a(1)}]]
    r = client.post('/lectures/demande', json={'numero': '2948', 'forcer': True})
    assert r.status_code == 201
    # forcer -> pas même de requête cache : le seul appel est le POST
    assert [m for m, _, _ in client.faux.appels] == ['POST']


# ---------- mapping dump -> champs règlement ----------

DUMP_COMPLET = {
    'general': {
        'Nom': 'THE HEALDER', 'Adresse (rue)': 'Avenue Louise', 'No.': '523',
        'Code postal': '1050', 'Localite': 'Bruxelles',
        'Comm. paritaire': '329.02 (Français)', 'Hrs/sem.': '38,00',
        'No. entreprise': '1022.992.781', 'N ONSS': '1482420-92',
        'Langue off.': 'Français',
    },
    'institutions': [
        {'type': 'ONSS', 'nom1': 'OFF. NAT. SECURITE SOCIALE', 'nom2': ''},
        {'type': 'Service médical', 'nom1': 'MENSURA', 'nom2': 'SEPPT'},
        {'type': 'Accident travail', 'nom1': 'AXA', 'nom2': 'Assurances'},
    ],
}

def test_mapping_complet():
    champs, institutions = app._dump_vers_reglement(DUMP_COMPLET)
    assert champs['nom_societe'] == 'THE HEALDER'
    assert champs['adresse_siege_social'] == 'Avenue Louise 523'
    assert champs['adresse_siege_social_2'] == '1050 Bruxelles'
    assert champs['commission_paritaire'] == '329.02'
    assert champs['reglement_langue'] == 'FR'
    assert champs['regime_horaire'] == '38'
    assert champs['num_entreprise'] == '1022992781'     # normalisé (le portail chaîne la BCE)
    assert champs['num_onss'] == '1482420-92'
    assert 'MENSURA' in champs['seppt'].upper()
    assert champs['assurance_loi'].startswith('AXA')
    assert len(institutions) == 3

def test_mapping_langue_off_gagne_sur_le_libelle_cp():
    # fiche NL avec une CP au libellé français : « Langue off. » fait foi
    champs, _ = app._dump_vers_reglement(
        {'general': {'Comm. paritaire': '200 (Français)', 'Langue off.': 'Nederlands'},
         'institutions': []})
    assert champs['reglement_langue'] == 'NL'

def test_mapping_num_entreprise_invalide_ignore():
    champs, _ = app._dump_vers_reglement(
        {'general': {'No. entreprise': '123'}, 'institutions': []})
    assert 'num_entreprise' not in champs

def test_institutions_ciblees_par_categorie():
    # même si le nom n'est pas dans la liste connue, la CATÉGORIE suffit
    champs, _ = app._dump_vers_reglement({'general': {}, 'institutions': [
        {'type': 'Service médical', 'nom1': 'SEPPT REGIONAL XYZ'},
        {'type': 'Accident travail', 'nom1': 'ASSUREUR LOCAL SA'},
    ]})
    assert champs['seppt'] == 'Seppt Regional Xyz'   # nom tout-en-majuscules -> Title
    assert champs['assurance_loi'] == 'ASSUREUR LOCAL SA'

def test_vieux_dump_sans_type_repli_sur_le_nom():
    champs, _ = app._dump_vers_reglement({'general': {}, 'institutions': [
        {'nom1': 'MENSURA', 'nom2': 'prévention'},
        {'nom1': 'AXA', 'nom2': 'accidents'},
    ]})
    assert 'MENSURA' in champs['seppt'].upper()
    assert champs['assurance_loi'].startswith('AXA')

def test_mapping_heures_a_la_demi():
    champs, _ = app._dump_vers_reglement(
        {'general': {'Hrs/sem.': '36,50'}, 'institutions': []})
    assert champs['regime_horaire'] == '36h30'

def test_mapping_langue_nl():
    champs, _ = app._dump_vers_reglement(
        {'general': {'Comm. paritaire': '302 (Nederlands)'}, 'institutions': []})
    assert champs['reglement_langue'] == 'NL'

def test_mapping_vide_ne_renvoie_rien():
    champs, institutions = app._dump_vers_reglement({})
    assert champs == {} and institutions == []

def test_mapping_langue_mal_encodee():
    # le dump RDP arrive parfois avec l'accent cassé : "329.02 (Fran�ais)"
    champs, _ = app._dump_vers_reglement(
        {'general': {'Comm. paritaire': '329.02 (Fran�ais)'}, 'institutions': []})
    assert champs['reglement_langue'] == 'FR'
    assert champs['commission_paritaire'] == '329.02'
