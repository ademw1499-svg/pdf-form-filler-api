# -*- coding: utf-8 -*-
"""
reglement_gen.py — Génère le règlement de travail (.docx) à partir du contrat §6.

Le corps (chapitres légaux) est construit avec python-docx ; si un modèle
d'horaire sectoriel est choisi, son .docx est ajouté en Annexe 1 (docxcompose).

⚠ Le document produit est un PROJET : il doit être validé par un conseiller
juridique avant dépôt au Contrôle des lois sociales.
"""
import io
from docx import Document
from docx.shared import Pt, RGBColor, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docxcompose.composer import Composer

ACCENT = RGBColor(0x1c, 0x22, 0x44)   # navy « Encre »
GREY = RGBColor(0x5c, 0x60, 0x72)

JOURS = ['lundi', 'mardi', 'mercredi', 'jeudi', 'vendredi', 'samedi', 'dimanche']

# --- Libellés bilingues (FR / NL) -------------------------------------------
L = {
    'FR': {
        'titre': 'RÈGLEMENT DE TRAVAIL',
        'jours': {'lundi': 'Lundi', 'mardi': 'Mardi', 'mercredi': 'Mercredi', 'jeudi': 'Jeudi',
                  'vendredi': 'Vendredi', 'samedi': 'Samedi', 'dimanche': 'Dimanche'},
        'entreprise': 'Entreprise', 'forme': 'Forme juridique', 'adresse': 'Siège social',
        'num_ent': "N° d'entreprise", 'cp': 'Commission paritaire', 'onss': "N° ONSS",
        'th_jour': 'Jour', 'th_matin': 'Matin', 'th_apres': 'Après-midi', 'th_total': 'Durée',
        'repos': 'Repos',
        'projet': ('PROJET — Ce règlement de travail a été pré-rempli automatiquement à partir '
                   'des données de la Banque-Carrefour des Entreprises et des informations '
                   "encodées. Il doit être vérifié et validé par un conseiller juridique avant "
                   'son dépôt au Contrôle des lois sociales.'),
        'chapitres': [
            ('CHAPITRE I — DURÉE ET HORAIRES DE TRAVAIL', [
                "La durée hebdomadaire de travail est de {heures} heures, répartie selon l'horaire "
                "ci-dessous (ou l'horaire figurant en Annexe 1 pour les horaires sectoriels).",
                "Les prestations sont organisées dans le respect de la loi du 16 mars 1971 sur le "
                "travail. Tout dépassement éventuel est régi par la réglementation en vigueur et les "
                "conventions de la commission paritaire compétente.",
            ]),
            ('CHAPITRE II — RÉMUNÉRATION', [
                "La rémunération est payée mensuellement, par virement sur le compte du travailleur, "
                "au plus tard le dernier jour ouvrable du mois auquel elle se rapporte.",
                "Les cotisations de sécurité sociale sont versées à l'Office national de sécurité "
                "sociale (ONSS){onss}. Le pécule de vacances des ouvriers est géré par la caisse de "
                "vacances compétente{caisse}.",
            ]),
            ('CHAPITRE III — CONGÉS ANNUELS ET JOURS FÉRIÉS', [
                "Le travailleur a droit aux congés annuels légaux (20 jours pour un régime de 5 jours "
                "par semaine, au prorata des prestations de l'exercice de vacances précédent).",
                "Les dix jours fériés légaux sont respectés conformément à la loi du 4 janvier 1974. "
                "Les jours de remplacement éventuels sont fixés au niveau de l'entreprise ou du "
                "secteur et communiqués aux travailleurs.",
            ]),
            ('CHAPITRE IV — ABSENCES ET INCAPACITÉ DE TRAVAIL', [
                "Toute absence doit être signalée à l'employeur le jour même, avant le début de la "
                "journée de travail. En cas d'incapacité de travail, un certificat médical est remis "
                "ou envoyé à l'employeur dans les deux jours ouvrables.",
                "L'employeur peut faire procéder à un contrôle médical. Le travailleur se tient à la "
                "disposition du médecin-contrôleur conformément à la loi du 3 juillet 1978.",
            ]),
            ('CHAPITRE V — FIN DU CONTRAT ET PRÉAVIS', [
                "Les délais de préavis sont fixés conformément à la loi du 3 juillet 1978 relative aux "
                "contrats de travail et à la loi du 26 décembre 2013 sur le statut unique.",
                "En cas de motif grave, le contrat peut être rompu sans préavis ni indemnité dans les "
                "conditions et délais prévus par la loi.",
            ]),
            ('CHAPITRE VI — SÉCURITÉ, SANTÉ ET PREMIERS SOINS', [
                "Les accidents du travail sont couverts par l'assurance-loi souscrite auprès de "
                "{assurance}. L'employeur est affilié au service externe pour la prévention et la "
                "protection au travail (SEPPT) {seppt}.",
                "Les premiers soins sont assurés par les secouristes désignés : {ps_noms}{ps_lieux}. "
                "La boîte de secours se trouve : {boite}.",
                "Tout accident, même bénin, doit être déclaré immédiatement à l'employeur.",
            ]),
            ('CHAPITRE VII — BIEN-ÊTRE PSYCHOSOCIAL', [
                "Conformément à la loi du 4 août 1996 relative au bien-être des travailleurs, "
                "l'employeur veille à prévenir les risques psychosociaux (stress, violence, "
                "harcèlement moral ou sexuel au travail).",
                "La personne de confiance désignée est : {confiance}. Le travailleur peut également "
                "s'adresser au conseiller en prévention aspects psychosociaux du SEPPT.",
            ]),
            ('CHAPITRE VIII — SURVEILLANCE PAR CAMÉRAS', [
                "La surveillance par caméras est mise en œuvre conformément à la CCT n° 68 et au "
                "Règlement général sur la protection des données (RGPD). Caméras installées : {cameras}.",
                "Les finalités, la conservation des images et les droits des travailleurs sont "
                "communiqués préalablement et de manière transparente.",
            ]),
            ('CHAPITRE IX — DROITS, DEVOIRS ET SANCTIONS', [
                "Le travailleur exécute son travail avec soin, probité et conscience. Il respecte les "
                "instructions de l'employeur et les règles de sécurité.",
                "L'échelle des sanctions est la suivante : avertissement verbal, avertissement écrit, "
                "puis, en cas de manquement grave, rupture du contrat pour motif grave. Les amendes "
                "éventuelles sont limitées et affectées conformément à la loi.",
            ]),
            ('CHAPITRE X — DISPOSITIONS FINALES', [
                "Le présent règlement est établi conformément à la loi du 8 avril 1965 instituant les "
                "règlements de travail. Un exemplaire est remis à chaque travailleur et affiché dans "
                "les locaux de l'entreprise.",
                "Le règlement (et ses modifications) est déposé auprès du Contrôle des lois sociales "
                "compétent. Il entre en vigueur après la procédure légale d'information et de "
                "consultation des travailleurs.",
            ]),
        ],
        'signatures': 'Fait à ……………………………, le ……………………………',
        'sig_emp': "Pour l'employeur", 'sig_trav': 'Le travailleur (pour réception)',
        'annexe1': 'ANNEXE 1 — HORAIRE DE TRAVAIL',
        'preambule_titre': 'PRÉAMBULE',
        'preambule': ("Le présent règlement de travail s'applique à l'ensemble du personnel de "
                      "l'entreprise, sans distinction. Il complète les dispositions légales, les "
                      "conventions collectives de travail de la commission paritaire compétente et le "
                      "contrat de travail individuel."),
    },
    'NL': {
        'titre': 'ARBEIDSREGLEMENT',
        'jours': {'lundi': 'Maandag', 'mardi': 'Dinsdag', 'mercredi': 'Woensdag', 'jeudi': 'Donderdag',
                  'vendredi': 'Vrijdag', 'samedi': 'Zaterdag', 'dimanche': 'Zondag'},
        'entreprise': 'Onderneming', 'forme': 'Rechtsvorm', 'adresse': 'Maatschappelijke zetel',
        'num_ent': 'Ondernemingsnr.', 'cp': 'Paritair comité', 'onss': 'RSZ-nr.',
        'th_jour': 'Dag', 'th_matin': 'Voormiddag', 'th_apres': 'Namiddag', 'th_total': 'Duur',
        'repos': 'Rust',
        'projet': ('ONTWERP — Dit arbeidsreglement werd automatisch voorbereid op basis van de '
                   'gegevens van de Kruispuntbank van Ondernemingen. Het moet door een juridisch '
                   'adviseur worden nagekeken en gevalideerd vóór neerlegging bij het Toezicht op de '
                   'sociale wetten.'),
        'chapitres': [
            ('HOOFDSTUK I — ARBEIDSDUUR EN UURROOSTERS', [
                "De wekelijkse arbeidsduur bedraagt {heures} uur, verdeeld volgens onderstaand "
                "uurrooster (of het uurrooster in Bijlage 1 voor sectorale roosters).",
                "De prestaties worden georganiseerd conform de arbeidswet van 16 maart 1971.",
            ]),
            ('HOOFDSTUK II — LOON', [
                "Het loon wordt maandelijks per overschrijving betaald, uiterlijk de laatste werkdag "
                "van de maand.",
                "De socialezekerheidsbijdragen worden gestort aan de RSZ{onss}. Het vakantiegeld van "
                "de arbeiders wordt beheerd door het bevoegde vakantiefonds{caisse}.",
            ]),
            ('HOOFDSTUK III — JAARLIJKSE VAKANTIE EN FEESTDAGEN', [
                "De werknemer heeft recht op de wettelijke jaarlijkse vakantie (20 dagen bij een "
                "5-dagenweek).",
                "De tien wettelijke feestdagen worden nageleefd conform de wet van 4 januari 1974.",
            ]),
            ('HOOFDSTUK IV — AFWEZIGHEID EN ARBEIDSONGESCHIKTHEID', [
                "Elke afwezigheid wordt dezelfde dag gemeld. Bij arbeidsongeschiktheid wordt binnen "
                "twee werkdagen een medisch attest bezorgd.",
                "De werkgever kan een medische controle laten uitvoeren.",
            ]),
            ('HOOFDSTUK V — EINDE VAN DE OVEREENKOMST EN OPZEGGING', [
                "De opzeggingstermijnen worden bepaald conform de wet van 3 juli 1978 en de wet van "
                "26 december 2013 (eenheidsstatuut).",
                "Bij dringende reden kan de overeenkomst zonder opzegging worden beëindigd.",
            ]),
            ('HOOFDSTUK VI — VEILIGHEID, GEZONDHEID EN EERSTE HULP', [
                "Arbeidsongevallen zijn verzekerd bij {assurance}. De werkgever is aangesloten bij de "
                "externe dienst voor preventie en bescherming op het werk (EDPBW) {seppt}.",
                "Eerste hulp wordt verleend door de aangeduide hulpverleners: {ps_noms}{ps_lieux}. "
                "De verbandkist bevindt zich: {boite}.",
            ]),
            ('HOOFDSTUK VII — PSYCHOSOCIAAL WELZIJN', [
                "Conform de wet van 4 augustus 1996 voorkomt de werkgever psychosociale risico's.",
                "De aangeduide vertrouwenspersoon is: {confiance}.",
            ]),
            ('HOOFDSTUK VIII — CAMERABEWAKING', [
                "Camerabewaking gebeurt conform CAO nr. 68 en de AVG. Geïnstalleerde camera's: {cameras}.",
            ]),
            ('HOOFDSTUK IX — RECHTEN, PLICHTEN EN SANCTIES', [
                "De werknemer voert het werk zorgvuldig uit en respecteert de veiligheidsregels.",
                "Sanctieladder: mondelinge verwittiging, schriftelijke verwittiging, en bij zware "
                "tekortkoming ontslag om dringende reden.",
            ]),
            ('HOOFDSTUK X — SLOTBEPALINGEN', [
                "Dit reglement is opgesteld conform de wet van 8 april 1965. Elk personeelslid "
                "ontvangt een exemplaar; het reglement wordt uitgehangen.",
                "Het reglement wordt neergelegd bij het bevoegde Toezicht op de sociale wetten.",
            ]),
        ],
        'signatures': 'Opgemaakt te ……………………………, op ……………………………',
        'sig_emp': 'Voor de werkgever', 'sig_trav': 'De werknemer (voor ontvangst)',
        'annexe1': 'BIJLAGE 1 — UURROOSTER',
        'preambule_titre': 'INLEIDING',
        'preambule': ("Dit arbeidsreglement is van toepassing op het volledige personeel van de "
                      "onderneming."),
    },
}


def _set_base_font(doc):
    st = doc.styles['Normal']
    st.font.name = 'Calibri'
    st.font.size = Pt(10.5)


def _h_title(doc, text):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run(text)
    r.bold = True
    r.font.size = Pt(20)
    r.font.color.rgb = ACCENT
    p.space_after = Pt(4)
    return p


def _h_chapter(doc, text):
    p = doc.add_paragraph()
    r = p.add_run(text)
    r.bold = True
    r.font.size = Pt(12.5)
    r.font.color.rgb = ACCENT
    p.paragraph_format.space_before = Pt(14)
    p.paragraph_format.space_after = Pt(4)
    return p


def _para(doc, text, size=10.5, color=None, italic=False, bold=False, align=None, space_after=6):
    p = doc.add_paragraph()
    r = p.add_run(text)
    r.font.size = Pt(size)
    r.italic = italic
    r.bold = bold
    if color is not None:
        r.font.color.rgb = color
    if align is not None:
        p.alignment = align
    p.paragraph_format.space_after = Pt(space_after)
    return p


def _fmt_ent(num):
    s = ''.join(c for c in str(num or '') if c.isdigit())
    if len(s) == 9:
        s = '0' + s
    return f"BE {s[0:4]}.{s[4:7]}.{s[7:10]}" if len(s) == 10 else (num or '')


def _identity_block(doc, lang, payload, identity):
    t = L[lang]
    identity = identity or {}
    lines = []
    nom = identity.get('nom_societe') or ''
    if nom:
        lines.append((t['entreprise'], nom))
    if identity.get('forme_juridique'):
        lines.append((t['forme'], identity['forme_juridique']))
    adr = ' — '.join(x for x in [identity.get('adresse_siege_social_1'),
                                 identity.get('adresse_siege_social_2')] if x)
    if adr:
        lines.append((t['adresse'], adr))
    lines.append((t['num_ent'], _fmt_ent(payload.get('num_entreprise'))))
    if payload.get('commission_paritaire'):
        lines.append((t['cp'], str(payload['commission_paritaire'])))
    if payload.get('num_onss'):
        lines.append((t['onss'], str(payload['num_onss'])))
    for label, val in lines:
        p = doc.add_paragraph()
        r = p.add_run(f"{label} : ")
        r.bold = True
        r.font.size = Pt(10.5)
        r.font.color.rgb = GREY
        r2 = p.add_run(str(val))
        r2.font.size = Pt(10.5)
        p.paragraph_format.space_after = Pt(2)


def _horaire_table(doc, lang, jours, heures):
    t = L[lang]
    tbl = doc.add_table(rows=1, cols=4)
    tbl.style = 'Light Grid Accent 1'
    hdr = tbl.rows[0].cells
    for i, key in enumerate(['th_jour', 'th_matin', 'th_apres', 'th_total']):
        hdr[i].paragraphs[0].add_run(t[key]).bold = True
    for j in JOURS:
        d = (jours or {}).get(j) or {}
        matin = _plage(d.get('matin_de'), d.get('matin_a'))
        apres = _plage(d.get('apres_de'), d.get('apres_a'))
        total = _duree(d)
        travaille = bool(matin or apres)
        row = tbl.add_row().cells
        row[0].paragraphs[0].add_run(t['jours'][j])
        row[1].paragraphs[0].add_run(matin or ('—' if not travaille else ''))
        row[2].paragraphs[0].add_run(apres or '')
        row[3].paragraphs[0].add_run(total or (t['repos'] if not travaille else ''))
    if heures:
        _para(doc, f"{t['th_total']} : {heures} h / " + ('semaine' if lang == 'FR' else 'week'),
              size=9.5, color=GREY, italic=True, space_after=4)


def _plage(de, a):
    de = (de or '').strip()
    a = (a or '').strip()
    if de and a:
        return f"{de} – {a}"
    return de or a or ''


def _duree(d):
    """Somme matin + après-midi en heures décimales -> 'Xh'."""
    def mins(de, a):
        de, a = (de or '').strip(), (a or '').strip()
        if not de or not a:
            return 0
        try:
            hd, md = map(int, de.replace('h', ':').split(':')[:2])
            ha, ma = map(int, a.replace('h', ':').split(':')[:2])
            return max(0, (ha * 60 + ma) - (hd * 60 + md))
        except Exception:
            return 0
    tot = mins(d.get('matin_de'), d.get('matin_a')) + mins(d.get('apres_de'), d.get('apres_a'))
    if not tot:
        return ''
    h, m = divmod(tot, 60)
    return f"{h}h{m:02d}" if m else f"{h}h"


def build_reglement(payload, identity=None, model_bytes=None):
    """Construit le .docx et renvoie les bytes.
    payload  : contrat §6 (voir reglementService.ts)
    identity : dict BCE (nom_societe, forme_juridique, adresse_siege_social_1/2)
    model_bytes : contenu .docx du modèle d'horaire à joindre en Annexe 1 (ou None)
    """
    lang = (payload.get('reglement_langue') or 'FR').upper()
    if lang not in L:
        lang = 'FR'
    t = L[lang]
    doc = Document()
    _set_base_font(doc)
    for s in doc.sections:
        s.top_margin = s.bottom_margin = Cm(1.8)
        s.left_margin = s.right_margin = Cm(2.0)

    _h_title(doc, t['titre'])
    _para(doc, t['projet'], size=8.5, color=RGBColor(0xc7, 0x6a, 0x06), italic=True,
          align=WD_ALIGN_PARAGRAPH.CENTER, space_after=12)

    _identity_block(doc, lang, payload, identity)

    _h_chapter(doc, t['preambule_titre'])
    _para(doc, t['preambule'])

    # Champs de substitution
    onss = payload.get('num_onss')
    caisse = payload.get('caisse_vacances')
    ps_noms = payload.get('premiers_soins_noms')
    ps_lieux = payload.get('premiers_soins_lieux')
    subst = {
        'heures': (payload.get('horaires', {}) or {}).get('ouvrier', {}).get('heures_semaine') or '38',
        'onss': f" (n° {onss})" if onss else '',
        'caisse': f" ({caisse})" if caisse else '',
        'assurance': payload.get('assurance_loi') or '…………',
        'seppt': payload.get('seppt') or '…………',
        'ps_noms': ps_noms or '…………',
        'ps_lieux': f" — {ps_lieux}" if ps_lieux else '',
        'boite': payload.get('boite_secours_emplacement') or '…………',
        'confiance': payload.get('personne_de_confiance') or '(à désigner)',
        'cameras': payload.get('cameras') or '0',
    }
    cameras_actives = str(payload.get('cameras') or '0').strip() not in ('', '0', 'non', 'Non', 'aucune')

    hor = payload.get('horaires') or {}
    modele = (payload.get('horaire_modele') or '').strip()

    for titre, paras in t['chapitres']:
        # Chapitre caméras masqué s'il n'y en a pas
        if 'CAMÉRAS' in titre or 'CAMERABEWAKING' in titre:
            if not cameras_actives:
                continue
        _h_chapter(doc, titre)
        for para in paras:
            _para(doc, para.format(**subst))
        # Après le chapitre I : insère l'horaire (annexe modèle, table manuelle,
        # ou simple référence au modèle si le fichier n'a pas pu être joint).
        if titre.startswith('CHAPITRE I ') or titre.startswith('HOOFDSTUK I '):
            ouv = hor.get('ouvrier') or {}
            emp = hor.get('employe')
            a_manuel = any((ouv.get('jours') or {}).get(j) for j in JOURS) or \
                (emp and any((emp.get('jours') or {}).get(j) for j in JOURS))
            if model_bytes:
                _para(doc, ('L\'horaire de travail applicable figure en Annexe 1.' if lang == 'FR'
                            else 'Het toepasselijke uurrooster staat in Bijlage 1.'),
                      italic=True, color=GREY)
            elif a_manuel:
                if any((ouv.get('jours') or {}).get(j) for j in JOURS):
                    _para(doc, ('Horaire — ouvriers / personnel' if lang == 'FR' else 'Uurrooster — arbeiders'),
                          bold=True, size=10.5, space_after=3)
                    _horaire_table(doc, lang, ouv.get('jours'), ouv.get('heures_semaine'))
                if emp and any((emp.get('jours') or {}).get(j) for j in JOURS):
                    _para(doc, ('Horaire — employés' if lang == 'FR' else 'Uurrooster — bedienden'),
                          bold=True, size=10.5, space_after=3)
                    _horaire_table(doc, lang, emp.get('jours'), emp.get('heures_semaine'))
            elif modele:
                label = modele.split('/')[-1].rsplit('.', 1)[0]
                _para(doc, (f'Horaire de travail : modèle sectoriel « {label} » — à joindre en annexe.'
                            if lang == 'FR'
                            else f'Uurrooster: sectoraal model « {label} » — als bijlage toe te voegen.'),
                      italic=True, color=GREY)

    # Signatures
    doc.add_paragraph()
    _para(doc, t['signatures'], space_after=16)
    sig = doc.add_table(rows=1, cols=2)
    sig.rows[0].cells[0].paragraphs[0].add_run(t['sig_emp']).bold = True
    sig.rows[0].cells[1].paragraphs[0].add_run(t['sig_trav']).bold = True

    # Annexe 1 : modèle d'horaire sectoriel (page séparée)
    if model_bytes:
        doc.add_page_break()
        _h_chapter(doc, t['annexe1'])
        base = doc  # composer va coller le modèle à la suite
        buf = io.BytesIO()
        base.save(buf)
        buf.seek(0)
        composed = Composer(Document(buf))
        composed.append(Document(io.BytesIO(model_bytes)))
        out = io.BytesIO()
        composed.save(out)
        return out.getvalue()

    out = io.BytesIO()
    doc.save(out)
    return out.getvalue()
