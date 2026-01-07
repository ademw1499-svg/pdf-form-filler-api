from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
import io
import os
import zipfile
from datetime import datetime

app = Flask(__name__)
CORS(app)

# Template paths
TEMPLATES = {
    'employer': 'FICHE_RENSEIGNEMENTS_EMPLOYEUR_FR_2020.pdf',
    'worker': 'FICHE_RENSEIGNEMENTS_TRAVAILLEUR_FR.pdf',
    'independent': 'FICHE_RENSEIGNEMENTS_INDEPENDANT.pdf',
    'seppt': 'ATTESTATION_SEPPT.pdf',
    'accident': 'ATTESTATION_ASSURANCE_ACCIDENT_DE_TRAVAIL.pdf',
    'dispense': 'Dispense_partielle_de_versement_du_pre_compte_professionnel.pdf',
    'procuration': 'PROCURATION.pdf',
    'mensura': 'FOR140106_FR.pdf',
    'obligations': 'Obligation_Employeur_2025.pdf'
}

# Scale factors for different form types
EMPLOYER_SCALE_X = 595 / 707  # Employer form (original working)
EMPLOYER_SCALE_Y = 842 / 1000

STANDARD_SCALE_X = 595 / 1241  # All other forms @ 150 DPI
STANDARD_SCALE_Y = 842 / 1754

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy", "timestamp": datetime.now().isoformat()})

# ============================================================================
# MAIN ENDPOINT - MULTI-DOCUMENT GENERATION
# ============================================================================

@app.route('/fill-multiple-forms', methods=['POST'])
def fill_multiple_forms():
    """Generate multiple PDFs and return as ZIP"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400
        
        selected_docs = data.get('selected_documents', [])
        if not selected_docs:
            return jsonify({"error": "No documents selected"}), 400
        
        # Create ZIP file in memory
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for doc_id in selected_docs:
                if doc_id == 'employer':
                    pdf_data = fill_employer_form_data(data)
                    zip_file.writestr('01_Fiche_Employeur.pdf', pdf_data.getvalue())
                elif doc_id == 'worker':
                    pdf_data = fill_worker_form_data(data)
                    zip_file.writestr('02_Fiche_Travailleur.pdf', pdf_data.getvalue())
                elif doc_id == 'independent':
                    pdf_data = fill_independent_form_data(data)
                    zip_file.writestr('03_Fiche_Independant.pdf', pdf_data.getvalue())
                elif doc_id == 'seppt':
                    pdf_data = fill_attestation_data(data, 'seppt')
                    zip_file.writestr('04_Attestation_SEPPT.pdf', pdf_data.getvalue())
                elif doc_id == 'accident':
                    pdf_data = fill_attestation_data(data, 'accident')
                    zip_file.writestr('05_Attestation_Accident.pdf', pdf_data.getvalue())
                elif doc_id == 'dispense':
                    pdf_data = fill_dispense_data(data)
                    zip_file.writestr('06_Dispense_Precompte.pdf', pdf_data.getvalue())
                elif doc_id == 'procuration':
                    pdf_data = fill_procuration_data(data)
                    zip_file.writestr('07_Procuration_ONSS.pdf', pdf_data.getvalue())
                elif doc_id == 'mensura':
                    pdf_data = fill_mensura_data(data)
                    zip_file.writestr('08_Contrat_Mensura.pdf', pdf_data.getvalue())
                elif doc_id == 'obligations':
                    pdf_data = fill_obligations_data(data)
                    zip_file.writestr('09_Obligations_Employeur.pdf', pdf_data.getvalue())
        
        zip_buffer.seek(0)
        return send_file(
            zip_buffer,
            mimetype='application/zip',
            as_attachment=True,
            download_name=f'Documents_PersoProject_{datetime.now().strftime("%Y%m%d_%H%M%S")}.zip'
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ============================================================================
# INDIVIDUAL ENDPOINTS
# ============================================================================

@app.route('/fill-employer-form', methods=['POST'])
def fill_employer_form():
    try:
        data = request.get_json()
        output_pdf = fill_employer_form_data(data)
        return send_file(output_pdf, mimetype='application/pdf', as_attachment=True,
                        download_name=f"Employer_{datetime.now().strftime('%Y%m%d')}.pdf")
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/fill-worker-form', methods=['POST'])
def fill_worker_form():
    try:
        data = request.get_json()
        output_pdf = fill_worker_form_data(data)
        return send_file(output_pdf, mimetype='application/pdf', as_attachment=True,
                        download_name=f"Worker_{datetime.now().strftime('%Y%m%d')}.pdf")
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ============================================================================
# PDF FILLING FUNCTIONS
# ============================================================================

def fill_employer_form_data(data):
    """Fill employer form - WORKING VERSION (keep exact same code)"""
    reader = PdfReader(TEMPLATES['employer'])
    packet = io.BytesIO()
    can = canvas.Canvas(packet, pagesize=(595, 842))
    
    SCALE_X = EMPLOYER_SCALE_X
    SCALE_Y = EMPLOYER_SCALE_Y
    ALIGN_X = 440
    
    def convert_coords(x_img, y_img):
        x_pdf = x_img * SCALE_X
        y_pdf = 842 - (y_img * SCALE_Y)
        return (x_pdf, y_pdf)
    
    def add_text(text, x_img, y_img, font_size=10):
        can.setFont("Helvetica", font_size)
        x_pdf, y_pdf = convert_coords(x_img, y_img)
        can.drawString(x_pdf, y_pdf, str(text))
    
    # PAGE 1 - COMPLETE with ALL fields from Day 1
    if data.get('recu_par'):
        add_text(data['recu_par'], 185, 197)
    
    forme = data.get('forme_juridique', '')
    if forme == 'SRL':
        add_text('X', 195, 235, 12)
    elif forme == 'SC':
        add_text('X', 240, 235, 12)
    elif forme == 'SA':
        add_text('X', 285, 235, 12)
    elif forme == 'ASBL':
        add_text('X', 345, 235, 12)
    elif forme == 'PERSONNE PHYSIQUE':
        add_text('X', 415, 235, 12)
    
    if data.get('nom_societe'):
        add_text(data['nom_societe'], 300, 275)
    if data.get('nom_prenom_gerant'):
        add_text(data['nom_prenom_gerant'], 335, 308)
    if data.get('niss_gerant'):
        add_text(data['niss_gerant'], 240, 340)
    if data.get('adresse_siege_social_1'):
        add_text(data['adresse_siege_social_1'], 325, 373)
    if data.get('adresse_siege_social_2'):
        add_text(data['adresse_siege_social_2'], 325, 390)
    
    # Adresse d'exploitation
    if data.get('adresse_exploitation_1'):
        add_text(data['adresse_exploitation_1'], 325, 423)
    if data.get('adresse_exploitation_2'):
        add_text(data['adresse_exploitation_2'], 325, 440)
    
    if data.get('telephone_gsm'):
        add_text(data['telephone_gsm'], 260, 505)
    if data.get('email'):
        add_text(data['email'], 245, 538)
    if data.get('num_entreprise'):
        add_text(data['num_entreprise'], 280, 571)
    if data.get('num_onss'):
        add_text(data['num_onss'], 240, 604)
    
    # Assurance loi
    if data.get('assurance_loi'):
        add_text(data['assurance_loi'], 360, 637)
    
    # SEPPT
    if data.get('seppt'):
        add_text(data['seppt'], 180, 670)
    
    # Secteur d'activité
    if data.get('secteur_activite'):
        add_text(data['secteur_activite'], 265, 703)
    
    # Réduction premier engagement
    reduction = data.get('reduction_premier', '')
    if reduction == 'Oui':
        add_text('X', 75, 768, 12)
    elif reduction == 'Non':
        add_text('X', 112, 768, 12)
    elif reduction == 'Enquete':
        add_text('X', 157, 768, 12)
    
    # Commission paritaire
    if data.get('commission_paritaire'):
        add_text(data['commission_paritaire'], 295, 803)
    
    # Indice ONSS
    if data.get('indice_onss'):
        add_text(data['indice_onss'], 220, 836)
    
    # Code Nace
    if data.get('code_nace'):
        add_text(data['code_nace'], 210, 869)
    
    # Salaire garanti
    salaire = data.get('salaire_garanti', '')
    if salaire == 'OUI':
        add_text('X', 640, 900, 12)
    elif salaire == 'NON':
        add_text('X', 677, 900, 12)
    
    can.showPage()
    
    # PAGE 2 - COMPLETE with ALL fields
    
    # Régime horaire
    if data.get('regime_horaire'):
        add_text(data['regime_horaire'], 255, 146)
    
    # Weekly schedule
    can.setFont("Helvetica", 9)
    
    # Monday
    if data.get('lundi_matin_de'):
        add_text(data['lundi_matin_de'], 200, 224, 9)
    if data.get('lundi_matin_a'):
        add_text(data['lundi_matin_a'], 255, 224, 9)
    if data.get('lundi_pause_de'):
        add_text(data['lundi_pause_de'], 372, 224, 9)
    if data.get('lundi_pause_a'):
        add_text(data['lundi_pause_a'], 427, 224, 9)
    if data.get('lundi_apres_de'):
        add_text(data['lundi_apres_de'], 572, 224, 9)
    if data.get('lundi_apres_a'):
        add_text(data['lundi_apres_a'], 627, 224, 9)
    
    # Tuesday
    if data.get('mardi_matin_de'):
        add_text(data['mardi_matin_de'], 200, 243, 9)
    if data.get('mardi_matin_a'):
        add_text(data['mardi_matin_a'], 255, 243, 9)
    if data.get('mardi_pause_de'):
        add_text(data['mardi_pause_de'], 372, 243, 9)
    if data.get('mardi_pause_a'):
        add_text(data['mardi_pause_a'], 427, 243, 9)
    if data.get('mardi_apres_de'):
        add_text(data['mardi_apres_de'], 572, 243, 9)
    if data.get('mardi_apres_a'):
        add_text(data['mardi_apres_a'], 627, 243, 9)
    
    # Wednesday
    if data.get('mercredi_matin_de'):
        add_text(data['mercredi_matin_de'], 200, 262, 9)
    if data.get('mercredi_matin_a'):
        add_text(data['mercredi_matin_a'], 255, 262, 9)
    if data.get('mercredi_pause_de'):
        add_text(data['mercredi_pause_de'], 372, 262, 9)
    if data.get('mercredi_pause_a'):
        add_text(data['mercredi_pause_a'], 427, 262, 9)
    if data.get('mercredi_apres_de'):
        add_text(data['mercredi_apres_de'], 572, 262, 9)
    if data.get('mercredi_apres_a'):
        add_text(data['mercredi_apres_a'], 627, 262, 9)
    
    # Thursday
    if data.get('jeudi_matin_de'):
        add_text(data['jeudi_matin_de'], 200, 281, 9)
    if data.get('jeudi_matin_a'):
        add_text(data['jeudi_matin_a'], 255, 281, 9)
    if data.get('jeudi_pause_de'):
        add_text(data['jeudi_pause_de'], 372, 281, 9)
    if data.get('jeudi_pause_a'):
        add_text(data['jeudi_pause_a'], 427, 281, 9)
    if data.get('jeudi_apres_de'):
        add_text(data['jeudi_apres_de'], 572, 281, 9)
    if data.get('jeudi_apres_a'):
        add_text(data['jeudi_apres_a'], 627, 281, 9)
    
    # Friday
    if data.get('vendredi_matin_de'):
        add_text(data['vendredi_matin_de'], 200, 300, 9)
    if data.get('vendredi_matin_a'):
        add_text(data['vendredi_matin_a'], 255, 300, 9)
    if data.get('vendredi_pause_de'):
        add_text(data['vendredi_pause_de'], 372, 300, 9)
    if data.get('vendredi_pause_a'):
        add_text(data['vendredi_pause_a'], 427, 300, 9)
    if data.get('vendredi_apres_de'):
        add_text(data['vendredi_apres_de'], 572, 300, 9)
    if data.get('vendredi_apres_a'):
        add_text(data['vendredi_apres_a'], 627, 300, 9)
    
    # Saturday
    if data.get('samedi_matin_de'):
        add_text(data['samedi_matin_de'], 200, 319, 9)
    if data.get('samedi_matin_a'):
        add_text(data['samedi_matin_a'], 255, 319, 9)
    if data.get('samedi_pause_de'):
        add_text(data['samedi_pause_de'], 372, 319, 9)
    if data.get('samedi_pause_a'):
        add_text(data['samedi_pause_a'], 427, 319, 9)
    if data.get('samedi_apres_de'):
        add_text(data['samedi_apres_de'], 572, 319, 9)
    if data.get('samedi_apres_a'):
        add_text(data['samedi_apres_a'], 627, 319, 9)
    
    # Sunday
    if data.get('dimanche_matin_de'):
        add_text(data['dimanche_matin_de'], 200, 338, 9)
    if data.get('dimanche_matin_a'):
        add_text(data['dimanche_matin_a'], 255, 338, 9)
    if data.get('dimanche_pause_de'):
        add_text(data['dimanche_pause_de'], 372, 338, 9)
    if data.get('dimanche_pause_a'):
        add_text(data['dimanche_pause_a'], 427, 338, 9)
    if data.get('dimanche_apres_de'):
        add_text(data['dimanche_apres_de'], 572, 338, 9)
    if data.get('dimanche_apres_a'):
        add_text(data['dimanche_apres_a'], 627, 338, 9)
    
    can.setFont("Helvetica", 10)
    
    # Caméras
    if data.get('cameras'):
        add_text(data['cameras'], 430, 365)
    
    # Trousse de secours
    if data.get('trousse_secours'):
        add_text(data['trousse_secours'], 410, 415)
    
    # Vêtements fourniture
    vetements_fourniture = data.get('vetements_fourniture', '')
    if vetements_fourniture == 'Oui':
        add_text('X', 442, 448, 12)
    elif vetements_fourniture == 'Non':
        add_text('X', 479, 448, 12)
    
    # Vêtements entretien
    vetements_entretien = data.get('vetements_entretien', '')
    if vetements_entretien == 'Oui':
        add_text('X', 442, 481, 12)
    elif vetements_entretien == 'Non':
        add_text('X', 479, 481, 12)
    
    # Primes
    if data.get('primes'):
        add_text(data['primes'], 380, 514)
    
    # Secrétariat actuel
    if data.get('secretariat_actuel'):
        add_text(data['secretariat_actuel'], 310, 547)
    
    # Nom comptable
    if data.get('nom_comptable'):
        add_text(data['nom_comptable'], 265, 580)
    
    # Coordonnées comptable
    if data.get('coord_comptable'):
        add_text(data['coord_comptable'], 330, 613)
    
    # Origine
    origine = data.get('origine', '')
    if origine == 'Internet':
        add_text('X', 145, 662, 12)
    elif origine == 'Comptable':
        add_text('X', 341, 662, 12)
    elif origine == 'Client':
        add_text('X', 145, 696, 12)
    elif origine == 'Autre':
        add_text('X', 341, 696, 12)
    
    # Date signature
    if data.get('date_signature'):
        add_text(data['date_signature'], 160, 846)
    
    can.save()
    
    packet.seek(0)
    overlay = PdfReader(packet)
    writer = PdfWriter()
    
    for i, page in enumerate(reader.pages):
        if i < len(overlay.pages):
            page.merge_page(overlay.pages[i])
        writer.add_page(page)
    
    output = io.BytesIO()
    writer.write(output)
    output.seek(0)
    return output

def fill_worker_form_data(data):
    """Fill worker form with proper coordinates"""
    reader = PdfReader(TEMPLATES['worker'])
    packet = io.BytesIO()
    can = canvas.Canvas(packet, pagesize=(595, 842))
    
    SCALE_X = STANDARD_SCALE_X
    SCALE_Y = STANDARD_SCALE_Y
    
    def convert_coords(x_img, y_img):
        x_pdf = x_img * SCALE_X
        y_pdf = 842 - (y_img * SCALE_Y)
        return (x_pdf, y_pdf)
    
    def add_text(text, x_img, y_img, font_size=10):
        can.setFont("Helvetica", font_size)
        x_pdf, y_pdf = convert_coords(x_img, y_img)
        can.drawString(x_pdf, y_pdf, str(text))
    
    def add_checkbox(x_img, y_img):
        add_text('X', x_img, y_img, 12)
    
    # Page 1
    if data.get('nom_employeur'):
        add_text(data['nom_employeur'], 440, 264)
    
    # Civilité
    civilite = data.get('civilite', '')
    if civilite == 'Mr':
        add_checkbox(175, 335)
    elif civilite == 'Mme':
        add_checkbox(365, 335)
    elif civilite == 'Melle':
        add_checkbox(595, 335)
    
    if data.get('nom_prenom_travailleur'):
        add_text(data['nom_prenom_travailleur'], 440, 375)
    if data.get('adresse_travailleur_1'):
        add_text(data['adresse_travailleur_1'], 440, 410)
    if data.get('adresse_travailleur_2'):
        add_text(data['adresse_travailleur_2'], 440, 430)
    if data.get('date_naissance'):
        add_text(data['date_naissance'], 440, 480)
    if data.get('niss_travailleur'):
        add_text(data['niss_travailleur'], 440, 515)
    if data.get('nationalite'):
        add_text(data['nationalite'], 440, 550)
    
    # Etat civil
    etat = data.get('etat_civil', '')
    if etat == 'Marié(e)':
        add_checkbox(365, 670)
    elif etat == 'Célibataire':
        add_checkbox(365, 700)
    elif etat == 'Divorcé(e)':
        add_checkbox(365, 730)
    elif etat == 'Veuf/veuve':
        add_checkbox(620, 670)
    elif etat == 'Séparé(e)':
        add_checkbox(620, 700)
    elif etat == 'Cohabitation légale':
        add_checkbox(620, 730)
    
    # Dependents
    if data.get('nombre_enfants'):
        add_text(data['nombre_enfants'], 770, 785)
    if data.get('nombre_enfants_handicapes'):
        add_text(data['nombre_enfants_handicapes'], 770, 805)
    
    # Contract details
    if data.get('date_entree'):
        add_text(data['date_entree'], 320, 875)
    if data.get('date_sortie'):
        add_text(data['date_sortie'], 670, 875)
    
    # Category
    cat = data.get('categorie_professionnelle', '')
    if cat == 'Employé':
        add_checkbox(365, 915)
    elif cat == 'Ouvrier':
        add_checkbox(480, 915)
    elif cat == 'Chef d\'entreprise':
        add_checkbox(620, 915)
    elif cat == 'Autre':
        add_checkbox(760, 915)
    
    if data.get('fonction'):
        add_text(data['fonction'], 440, 955)
    
    # Contract type
    contrat_type = data.get('type_contrat', '')
    if contrat_type == 'C.D.D.':
        add_checkbox(365, 995)
    elif contrat_type == 'C.D.I.':
        add_checkbox(365, 1020)
    elif contrat_type == 'Etudiant':
        add_checkbox(365, 1045)
    elif contrat_type == 'Remplacement':
        add_checkbox(620, 995)
    elif contrat_type == 'Nettement défini':
        add_checkbox(620, 1020)
    
    # Work schedule
    regime = data.get('regime_horaire', '')
    if regime == 'Temps plein':
        add_checkbox(300, 1090)
    elif regime == 'Temps partiel':
        add_checkbox(530, 1090)
    
    # Start page 2 for additional fields
    can.showPage()
    
    # Page 2
    horaire = data.get('horaire_type', '')
    if horaire == 'Fixe':
        add_checkbox(290, 100)
    elif horaire == 'Variable':
        add_checkbox(480, 100)
    
    if data.get('heures_semaine'):
        add_text(data['heures_semaine'], 430, 135)
    
    if data.get('remuneration'):
        add_text(data['remuneration'], 440, 720)
    if data.get('compte_bancaire'):
        add_text(data['compte_bancaire'], 440, 760)
    
    # Signatures
    if data.get('date_signature'):
        add_text(data['date_signature'], 250, 1280)
    
    can.save()
    
    # Merge overlay with template
    packet.seek(0)
    overlay = PdfReader(packet)
    writer = PdfWriter()
    
    for i, page in enumerate(reader.pages):
        if i < len(overlay.pages):
            page.merge_page(overlay.pages[i])
        writer.add_page(page)
    
    output = io.BytesIO()
    writer.write(output)
    output.seek(0)
    return output

def fill_independent_form_data(data):
    """Fill independent form - similar to worker"""
    reader = PdfReader(TEMPLATES['independent'])
    packet = io.BytesIO()
    can = canvas.Canvas(packet, pagesize=(595, 842))
    
    SCALE_X = STANDARD_SCALE_X
    SCALE_Y = STANDARD_SCALE_Y
    
    def convert_coords(x_img, y_img):
        x_pdf = x_img * SCALE_X
        y_pdf = 842 - (y_img * SCALE_Y)
        return (x_pdf, y_pdf)
    
    def add_text(text, x_img, y_img, font_size=10):
        can.setFont("Helvetica", font_size)
        x_pdf, y_pdf = convert_coords(x_img, y_img)
        can.drawString(x_pdf, y_pdf, str(text))
    
    def add_checkbox(x_img, y_img):
        add_text('X', x_img, y_img, 12)
    
    # Civilité
    civilite = data.get('civilite', '')
    if civilite == 'Mr':
        add_checkbox(175, 250)
    elif civilite == 'Mme':
        add_checkbox(365, 250)
    elif civilite == 'Melle':
        add_checkbox(595, 250)
    
    if data.get('nom_prenom_travailleur'):
        add_text(data['nom_prenom_travailleur'], 440, 285)
    if data.get('adresse_travailleur_1'):
        add_text(data['adresse_travailleur_1'], 440, 320)
    if data.get('date_naissance'):
        add_text(data['date_naissance'], 440, 385)
    if data.get('niss_travailleur'):
        add_text(data['niss_travailleur'], 440, 420)
    if data.get('nationalite'):
        add_text(data['nationalite'], 440, 455)
    
    if data.get('remuneration'):
        add_text(data['remuneration'], 440, 765)
    
    if data.get('date_signature'):
        add_text(data['date_signature'], 250, 970)
    
    can.save()
    packet.seek(0)
    overlay = PdfReader(packet)
    writer = PdfWriter()
    
    page = reader.pages[0]
    page.merge_page(overlay.pages[0])
    writer.add_page(page)
    
    output = io.BytesIO()
    writer.write(output)
    output.seek(0)
    return output

def fill_attestation_data(data, attestation_type):
    """Fill SEPPT or Accident attestation (identical layout)"""
    template = TEMPLATES[attestation_type]
    reader = PdfReader(template)
    packet = io.BytesIO()
    can = canvas.Canvas(packet, pagesize=(595, 842))
    
    SCALE_X = STANDARD_SCALE_X
    SCALE_Y = STANDARD_SCALE_Y
    
    def convert_coords(x_img, y_img):
        x_pdf = x_img * SCALE_X
        y_pdf = 842 - (y_img * SCALE_Y)
        return (x_pdf, y_pdf)
    
    def add_text(text, x_img, y_img, font_size=10):
        can.setFont("Helvetica", font_size)
        x_pdf, y_pdf = convert_coords(x_img, y_img)
        can.drawString(x_pdf, y_pdf, str(text))
    
    if data.get('nom_prenom_gerant'):
        add_text(data['nom_prenom_gerant'], 440, 150)
    if data.get('niss_gerant'):
        add_text(data['niss_gerant'], 440, 180)
    if data.get('adresse_siege_social_1'):
        add_text(data['adresse_siege_social_1'], 440, 215)
    if data.get('adresse_siege_social_2'):
        add_text(data['adresse_siege_social_2'], 440, 235)
    if data.get('qualite_representant'):
        add_text(data['qualite_representant'], 440, 270)
    if data.get('nom_societe'):
        add_text(data['nom_societe'], 440, 305)
    
    if data.get('lieu_signature'):
        add_text(data['lieu_signature'], 390, 800)
    if data.get('date_signature'):
        add_text(data['date_signature'], 520, 800)
    
    can.save()
    packet.seek(0)
    overlay = PdfReader(packet)
    writer = PdfWriter()
    
    page = reader.pages[0]
    page.merge_page(overlay.pages[0])
    writer.add_page(page)
    
    output = io.BytesIO()
    writer.write(output)
    output.seek(0)
    return output

def fill_dispense_data(data):
    """Fill dispense précompte form"""
    reader = PdfReader(TEMPLATES['dispense'])
    packet = io.BytesIO()
    can = canvas.Canvas(packet, pagesize=(595, 842))
    
    SCALE_X = STANDARD_SCALE_X
    SCALE_Y = STANDARD_SCALE_Y
    
    def convert_coords(x_img, y_img):
        x_pdf = x_img * SCALE_X
        y_pdf = 842 - (y_img * SCALE_Y)
        return (x_pdf, y_pdf)
    
    def add_text(text, x_img, y_img, font_size=10):
        can.setFont("Helvetica", font_size)
        x_pdf, y_pdf = convert_coords(x_img, y_img)
        can.drawString(x_pdf, y_pdf, str(text))
    
    # Page 1
    if data.get('nom_prenom_gerant'):
        add_text(data['nom_prenom_gerant'], 440, 145)
    if data.get('nom_societe'):
        add_text(data['nom_societe'], 440, 185)
    if data.get('num_entreprise'):
        add_text(data['num_entreprise'], 440, 210)
    
    # Page 2 - signature
    can.showPage()
    if data.get('lieu_signature'):
        add_text(data['lieu_signature'], 300, 680)
    if data.get('date_signature'):
        add_text(data['date_signature'], 460, 680)
    
    can.save()
    packet.seek(0)
    overlay = PdfReader(packet)
    writer = PdfWriter()
    
    for i, page in enumerate(reader.pages):
        if i < len(overlay.pages):
            page.merge_page(overlay.pages[i])
        writer.add_page(page)
    
    output = io.BytesIO()
    writer.write(output)
    output.seek(0)
    return output

def fill_procuration_data(data):
    """Fill ONSS procuration"""
    reader = PdfReader(TEMPLATES['procuration'])
    packet = io.BytesIO()
    can = canvas.Canvas(packet, pagesize=(595, 842))
    
    SCALE_X = STANDARD_SCALE_X
    SCALE_Y = STANDARD_SCALE_Y
    
    def convert_coords(x_img, y_img):
        x_pdf = x_img * SCALE_X
        y_pdf = 842 - (y_img * SCALE_Y)
        return (x_pdf, y_pdf)
    
    def add_text(text, x_img, y_img, font_size=10):
        can.setFont("Helvetica", font_size)
        x_pdf, y_pdf = convert_coords(x_img, y_img)
        can.drawString(x_pdf, y_pdf, str(text))
    
    if data.get('num_entreprise'):
        add_text(data['num_entreprise'], 440, 260)
    if data.get('nom_societe'):
        add_text(data['nom_societe'], 440, 280)
    if data.get('adresse_siege_social_1'):
        parts = data['adresse_siege_social_1'].rsplit(',', 1)
        if len(parts) == 2:
            add_text(parts[0].strip(), 440, 320)  # Rue
        else:
            add_text(data['adresse_siege_social_1'], 440, 320)
    if data.get('num_onss'):
        add_text(data['num_onss'], 440, 385)
    
    # Prestataire (always PERSOPROJECT)
    add_text('0479.995.689', 440, 485)
    add_text('PERSOPROJECT', 440, 560)
    
    if data.get('date_signature'):
        add_text(data['date_signature'], 300, 920)
    if data.get('nom_prenom_gerant'):
        add_text(data['nom_prenom_gerant'], 440, 980)
    
    can.save()
    packet.seek(0)
    overlay = PdfReader(packet)
    writer = PdfWriter()
    
    page = reader.pages[0]
    page.merge_page(overlay.pages[0])
    writer.add_page(page)
    
    output = io.BytesIO()
    writer.write(output)
    output.seek(0)
    return output

def fill_mensura_data(data):
    """Fill Mensura contract"""
    reader = PdfReader(TEMPLATES['mensura'])
    packet = io.BytesIO()
    can = canvas.Canvas(packet, pagesize=(595, 842))
    
    SCALE_X = STANDARD_SCALE_X
    SCALE_Y = STANDARD_SCALE_Y
    
    def convert_coords(x_img, y_img):
        x_pdf = x_img * SCALE_X
        y_pdf = 842 - (y_img * SCALE_Y)
        return (x_pdf, y_pdf)
    
    def add_text(text, x_img, y_img, font_size=10):
        can.setFont("Helvetica", font_size)
        x_pdf, y_pdf = convert_coords(x_img, y_img)
        can.drawString(x_pdf, y_pdf, str(text))
    
    # Page 1
    if data.get('nom_societe'):
        add_text(data['nom_societe'], 440, 270)
    if data.get('adresse_siege_social_1'):
        add_text(data['adresse_siege_social_1'], 440, 320)
    if data.get('telephone_gsm'):
        add_text(data['telephone_gsm'], 440, 450)
    if data.get('email'):
        add_text(data['email'], 440, 485)
    if data.get('num_entreprise'):
        add_text(data['num_entreprise'], 440, 520)
    if data.get('num_onss'):
        add_text(data['num_onss'], 615, 520)
    
    # Jump to page 4 for signature
    can.showPage()
    can.showPage()
    can.showPage()
    
    if data.get('date_signature'):
        add_text(data['date_signature'], 400, 620)
    if data.get('nom_prenom_gerant'):
        add_text(data['nom_prenom_gerant'], 400, 670)
    
    can.save()
    packet.seek(0)
    overlay = PdfReader(packet)
    writer = PdfWriter()
    
    for i, page in enumerate(reader.pages):
        if i < len(overlay.pages):
            page.merge_page(overlay.pages[i])
        writer.add_page(page)
    
    output = io.BytesIO()
    writer.write(output)
    output.seek(0)
    return output

def fill_obligations_data(data):
    """Fill obligations letter - mostly static"""
    reader = PdfReader(TEMPLATES['obligations'])
    packet = io.BytesIO()
    can = canvas.Canvas(packet, pagesize=(595, 842))
    
    SCALE_X = STANDARD_SCALE_X
    SCALE_Y = STANDARD_SCALE_Y
    
    def convert_coords(x_img, y_img):
        x_pdf = x_img * SCALE_X
        y_pdf = 842 - (y_img * SCALE_Y)
        return (x_pdf, y_pdf)
    
    def add_text(text, x_img, y_img, font_size=10):
        can.setFont("Helvetica", font_size)
        x_pdf, y_pdf = convert_coords(x_img, y_img)
        can.drawString(x_pdf, y_pdf, str(text))
    
    # Jump to last page for signature
    for _ in range(len(reader.pages) - 1):
        can.showPage()
    
    if data.get('date_signature'):
        add_text(data['date_signature'], 250, 720)
    
    can.save()
    packet.seek(0)
    overlay = PdfReader(packet)
    writer = PdfWriter()
    
    for i, page in enumerate(reader.pages):
        if i < len(overlay.pages):
            page.merge_page(overlay.pages[i])
        writer.add_page(page)
    
    output = io.BytesIO()
    writer.write(output)
    output.seek(0)
    return output

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
