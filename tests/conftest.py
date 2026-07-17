# -*- coding: utf-8 -*-
"""Garde-fou : sans les modèles Word, la suite passe au VERT sans rien vérifier.

Les 2 modèles officiels (reglement_FR.docx / reglement_NL.docx) vivent HORS du dépôt,
dans ../../_reglement_bundle — ce dépôt est PUBLIC et ce sont des documents PersoProject.
Les tests qui les utilisent font `pytest.skip` s'ils manquent : sur un autre poste ou en
CI, on obtenait « 99 passed, 40 skipped » et un code de sortie 0, alors que TOUT ce qui
vérifie le document réel (dénominations, fonds, article 66, annexes, placement des
institutions) n'avait pas tourné.

On échoue donc bruyamment. Pour lancer volontairement sans le bundle (tests unitaires
seuls) : PERSOPROJECT_SANS_BUNDLE=1 python3 -m pytest tests/
"""
import os

import pytest

BUNDLE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..',
                      '_reglement_bundle')
MODELES = ('reglement_FR.docx', 'reglement_NL.docx')


def pytest_sessionstart(session):
    if os.environ.get('PERSOPROJECT_SANS_BUNDLE'):
        return
    manquants = [m for m in MODELES if not os.path.exists(os.path.join(BUNDLE, m))]
    if manquants:
        raise pytest.UsageError(
            f"Modèles Word introuvables dans {os.path.normpath(BUNDLE)} : "
            f"{', '.join(manquants)}.\n"
            "Sans eux, ~40 tests — tout ce qui vérifie le document réellement produit — "
            "se sautent et la suite passe au vert sans rien prouver.\n"
            "Récupère le bundle, ou assume le choix : "
            "PERSOPROJECT_SANS_BUNDLE=1 python3 -m pytest tests/")
