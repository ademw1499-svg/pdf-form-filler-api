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


def _jour(idx, lang):
    """Nom de jour localisé depuis un index 0=lundi (ou un nom déjà écrit)."""
    if idx in (None, ''):
        return BLANK
    tab = JOURS_NL if lang == 'NL' else JOURS_FR
    try:
        return tab[int(idx) % 7]
    except (ValueError, TypeError):
        return str(idx)


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
        # --- Cadre horaire (Article 10 §2) depuis les heures d'ouverture ---
        'cadre_debut': ou(payload.get('ouverture_debut')),
        'cadre_fin': ou(payload.get('ouverture_fin')),
        'cadre_jour_debut': _jour(payload.get('ouverture_jour_debut'), lang),
        'cadre_jour_fin': _jour(payload.get('ouverture_jour_fin'), lang),
        'cadre_min': '3',
        'cadre_max': ou(payload.get('max_journalier')) if payload.get('max_journalier') else '9',
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


def _decoupe_jour(st, work, pause):
    """Découpe une journée en matin + pause + après-midi (pause si travail > 6h).
    Retourne (matin_de, matin_a, aprem_de, aprem_a) en minutes ; aprem_de==matin_a
    s'il n'y a pas de pause."""
    if work <= 360:  # ≤ 6h : pas de pause obligatoire, bloc continu
        return st, st + work, st + work, st + work
    matin = int(round((work / 2) / 30.0)) * 30      # moitié arrondie à 30 min
    matin = max(180, min(matin, work - 180))          # chaque bloc ≥ 3h
    aprem = work - matin
    m_a = st + matin
    a_de = m_a + pause
    return st, m_a, a_de, a_de + aprem


def generer_horaires(payload, langue='FR', cible=2280, max_daily=480, min_block=180,
                     pause=30, pas=30, max_tables=600):
    """Génère les horaires-types valides depuis les heures d'ouverture.
    Pour 5 et 6 jours de travail, avec les différentes combinaisons de jours de
    repos ET toutes les heures de début par pas de 30 min. Chaque journée intègre
    la pause si le travail dépasse 6h. Même bloc chaque jour -> 11h de repos OK."""
    d, f = _min(payload.get('ouverture_debut')), _min(payload.get('ouverture_fin'))
    if d is None or f is None:
        return []
    ouverts = _jours_ouverts(payload.get('ouverture_jour_debut', 0), payload.get('ouverture_jour_fin', 6))
    if len(ouverts) < 5:
        return []
    win_s = d
    win_e = f if f > d else f + 1440           # ouverture de nuit (ex. 05:00->03:00)
    noms = JOURS_NL if langue == 'NL' else JOURS_FR
    schedules = []

    def arrangements():
        # 6 jours : 1 jour de repos ; 5 jours : 2 jours de repos consécutifs
        if len(ouverts) >= 6:
            for off in ouverts:
                work = [x for x in ouverts if x != off]
                if len(work) == 6:
                    yield work, [off], ('6 jours' if langue != 'NL' else '6 dagen')
        for i in range(7):
            pair = [i % 7, (i + 1) % 7]
            if pair[0] in ouverts and pair[1] in ouverts:
                work = [x for x in ouverts if x not in pair]
                if len(work) == 5:
                    yield work, pair, ('5 jours' if langue != 'NL' else '5 dagen')

    for work, off, mode in arrangements():
        n = len(work)
        daily = cible // n
        if daily > max_daily or daily < min_block:
            continue
        span = daily + (pause if daily > 360 else 0)   # amplitude = travail + pause
        st = win_s
        while st + span <= win_e:
            m_de, m_a, a_de, a_a = _decoupe_jour(st, daily, pause)
            lignes = [(day, m_de, m_a, a_de, a_a) for day in sorted(work)]
            repos = ', '.join(noms[o] for o in off)
            titre = (f"{mode} — {'repos' if langue != 'NL' else 'rust'} {repos}"
                     f" · {'début' if langue != 'NL' else 'start'} {_hhmm(st)}")
            schedules.append({'titre': titre, 'lignes': lignes, 'off': off,
                              'total': daily * n, 'pause': pause if daily > 360 else 0})
            if len(schedules) >= max_tables:
                return schedules
            st += pas
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


def _ajouter_annexe_horaires(doc, schedules, langue='FR'):
    from docx.shared import Pt, RGBColor
    noms = JOURS_NL if langue == 'NL' else JOURS_FR
    ACCENT = RGBColor(0x1c, 0x22, 0x44)
    doc.add_page_break()
    h = doc.add_paragraph()
    r = h.add_run('ANNEXE — HORAIRES DE TRAVAIL POSSIBLES' if langue != 'NL' else 'BIJLAGE — MOGELIJKE UURROOSTERS')
    r.bold = True; r.font.size = Pt(14); r.font.color.rgb = ACCENT
    intro = doc.add_paragraph()
    ri = intro.add_run(
        "Horaires-types compatibles avec les heures d'ouverture, en 38h/semaine. "
        "L'employeur communique l'horaire applicable au travailleur (à valider juridiquement)."
        if langue != 'NL' else
        "Mogelijke uurroosters binnen de openingsuren, 38u/week. Juridisch te valideren.")
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
        for day, m_de, m_a, a_de, a_a in sc['lignes']:
            c = tbl.add_row().cells
            c[0].paragraphs[0].add_run(noms[day].capitalize())
            c[1].paragraphs[0].add_run(f"{_hhmm(m_de)} – {_hhmm(m_a)}")
            c[2].paragraphs[0].add_run(f"{_hhmm(m_a)} – {_hhmm(a_de)}" if a_de > m_a else '—')
            c[3].paragraphs[0].add_run(f"{_hhmm(a_de)} – {_hhmm(a_a)}" if a_a > a_de else '—')
            c[4].paragraphs[0].add_run(_duree((m_a - m_de) + (a_a - a_de)))
        tot = doc.add_paragraph()
        pz = (f" · pause {sc['pause']} min/jour" if sc.get('pause') else '')
        rt = tot.add_run(('Total : ' if langue != 'NL' else 'Totaal: ') + _duree(sc['total']) + ' / '
                         + ('semaine' if langue != 'NL' else 'week') + pz)
        rt.font.size = Pt(9); rt.italic = True


def build_reglement(payload, identity=None, template_bytes=None, model_bytes=None):
    """Remplit le modèle officiel et renvoie les bytes du .docx.
    template_bytes : le modèle FR/NL (jetons {{...}}) depuis Supabase Storage.
    model_bytes    : (optionnel) horaire sectoriel à ajouter en fin de document.
    """
    if not template_bytes:
        raise ValueError("Modèle de règlement introuvable (pas encore hébergé).")
    lang = 'NL' if str(payload.get('reglement_langue') or 'FR').upper() == 'NL' else 'FR'
    doc = Document(io.BytesIO(template_bytes))
    _remplir_jetons(doc, _valeurs(payload, identity))

    # Annexe : horaires-types générés depuis les heures d'ouverture (5j / 6j).
    if payload.get('ouverture_debut') and payload.get('ouverture_fin'):
        try:
            mx = _min(f"{payload.get('max_journalier')}:00") if str(payload.get('max_journalier') or '').isdigit() else 480
            scheds = generer_horaires(payload, langue=lang, max_daily=mx or 480)
            if scheds:
                _ajouter_annexe_horaires(doc, scheds, lang)
        except Exception as e:
            print(f"[REGLEMENT] génération horaires ignorée : {e}")

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
