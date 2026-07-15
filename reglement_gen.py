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

JOURS_FR = ['lundi', 'mardi', 'mercredi', 'jeudi', 'vendredi', 'samedi', 'dimanche']
JOURS_NL = ['maandag', 'dinsdag', 'woensdag', 'donderdag', 'vrijdag', 'zaterdag', 'zondag']

# Personne de confiance + conseiller harcèlement selon le SEPPT (source : listes
# PersoProject — Excel « personne de confiance RT » + Attentia + Arista).
SEPPT_PDC = {
    'securex':  {'pc': 'Delphine PIETERS (0800/100.59)',
                 'harc': 'Delphine PIETERS (0800/100.59 — Health_safety@securex.be)'},
    'mensura':  {'pc': 'Benoit VAN TICHELEN et Dominique DEHON (02/549.71.07 et 011/26.40.90)',
                 'harc': 'Benoit VAN TICHELEN (02/549.71.07)'},
    'cesi':     {'pc': 'Tina SCHOLIERS (02/761.17.74)',
                 'harc': 'Mme MOREAU (02/771.00.25)'},
    'idewe':    {'pc': 'N° général (02/237.33.24)',
                 'harc': 'N° général (02/237.33.24)'},
    'proviko':  {'pc': 'Suzi Broupkmans (02/250.00.57)',
                 'harc': 'Suzi Broupkmans (02/250.00.57)'},
    'mediwet':  {'pc': 'Peter VAN SLEMBROUCK (09/221.06.07)',
                 'harc': 'Peter VAN SLEMBROUCK (09/221.06.07)'},
    'adhesia':  {'pc': 'N° général (02/511.06.86)',
                 'harc': 'N° général (02/511.06.86)'},
    'liantis':  {'pc': "Ana Rodriguez Sio — L'équipe psychosociale (078/150.888)",
                 'harc': "L'équipe psychosociale (078/150.888)"},
    'attentia': {'pc': "L'équipe des conseillers en prévention aspects psychosociaux "
                       "(02/738 75 31 — psy.prev@attentia.be)",
                 'harc': "L'équipe des conseillers en prévention aspects psychosociaux "
                         "(02/738 75 31 — psy.prev@attentia.be)"},
    'arista':   {'pc': 'Arista — conseiller psychosocial (02 533 74 11 — arista@arista.be)',
                 'harc': 'Arista — conseiller psychosocial (02 533 74 11 — arista@arista.be)'},
}


def _pdc_du_seppt(seppt):
    """Retourne {pc, harc} de la personne de confiance selon le SEPPT, ou None."""
    s = (seppt or '').lower()
    for cle, val in SEPPT_PDC.items():
        if cle in s:
            return val
    return None


def _jour(idx, lang):
    """Nom de jour localisé depuis un index 0=lundi (ou un nom déjà écrit)."""
    if idx in (None, ''):
        return BLANK
    tab = JOURS_NL if lang == 'NL' else JOURS_FR
    try:
        return tab[int(idx) % 7]
    except (ValueError, TypeError):
        return str(idx)


# Chaque institution du répertoire -> les jetons du modèle (Nom/Rue/N°/CP/Localité).
INST_TOKENS = {
    'caisse':            {'nom': 'Nom_1_institution_Inst_v1', 'rue': 'Rue_institution_Inst_v4',
                          'no': 'No_de_la_maison_inst_Inst_v4', 'cp': 'Code_postal_Institutions_v4',
                          'loc': 'Localité_institution_Inst_v4'},
    'assurance':         {'nom': 'Nom_1_institution_Inst_v5', 'rue': 'Rue_institution_Inst_v3',
                          'no': 'No_de_la_maison_inst_Inst_v3', 'cp': 'Code_postal_Institutions_v3',
                          'loc': 'Localité_institution_Inst_v3'},
    'fonds':             {'nom': 'Nom_1_institution_Inst_v4', 'rue': 'Rue_institution_Inst_v5',
                          'no': 'No_de_la_maison_inst_Inst_v5', 'cp': 'Code_postal_Institutions_v5',
                          'loc': 'Localité_institution_Inst_v5'},
    'seppt':             {'nom': 'Nom_1_institution_Inst', 'rue': 'Rue_institution_Inst_v1',
                          'no': 'No_de_la_maison_inst_Inst_v1', 'cp': 'Code_postal_Institutions_v1',
                          'loc': 'Localité_institution_Inst_v1'},
    'controle_lois':     {'rue': 'Rue_institution_Inst_v2', 'no': 'No_de_la_maison_inst_Inst_v2',
                          'cp': 'Code_postal_Institutions_v2', 'loc': 'Localité_institution_Inst_v2'},
    'controle_bienetre': {'rue': 'Rue_institution_Inst_v6', 'no': 'No_de_la_maison_inst_Inst_v6',
                          'cp': 'Code_postal_Institutions_v6', 'loc': 'Localité_institution_Inst_v6'},
}


def _province_from_cp(cp):
    try:
        n = int(re.sub(r'\D', '', str(cp))[:4])
    except (ValueError, TypeError):
        return ''
    if 1000 <= n <= 1299: return 'Bruxelles'
    if 1300 <= n <= 1499: return 'Brabant wallon'
    if 1500 <= n <= 1999 or 3000 <= n <= 3499: return 'Brabant flamand'
    if 2000 <= n <= 2999: return 'Anvers'
    if 3500 <= n <= 3999: return 'Limbourg'
    if 4000 <= n <= 4999: return 'Liège'
    if 5000 <= n <= 5999: return 'Namur'
    if 6000 <= n <= 6599 or 7000 <= n <= 7999: return 'Hainaut'
    if 6600 <= n <= 6999: return 'Luxembourg'
    if 8000 <= n <= 8999: return 'Flandre occidentale'
    if 9000 <= n <= 9999: return 'Flandre orientale'
    return ''


def _valeurs_institutions(payload, identity, repertoire):
    """Remplit les jetons d'adresses d'institutions depuis le répertoire.
    Assurance/caisse/SEPPT : par nom ; bureaux de contrôle : par province du client."""
    out = {}
    if not repertoire:
        return out
    idd = identity or {}
    _, _, cp_cli, _ = _decoupe_adresse(idd)
    prov = _province_from_cp(cp_cli)

    def pose(inst, typ):
        toks = INST_TOKENS.get(typ, {})
        if toks.get('nom') and inst.get('nom'):
            out[toks['nom']] = inst['nom']
        if toks.get('rue'):
            out[toks['rue']] = inst.get('rue') or ''
        if toks.get('no'):
            out[toks['no']] = inst.get('numero') or ''
        if toks.get('cp'):
            out[toks['cp']] = inst.get('code_postal') or ''
        if toks.get('loc'):
            out[toks['loc']] = inst.get('localite') or ''

    def trouve_par_nom(typ, nom):
        nom = (nom or '').lower().strip()
        cands = [i for i in repertoire if (i.get('type') or '') == typ]
        if nom:
            for i in cands:
                if (i.get('nom') or '').lower().strip() in nom or nom in (i.get('nom') or '').lower():
                    return i
        return cands[0] if len(cands) == 1 else None

    for typ, champ in (('assurance', 'assurance_loi'), ('caisse', 'caisse_vacances'), ('seppt', 'seppt')):
        inst = trouve_par_nom(typ, payload.get(champ))
        if inst:
            pose(inst, typ)
    # fonds : s'il n'y en a qu'un, ou celui de la province
    fonds = [i for i in repertoire if (i.get('type') or '') == 'fonds']
    if len(fonds) == 1:
        pose(fonds[0], 'fonds')
    # bureaux de contrôle : par province du client (ou l'unique)
    for typ in ('controle_lois', 'controle_bienetre'):
        cands = [i for i in repertoire if (i.get('type') or '') == typ]
        pick = next((i for i in cands if (i.get('province') or '') == prov and prov), None) \
            or (cands[0] if len(cands) == 1 else None)
        if pick:
            pose(pick, typ)
    return out


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


def _valeurs(payload, identity, repertoire=None):
    """Correspondance jeton -> valeur. Ce qu'on n'a pas -> BLANK (à compléter)."""
    idd = identity or {}
    lang = 'NL' if str(payload.get('reglement_langue') or 'FR').upper() == 'NL' else 'FR'
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
        'Nom_1_institution_Inst_v2': ou(payload.get('seppt')),           # conseiller prévention externe (SEPPT)
        # --- Annexe 4 (bien-être) + Annexe 5 (lieux) ---
        'ps_nom1': ou(payload.get('premiers_soins_noms')),
        'ps_lieu1': ou(payload.get('premiers_soins_lieux')),
        'ps_nom2': BLANK, 'ps_lieu2': BLANK,
        'boite_secours': ou(payload.get('boite_secours_emplacement')),
        # Personne de confiance + harcèlement : selon le SEPPT (saisie manuelle prioritaire)
        'personne_confiance': ou(payload.get('personne_de_confiance')
                                 or (_pdc_du_seppt(payload.get('seppt')) or {}).get('pc')),
        'harcelement': ou((_pdc_du_seppt(payload.get('seppt')) or {}).get('harc')),
        # sièges d'exploitation (annexe 5) : vraies unités d'établissement BCE si
        # disponibles (identity['sieges_exploitation']), sinon repli sur le siège social
        'sieges_exploitation': ou(idd.get('sieges_exploitation')
                                  or ' — '.join(x for x in [adr1, (idd.get('adresse_siege_social_2') or '').strip()] if x)),
        # --- Cadre horaire (Article 10 §2) depuis les heures d'ouverture ---
        'cadre_debut': ou(payload.get('ouverture_debut')),
        'cadre_fin': ou(payload.get('ouverture_fin')),
        'cadre_jour_debut': _jour(payload.get('ouverture_jour_debut'), lang),
        'cadre_jour_fin': _jour(payload.get('ouverture_jour_fin'), lang),
        'cadre_min': '3',
        'cadre_max': ou(payload.get('max_journalier')) if payload.get('max_journalier') else '9',
    }
    # Adresses des institutions depuis le répertoire (écrase les valeurs par défaut)
    v.update({k: val for k, val in _valeurs_institutions(payload, identity, repertoire).items() if val})
    # Tout jeton non couvert -> BLANK (renseigné dynamiquement au remplissage)
    return v


def _remplir_jetons(doc, valeurs, sequentiels=None):
    """Remplace {{X}} par la valeur (ou BLANK) et retire le placeholder « [date] ».

    `sequentiels` : {jeton: [val1, val2, …]} — pour les jetons qui se répètent et
    doivent prendre une valeur DIFFÉRENTE à chaque occurrence (ex. la commission
    paritaire, utilisée pour la ligne ouvrier PUIS la ligne employé). La 1ʳᵉ
    occurrence prend val1, la 2ᵉ val2, etc. ; au-delà on garde la dernière.
    """
    sequentiels = sequentiels or {}
    compteurs = {}

    def _rep(m):
        k = m.group(1)
        if k in sequentiels:
            vals = sequentiels[k]
            i = compteurs.get(k, 0)
            compteurs[k] = i + 1
            return str(vals[i] if i < len(vals) else vals[-1]) if vals else BLANK
        return str(valeurs.get(k, BLANK))

    for t in doc.element.body.iter(qn('w:t')):
        s = o = t.text or ''
        if '[date]' in s:
            s = s.replace('[date]', '')
        if '{{' in s:
            s = re.sub(r'\{\{(\w+)\}\}', _rep, s)
        if s != o:
            t.text = s


def _min(hhmm):
    try:
        h, m = str(hhmm).split(':')[:2]
        return int(h) * 60 + int(m)
    except Exception:
        return None


def _hhmm(minutes):
    minutes %= 1440
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _duree(m):
    h, mm = divmod(m, 60)
    return f"{h}h{mm:02d}" if mm else f"{h}h"


def _hebdo_min(v, defaut=2280):
    """Temps plein hebdomadaire -> minutes. Accepte « 36h30 », « 36,5 », « 38 »."""
    s = str(v or '').strip().lower().replace(',', '.')
    if not s:
        return defaut
    m = re.match(r'^(\d+)\s*h\s*(\d{1,2})?$', s)      # « 36h30 » / « 38h »
    if m:
        return int(m.group(1)) * 60 + int(m.group(2) or 0)
    try:
        return int(round(float(s) * 60))              # « 36.5 » / « 38 »
    except ValueError:
        return defaut


def _cp_norm(x):
    """Clé de CP normalisée : chiffres + éventuel sous-numéro, sans « .00 » final.
    « 112 »/« 112.00 » -> « 112 » ; « 102.01 » -> « 102.01 »."""
    s = re.sub(r'[^0-9.]', '', str(x or ''))
    s = re.sub(r'\.00$', '', s)
    return s


def _cp_lookup(cp_repertoire):
    """{clé CP normalisée -> {'hebdo', 'denom'}} depuis le répertoire des CP.
    Indexe aussi la variante chiffres-seuls (ex. « 10201 ») pour tolérer les saisies."""
    out = {}
    for row in (cp_repertoire or []):
        k = _cp_norm(row.get('cp'))
        if not k:
            continue
        rec = {'hebdo': str(row.get('heures_semaine') or '').strip(),
               'denom': str(row.get('denomination') or '').strip()}
        out.setdefault(k, rec)
        dk = re.sub(r'\D', '', k)
        if dk:
            out.setdefault(dk, rec)
    return out


def _cp_info(lut, cp):
    """Retrouve {'hebdo','denom'} d'une CP dans le lookup (tolère « 112 »/« 112.00 »/« 11200 »)."""
    if not lut:
        return {}
    n = _cp_norm(cp)
    return lut.get(n) or lut.get(re.sub(r'\D', '', n)) or {}


def _jours_ouverts(jd, jf):
    """Plage de jours contiguë de jd à jf (index 0=lundi), gère le passage de semaine."""
    try:
        a, b = int(jd), int(jf)
    except (ValueError, TypeError):
        return list(range(7))
    out, i = [], a
    for _ in range(7):
        out.append(i % 7)
        if i % 7 == b % 7:
            break
        i += 1
    return out


SEUIL_PAUSE = 240   # à partir de 4h de travail on insère une pause (matin/après-midi)


def _decoupe_jour(st, work, pause):
    """Découpe une journée en matin + pause + après-midi (pause dès 4h de travail).
    Retourne (matin_de, matin_a, aprem_de, aprem_a) en minutes ; aprem_de==matin_a
    s'il n'y a pas de pause (journée très courte)."""
    if work < SEUIL_PAUSE:                              # < 4h : bloc continu
        return st, st + work, st + work, st + work
    matin = int(round((work / 2) / 30.0)) * 30          # moitié arrondie à 30 min
    matin = max(90, min(matin, work - 90))              # chaque bloc ≥ 1h30
    aprem = work - matin
    m_a = st + matin
    a_de = m_a + pause
    return st, m_a, a_de, a_de + aprem


def generer_horaires(payload, langue='FR', cible=2280, max_daily=480, min_block=180,
                     pause=30, pas=30, max_tables=600,
                     debut=None, fin=None, jour_debut=None, jour_fin=None):
    """Génère les horaires-types valides depuis les heures d'ouverture.
    Pour 5 et 6 jours de travail, avec les différentes combinaisons de jours de
    repos ET toutes les heures de début par pas de 30 min. Chaque journée intègre
    la pause si le travail dépasse 6h. Même bloc chaque jour -> 11h de repos OK.

    debut/fin/jour_debut/jour_fin : ouverture explicite (par régime) ; à défaut on
    prend celle du payload (ouverture globale)."""
    ouv_debut = debut if debut is not None else payload.get('ouverture_debut')
    ouv_fin = fin if fin is not None else payload.get('ouverture_fin')
    jd = jour_debut if jour_debut is not None else payload.get('ouverture_jour_debut', 0)
    jf = jour_fin if jour_fin is not None else payload.get('ouverture_jour_fin', 6)
    d, f = _min(ouv_debut), _min(ouv_fin)
    if d is None or f is None:
        return []
    ouverts = _jours_ouverts(jd, jf)
    if len(ouverts) < 5:
        return []
    win_s = d
    win_e = f if f > d else f + 1440           # ouverture de nuit (ex. 05:00->03:00)
    noms = JOURS_NL if langue == 'NL' else JOURS_FR
    schedules = []

    from itertools import combinations

    def arrangements():
        # 6 jours puis 5 jours ; repos = TOUTES les combinaisons possibles de jours
        # de repos parmi les jours d'ouverture (pas seulement consécutives).
        n_open = len(ouverts)
        for n_work, label in ((6, '6 jours'), (5, '5 jours')):
            if n_open < n_work:
                continue
            n_off = n_open - n_work
            combos = [()] if n_off <= 0 else combinations(ouverts, n_off)
            for off_open in combos:
                work = [x for x in ouverts if x not in off_open]
                if len(work) != n_work:
                    continue
                off_disp = [d for d in range(7) if d not in work]  # tous les jours non prestés
                lab = label if langue != 'NL' else label.replace('jours', 'dagen')
                yield work, off_disp, lab

    win_len = win_e - win_s

    for work, off, mode in arrangements():
        n = len(work)
        daily_t = cible // n
        span_t = daily_t + (pause if daily_t >= SEUIL_PAUSE else 0)
        if span_t <= win_len:
            daily = daily_t                                   # temps plein pile
        elif (win_len - pause) >= min_block:
            daily = min(win_len - pause, max_daily)            # remplit la fenêtre
        else:
            continue
        span = daily + (pause if daily >= SEUIL_PAUSE else 0)
        workset = set(work)
        total = daily * n
        approx = '' if total == cible else (
            f" · {_duree(total)}/sem" if langue != 'NL' else f" · {_duree(total)}/week")

        def ajoute(st):
            m_de, m_a, a_de, a_a = _decoupe_jour(st, daily, pause)
            # TOUS les 7 jours : jour presté = horaire, sinon repos (None)
            lignes = [((day, m_de, m_a, a_de, a_a) if day in workset
                       else (day, None, None, None, None)) for day in range(7)]
            repos = ', '.join(noms[o] for o in off)
            titre = (f"{mode} — {'repos' if langue != 'NL' else 'rust'} {repos}"
                     f" · {'début' if langue != 'NL' else 'start'} {_hhmm(st)}{approx}")
            schedules.append({'titre': titre, 'lignes': lignes, 'off': off,
                              'total': total, 'pause': pause if daily >= SEUIL_PAUSE else 0})

        st, last = win_s, None
        while st + span <= win_e:
            ajoute(st); last = st
            if len(schedules) >= max_tables:
                return schedules
            st += pas
        # dernier horaire calé sur la fermeture (pour couvrir jusqu'à l'heure de fin)
        close_st = win_e - span
        if last is not None and close_st > last:
            ajoute(close_st)
            if len(schedules) >= max_tables:
                return schedules
    return schedules


def _bordures(tbl):
    """Applique des bordures fines à un tableau (sans dépendre d'un style nommé)."""
    from docx.oxml import OxmlElement
    tblPr = tbl._tbl.tblPr
    borders = OxmlElement('w:tblBorders')
    for edge in ('top', 'left', 'bottom', 'right', 'insideH', 'insideV'):
        e = OxmlElement(f'w:{edge}')
        e.set(qn('w:val'), 'single'); e.set(qn('w:sz'), '4')
        e.set(qn('w:space'), '0'); e.set(qn('w:color'), 'BFC4D6')
        borders.append(e)
    tblPr.append(borders)


def _ajouter_annexe_horaires(doc, schedules, langue='FR', titre_section=None):
    from docx.shared import Pt, RGBColor
    noms = JOURS_NL if langue == 'NL' else JOURS_FR
    ACCENT = RGBColor(0x1c, 0x22, 0x44)
    doc.add_page_break()
    h = doc.add_paragraph()
    entete = titre_section or ('ANNEXE — HORAIRES DE TRAVAIL POSSIBLES' if langue != 'NL'
                               else 'BIJLAGE — MOGELIJKE UURROOSTERS')
    r = h.add_run(entete)
    r.bold = True; r.font.size = Pt(14); r.font.color.rgb = ACCENT
    intro = doc.add_paragraph()
    ri = intro.add_run(
        "Horaires-types compatibles avec les heures d'ouverture. "
        "L'employeur communique l'horaire applicable au travailleur (à valider juridiquement)."
        if langue != 'NL' else
        "Mogelijke uurroosters binnen de openingsuren. Juridisch te valideren.")
    ri.italic = True; ri.font.size = Pt(9)
    thd = (['Jour', 'Matin', 'Pause', 'Après-midi', 'Durée'] if langue != 'NL'
           else ['Dag', 'Voormiddag', 'Pauze', 'Namiddag', 'Duur'])
    for sc in schedules:
        p = doc.add_paragraph()
        rp = p.add_run(sc['titre']); rp.bold = True; rp.font.size = Pt(10.5); rp.font.color.rgb = ACCENT
        p.paragraph_format.space_before = Pt(9); p.paragraph_format.space_after = Pt(2)
        tbl = doc.add_table(rows=1, cols=5)
        _bordures(tbl)
        for i, t in enumerate(thd):
            tbl.rows[0].cells[i].paragraphs[0].add_run(t).bold = True
        repos_txt = 'Repos' if langue != 'NL' else 'Rust'
        for day, m_de, m_a, a_de, a_a in sc['lignes']:
            c = tbl.add_row().cells
            c[0].paragraphs[0].add_run(noms[day].capitalize())
            if m_de is None:                      # jour de repos : ligne vide (visible)
                c[1].paragraphs[0].add_run(repos_txt)
                for k in (2, 3, 4):
                    c[k].paragraphs[0].add_run('—')
                continue
            c[1].paragraphs[0].add_run(f"{_hhmm(m_de)} – {_hhmm(m_a)}")
            c[2].paragraphs[0].add_run(f"{_hhmm(m_a)} – {_hhmm(a_de)}" if a_de > m_a else '—')
            c[3].paragraphs[0].add_run(f"{_hhmm(a_de)} – {_hhmm(a_a)}" if a_a > a_de else '—')
            c[4].paragraphs[0].add_run(_duree((m_a - m_de) + (a_a - a_de)))
        tot = doc.add_paragraph()
        pz = (f" · pause {sc['pause']} min/jour" if sc.get('pause') else '')
        rt = tot.add_run(('Total : ' if langue != 'NL' else 'Totaal: ') + _duree(sc['total']) + ' / '
                         + ('semaine' if langue != 'NL' else 'week') + pz)
        rt.font.size = Pt(9); rt.italic = True


def _remplir_cameras(doc, nb, lieux, lang='FR'):
    """Annexe 7 (Caméras) : « comporte … caméra(s) … aux endroits suivants : … ».
    Ces blancs sont des runs de « ……… » (pas des jetons). On remplit le 1er blanc
    (nombre) et le 2e (emplacements) du paragraphe caméras, sans toucher au reste
    (préserve la mise en page). Défaut : 0 caméra / « Néant »."""
    kw = 'caméra' if lang != 'NL' else 'camera'
    mk = 'comporte' if lang != 'NL' else 'bestaat uit'

    def isblank(s):
        t = (s or '').strip()
        return bool(t) and set(t) <= set('….') and len(t) >= 2

    for p in doc.paragraphs:
        runs = p.runs
        full = ''.join(r.text or '' for r in runs).lower()
        if kw not in full or mk not in full:
            continue
        blanks = [i for i, r in enumerate(runs) if isblank(r.text)]
        if not blanks:
            return False
        i0 = blanks[0]
        runs[i0].text = re.sub(r'[….]+', str(nb), runs[i0].text, count=1)
        if i0 + 1 < len(runs):                       # nettoie les points résiduels (ex. NL « ..camera »)
            runs[i0 + 1].text = re.sub(r'^\s*[….]+', '', runs[i0 + 1].text or '')
        if len(blanks) >= 2:
            i1 = blanks[1]
            runs[i1].text = re.sub(r'[….]+', str(lieux), runs[i1].text, count=1)
            if i1 + 1 < len(runs):
                runs[i1 + 1].text = re.sub(r'^\s*[….]+', '', runs[i1 + 1].text or '')
        return True
    return False


def build_reglement(payload, identity=None, template_bytes=None, model_bytes=None,
                    repertoire=None, cp_repertoire=None):
    """Remplit le modèle officiel et renvoie les bytes du .docx.
    template_bytes : le modèle FR/NL (jetons {{...}}) depuis Supabase Storage.
    model_bytes    : (optionnel) horaire sectoriel à ajouter en fin de document.
    repertoire     : liste d'institutions (adresses) pour remplir Art. 2 & 66.
    cp_repertoire  : liste des commissions paritaires (n° + dénomination + temps plein)
                     pour compléter la dénomination de la CP en Article 2.
    """
    if not template_bytes:
        raise ValueError("Modèle de règlement introuvable (pas encore hébergé).")
    lang = 'NL' if str(payload.get('reglement_langue') or 'FR').upper() == 'NL' else 'FR'
    lut = _cp_lookup(cp_repertoire)
    doc = Document(io.BytesIO(template_bytes))
    # Commission paritaire : la MÊME balise sert pour les 2 lignes du modèle
    # (ouvrier + employé) -> remplacement positionnel (1ʳᵉ occ. = 1er régime/CP,
    # 2ᵉ occ. = 2e régime/CP). Si des régimes explicites sont fournis, on les utilise.
    regs = payload.get('regimes') if isinstance(payload.get('regimes'), list) else []
    if regs:
        def _cpn(i):
            return re.sub(r'\D', '', str(regs[i].get('cp') or '')) if i < len(regs) else ''
        def _den(i):
            if i >= len(regs):
                return ''
            lbl = (regs[i].get('label') or regs[i].get('denomination') or '').strip()
            return lbl or _cp_info(lut, regs[i].get('cp')).get('denom', '')
        cp_ouv = _cpn(0) or BLANK
        cp_emp = _cpn(1) or BLANK
        den_ouv = _den(0) or BLANK
        den_emp = _den(1) or BLANK
    else:
        cp_ouv = re.sub(r'\D', '', str(payload.get('commission_paritaire') or '')) or BLANK
        cp_emp = re.sub(r'\D', '', str(payload.get('cp_employe') or '')) or BLANK
        den_ouv = ((payload.get('cp_ouvrier_denomination') or '').strip()
                   or _cp_info(lut, payload.get('commission_paritaire')).get('denom', '')) or BLANK
        den_emp = ((payload.get('cp_employe_denomination') or '').strip()
                   or _cp_info(lut, payload.get('cp_employe')).get('denom', '')) or BLANK
    sequentiels = {
        'Commission_paritaire_Em': [cp_ouv, cp_emp],
        'Commission_paritaire_Em_v1': [den_ouv, den_emp],
    }
    _remplir_jetons(doc, _valeurs(payload, identity, repertoire), sequentiels)
    # Annexe 7 — caméras de surveillance (défaut 0 si le client n'en a pas)
    nb_cam = str(payload.get('nombre_cameras') or payload.get('cameras') or '').strip() or '0'
    lieux_cam = (payload.get('cameras_emplacement') or '').strip() or (
        ('Néant' if lang != 'NL' else 'Geen') if nb_cam in ('0', '') else BLANK)
    _remplir_cameras(doc, nb_cam, lieux_cam, lang)
    # NB : les horaires générés vont dans un DOCUMENT SÉPARÉ (generer_doc_horaires),
    # plus le règlement lui-même, car ils peuvent faire des centaines de pages.

    if model_bytes:
        # Ajoute aussi l'horaire sectoriel choisi. Certains « modèles » sont en
        # réalité des fichiers Excel (non joignables) -> on n'échoue PAS.
        try:
            from docxcompose.composer import Composer
            doc.add_page_break()
            buf = io.BytesIO(); doc.save(buf); buf.seek(0)
            comp = Composer(Document(buf))
            comp.append(Document(io.BytesIO(model_bytes)))
            out = io.BytesIO(); comp.save(out)
            return out.getvalue()
        except Exception as e:
            print(f"[REGLEMENT] annexe modèle ignorée (non joignable) : {e}")

    out = io.BytesIO(); doc.save(out)
    return out.getvalue()


def _regimes_du_payload(payload, cp_repertoire=None):
    """Normalise les régimes de travail à générer. Chaque régime = une CP avec SON
    temps plein et SES propres heures d'ouverture -> une section d'horaires dédiée.

    - Si payload['regimes'] est fourni (liste), on l'utilise ; le temps plein et le
      libellé manquants sont complétés depuis le répertoire des CP (sinon 38h/sem).
    - Sinon rétro-compat : ouvriers (CP principale + ouverture globale) et,
      si une 2e CP/temps plein employés existe, une section employés (même ouverture).
    """
    lut = _cp_lookup(cp_repertoire)

    def _mxj(v):
        return (_min(f"{v}:00") if str(v or '').isdigit() else 480) or 480

    def _cible(cp, hebdo):
        h = hebdo if str(hebdo or '').strip() else _cp_info(lut, cp).get('hebdo')
        return _hebdo_min(h, 2280)

    def _lib(cp, label):
        return (label or '').strip() or _cp_info(lut, cp).get('denom', '')

    regs = payload.get('regimes')
    items = []
    if isinstance(regs, list) and regs:
        for rg in regs:
            deb, fin = rg.get('ouverture_debut'), rg.get('ouverture_fin')
            if not (deb and fin):
                continue
            cp = str(rg.get('cp') or '').strip()
            hebdo = rg.get('hebdo') if rg.get('hebdo') not in (None, '') else rg.get('heures_semaine')
            items.append({
                'label': _lib(cp, rg.get('label')),
                'cp': cp,
                'cible': _cible(cp, hebdo),
                'debut': deb, 'fin': fin,
                'jd': rg.get('jour_debut', rg.get('ouverture_jour_debut', 0)),
                'jf': rg.get('jour_fin', rg.get('ouverture_jour_fin', 6)),
                'mx': _mxj(rg.get('max_journalier')),
            })
        return items

    # Rétro-compat (ancien modèle ouvrier/employé, ouverture globale unique)
    if not (payload.get('ouverture_debut') and payload.get('ouverture_fin')):
        return []
    base = {'debut': payload.get('ouverture_debut'), 'fin': payload.get('ouverture_fin'),
            'jd': payload.get('ouverture_jour_debut', 0), 'jf': payload.get('ouverture_jour_fin', 6),
            'mx': _mxj(payload.get('max_journalier'))}
    cp_o = payload.get('commission_paritaire')
    items.append({**base, 'label': _lib(cp_o, 'ouvriers'), 'cp': cp_o,
                  'cible': _cible(cp_o, payload.get('heures_ouvrier'))})
    cp_e = str(payload.get('cp_employe') or '').strip()
    h_e = payload.get('heures_employe')
    if cp_e or h_e:
        items.append({**base, 'label': _lib(cp_e or cp_o, 'employés'), 'cp': cp_e or cp_o,
                      'cible': _cible(cp_e or cp_o, h_e)})
    return items


def generer_doc_horaires(payload, identity=None, cp_repertoire=None):
    """Document Word SÉPARÉ contenant tous les horaires-types (5j + 6j, toutes les
    combinaisons de jours de repos, tous les débuts par 30 min), UNE SECTION PAR
    RÉGIME (chaque CP avec son temps plein et sa propre ouverture).
    Renvoie les bytes, ou None si aucun horaire."""
    lang = 'NL' if str(payload.get('reglement_langue') or 'FR').upper() == 'NL' else 'FR'
    items = _regimes_du_payload(payload, cp_repertoire)
    if not items:
        return None

    from docx.shared import Pt, RGBColor
    doc = Document()
    stl = doc.styles['Normal']; stl.font.name = 'Calibri'; stl.font.size = Pt(10)
    ti = doc.add_paragraph()
    rt = ti.add_run(('HORAIRES DE TRAVAIL — ' if lang != 'NL' else 'UURROOSTERS — ')
                    + (identity or {}).get('nom_societe', ''))
    rt.bold = True; rt.font.size = Pt(16); rt.font.color.rgb = RGBColor(0x1c, 0x22, 0x44)

    total_tables = 0
    for it in items:
        try:
            scheds = generer_horaires(payload, langue=lang, cible=it['cible'], max_daily=it['mx'],
                                      max_tables=1500, debut=it['debut'], fin=it['fin'],
                                      jour_debut=it['jd'], jour_fin=it['jf'])
        except Exception as e:
            print(f"[REGLEMENT] horaires {it.get('label') or it.get('cp')} échoués : {e}"); continue
        if not scheds:
            continue
        cpnum = re.sub(r'[^0-9.]', '', str(it['cp'])) if it['cp'] else ''
        cph = f" (CP {cpnum})" if cpnum else ''
        base = (it['label'] or (f"CP {cpnum}" if cpnum else 'Horaires')).upper()
        titre = (f"{base}{cph} — {_duree(it['cible'])}/semaine" if lang != 'NL'
                 else f"{base}{cph} — {_duree(it['cible'])}/week")
        _ajouter_annexe_horaires(doc, scheds, lang, titre_section=titre)
        total_tables += len(scheds)
    if total_tables == 0:
        return None
    out = io.BytesIO(); doc.save(out)
    return out.getvalue()
