# -*- coding: utf-8 -*-
"""Verrous de sécurité posés suite à l'audit du 04/08.

- Les routes de debug/test sont COUPÉES par défaut (DEBUG_ROUTES absent) ;
- /download-all-zip et /parse-prestations exigent une authentification
  (avant : écriture en base / upload PDF totalement anonymes) ;
- /affiliations/maj rejette un id non uuid/entier (injection PostgREST
  `1&statut=eq.pending` -> PATCH de masse).
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import app  # noqa: E402


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv('DEBUG_ROUTES', raising=False)
    return app.app.test_client()


# ---------- routes debug coupées en prod ----------

@pytest.mark.parametrize('route', ['/debug-config', '/debug-offre-raw',
                                   '/debug-each', '/test-zip'])
def test_routes_debug_404_par_defaut(client, route):
    assert client.get(route).status_code == 404

def test_debug_request_404_par_defaut(client):
    assert client.post('/debug-request', json={}).status_code == 404

def test_debug_reactivable_en_local(client, monkeypatch):
    monkeypatch.setenv('DEBUG_ROUTES', '1')
    assert client.get('/debug-config').status_code == 200


# ---------- endpoints anonymes verrouillés ----------

def test_download_all_zip_sans_jeton_401(client):
    r = client.post('/download-all-zip', json={'documents': ['employer'], 'form_data': {}})
    assert r.status_code == 401

def test_parse_prestations_sans_jeton_401(client):
    assert client.post('/parse-prestations', data={}).status_code == 401


# ---------- injection PostgREST /affiliations/maj ----------

def test_maj_id_injecte_rejete(client, monkeypatch):
    monkeypatch.setenv('PRESTATIONS_TOKEN', 'jeton-test-long-pour-compare-digest')
    monkeypatch.setattr(app, 'SUPABASE_URL', 'https://fake.supabase.co')
    monkeypatch.setattr(app, 'SUPABASE_KEY', 'sk-fake')
    r = client.post('/affiliations/maj',
                    headers={'X-Prestations-Token': 'jeton-test-long-pour-compare-digest'},
                    json={'id': '1&statut=eq.pending', 'statut': 'done'})
    assert r.status_code == 400   # rejeté AVANT toute requête PostgREST
