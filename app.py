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

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy", "timestamp": datetime.now().isoformat()})

# ============================================================================
# MULTI-DOCUMENT GENERATION (Main endpoint)
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
                    zip_file.writestr('Fiche_Employeur.pdf', pdf_data.getvalue())
                elif doc_id == 'worker':
                    pdf_data = fill_worker_form_data(data)
                    zip_file.writestr('Fiche_Travailleur.pdf', pdf_data.getvalue())
                elif doc_id == 'independent':
                    pdf_data = fill_independent_form_data(data)
                    zip_file.writestr('Fiche_Independant.pdf', pdf_data.getvalue())
                elif doc_id == 'seppt':
                    pdf_data = fill_attestation_data(data, 'seppt')
                    zip_file.writestr('Attestation_SEPPT.pdf', pdf_data.getvalue())
                elif doc_id == 'accident':
                    pdf_data = fill_attestation_data(data, 'accident')
                    zip_file.writestr('Attestation_Accident.pdf', pdf_data.getvalue())
                elif doc_id == 'dispense':
                    pdf_data = fill_dispense_data(data)
                    zip_file.writestr('Dispense_Precompte.pdf', pdf_data.getvalue())
                elif doc_id == 'procuration':
                    pdf_data = fill_procuration_data(data)
                    zip_file.writestr('Procuration_ONSS.pdf', pdf_data.getvalue())
                elif doc_id == 'mensura':
                    pdf_data = fill_mensura_data(data)
                    zip_file.writestr('Contrat_Mensura.pdf', pdf_data.getvalue())
                elif doc_id == 'obligations':
                    pdf_data = fill_obligations_data(data)
                    zip_file.writestr('Obligations_Employeur.pdf', pdf_data.getvalue())
        
        zip_buffer.seek(0)
        return send_file(
            zip_buffer,
            mimetype='application/zip',
            as_attachment=True,
            download_name=f'documents_persoproject_{datetime.now().strftime("%Y%m%d_%H%M%S")}.zip'
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ============================================================================
# INDIVIDUAL ENDPOINTS (for testing/single document generation)
# ============================================================================

@app.route('/fill-employer-form', methods=['POST'])
def fill_employer_form():
    try:
        data = request.get_json()
        output_pdf = fill_employer_form_data(data)
        return send_file(output_pdf, mimetype='application/pdf', as_attachment=True,
                        download_name=f"employer_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf")
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/fill-worker-form', methods=['POST'])
def fill_worker_form():
    try:
        data = request.get_json()
        output_pdf = fill_worker_form_data(data)
        return send_file(output_pdf, mimetype='application/pdf', as_attachment=True,
                        download_name=f"worker_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf")
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ============================================================================
# PDF FILLING FUNCTIONS
# ============================================================================

def fill_employer_form_data(data):
    """Fill employer form (ALREADY WORKING - keeping exact same code)"""
    reader = PdfReader(TEMPLATES['employer'])
    packet = io.BytesIO()
    can = canvas.Canvas(packet, pagesize=(595, 842))
    
    SCALE_X = 595 / 707
    SCALE_Y = 842 / 1000
    ALIGN_X = 440
    
    def convert_coords(x_img, y_img):
        x_pdf = x_img * SCALE_X
        y_pdf = 842 - (y_img * SCALE_Y)
        return (x_pdf, y_pdf)
    
    def add_text(text, x_img, y_img, font_size=10):
        can.setFont("Helvetica", font_size)
        x_pdf, y_pdf = convert_coords(x_img, y_img)
        can.drawString(x_pdf, y_pdf, str(text))
    
    # Page 1 fields
    if data.get('recu_par'):
        add_text(data['recu_par'], ALIGN_X, 197)
    
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
        add_text(data['nom_societe'], ALIGN_X, 275)
    if data.get('nom_prenom_gerant'):
        add_text(data['nom_prenom_gerant'], ALIGN_X, 308)
    if data.get('niss_gerant'):
        add_text(data['niss_gerant'], ALIGN_X, 340)
    if data.get('adresse_siege_social_1'):
        add_text(data['adresse_siege_social_1'], ALIGN_X, 373)
    if data.get('adresse_siege_social_2'):
        add_text(data['adresse_siege_social_2'], ALIGN_X, 390)
    if data.get('telephone_gsm'):
        add_text(data['telephone_gsm'], ALIGN_X, 505)
    if data.get('email'):
        add_text(data['email'], ALIGN_X, 538)
    if data.get('num_entreprise'):
        add_text(data['num_entreprise'], ALIGN_X, 571)
    if data.get('num_onss'):
        add_text(data['num_onss'], ALIGN_X, 604)
    if data.get('date_signature'):
        add_text(data['date_signature'], 160, 846)
    
    can.showPage()
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
    """Fill worker form"""
    reader = PdfReader(TEMPLATES['worker'])
    packet = io.BytesIO()
    can = canvas.Canvas(packet, pagesize=A4)
    
    def add_text(text, x, y, font_size=10):
        can.setFont("Helvetica", font_size)
        can.drawString(x, 842 - y, str(text))
    
    # Worker form fields (simplified positioning)
    if data.get('nom_employeur'):
        add_text(data['nom_employeur'], 250, 80)
    if data.get('civilite'):
        if data['civilite'] == 'Mr':
            add_text('X', 80, 130, 12)
        elif data['civilite'] == 'Mme':
            add_text('X', 150, 130, 12)
        elif data['civilite'] == 'Melle':
            add_text('X', 220, 130, 12)
    if data.get('nom_prenom_travailleur'):
        add_text(data['nom_prenom_travailleur'], 250, 160)
    if data.get('niss_travailleur'):
        add_text(data['niss_travailleur'], 250, 240)
    if data.get('date_naissance'):
        add_text(data['date_naissance'], 250, 210)
    if data.get('nationalite'):
        add_text(data['nationalite'], 250, 270)
    if data.get('date_signature'):
        add_text(data['date_signature'], 100, 800)
    
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

def fill_independent_form_data(data):
    """Fill independent form - similar structure to worker"""
    reader = PdfReader(TEMPLATES['independent'])
    packet = io.BytesIO()
    can = canvas.Canvas(packet, pagesize=A4)
    
    def add_text(text, x, y, font_size=10):
        can.setFont("Helvetica", font_size)
        can.drawString(x, 842 - y, str(text))
    
    if data.get('civilite'):
        if data['civilite'] == 'Mr':
            add_text('X', 80, 130, 12)
    if data.get('nom_prenom_travailleur'):
        add_text(data['nom_prenom_travailleur'], 250, 160)
    if data.get('niss_travailleur'):
        add_text(data['niss_travailleur'], 250, 240)
    if data.get('date_signature'):
        add_text(data['date_signature'], 100, 800)
    
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
    """Fill SEPPT or Accident attestation (same structure)"""
    template = TEMPLATES[attestation_type]
    reader = PdfReader(template)
    packet = io.BytesIO()
    can = canvas.Canvas(packet, pagesize=A4)
    
    def add_text(text, x, y, font_size=10):
        can.setFont("Helvetica", font_size)
        can.drawString(x, 842 - y, str(text))
    
    # Attestation fields
    if data.get('nom_prenom_gerant'):
        add_text(data['nom_prenom_gerant'], 200, 150)
    if data.get('niss_gerant'):
        add_text(data['niss_gerant'], 200, 180)
    if data.get('adresse_siege_social_1'):
        add_text(data['adresse_siege_social_1'], 200, 210)
    if data.get('nom_societe'):
        add_text(data['nom_societe'], 200, 300)
    if data.get('date_attestation'):
        add_text(data['date_attestation'], 400, 750)
    
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
    can = canvas.Canvas(packet, pagesize=A4)
    
    def add_text(text, x, y, font_size=10):
        can.setFont("Helvetica", font_size)
        can.drawString(x, 842 - y, str(text))
    
    if data.get('nom_prenom_gerant'):
        add_text(data['nom_prenom_gerant'], 200, 120)
    if data.get('nom_societe'):
        add_text(data['nom_societe'], 300, 150)
    if data.get('num_entreprise'):
        add_text(data['num_entreprise'], 350, 180)
    if data.get('date_signature'):
        add_text(data['date_signature'], 300, 800)
    
    can.save()
    packet.seek(0)
    overlay = PdfReader(packet)
    writer = PdfWriter()
    
    for i, page in enumerate(reader.pages):
        if i == 0 and len(overlay.pages) > 0:
            page.merge_page(overlay.pages[0])
        writer.add_page(page)
    
    output = io.BytesIO()
    writer.write(output)
    output.seek(0)
    return output

def fill_procuration_data(data):
    """Fill ONSS procuration"""
    reader = PdfReader(TEMPLATES['procuration'])
    packet = io.BytesIO()
    can = canvas.Canvas(packet, pagesize=A4)
    
    def add_text(text, x, y, font_size=10):
        can.setFont("Helvetica", font_size)
        can.drawString(x, 842 - y, str(text))
    
    if data.get('num_entreprise'):
        add_text(data['num_entreprise'], 250, 180)
    if data.get('nom_societe'):
        add_text(data['nom_societe'], 250, 200)
    if data.get('num_onss'):
        add_text(data['num_onss'], 350, 220)
    # Prestataire is always PERSOPROJECT
    add_text('0479.995.689', 250, 300)
    add_text('PERSOPROJECT', 250, 320)
    if data.get('date_signature'):
        add_text(data['date_signature'], 200, 750)
    if data.get('nom_prenom_gerant'):
        add_text(data['nom_prenom_gerant'], 300, 780)
    
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
    can = canvas.Canvas(packet, pagesize=A4)
    
    def add_text(text, x, y, font_size=10):
        can.setFont("Helvetica", font_size)
        can.drawString(x, 842 - y, str(text))
    
    if data.get('nom_societe'):
        add_text(data['nom_societe'], 250, 280)
    if data.get('adresse_siege_social_1'):
        add_text(data['adresse_siege_social_1'], 250, 320)
    if data.get('telephone_gsm'):
        add_text(data['telephone_gsm'], 250, 380)
    if data.get('email'):
        add_text(data['email'], 250, 420)
    if data.get('num_entreprise'):
        add_text(data['num_entreprise'], 250, 450)
    if data.get('num_onss'):
        add_text(data['num_onss'], 350, 450)
    if data.get('date_signature'):
        add_text(data['date_signature'], 200, 750)
    
    can.save()
    packet.seek(0)
    overlay = PdfReader(packet)
    writer = PdfWriter()
    
    for page in reader.pages:
        writer.add_page(page)
    if len(overlay.pages) > 0:
        writer.pages[0].merge_page(overlay.pages[0])
    
    output = io.BytesIO()
    writer.write(output)
    output.seek(0)
    return output

def fill_obligations_data(data):
    """Fill obligations letter - mostly static, just add signature"""
    reader = PdfReader(TEMPLATES['obligations'])
    packet = io.BytesIO()
    can = canvas.Canvas(packet, pagesize=A4)
    
    def add_text(text, x, y, font_size=10):
        can.setFont("Helvetica", font_size)
        can.drawString(x, 842 - y, str(text))
    
    # This is mostly a static document, just add date/signature
    if data.get('date_signature'):
        add_text(data['date_signature'], 200, 800)
    
    can.save()
    packet.seek(0)
    overlay = PdfReader(packet)
    writer = PdfWriter()
    
    for i, page in enumerate(reader.pages):
        if i == len(reader.pages) - 1 and len(overlay.pages) > 0:
            page.merge_page(overlay.pages[0])
        writer.add_page(page)
    
    output = io.BytesIO()
    writer.write(output)
    output.seek(0)
    return output

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
