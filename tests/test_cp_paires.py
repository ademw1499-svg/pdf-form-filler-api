# -*- coding: utf-8 -*-
"""Paires de commissions paritaires ouvriers <-> employés (cp_paires.py + /cp/analyse).

Ce qu'on verrouille :
- la classification par série (1xx ouvriers / 2xx employés / 3xx mixte), y compris
  les sous-commissions (140.03) et l'exception 211 (pétrole, mixte depuis 2023) ;
- les paires confirmées par la recherche du 03/08 (sources ONSS annexe 26,
  SPF Emploi, Securex, Fonds CP 200) : 226<->140, 201->100, 124->200, 202<->119... ;
- les cas SANS suggestion (216 notaires) : paire None + note « à vérifier »,
  jamais d'invention ;
- l'endpoint public GET /cp/analyse/<cp>.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cp_paires as CP          # noqa: E402
import app                      # noqa: E402


# ---------- normalisation ----------

def test_normaliser_variantes():
    assert CP.normaliser('CP 226') == '226'
    assert CP.normaliser('112.00') == '112'
    assert CP.normaliser('14003') == '140.03'
    assert CP.normaliser(' 140.03 ') == '140.03'


# ---------- classification ----------

def test_series():
    assert CP.categorie('124') == 'ouvriers'
    assert CP.categorie('140.03') == 'ouvriers'
    assert CP.categorie('226') == 'employes'
    assert CP.categorie('302') == 'mixte'
    assert CP.categorie('330.01.10') == 'mixte'
    assert CP.categorie('') == ''

def test_exception_211_petrole_mixte():
    # 211 est numérotée 2xx mais couvre ouvriers ET employés depuis la fusion
    # 117 -> 211 (01/04/2023) : elle doit sortir « mixte », pas « employés ».
    assert CP.categorie('211') == 'mixte'


# ---------- paires ----------

def test_226_suggere_140():
    a = CP.analyser('226')
    assert a['categorie'] == 'employes'
    assert a['paire'] == {'champ': 'cp_ouvrier', 'cp': '140'}

def test_140_03_suggere_226():
    a = CP.analyser('140.03')
    assert a['paire'] == {'champ': 'cp_employe', 'cp': '226'}

def test_201_suggere_100():
    assert CP.analyser('201')['paire'] == {'champ': 'cp_ouvrier', 'cp': '100'}

def test_124_suggere_200():
    assert CP.analyser('124')['paire'] == {'champ': 'cp_employe', 'cp': '200'}

def test_202_bidirectionnel():
    assert CP.analyser('202')['paire'] == {'champ': 'cp_ouvrier', 'cp': '119'}
    assert CP.analyser('119')['paire'] == {'champ': 'cp_employe', 'cp': '202'}

def test_mixte_pas_de_paire():
    a = CP.analyser('302')
    assert a['categorie'] == 'mixte' and a['paire'] is None
    assert 'mixte' in a['note'].lower()

def test_216_notaires_pas_dinvention():
    # Ouvriers d'un notaire : 100 ou 336 selon les sources -> on ne suggère RIEN.
    a = CP.analyser('216')
    assert a['paire'] is None and 'vérifier' in a['note']


# ---------- endpoint public ----------

def test_endpoint_cp_analyse_public():
    c = app.app.test_client()
    r = c.get('/cp/analyse/226')
    assert r.status_code == 200
    d = r.get_json()
    assert d['categorie'] == 'employes' and d['paire']['cp'] == '140'
