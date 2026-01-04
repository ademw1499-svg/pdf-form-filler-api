from flask import Flask, request, jsonify, send_file
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
import io
import os
from datetime import datetime

app = Flask(__name__)

TEMPLATE_PATH = "FICHE_RENSEIGNEMENTS_EMPLOYEUR_FR_2020.pdf"

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({"status": "healthy", "timestamp": datetime.now().isoformat()})

@app.route('/fill-employer-form', methods=['POST'])
def fill_employer_form():
    """Fill the employer affiliation form with provided data"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400
        
        output_pdf = fill_pdf_with_data(data)
        return send_file(
            output_pdf,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f"employer_form_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500

def fill_pdf_with_data(data):
    """Fill PDF using ReportLab overlay - CORRECTED POSITIONING"""
    
    reader = PdfReader(TEMPLATE_PATH)
    packet = io.BytesIO()
    can = canvas.Canvas(packet, pagesize=(595, 842))
    
    # Scale factors
    SCALE_X = 595 / 707
    SCALE_Y = 842 / 1000
    
    def convert_y(y_img):
        """Convert image Y to PDF Y (flipped)"""
        return 842 - (y_img * SCALE_Y)
    
    def add_text(text, x_img, y_bottom_img, font_size=10):
        """Add text at bottom of bounding box (on the line)"""
        can.setFont("Helvetica", font_size)
        x_pdf = x_img * SCALE_X
        y_pdf = convert_y(y_bottom_img)  # Use BOTTOM of box
        can.drawString(x_pdf, y_pdf, str(text))
    
    # PAGE 1 - Using BOTTOM Y-coordinate of each box
    if data.get('recu_par'):
        add_text(data['recu_par'], 148, 203)  # Bottom of box
    
    # Legal form checkboxes
    forme = data.get('forme_juridique', '')
    if forme == 'SRL':
        add_text('X', 190, 246, 12)
    elif forme == 'SC':
        add_text('X', 234, 246, 12)
    elif forme == 'SA':
        add_text('X', 280, 246, 12)
    elif forme == 'ASBL':
        add_text('X', 337, 246, 12)
    elif forme == 'PERSONNE PHYSIQUE':
        add_text('X', 408, 246, 12)
    
    if data.get('nom_societe'):
        add_text(data['nom_societe'], 217, 282)
    
    if data.get('nom_prenom_gerant'):
        add_text(data['nom_prenom_gerant'], 260, 314)
    
    if data.get('niss_gerant'):
        add_text(data['niss_gerant'], 194, 347)
    
    if data.get('adresse_siege_social_1'):
        add_text(data['adresse_siege_social_1'], 249, 380)
    
    if data.get('adresse_siege_social_2'):
        add_text(data['adresse_siege_social_2'], 249, 397)
    
    if data.get('adresse_exploitation_1'):
        add_text(data['adresse_exploitation_1'], 301, 430)
    
    if data.get('adresse_exploitation_2'):
        add_text(data['adresse_exploitation_2'], 301, 447)
    
    if data.get('telephone_gsm'):
        add_text(data['telephone_gsm'], 204, 513)
    
    if data.get('email'):
        add_text(data['email'], 189, 546)
    
    if data.get('num_entreprise'):
        add_text(data['num_entreprise'], 204, 579)
    
    if data.get('num_onss'):
        add_text(data['num_onss'], 185, 612)
    
    if data.get('assurance_loi'):
        add_text(data['assurance_loi'], 264, 645)
    
    if data.get('seppt'):
        add_text(data['seppt'], 135, 678)
    
    if data.get('secteur_activite'):
        add_text(data['secteur_activite'], 204, 711)
    
    # First hire reduction checkboxes
    reduction = data.get('reduction_premier', '')
    if reduction == 'Oui':
        add_text('X', 69, 773, 12)
    elif reduction == 'Non':
        add_text('X', 106, 773, 12)
    elif reduction == 'Enquete':
        add_text('X', 151, 773, 12)
    
    if data.get('commission_paritaire'):
        add_text(data['commission_paritaire'], 233, 809)
    
    if data.get('indice_onss'):
        add_text(data['indice_onss'], 174, 842)
    
    if data.get('code_nace'):
        add_text(data['code_nace'], 162, 875)
    
    # Save page 1
    can.showPage()
    
    # PAGE 2
    if data.get('regime_horaire'):
        add_text(data['regime_horaire'], 204, 152)
    
    # Weekly schedule - using smaller font
    schedule_fields = [
        ('lundi_matin_de', 168, 234),
        ('lundi_matin_a', 221, 234),
        ('lundi_pause_de', 340, 234),
        ('lundi_pause_a', 393, 234),
        ('lundi_apres_de', 540, 234),
        ('lundi_apres_a', 593, 234),
        # Add more days as needed
        ('mardi_matin_de', 168, 253),
        ('mardi_matin_a', 221, 253),
        ('mercredi_matin_de', 168, 272),
        ('mercredi_matin_a', 221, 272),
        ('jeudi_matin_de', 168, 291),
        ('jeudi_matin_a', 221, 291),
        ('vendredi_matin_de', 168, 310),
        ('vendredi_matin_a', 221, 310),
    ]
    
    for field_name, x, y in schedule_fields:
        if data.get(field_name):
            add_text(data[field_name], x, y, 9)
    
    if data.get('cameras'):
        add_text(data['cameras'], 340, 374)
    
    if data.get('trousse_secours'):
        add_text(data['trousse_secours'], 323, 424)
    
    if data.get('nom_comptable'):
        add_text(data['nom_comptable'], 221, 589)
    
    # Origin checkboxes
    origine = data.get('origine', '')
    if origine == 'Internet':
        add_text('X', 138, 668, 12)
    elif origine == 'Comptable':
        add_text('X', 334, 668, 12)
    elif origine == 'Client':
        add_text('X', 138, 702, 12)
    elif origine == 'Autre':
        add_text('X', 334, 702, 12)
    
    if data.get('date_signature'):
        add_text(data['date_signature'], 123, 852)
    
    can.save()
    
    # Merge with template
    packet.seek(0)
    overlay = PdfReader(packet)
    
    writer = PdfWriter()
    
    # Merge page 1
    page1 = reader.pages[0]
    page1.merge_page(overlay.pages[0])
    writer.add_page(page1)
    
    # Merge page 2
    page2 = reader.pages[1]
    page2.merge_page(overlay.pages[1])
    writer.add_page(page2)
    
    output = io.BytesIO()
    writer.write(output)
    output.seek(0)
    
    return output

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
