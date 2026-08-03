# -*- coding: utf-8 -*-
"""cp_paires.py — Correspondances commissions paritaires OUVRIERS ↔ EMPLOYÉS.

Quand une gestionnaire saisit une CP employés (2xx), le portail propose
automatiquement la CP ouvriers du même secteur (ex. 226 -> 140), et
inversement (124 -> 200). Les CP mixtes (3xx) couvrent les deux statuts :
pas de paire à proposer.

SOURCES (recherche du 03/08/2026, ne pas modifier sans re-vérifier) :
- ONSS, annexe 26 « Liste des commissions paritaires » v.2023/2 (catégorie
  officielle de chaque CP : manuel / intellectuel / général).
- Fedris, tableau 9 ; SPF Emploi (champs de compétence des CP).
- Securex Lex4You (construction 124 -> employés CP 200 ; électriciens 149.01
  -> CP 200 ; CP 226), Fonds social CP 200 (sfonds200.be), CGSLB (CP 100/200/226).

Règles par défaut confirmées :
- 1xx = ouvriers, 2xx = employés, 3xx = mixte (exception : 211 pétrole,
  numérotée 2xx mais couvre les DEUX statuts depuis la fusion 117->211 du
  01/04/2023).
- Secteur avec CP ouvriers mais SANS CP employés dédiée -> employés en CP 200.
- Secteur avec CP employés mais SANS CP ouvriers dédiée -> ouvriers en CP 100.
- La CP reste déterminée par l'activité principale de l'employeur : la
  suggestion est une AIDE, la gestionnaire garde la main (champ modifiable).

Cas volontairement SANS suggestion automatique (à trancher par un humain) :
- 216 (notaires) : ouvriers d'un notaire = 100 ou 336, à confirmer.
- 203 (petit granit) : la CP ouvriers se choisit entre 102.01/102.02 (bassin).
"""

# CP employés (2xx) -> CP ouvriers (1xx) du même secteur.
EMPLOYES_VERS_OUVRIERS = {
    '200': '100',      # auxiliaire (défaut)
    '201': '100',      # commerce de détail indépendant (pas de CP ouvriers dédiée)
    '202': '119',      # commerce de détail alimentaire
    '202.01': '119',   # moyennes entreprises d'alimentation
    '207': '116',      # chimie
    '209': '111',      # fabrications métalliques
    '210': '104',      # sidérurgie
    '214': '120',      # textile
    '215': '109',      # habillement-confection
    '220': '118',      # industrie alimentaire
    '221': '129',      # papier (production)
    '222': '136',      # transformation papier-carton
    '224': '105',      # métaux non ferreux
    '226': '140',      # commerce international, transport & logistique
}

# CP ouvriers (1xx) -> CP employés (2xx) du même secteur.
# Les secteurs sans CP employés dédiée retombent sur la CP 200 (source :
# Fonds social CP 200 + Securex : construction, garages, électriciens,
# nettoyage, bois, agriculture/horticulture, entretien du textile, imprimerie).
OUVRIERS_VERS_EMPLOYES = {
    '100': '200',
    '102.01': '203', '102.02': '203',   # carrières de petit granit
    '104': '210',
    '105': '224',
    '109': '215',
    '110': '200',      # entretien du textile
    '111': '209',
    '112': '200',      # garages
    '116': '207',
    '118': '220',
    '119': '202',      # commerce alimentaire
    '120': '214', '120.01': '214', '120.03': '214',
    '121': '200',      # nettoyage
    '124': '200',      # construction
    '125': '200', '125.01': '200', '125.02': '200', '125.03': '200',  # bois
    '126': '200',      # ameublement
    '129': '221',
    '130': '200',      # imprimerie (journaux : statut particulier, à confirmer)
    '132': '200',      # travaux techniques agricoles et horticoles
    '136': '222',
    '140': '226', '140.01': '226', '140.02': '226',
    '140.03': '226', '140.04': '226', '140.05': '226',   # transport & logistique
    '144': '200',      # agriculture
    '145': '200',      # horticulture
    '149.01': '200', '149.02': '200', '149.03': '200', '149.04': '200',
}

# CP numérotées hors 3xx mais couvrant les DEUX statuts (mixtes de fait).
MIXTES_EXCEPTIONS = {'211'}   # pétrole : fusion 117 -> 211 au 01/04/2023


def normaliser(cp):
    """« CP 140.03 », « 14003 », « 140.03.00 » -> clé normalisée « 140.03 »."""
    import re
    s = re.sub(r'[^0-9.]', '', str(cp or ''))
    s = re.sub(r'\.00$', '', s)
    if '.' not in s and len(s) > 3:      # « 14003 » -> « 140.03 »
        s = s[:3] + '.' + s[3:]
    return s


def categorie(cp):
    """'ouvriers' (1xx) | 'employes' (2xx) | 'mixte' (3xx + exceptions) | ''."""
    n = normaliser(cp)
    if not n[:3].isdigit():
        return ''
    if n.split('.')[0] in MIXTES_EXCEPTIONS:
        return 'mixte'
    serie = int(n[:3])
    if 100 <= serie <= 199:
        return 'ouvriers'
    if 200 <= serie <= 299:
        return 'employes'
    if 300 <= serie <= 399:
        return 'mixte'
    return ''


def analyser(cp):
    """Analyse une CP saisie -> dict pour le portail :
    { cp (normalisée), categorie, paire: {champ, cp} | None, note }.
    'paire.champ' = le champ du formulaire à pré-remplir avec 'paire.cp'."""
    n = normaliser(cp)
    cat = categorie(n)
    out = {'cp': n, 'categorie': cat, 'paire': None, 'note': ''}
    if cat == 'mixte':
        out['note'] = ("CP mixte : couvre ouvriers ET employés — pas de seconde "
                       "commission paritaire à ajouter.")
        return out
    if cat == 'employes':
        sugg = EMPLOYES_VERS_OUVRIERS.get(n) or EMPLOYES_VERS_OUVRIERS.get(n.split('.')[0])
        if sugg:
            out['paire'] = {'champ': 'cp_ouvrier', 'cp': sugg}
        else:
            out['note'] = "Pas de CP ouvriers suggérée pour ce secteur — à vérifier."
        return out
    if cat == 'ouvriers':
        sugg = OUVRIERS_VERS_EMPLOYES.get(n) or OUVRIERS_VERS_EMPLOYES.get(n.split('.')[0])
        if sugg:
            out['paire'] = {'champ': 'cp_employe', 'cp': sugg}
        else:
            out['note'] = "Pas de CP employés suggérée pour ce secteur — à vérifier."
        return out
    out['note'] = "Numéro de commission paritaire non reconnu."
    return out
