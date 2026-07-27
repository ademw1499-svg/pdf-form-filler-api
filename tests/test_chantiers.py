"""Endpoints /chantiers : le tableau de bord partagé Dims <-> Claude PC06.

Ce qu'on verrouille ici :
- AUCUN accès sans identité (ni token portail, ni clé PC06) -> 401 ;
- une MAUVAISE clé PC06 est refusée (pas de comparaison laxiste) ;
- la bonne clé PC06 passe, et cocher une case trace fait_par='pc06' + fait_le ;
- décocher EFFACE la trace (fait_par='', fait_le=None) ;
- création sans titre -> 400 (pas de lignes fantômes).

Supabase est simulé (monkeypatch de requests.*) : on teste NOTRE logique
d'auth et de traçage, pas PostgREST.
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
        return self._reponse([{'id': 1, 'fiche': 'Test', 'titre': 'tâche', 'fait': False}])

    def post(self, url, **kw):
        self.appels.append(('POST', url, kw))
        if '/auth/v1/user' in url:  # verify_user_token ne passe jamais ici (GET), sûreté
            raise AssertionError('inattendu')
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
    # Les endpoints chantiers passent par app.requests ; verify_user_token aussi
    # (GET /auth/v1/user) -> notre faux GET renvoie 200 mais SANS email : on force
    # le chemin token invalide en faisant échouer côté statut quand pas de token.
    monkeypatch.setattr(app.requests, 'get', faux.get)
    monkeypatch.setattr(app.requests, 'post', faux.post)
    monkeypatch.setattr(app.requests, 'patch', faux.patch)
    monkeypatch.setattr(app.requests, 'delete', faux.delete)
    c = app.app.test_client()
    c.faux = faux
    return c


# ---------- refus ----------

def test_liste_sans_identite_401(client):
    assert client.get('/chantiers').status_code == 401

def test_upsert_sans_identite_401(client):
    assert client.post('/chantiers/upsert', json={'titre': 'x'}).status_code == 401

def test_supprimer_sans_identite_401(client):
    assert client.post('/chantiers/supprimer', json={'id': 1}).status_code == 401

def test_mauvaise_cle_401(client):
    r = client.get('/chantiers', headers={'X-PC06-Key': 'mauvaise-cle'})
    assert r.status_code == 401

def test_cle_vide_401_meme_si_env_vide(client, monkeypatch):
    # Si PC06_API_KEY n'est pas configurée côté Railway, une clé vide NE passe PAS.
    monkeypatch.setenv('PC06_API_KEY', '')
    r = client.get('/chantiers', headers={'X-PC06-Key': ''})
    assert r.status_code == 401


# ---------- accès PC06 ----------

def test_bonne_cle_liste_200(client):
    r = client.get('/chantiers', headers={'X-PC06-Key': CLE})
    assert r.status_code == 200
    assert isinstance(r.get_json(), list)

def test_cocher_trace_fait_par_et_fait_le(client):
    r = client.post('/chantiers/upsert', headers={'X-PC06-Key': CLE},
                    json={'id': 1, 'fait': True})
    assert r.status_code == 200
    _, _, kw = client.faux.appels[-1]
    envoye = kw['json']
    assert envoye['fait_par'] == 'pc06'
    assert envoye['fait_le']  # horodaté

def test_decocher_efface_la_trace(client):
    client.post('/chantiers/upsert', headers={'X-PC06-Key': CLE},
                json={'id': 1, 'fait': False})
    _, _, kw = client.faux.appels[-1]
    envoye = kw['json']
    assert envoye['fait_par'] == ''
    assert envoye['fait_le'] is None

def test_creation_sans_titre_400(client):
    r = client.post('/chantiers/upsert', headers={'X-PC06-Key': CLE},
                    json={'fiche': 'Test'})
    assert r.status_code == 400

def test_creation_stampe_cree_par(client):
    r = client.post('/chantiers/upsert', headers={'X-PC06-Key': CLE},
                    json={'titre': 'nouvelle tâche', 'fiche': 'Test'})
    assert r.status_code == 200
    _, _, kw = client.faux.appels[-1]
    assert kw['json']['cree_par'] == 'pc06'

def test_colonnes_inconnues_filtrees(client):
    # On n'envoie jamais à Supabase un champ hors CHANTIER_COLS (pas d'injection de colonnes).
    client.post('/chantiers/upsert', headers={'X-PC06-Key': CLE},
                json={'id': 1, 'titre': 'x', 'hack': 'oui', 'statut': 'pwn'})
    _, _, kw = client.faux.appels[-1]
    assert 'hack' not in kw['json'] and 'statut' not in kw['json']
