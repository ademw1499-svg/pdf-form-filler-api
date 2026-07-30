"""Endpoints /itia : la todolist interne du service IT-IA (Kamil & Adem).

Ce qu'on verrouille ici (même modèle que test_chantiers) :
- AUCUN accès sans identité (ni token portail, ni clé PC06) -> 401 ;
- un statut ou un assigné hors liste est refusé -> 400 (pas de valeurs libres) ;
- création sans titre -> 400, création valide stampe cree_par ;
- on n'envoie jamais à Supabase une colonne hors ITIA_COLS.

Supabase est simulé (monkeypatch de requests.*) : on teste NOTRE logique,
pas PostgREST.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import app  # noqa: E402

CLE = 'cle-de-test-suffisamment-longue'


class FauxSupabase:
    """Capture la requête envoyée à Supabase et renvoie une réponse canned."""
    def __init__(self):
        self.appels = []

    def _reponse(self, corps):
        class R:
            status_code = 200
            text = ''
            def json(self):
                return corps
        return R()

    def get(self, url, **kw):
        self.appels.append(('GET', url, kw))
        return self._reponse([{'id': 1, 'titre': 'tâche', 'assigne': 'kamil', 'statut': 'afaire'}])

    def post(self, url, **kw):
        self.appels.append(('POST', url, kw))
        return self._reponse([{**(kw.get('json') or {}), 'id': 42}])

    def patch(self, url, **kw):
        self.appels.append(('PATCH', url, kw))
        return self._reponse([{**(kw.get('json') or {}), 'id': 1}])

    def delete(self, url, **kw):
        self.appels.append(('DELETE', url, kw))
        return self._reponse({})


@pytest.fixture
def client(monkeypatch):
    """Client Flask avec clé PC06 configurée et Supabase simulé."""
    monkeypatch.setenv('PC06_API_KEY', CLE)
    monkeypatch.setattr(app, 'SUPABASE_URL', 'https://fake.supabase.co')
    monkeypatch.setattr(app, 'SUPABASE_KEY', 'sk-fake')
    faux = FauxSupabase()
    monkeypatch.setattr(app.requests, 'get', faux.get)
    monkeypatch.setattr(app.requests, 'post', faux.post)
    monkeypatch.setattr(app.requests, 'patch', faux.patch)
    monkeypatch.setattr(app.requests, 'delete', faux.delete)
    c = app.app.test_client()
    c.faux = faux
    return c


# ---------- refus ----------

def test_liste_sans_identite_401(client):
    assert client.get('/itia').status_code == 401

def test_upsert_sans_identite_401(client):
    assert client.post('/itia/upsert', json={'titre': 'x'}).status_code == 401

def test_supprimer_sans_identite_401(client):
    assert client.post('/itia/supprimer', json={'id': 1}).status_code == 401

def test_statut_invalide_400(client):
    r = client.post('/itia/upsert', headers={'X-PC06-Key': CLE},
                    json={'id': 1, 'statut': 'pwn'})
    assert r.status_code == 400

def test_assigne_invalide_400(client):
    r = client.post('/itia/upsert', headers={'X-PC06-Key': CLE},
                    json={'id': 1, 'assigne': 'quelquun'})
    assert r.status_code == 400

def test_creation_sans_titre_400(client):
    r = client.post('/itia/upsert', headers={'X-PC06-Key': CLE},
                    json={'assigne': 'kamil'})
    assert r.status_code == 400


# ---------- accès ----------

def test_bonne_cle_liste_200(client):
    r = client.get('/itia', headers={'X-PC06-Key': CLE})
    assert r.status_code == 200
    assert isinstance(r.get_json(), list)

def test_changement_statut_patch(client):
    r = client.post('/itia/upsert', headers={'X-PC06-Key': CLE},
                    json={'id': 1, 'statut': 'fait'})
    assert r.status_code == 200
    methode, url, kw = client.faux.appels[-1]
    assert methode == 'PATCH' and 'suivi_itia' in url
    assert kw['json']['statut'] == 'fait'

def test_creation_stampe_cree_par(client):
    r = client.post('/itia/upsert', headers={'X-PC06-Key': CLE},
                    json={'titre': 'nouvelle tâche', 'assigne': 'adem'})
    assert r.status_code == 200
    _, _, kw = client.faux.appels[-1]
    assert kw['json']['cree_par'] == 'pc06'

def test_non_assigne_accepte(client):
    r = client.post('/itia/upsert', headers={'X-PC06-Key': CLE},
                    json={'titre': 'tâche libre', 'assigne': ''})
    assert r.status_code == 200

def test_colonnes_inconnues_filtrees(client):
    client.post('/itia/upsert', headers={'X-PC06-Key': CLE},
                json={'id': 1, 'titre': 'x', 'hack': 'oui', 'fait_par': 'moi'})
    _, _, kw = client.faux.appels[-1]
    assert 'hack' not in kw['json'] and 'fait_par' not in kw['json']
