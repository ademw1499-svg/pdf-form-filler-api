# -*- coding: utf-8 -*-
"""
reglement_gen.py — Remplit LE modèle officiel PersoProject de règlement de travail.

Le modèle Word (FR ou NL) est un mail-merge : ses champs ont été transformés en
jetons {{Nom_Em}}, {{Commission_paritaire_Em}}, … (voir _reglement_bundle/). On
charge le modèle depuis Supabase Storage, on remplace les jetons par les données
(BCE + formulaire), et on renvoie le .docx. Les champs inconnus deviennent un
blanc « ………… » que la gestionnaire complète.

⚠ Document = PROJET, à faire valider juridiquement avant dépôt.
"""
import io
import re
from docx import Document
from docx.oxml.ns import qn

BLANK = '…………'


def _decoupe_adresse(idd):
    """(adresse_1, adresse_2 BCE) -> (rue, n°, code postal, localité)."""
    adr1 = (idd.get('adresse_siege_social_1') or '').strip()
    adr2 = (idd.get('adresse_siege_social_2') or '').strip()
    cp = loc = ''
    m = re.match(r'\s*(\d{4})\s+(.+)', adr2)
    if m:
        cp, loc = m.group(1), m.group(2).strip()
    rue, nomaison = adr1, ''
    m2 = re.match(r'(.+?)\s+(\d+\s*[A-Za-z]?)\s*$', adr1)
    if m2:
        rue, nomaison = m2.group(1).strip(), m2.group(2).strip()
    return rue, nomaison, cp, loc


def _valeurs(payload, identity):
    """Correspondance jeton -> valeur. Ce qu'on n'a pas -> BLANK (à compléter)."""
    idd = identity or {}
    rue, nomaison, cp, loc = _decoupe_adresse(idd)
    ent = re.sub(r'\D', '', payload.get('num_entreprise', '') or '')
    if len(ent) == 9:
        ent = '0' + ent
    ent_fmt = f"{ent[0:4]}.{ent[4:7]}.{ent[7:10]}" if len(ent) == 10 else (ent or BLANK)
    cpnum = re.sub(r'\D', '', payload.get('commission_paritaire', '') or '')
    adr1 = (idd.get('adresse_siege_social_1') or '').strip()

    def ou(v):  # valeur ou blanc
        return (str(v).strip() if v not in (None, '') else BLANK)

    v = {
        # --- Société (BCE + formulaire) ---
        'Nom_Em': ou(idd.get('nom_societe')),
        'Forme_juridique_Em': ou(idd.get('forme_juridique')),
        'Adresse_Em': ou(adr1),
        'Rue_Em': ou(rue),
        'No_de_la_maison_Em': ou(nomaison),
        'Code_postal_Em': ou(cp),
        'Localité_Em': ou(loc),
        'Activité_générale_Em': ou(idd.get('secteur_activite')),
        'Téléphone_Em': ou(payload.get('telephone')),
        'No_ONSS_Em': ou(payload.get('num_onss')),
        'No_d_entreprise_Emp': ent_fmt,
        'No_employeur_Em': ou(payload.get('num_onss')),
        'No_affiliation_instit_Em': BLANK,
        'No_affiliation_instit_Em_v1': BLANK,
        'Commission_paritaire_Em': ou(cpnum),
        'Commission_paritaire_Em_v1': BLANK,
        # --- ONSS : adresse officielle (constante) ---
        'Rue_institution_Inst': 'Place Victor Horta',
        'No_de_la_maison_inst_Inst': '11',
        'Code_postal_Institutions': '1060',
        'Localité_institution_Inst': 'Bruxelles',
        # --- Noms d'institutions sans ambiguïté dans le modèle ---
        'Nom_1_institution_Inst_v5': ou(payload.get('assurance_loi')),   # assurance-loi
        'Nom_1_institution_Inst_v1': ou(payload.get('caisse_vacances')),  # caisse de vacances
    }
    # Tout jeton non couvert -> BLANK (renseigné dynamiquement au remplissage)
    return v


def _remplir_jetons(doc, valeurs):
    """Remplace {{X}} par la valeur (ou BLANK) dans chaque run de texte."""
    for t in doc.element.body.iter(qn('w:t')):
        s = t.text or ''
        if '{{' in s:
            t.text = re.sub(r'\{\{(\w+)\}\}',
                            lambda m: str(valeurs.get(m.group(1), BLANK)), s)


def build_reglement(payload, identity=None, template_bytes=None, model_bytes=None):
    """Remplit le modèle officiel et renvoie les bytes du .docx.
    template_bytes : le modèle FR/NL (jetons {{...}}) depuis Supabase Storage.
    model_bytes    : (optionnel) horaire sectoriel à ajouter en fin de document.
    """
    if not template_bytes:
        raise ValueError("Modèle de règlement introuvable (pas encore hébergé).")
    doc = Document(io.BytesIO(template_bytes))
    _remplir_jetons(doc, _valeurs(payload, identity))

    if model_bytes:
        # Ajoute l'horaire sectoriel choisi à la fin (après les annexes du modèle).
        from docxcompose.composer import Composer
        doc.add_page_break()
        buf = io.BytesIO(); doc.save(buf); buf.seek(0)
        comp = Composer(Document(buf))
        comp.append(Document(io.BytesIO(model_bytes)))
        out = io.BytesIO(); comp.save(out)
        return out.getvalue()

    out = io.BytesIO(); doc.save(out)
    return out.getvalue()
