from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
import io
import os
import zipfile
from datetime import datetime

app = Flask(__name__)
CORS(app)

# ============== CONFIGURATION ==============

# PDF Templates - All documents are single PDFs (no more split files)
TEMPLATES = {
    # French templates
    'employer': 'FICHE_RENSEIGNEMENTS_EMPLOYEUR_FR_2020.pdf',
    'travailleur': 'FICHE_RENSEIGNEMENTS_TRAVAILLEUR_FR.pdf',
    'independant': 'FICHE_RENSEIGNEMENTS_INDEPENDANT.pdf',
    'att_accident_fr': 'ATTESTATION_ASSURANCE_ACCIDENT_DE_TRAVAIL.pdf',
    'att_seppt_fr': 'ATTESTATION_SEPPT.pdf',
    'dispense': 'Dispense_partielle_de_versement_du_precompte_professionnel.pdf',
    'mensura': 'FOR140106_FR.pdf',
    'procuration': 'PROCURATION.pdf',
    # Offre de collaboration - SINGLE 20-page documents (FR & NL)
    'offre_fr': 'Offre_de_collaboration_FR_2025-2026.pdf',
    'offre_nl': 'Offre_de_collaboration_NL_2025-2026.pdf',
    # Dutch templates
    'att_accident_nl': 'Attestation_accident_travail_NL.pdf',
    'att_seppt_nl': 'Attestation_SEPPT_NL.pdf',
}

# ============== STATIC DOCUMENTS ==============
# These are informational documents included automatically (no fillable fields)

STATIC_DOCUMENTS = {
    'obligation_employeur': ('Obligation_Employeur_2025.pdf', 'Obligation_Employeur_2025.pdf'),
}

# Which static documents to include with each main document
DOCUMENT_BUNDLES = {
    'offre': ['obligation_employeur'],  # Offre includes Obligation Employeur
    'employer': [],
    'travailleur': [],
    'independant': [],
    'seppt': [],
    'accident': [],
    'dispense': [],
    'procuration': [],
    'mensura': [],
}

# ============== HELPER FUNCTIONS ==============

SCALE_X, SCALE_Y = 595/707, 842/1000

def cvt(x, y):
    """Convert coordinates from template space to PDF space"""
    return (x * SCALE_X, 842 - (y * SCALE_Y))

def txt(c, t, x, y, s=10):
    """Draw text on canvas at specified position"""
    c.setFont("Helvetica", s)
    c.drawString(*cvt(x, y), str(t))

def newcan():
    """Create new canvas and buffer"""
    p = io.BytesIO()
    return p, canvas.Canvas(p, pagesize=(595, 842))

def merge(tpl, pkt, npg=1):
    """Merge overlay canvas with template PDF"""
    pkt.seek(0)
    ov = PdfReader(pkt)
    rd = PdfReader(tpl)
    wr = PdfWriter()
    for i in range(len(rd.pages)):
        pg = rd.pages[i]
        if i < len(ov.pages):
            pg.merge_page(ov.pages[i])
        wr.add_page(pg)
    out = io.BytesIO()
    wr.write(out)
    out.seek(0)
    return out

def get_static_document_bytes(doc_key):
    """Read a static document from disk and return (bytes, display_name)"""
    if doc_key not in STATIC_DOCUMENTS:
        return None, None
    filename, display_name = STATIC_DOCUMENTS[doc_key]
    if os.path.exists(filename):
        with open(filename, 'rb') as f:
            return f.read(), display_name
    print(f"WARNING: Static document not found: {filename}")
    return None, None

def get_bundle_for_document(doc_type):
    """Get list of static document keys that should accompany a document type"""
    return DOCUMENT_BUNDLES.get(doc_type, [])


# ============== HEALTH & DEBUG ENDPOINTS ==============

@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        "status": "healthy",
        "ts": datetime.now().isoformat(),
        "bilingual_support": True,
        "bilingual_documents": ["seppt", "accident", "offre"],
        "static_documents": list(STATIC_DOCUMENTS.keys()),
        "document_bundles": {k: v for k, v in DOCUMENT_BUNDLES.items() if v}
    })

@app.route('/debug-config', methods=['GET'])
def debug_config():
    template_status = {}
    for key, filename in TEMPLATES.items():
        template_status[key] = {
            "filename": filename,
            "exists": os.path.exists(filename)
        }
    
    static_status = {}
    for key, (filename, display) in STATIC_DOCUMENTS.items():
        static_status[key] = {
            "filename": filename,
            "display_name": display,
            "exists": os.path.exists(filename),
            "size_kb": round(os.path.getsize(filename) / 1024, 1) if os.path.exists(filename) else 0
        }
    
    return jsonify({
        "templates": template_status,
        "static_documents": static_status,
        "document_bundles": DOCUMENT_BUNDLES,
        "supported_languages": ["fr", "nl"]
    })


# ============== INDIVIDUAL FORM ENDPOINTS ==============

@app.route('/fill-employer-form', methods=['POST'])
def fill_employer():
    d = request.get_json()
    if not d:
        return jsonify({"error": "No data"}), 400
    try:
        pdf_bytes = fill_employer_pdf(d)
        return send_file(io.BytesIO(pdf_bytes), mimetype='application/pdf', as_attachment=True, download_name='Fiche_employeur.pdf')
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/fill-travailleur', methods=['POST'])
def fill_travailleur():
    d = request.get_json()
    if not d:
        return jsonify({"error": "No data"}), 400
    try:
        pdf_bytes = fill_travailleur_pdf(d)
        return send_file(io.BytesIO(pdf_bytes), mimetype='application/pdf', as_attachment=True, download_name='Fiche_travailleur.pdf')
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/fill-independant', methods=['POST'])
def fill_independant():
    d = request.get_json()
    if not d:
        return jsonify({"error": "No data"}), 400
    try:
        pdf_bytes = fill_independant_pdf(d)
        return send_file(io.BytesIO(pdf_bytes), mimetype='application/pdf', as_attachment=True, download_name='Fiche_independant.pdf')
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/fill-att-accident', methods=['POST'])
def fill_att_accident():
    d = request.get_json()
    if not d:
        return jsonify({"error": "No data"}), 400
    try:
        pdf_bytes = fill_att_accident_pdf(d, 'fr')
        return send_file(io.BytesIO(pdf_bytes), mimetype='application/pdf', as_attachment=True, download_name='Attestation_accident_travail_FR.pdf')
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/fill-att-accident-nl', methods=['POST'])
def fill_att_accident_nl():
    d = request.get_json()
    if not d:
        return jsonify({"error": "No data"}), 400
    try:
        pdf_bytes = fill_att_accident_pdf(d, 'nl')
        return send_file(io.BytesIO(pdf_bytes), mimetype='application/pdf', as_attachment=True, download_name='Attestation_accident_travail_NL.pdf')
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/fill-att-seppt', methods=['POST'])
def fill_att_seppt():
    d = request.get_json()
    if not d:
        return jsonify({"error": "No data"}), 400
    try:
        pdf_bytes = fill_att_seppt_pdf(d, 'fr')
        return send_file(io.BytesIO(pdf_bytes), mimetype='application/pdf', as_attachment=True, download_name='Attestation_SEPPT_FR.pdf')
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/fill-att-seppt-nl', methods=['POST'])
def fill_att_seppt_nl():
    d = request.get_json()
    if not d:
        return jsonify({"error": "No data"}), 400
    try:
        pdf_bytes = fill_att_seppt_pdf(d, 'nl')
        return send_file(io.BytesIO(pdf_bytes), mimetype='application/pdf', as_attachment=True, download_name='Attestation_SEPPT_NL.pdf')
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/fill-offre', methods=['POST'])
def fill_offre():
    """Fill Offre de Collaboration - French (20 pages, single PDF)"""
    d = request.get_json()
    if not d:
        return jsonify({"error": "No data"}), 400
    try:
        pdf_bytes = fill_offre_pdf(d, 'fr')
        return send_file(io.BytesIO(pdf_bytes), mimetype='application/pdf', as_attachment=True, download_name='Offre_de_collaboration_FR.pdf')
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/fill-offre-nl', methods=['POST'])
def fill_offre_nl():
    """Fill Offre de Collaboration - Dutch (20 pages, single PDF)"""
    d = request.get_json()
    if not d:
        return jsonify({"error": "No data"}), 400
    try:
        pdf_bytes = fill_offre_pdf(d, 'nl')
        return send_file(io.BytesIO(pdf_bytes), mimetype='application/pdf', as_attachment=True, download_name='Offre_de_collaboration_NL.pdf')
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/fill-procuration', methods=['POST'])
def fill_procuration():
    d = request.get_json()
    if not d:
        return jsonify({"error": "No data"}), 400
    try:
        pdf_bytes = fill_procuration_pdf(d)
        return send_file(io.BytesIO(pdf_bytes), mimetype='application/pdf', as_attachment=True, download_name='Procuration_ONSS.pdf')
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/fill-dispense', methods=['POST'])
def fill_dispense():
    d = request.get_json()
    if not d:
        return jsonify({"error": "No data"}), 400
    try:
        pdf_bytes = fill_dispense_pdf(d)
        return send_file(io.BytesIO(pdf_bytes), mimetype='application/pdf', as_attachment=True, download_name='Dispense_precompte.pdf')
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/fill-mensura', methods=['POST'])
def fill_mensura():
    d = request.get_json()
    if not d:
        return jsonify({"error": "No data"}), 400
    try:
        pdf_bytes = fill_mensura_pdf(d)
        return send_file(io.BytesIO(pdf_bytes), mimetype='application/pdf', as_attachment=True, download_name='Contrat_Mensura.pdf')
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ============== PDF GENERATION FUNCTIONS ==============

def fill_employer_pdf(d):
    """Generate Employer PDF bytes (2 pages)"""
    p, c = newcan()
    # Page 1
    if d.get('recu_par'):
        txt(c, d['recu_par'], 235, 198)
    f = d.get('forme_juridique', '')
    if f == 'SRL':
        txt(c, 'X', 195, 235, 12)
    elif f == 'SC':
        txt(c, 'X', 240, 235, 12)
    elif f == 'SA':
        txt(c, 'X', 285, 235, 12)
    elif f == 'ASBL':
        txt(c, 'X', 345, 235, 12)
    elif f == 'PERSONNE PHYSIQUE':
        txt(c, 'X', 415, 235, 12)
    if d.get('nom_societe'):
        txt(c, d['nom_societe'], 469, 277)
    if d.get('nom_prenom_gerant'):
        txt(c, d['nom_prenom_gerant'], 469, 310)
    if d.get('niss_gerant'):
        txt(c, d['niss_gerant'], 468, 344)
    if d.get('adresse_siege_social_1'):
        txt(c, d['adresse_siege_social_1'], 466, 375)
    if d.get('adresse_siege_social_2'):
        txt(c, d['adresse_siege_social_2'], 465, 409)
    if d.get('adresse_exploitation_1'):
        txt(c, d['adresse_exploitation_1'], 466, 443)
    if d.get('adresse_exploitation_2'):
        txt(c, d['adresse_exploitation_2'], 464, 478)
    if d.get('telephone_gsm'):
        txt(c, d['telephone_gsm'], 461, 507)
    if d.get('email'):
        txt(c, d['email'], 462, 539)
    if d.get('num_entreprise'):
        txt(c, d['num_entreprise'], 462, 572)
    if d.get('num_onss'):
        txt(c, d['num_onss'], 462, 604)
    if d.get('assurance_loi'):
        txt(c, d['assurance_loi'], 464, 638)
    if d.get('seppt'):
        txt(c, d['seppt'], 464, 669)
    if d.get('secteur_activite'):
        txt(c, d['secteur_activite'], 464, 703)
    r = d.get('reduction_premier', '')
    if r == 'Oui':
        txt(c, 'X', 96, 768, 12)
    elif r == 'Non':
        txt(c, 'X', 133, 768, 12)
    if d.get('commission_paritaire'):
        txt(c, d['commission_paritaire'], 462, 802)
    if d.get('indice_onss'):
        txt(c, d['indice_onss'], 463, 834)
    if d.get('code_nace'):
        txt(c, d['code_nace'], 461, 868)
    s = d.get('salaire_garanti', '')
    if s == 'OUI':
        txt(c, 'X', 581, 899, 12)
    elif s == 'NON':
        txt(c, 'X', 618, 899, 12)
    
    # Page 2
    c.showPage()
    if d.get('regime_horaire'):
        txt(c, d['regime_horaire'], 357, 148)
    for day, y in [('lundi', 228), ('mardi', 247), ('mercredi', 266), ('jeudi', 285), ('vendredi', 304), ('samedi', 331), ('dimanche', 351)]:
        if d.get(f'{day}_matin_de'):
            txt(c, d[f'{day}_matin_de'], 213, y, 9)
        if d.get(f'{day}_matin_a'):
            txt(c, d[f'{day}_matin_a'], 276, y, 9)
        if d.get(f'{day}_pause_de'):
            txt(c, d[f'{day}_pause_de'], 363, y, 9)
        if d.get(f'{day}_pause_a'):
            txt(c, d[f'{day}_pause_a'], 423, y, 9)
        if d.get(f'{day}_apres_de'):
            txt(c, d[f'{day}_apres_de'], 522, y, 9)
        if d.get(f'{day}_apres_a'):
            txt(c, d[f'{day}_apres_a'], 585, y, 9)
    if d.get('cameras'):
        txt(c, d['cameras'], 427, 387)
    if d.get('trousse_secours'):
        txt(c, d['trousse_secours'], 400, 453)
    if d.get('vetements_fourniture') == 'Oui':
        txt(c, 'X', 348, 486, 12)
    elif d.get('vetements_fourniture') == 'Non':
        txt(c, 'X', 385, 485, 12)
    if d.get('vetements_entretien') == 'Oui':
        txt(c, 'X', 347, 518, 12)
    elif d.get('vetements_entretien') == 'Non':
        txt(c, 'X', 388, 518, 12)
    if d.get('primes'):
        txt(c, d['primes'], 394, 552)
    if d.get('secretariat_actuel'):
        txt(c, d['secretariat_actuel'], 394, 583)
    if d.get('nom_comptable'):
        txt(c, d['nom_comptable'], 390, 617)
    if d.get('coord_comptable'):
        txt(c, d['coord_comptable'], 390, 648)
    o = d.get('origine', '')
    if o == 'Internet':
        txt(c, 'X', 173, 683, 12)
    elif o == 'Comptable':
        txt(c, 'X', 342, 683, 12)
    elif o == 'Client':
        txt(c, 'X', 174, 716, 12)
    elif o == 'Autre':
        txt(c, 'X', 341, 716, 12)
    if d.get('date_signature'):
        txt(c, d['date_signature'], 177, 843)
    c.save()
    return merge(TEMPLATES['employer'], p, 2).getvalue()


def fill_travailleur_pdf(d):
    """Generate Travailleur PDF bytes (2 pages)"""
    p, c = newcan()
    # Page 1
    if d.get('contrat_email'):
        txt(c, 'X', 296, 135, 12)
    if d.get('contrat_fax'):
        txt(c, 'X', 364, 135, 12)
    if d.get('contrat_poste'):
        txt(c, 'X', 415, 134, 12)
    if d.get('contrat_main'):
        txt(c, 'X', 477, 136, 12)
    if d.get('nom_employeur'):
        txt(c, d['nom_employeur'], 384, 203)
    cv = d.get('civilite', '')
    if cv == 'Mr':
        txt(c, 'X', 141, 259, 12)
    elif cv == 'Mme':
        txt(c, 'X', 298, 260, 12)
    elif cv == 'Melle':
        txt(c, 'X', 459, 260, 12)
    if d.get('nom_prenom'):
        txt(c, d['nom_prenom'], 383, 286)
    if d.get('adresse_1'):
        txt(c, d['adresse_1'], 378, 313)
    if d.get('adresse_2'):
        txt(c, d['adresse_2'], 378, 340)
    if d.get('date_lieu_naissance'):
        txt(c, d['date_lieu_naissance'], 377, 366)
    if d.get('niss'):
        txt(c, d['niss'], 376, 392)
    if d.get('nationalite'):
        txt(c, d['nationalite'], 378, 421)
    if d.get('carte_identite'):
        txt(c, 'X', 133, 449, 12)
    if d.get('permis_travail'):
        txt(c, 'X', 133, 470, 12)
    if d.get('permis_date'):
        txt(c, d['permis_date'], 471, 466)
    et = d.get('etat_civil', '')
    if et == 'Marie':
        txt(c, 'X', 283, 532, 12)
    elif et == 'Veuf':
        txt(c, 'X', 475, 533, 12)
    elif et == 'Celibataire':
        txt(c, 'X', 283, 559, 12)
    elif et == 'Separe':
        txt(c, 'X', 476, 561, 12)
    elif et == 'Divorce':
        txt(c, 'X', 283, 586, 12)
    elif et == 'Cohabitation':
        txt(c, 'X', 473, 585, 12)
    if d.get('conjoint_charge'):
        txt(c, 'X', 90, 634, 12)
    if d.get('enfants_charge'):
        txt(c, 'X', 289, 635, 12)
    if d.get('autre_charge'):
        txt(c, 'X', 91, 655, 12)
    if d.get('nb_enfants'):
        txt(c, d['nb_enfants'], 604, 635)
    if d.get('nb_handicapes'):
        txt(c, d['nb_handicapes'], 604, 653)
    if d.get('date_entree'):
        txt(c, d['date_entree'], 223, 729)
    if d.get('date_sortie'):
        txt(c, d['date_sortie'], 515, 731)
    ct = d.get('categorie', '')
    if ct == 'Employe':
        txt(c, 'X', 260, 757, 12)
    elif ct == 'Ouvrier':
        txt(c, 'X', 347, 758, 12)
    elif ct == 'Chef':
        txt(c, 'X', 428, 757, 12)
    elif ct == 'Autre':
        txt(c, 'X', 562, 758, 12)
    if d.get('fonction'):
        txt(c, d['fonction'], 261, 791)
    tc = d.get('type_contrat', '')
    if tc == 'CDD':
        txt(c, 'X', 283, 826, 12)
    elif tc == 'CDI':
        txt(c, 'X', 283, 845, 12)
    elif tc == 'Etudiant':
        txt(c, 'X', 284, 870, 12)
    elif tc == 'Remplacement':
        txt(c, 'X', 474, 824, 12)
    elif tc == 'Nettement defini':
        txt(c, 'X', 475, 847, 12)
    rg = d.get('regime_horaire', '')
    if rg == 'Temps plein':
        txt(c, 'X', 257, 900, 12)
    elif rg == 'Temps partiel':
        txt(c, 'X', 384, 900, 12)
    
    # Page 2
    c.showPage()
    hr = d.get('horaire_type', '')
    if hr == 'Fixe':
        txt(c, 'X', 258, 99, 12)
    elif hr == 'Variable':
        txt(c, 'X', 385, 99, 12)
    if d.get('heures_semaine'):
        txt(c, d['heures_semaine'], 291, 127)
    sch = [('lundi', 202, 188, 276, 355, 418, 514, 584), ('mardi', 200, 205, 271, 360, 412, 512, 576), ('mercredi', 200, 223, 275, 362, 429, 512, 577), ('jeudi', 200, 241, 271, 356, 421, 513, 581), ('vendredi', 200, 258, 273, 357, 421, 513, 583), ('samedi', 208, 275, 276, 355, 419, 512, 579), ('dimanche', 207, 294, 270, 354, 424, 513, 582)]
    for day, x1, y, x2, x3, x4, x5, x6 in sch:
        if d.get(f'{day}_matin_de'):
            txt(c, d[f'{day}_matin_de'], x1, y, 9)
        if d.get(f'{day}_matin_a'):
            txt(c, d[f'{day}_matin_a'], x2, y, 9)
        if d.get(f'{day}_pause_de'):
            txt(c, d[f'{day}_pause_de'], x3, y, 9)
        if d.get(f'{day}_pause_a'):
            txt(c, d[f'{day}_pause_a'], x4, y, 9)
        if d.get(f'{day}_apres_de'):
            txt(c, d[f'{day}_apres_de'], x5, y, 9)
        if d.get(f'{day}_apres_a'):
            txt(c, d[f'{day}_apres_a'], x6, y, 9)
    if d.get('remuneration'):
        txt(c, d['remuneration'], 335, 319)
    if d.get('compte_bancaire'):
        txt(c, d['compte_bancaire'], 337, 347)
    if d.get('avantage_nourriture'):
        txt(c, 'X', 134, 401, 12)
    if d.get('avantage_vetements'):
        txt(c, 'X', 133, 431, 12)
    if d.get('avantage_voiture'):
        txt(c, 'X', 134, 455, 12)
    if d.get('avantage_gsm'):
        txt(c, 'X', 134, 484, 12)
    if d.get('avantage_autre'):
        txt(c, 'X', 134, 512, 12)
    if d.get('prime_nuit'):
        txt(c, 'X', 176, 547, 12)
    if d.get('prime_weekend'):
        txt(c, 'X', 240, 546, 12)
    if d.get('prime_froid'):
        txt(c, 'X', 345, 547, 12)
    if d.get('prime_autre'):
        txt(c, d['prime_autre'], 418, 547)
    if d.get('transport_train'):
        txt(c, 'X', 95, 601, 12)
    if d.get('transport_tram'):
        txt(c, 'X', 167, 602, 12)
    if d.get('transport_metro'):
        txt(c, 'X', 235, 602, 12)
    if d.get('transport_bus'):
        txt(c, 'X', 313, 602, 12)
    if d.get('transport_voiture'):
        txt(c, 'X', 374, 602, 12)
    if d.get('transport_pieds'):
        txt(c, 'X', 462, 601, 12)
    if d.get('transport_velo'):
        txt(c, 'X', 540, 600, 12)
    if d.get('km'):
        txt(c, d['km'], 331, 627)
    if d.get('chomage_depuis'):
        txt(c, d['chomage_depuis'], 375, 657)
    if d.get('c131'):
        txt(c, 'X', 135, 686, 12)
    if d.get('carte_activa'):
        txt(c, 'X', 136, 716, 12)
    if d.get('carte_recue'):
        txt(c, 'X', 312, 711, 12)
    if d.get('faire_demande'):
        txt(c, 'X', 291, 743, 12)
    if d.get('cpas_depuis'):
        txt(c, d['cpas_depuis'], 355, 768)
    if d.get('date_signature'):
        txt(c, d['date_signature'], 139, 813)
    c.save()
    return merge(TEMPLATES['travailleur'], p, 2).getvalue()


def fill_independant_pdf(d):
    """Generate Indépendant PDF bytes (1 page)"""
    p, c = newcan()
    if d.get('contrat_email'):
        txt(c, 'X', 296, 133, 12)
    if d.get('contrat_fax'):
        txt(c, 'X', 363, 133, 12)
    if d.get('contrat_poste'):
        txt(c, 'X', 414, 134, 12)
    if d.get('contrat_main'):
        txt(c, 'X', 476, 133, 12)
    cv = d.get('civilite', '')
    if cv == 'Mr':
        txt(c, 'X', 139, 203, 12)
    elif cv == 'Mme':
        txt(c, 'X', 300, 203, 12)
    elif cv == 'Melle':
        txt(c, 'X', 459, 203, 12)
    if d.get('nom_prenom'):
        txt(c, d['nom_prenom'], 395, 233)
    if d.get('adresse_1'):
        txt(c, d['adresse_1'], 392, 258)
    if d.get('adresse_2'):
        txt(c, d['adresse_2'], 388, 286)
    if d.get('date_lieu_naissance'):
        txt(c, d['date_lieu_naissance'], 392, 312)
    if d.get('niss'):
        txt(c, d['niss'], 391, 340)
    if d.get('nationalite'):
        txt(c, d['nationalite'], 386, 367)
    if d.get('carte_identite'):
        txt(c, 'X', 133, 396, 12)
    et = d.get('etat_civil', '')
    if et == 'Marie':
        txt(c, 'X', 283, 457, 12)
    elif et == 'Veuf':
        txt(c, 'X', 472, 458, 12)
    elif et == 'Celibataire':
        txt(c, 'X', 281, 484, 12)
    elif et == 'Separe':
        txt(c, 'X', 475, 483, 12)
    elif et == 'Divorce':
        txt(c, 'X', 283, 510, 12)
    elif et == 'Cohabitation':
        txt(c, 'X', 474, 511, 12)
    if d.get('conjoint_charge'):
        txt(c, 'X', 91, 559, 12)
    if d.get('enfants_charge'):
        txt(c, 'X', 288, 561, 12)
    if d.get('autre_charge'):
        txt(c, 'X', 91, 580, 12)
    if d.get('nb_enfants'):
        txt(c, d['nb_enfants'], 606, 559)
    if d.get('nb_handicapes'):
        txt(c, d['nb_handicapes'], 607, 579)
    if d.get('remuneration'):
        txt(c, d['remuneration'], 350, 639)
    if d.get('loi_sociale'):
        txt(c, 'X', 133, 683, 12)
    if d.get('loi_sociale_val'):
        txt(c, d['loi_sociale_val'], 322, 682)
    if d.get('cheques_repas'):
        txt(c, 'X', 133, 709, 12)
    if d.get('cheques_repas_val'):
        txt(c, d['cheques_repas_val'], 322, 709)
    if d.get('voiture'):
        txt(c, 'X', 133, 737, 12)
    if d.get('voiture_val'):
        txt(c, d['voiture_val'], 325, 736)
    if d.get('autre'):
        txt(c, 'X', 134, 765, 12)
    if d.get('autre_val'):
        txt(c, d['autre_val'], 325, 763)
    if d.get('date_signature'):
        txt(c, d['date_signature'], 139, 808)
    c.save()
    return merge(TEMPLATES['independant'], p, 1).getvalue()


def fill_att_accident_pdf(d, lang='fr'):
    """Generate Attestation Accident PDF bytes - FR or NL (1 page)"""
    p, c = newcan()
    tpl = TEMPLATES['att_accident_nl'] if lang == 'nl' else TEMPLATES['att_accident_fr']
    off = 12 if lang == 'nl' else 0
    
    if d.get('nom_soussigne'):
        txt(c, d['nom_soussigne'], 283, 130 + off)
    if d.get('niss'):
        txt(c, d['niss'], 283, 144 + off)
    if d.get('domicile_1'):
        txt(c, d['domicile_1'], 283, 159 + off)
    if d.get('domicile_2'):
        txt(c, d['domicile_2'], 282, 174 + off)
    if d.get('qualite'):
        txt(c, d['qualite'], 284, 204 + off)
    if d.get('societe'):
        txt(c, d['societe'], 284, 222 + off)
    if d.get('etablie_1'):
        txt(c, d['etablie_1'], 284, 235 + off)
    if d.get('etablie_2'):
        txt(c, d['etablie_2'], 283, 251 + off)
    if d.get('date_signature'):
        txt(c, d['date_signature'], 237, 443 + off)
    c.save()
    return merge(tpl, p, 1).getvalue()


def fill_att_seppt_pdf(d, lang='fr'):
    """Generate Attestation SEPPT PDF bytes - FR or NL (1 page)"""
    p, c = newcan()
    tpl = TEMPLATES['att_seppt_nl'] if lang == 'nl' else TEMPLATES['att_seppt_fr']
    off = 11 if lang == 'nl' else 0
    sig_y = 630 if lang == 'nl' else 548
    
    if d.get('nom_soussigne'):
        txt(c, d['nom_soussigne'], 313, 129 + off)
    if d.get('niss'):
        txt(c, d['niss'], 313, 145 + off)
    if d.get('domicile_1'):
        txt(c, d['domicile_1'], 310, 160 + off)
    if d.get('domicile_2'):
        txt(c, d['domicile_2'], 309, 173 + off)
    if d.get('qualite'):
        txt(c, d['qualite'], 311, 205 + off)
    if d.get('societe'):
        txt(c, d['societe'], 311, 220 + off)
    if d.get('etablie_1'):
        txt(c, d['etablie_1'], 311, 236 + off)
    if d.get('etablie_2'):
        txt(c, d['etablie_2'], 309, 252 + off)
    if d.get('date_signature'):
        txt(c, d['date_signature'], 252, sig_y)
    c.save()
    return merge(tpl, p, 1).getvalue()


def fill_offre_pdf(d, lang='fr'):
    """
    Generate Offre de Collaboration PDF bytes - FR or NL (20 pages, single document)
    
    Structure:
    - Page 1: Company info (fillable)
    - Pages 2-12: Terms and conditions (static)
    - Page 13: Conditions particulières (fillable)
    - Page 14: Procuration (fillable)
    - Page 15: Contrat de mandat (fillable)
    - Pages 16-20: Offre de prix (static)
    """
    tpl = TEMPLATES['offre_nl'] if lang == 'nl' else TEMPLATES['offre_fr']
    p, c = newcan()
    
    # Helper to get value with fallback
    def val(primary, fallback):
        return d.get(primary) or d.get(fallback)
    
    # === PAGE 1 - Company info ===
    if d.get('nom_societe'):
        txt(c, d['nom_societe'], 223, 470)
    if val('adresse_1', 'adresse_siege_social_1'):
        txt(c, val('adresse_1', 'adresse_siege_social_1'), 218, 496)
    if val('adresse_2', 'adresse_siege_social_2'):
        txt(c, val('adresse_2', 'adresse_siege_social_2'), 217, 526)
    if d.get('num_tva') or d.get('num_entreprise'):
        txt(c, d.get('num_tva') or d.get('num_entreprise'), 217, 551)
    if val('represente_par', 'nom_prenom_gerant'):
        txt(c, val('represente_par', 'nom_prenom_gerant'), 217, 577)
    
    # === PAGES 2-12 - Static content (no fields) ===
    for _ in range(11):
        c.showPage()
    
    # === PAGE 13 - Conditions particulières ===
    c.showPage()
    if d.get('nom_societe'):
        txt(c, d['nom_societe'], 210, 222)
    if val('adresse_1', 'adresse_siege_social_1'):
        txt(c, val('adresse_1', 'adresse_siege_social_1'), 207, 238)
    if val('adresse_2', 'adresse_siege_social_2'):
        txt(c, val('adresse_2', 'adresse_siege_social_2'), 202, 258)
    if d.get('num_tva') or d.get('num_entreprise'):
        txt(c, d.get('num_tva') or d.get('num_entreprise'), 202, 273)
    if val('represente_par', 'nom_prenom_gerant'):
        txt(c, val('represente_par', 'nom_prenom_gerant'), 199, 291)
    # Date d'entrée en vigueur
    if d.get('date_entree_jour'):
        txt(c, d['date_entree_jour'], 328, 585)
    if d.get('date_entree_mois'):
        txt(c, d['date_entree_mois'], 370, 585)
    if d.get('date_entree_annee'):
        txt(c, d['date_entree_annee'], 423, 587)
    # Date fait le
    if val('date_fait', 'date_signature'):
        txt(c, val('date_fait', 'date_signature'), 189, 640)
    
    # === PAGE 14 - Procuration ===
    c.showPage()
    if val('nom_soussigne', 'nom_prenom_gerant'):
        txt(c, val('nom_soussigne', 'nom_prenom_gerant'), 257, 183)
    if val('niss', 'niss_gerant'):
        txt(c, val('niss', 'niss_gerant'), 255, 200)
    if val('domicile_1', 'adresse_siege_social_1'):
        txt(c, val('domicile_1', 'adresse_siege_social_1'), 255, 214)
    if val('domicile_2', 'adresse_siege_social_2'):
        txt(c, val('domicile_2', 'adresse_siege_social_2'), 255, 228)
    if d.get('qualite'):
        txt(c, d['qualite'], 256, 246)
    if val('societe', 'nom_societe'):
        txt(c, val('societe', 'nom_societe'), 253, 263)
    if val('adresse_1', 'adresse_siege_social_1'):
        txt(c, val('adresse_1', 'adresse_siege_social_1'), 252, 280)
    if val('adresse_2', 'adresse_siege_social_2'):
        txt(c, val('adresse_2', 'adresse_siege_social_2'), 252, 295)
    if d.get('num_tva') or d.get('num_entreprise'):
        txt(c, d.get('num_tva') or d.get('num_entreprise'), 251, 311)
    if d.get('date_signature'):
        txt(c, d['date_signature'], 205, 801)
    
    # === PAGE 15 - Contrat de mandat ===
    c.showPage()
    if val('nom_soussigne', 'nom_prenom_gerant'):
        txt(c, val('nom_soussigne', 'nom_prenom_gerant'), 246, 185)
    if val('niss', 'niss_gerant'):
        txt(c, val('niss', 'niss_gerant'), 245, 200)
    if val('domicile_1', 'adresse_siege_social_1'):
        txt(c, val('domicile_1', 'adresse_siege_social_1'), 246, 216)
    if val('domicile_2', 'adresse_siege_social_2'):
        txt(c, val('domicile_2', 'adresse_siege_social_2'), 245, 234)
    if d.get('qualite'):
        txt(c, d['qualite'], 244, 249)
    if val('societe', 'nom_societe'):
        txt(c, val('societe', 'nom_societe'), 244, 265)
    if val('adresse_1', 'adresse_siege_social_1'):
        txt(c, val('adresse_1', 'adresse_siege_social_1'), 244, 282)
    if val('adresse_2', 'adresse_siege_social_2'):
        txt(c, val('adresse_2', 'adresse_siege_social_2'), 243, 297)
    if d.get('num_tva') or d.get('num_entreprise'):
        txt(c, d.get('num_tva') or d.get('num_entreprise'), 243, 312)
    if d.get('date_signature'):
        txt(c, d['date_signature'], 203, 782)
    
    # === PAGES 16-20 - Offre de prix (static) ===
    for _ in range(5):
        c.showPage()
    
    c.save()
    return merge(tpl, p, 20).getvalue()


def fill_procuration_pdf(d):
    """Generate Procuration PDF bytes (1 page)"""
    p, c = newcan()
    if d.get('num_entreprise'):
        txt(c, d['num_entreprise'], 215, 115)
    if d.get('denomination'):
        txt(c, d['denomination'], 184, 135)
    if d.get('rue'):
        txt(c, d['rue'], 119, 152)
    if d.get('numero'):
        txt(c, d['numero'], 440, 153)
    if d.get('boite'):
        txt(c, d['boite'], 571, 153)
    if d.get('code_postal'):
        txt(c, d['code_postal'], 145, 174)
    if d.get('commune'):
        txt(c, d['commune'], 286, 173)
    if d.get('pays'):
        txt(c, d['pays'], 482, 174)
    if d.get('num_onss'):
        txt(c, d['num_onss'], 476, 118)
    if d.get('num_affiliation_employeur'):
        txt(c, d['num_affiliation_employeur'], 274, 268)
    if d.get('trimestre_debut'):
        txt(c, d['trimestre_debut'], 202, 518)
    if d.get('trimestre_fin'):
        txt(c, d['trimestre_fin'], 462, 520)
    if d.get('date_signature'):
        txt(c, d['date_signature'], 186, 690)
    if d.get('niss_mandant'):
        txt(c, d['niss_mandant'], 241, 706)
    if d.get('nom_mandant'):
        txt(c, d['nom_mandant'], 171, 726)
    c.save()
    return merge(TEMPLATES['procuration'], p, 1).getvalue()


def fill_dispense_pdf(d):
    """Generate Dispense PDF bytes (2 pages)"""
    p, c = newcan()
    if d.get('nom_soussigne'):
        txt(c, d['nom_soussigne'], 334, 188)
    if d.get('qualite'):
        txt(c, d['qualite'], 255, 206)
    if d.get('societe'):
        txt(c, d['societe'], 463, 208)
    if d.get('num_entreprise'):
        txt(c, d['num_entreprise'], 514, 222)
    if d.get('depuis_date'):
        txt(c, d['depuis_date'], 187, 238)
    if d.get('checkbox_10pct'):
        txt(c, 'X', 91, 307, 12)
    c.showPage()
    if d.get('checkbox_20pct'):
        txt(c, 'X', 90, 312, 12)
    if d.get('etabli_lieu'):
        txt(c, d['etabli_lieu'], 176, 761)
    if d.get('etabli_date'):
        txt(c, d['etabli_date'], 329, 761)
    c.save()
    return merge(TEMPLATES['dispense'], p, 2).getvalue()


def fill_mensura_pdf(d):
    """Generate Mensura PDF bytes (4 pages)"""
    p, c = newcan()
    if d.get('nom_entreprise'):
        txt(c, d['nom_entreprise'], 144, 236)
    if d.get('siege_social_1'):
        txt(c, d['siege_social_1'], 148, 289)
    if d.get('siege_social_2'):
        txt(c, d['siege_social_2'], 147, 302)
    if d.get('siege_exploitation'):
        txt(c, d['siege_exploitation'], 167, 344)
    if d.get('telephone'):
        txt(c, d['telephone'], 189, 371)
    if d.get('gsm'):
        txt(c, d['gsm'], 439, 368)
    if d.get('email'):
        txt(c, d['email'], 184, 410)
    if d.get('tva_bce'):
        txt(c, d['tva_bce'], 210, 438)
    if d.get('num_onss'):
        txt(c, d['num_onss'], 476, 437)
    if d.get('compte_bancaire'):
        txt(c, d['compte_bancaire'], 233, 467)
    if d.get('code_nace'):
        txt(c, d['code_nace'], 342, 519)
    if d.get('nb_travailleurs'):
        txt(c, d['nb_travailleurs'], 617, 517)
    c.showPage()
    c.showPage()
    c.showPage()
    if d.get('date_cours'):
        txt(c, d['date_cours'], 322, 125)
    if d.get('fait_lieu'):
        txt(c, d['fait_lieu'], 181, 194)
    if d.get('fait_date'):
        txt(c, d['fait_date'], 326, 197)
    if d.get('nom_delegue'):
        txt(c, d['nom_delegue'], 143, 442)
    c.save()
    return merge(TEMPLATES['mensura'], p, 4).getvalue()


# ============== PDF GENERATION DISPATCHER ==============

def generate_pdf_bytes(doc_type, data, lang_prefs=None):
    """Generate PDF bytes for a document type with language support"""
    if lang_prefs is None:
        lang_prefs = {}
    
    # Bilingual documents
    if doc_type in ['accident', 'att_accident']:
        return fill_att_accident_pdf(data, lang_prefs.get('accident', 'fr'))
    
    if doc_type in ['seppt', 'att_seppt']:
        return fill_att_seppt_pdf(data, lang_prefs.get('seppt', 'fr'))
    
    if doc_type == 'offre':
        return fill_offre_pdf(data, lang_prefs.get('offre', 'fr'))
    
    # Standard documents
    generators = {
        'employer': fill_employer_pdf,
        'travailleur': fill_travailleur_pdf,
        'independant': fill_independant_pdf,
        'dispense': fill_dispense_pdf,
        'procuration': fill_procuration_pdf,
        'mensura': fill_mensura_pdf,
    }
    
    if doc_type in generators:
        return generators[doc_type](data)
    
    return None


# ============== ZIP DOWNLOAD ENDPOINT ==============

@app.route('/download-all-zip', methods=['POST'])
def download_all_zip():
    """
    Generate ZIP with all selected documents + associated static documents
    
    Request JSON:
    {
        "documents": ["employer", "offre", "seppt", ...],
        "form_data": { ... },
        "language_prefs": { "seppt": "nl", "accident": "fr", "offre": "fr" }
    }
    
    Response: ZIP file containing filled PDFs + static documents
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400
        
        documents = data.get('documents', [])
        form_data = data.get('form_data', {})
        language_prefs = data.get('language_prefs', {})
        
        if not documents:
            return jsonify({"error": "No documents selected"}), 400
        
        zip_buffer = io.BytesIO()
        static_docs_added = set()
        
        # Filename mapping
        FILENAMES = {
            'employer': 'Fiche_employeur.pdf',
            'travailleur': 'Fiche_travailleur.pdf',
            'independant': 'Fiche_independant.pdf',
            'dispense': 'Dispense_precompte.pdf',
            'procuration': 'Procuration_ONSS.pdf',
            'mensura': 'Contrat_Mensura.pdf',
        }
        
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            for doc_type in documents:
                try:
                    # Generate the filled PDF
                    pdf_bytes = generate_pdf_bytes(doc_type, form_data, language_prefs)
                    
                    if pdf_bytes:
                        # Determine filename
                        if doc_type == 'offre':
                            lang = language_prefs.get('offre', 'fr').upper()
                            filename = f"Offre_de_collaboration_{lang}.pdf"
                        elif doc_type in ['accident', 'att_accident']:
                            lang = language_prefs.get('accident', 'fr').upper()
                            filename = f"Attestation_accident_travail_{lang}.pdf"
                        elif doc_type in ['seppt', 'att_seppt']:
                            lang = language_prefs.get('seppt', 'fr').upper()
                            filename = f"Attestation_SEPPT_{lang}.pdf"
                        else:
                            filename = FILENAMES.get(doc_type, f"{doc_type}.pdf")
                        
                        zf.writestr(filename, pdf_bytes)
                        print(f"[ZIP] Added: {filename}")
                    
                    # Add associated static documents
                    bundle = get_bundle_for_document(doc_type)
                    for static_key in bundle:
                        if static_key not in static_docs_added:
                            static_bytes, display_name = get_static_document_bytes(static_key)
                            if static_bytes:
                                zf.writestr(display_name, static_bytes)
                                static_docs_added.add(static_key)
                                print(f"[ZIP] Added static: {display_name}")
                    
                except Exception as e:
                    print(f"Error processing {doc_type}: {str(e)}")
                    continue
        
        zip_buffer.seek(0)
        
        return send_file(
            zip_buffer,
            mimetype='application/zip',
            as_attachment=True,
            download_name=f'documents_persoproject_{datetime.now().strftime("%Y%m%d_%H%M%S")}.zip'
        )
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ============== MAIN ==============

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
