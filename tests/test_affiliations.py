# -*- coding: utf-8 -*-
"""Endpoints /affiliations/* : le veilleur d'encodage passe par le backend
(jeton stable X-Prestations-Token) au lieu de parler à Supabase en direct.

Ce qu'on verrouille ici :
- AUCUN accès sans le bon jeton -> 401 (et un jeton vide ne passe jamais) ;
- avec le bon jeton, /a-traiter renvoie la liste, /maj patche par id,
  /recuperer-orphelines repasse 'processing' -> 'pending' ;
- une colonne optionnelle absente (manquants/institutions) -> on retente sans
  elle au lieu d'échouer.

Supabase est simulé (monkeypatch de requests.*) : on teste NOTRE logique d'auth
et de relais, pas PostgREST.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import app  # noqa: E402

JETON = 'jeton-veilleur-de-test-suffisamment-long'


class FauxSupabase:
    """Capture les requêtes et renvoie des réponses canned paramétrables."""
    def __init__(self):
        self.appels = []
        self.patch_status = [200]   # statuts successifs renvoyés par patch()

    def _rep(self, corps, status=200):
        class R:
            status_code = status
            text = '' if status < 300 else 'column "manquants" does not exist'
            def json(self):
                return corps
        return R()

    def get(self, url, **kw):
        self.appels.append(('GET', url, kw))
        return self._rep([{'id': 1, 'nom_societe': 'ACME', 'statut': 'pending'}])

    def patch(self, url, **kw):
        self.appels.append(('PATCH', url, kw))
        status = self.patch_status.pop(0) if self.patch_status else 200
        return self._rep([{'id': 1, 'nom_societe': 'ACME'}], status)

    def post(self, url, **kw):
        self.appels.append(('POST', url, kw))
        return self._rep([{'id': 1}])


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv('PRESTATIONS_TOKEN', JETON)
    monkeypatch.setattr(app, 'SUPABASE_URL', 'https://fake.supabase.co')
    monkeypatch.setattr(app, 'SUPABASE_KEY', 'sk-fake')
    faux = FauxSupabase()
    monkeypatch.setattr(app.requests, 'get', faux.get)
    monkeypatch.setattr(app.requests, 'patch', faux.patch)
    monkeypatch.setattr(app.requests, 'post', faux.post)
    c = app.app.test_client()
    c.faux = faux
    return c


H = {'X-Prestations-Token': JETON}


# ---------- refus ----------

def test_a_traiter_sans_jeton_401(client):
    assert client.get('/affiliations/a-traiter').status_code == 401

def test_maj_sans_jeton_401(client):
    assert client.post('/affiliations/maj', json={'id': 1}).status_code == 401

def test_orphelines_sans_jeton_401(client):
    assert client.post('/affiliations/recuperer-orphelines', json={}).status_code == 401

def test_mauvais_jeton_401(client):
    r = client.get('/affiliations/a-traiter', headers={'X-Prestations-Token': 'faux'})
    assert r.status_code == 401

def test_jeton_vide_401_meme_si_env_vide(client, monkeypatch):
    monkeypatch.setenv('PRESTATIONS_TOKEN', '')
    r = client.get('/affiliations/a-traiter', headers={'X-Prestations-Token': ''})
    assert r.status_code == 401


# ---------- accès veilleur ----------

def test_a_traiter_renvoie_la_liste(client):
    r = client.get('/affiliations/a-traiter', headers=H)
    assert r.status_code == 200
    rows = r.get_json()
    assert isinstance(rows, list) and rows[0]['nom_societe'] == 'ACME'
    # la requête Supabase ne remonte QUE pending/a_encoder
    _, url, _ = client.faux.appels[-1]
    assert 'statut=in.(pending,a_encoder)' in url

def test_maj_patche_par_id(client):
    r = client.post('/affiliations/maj', headers=H,
                    json={'id': 7, 'statut': 'done', 'numero_employeur': 2950})
    assert r.status_code == 200 and r.get_json()['ok'] is True
    _, url, kw = client.faux.appels[-1]
    assert 'id=eq.7' in url
    assert kw['json']['statut'] == 'done' and kw['json']['numero_employeur'] == 2950

def test_maj_sans_id_400(client):
    assert client.post('/affiliations/maj', headers=H, json={'statut': 'done'}).status_code == 400

def test_maj_colonne_optionnelle_absente_retente_sans(client):
    # 1er PATCH -> 400 (colonne 'manquants' absente), 2e PATCH -> 200 sans elle.
    client.faux.patch_status = [400, 200]
    r = client.post('/affiliations/maj', headers=H,
                    json={'id': 1, 'statut': 'done', 'manquants': ['x']})
    assert r.status_code == 200
    dernier = client.faux.appels[-1][2]['json']
    assert 'manquants' not in dernier   # retenté sans la colonne absente

def test_orphelines_repasse_processing_en_pending(client):
    r = client.post('/affiliations/recuperer-orphelines', headers=H, json={})
    assert r.status_code == 200
    _, url, kw = client.faux.appels[-1]
    assert 'statut=eq.processing' in url and kw['json']['statut'] == 'pending'
