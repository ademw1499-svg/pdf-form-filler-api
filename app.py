from flask import Flask, request, jsonify, send_file
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import io
import json
import os
from datetime import datetime

app = Flask(__name__)

# Store the template PDF in memory
TEMPLATE_PATH = "FICHE_RENSEIGNEMENTS_EMPLOYEUR_FR_2020.pdf"

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({"status": "healthy", "timestamp": datetime.now().isoformat()})

@app.route('/fill-employer-form', methods=['POST'])
def fill_employer_form():
    """
    Fill the employer affiliation form with provided data
    
    Expected JSON format:
    {
        "recu_par": "Marie Dubois",
        "forme_juridique": "SRL",
        "nom_societe": "Tech Solutions SPRL",
        ... etc
    }
    """
    try:
        # Get JSON data from request
        data = request.get_json()
        
        if not data:
            return jsonify({"error": "No data provided"}), 400
        
        # Create filled PDF
        output_pdf = fill_pdf_with_data(data)
        
        # Return the PDF file
        return send_file(
            output_pdf,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f"employer_form_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        )
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

def fill_pdf_with_data(data):
    """Fill the PDF form with provided data using ReportLab overlay"""
    
    # Read the template PDF
    reader = PdfReader(TEMPLATE_PATH)
    
    # Create overlay with text
    packet = io.BytesIO()
    can = canvas.Canvas(packet, pagesize=(595, 842))  # A4 size in points
    
    # Set font
    can.setFont("Helvetica", 10)
    can.setFillColorRGB(0, 0, 0)
    
    # Helper function to add text
    def add_text(text, x, y, font_size=10):
        can.setFont("Helvetica", font_size)
        can.drawString(x, y, str(text))
    
    # Scale factors (image pixels to PDF points)
    SCALE_X = 595 / 707
    SCALE_Y = 842 / 1000
    
    def convert_y(y_img):
        """Convert image Y coordinate to PDF Y (flip axis)"""
        return 842 - (y_img * SCALE_Y)
    
    # PAGE 1 FIELDS
    if data.get('recu_par'):
        add_text(data['recu_par'], 148 * SCALE_X, convert_y(203))
    
    # Legal form checkboxes
    forme = data.get('forme_juridique', '')
    if forme == 'SRL':
        add_text('X', 190 * SCALE_X, convert_y(246), 12)
    elif forme == 'SC':
        add_text('X', 234 * SCALE_X, convert_y(246), 12)
    elif forme == 'SA':
        add_text('X', 280 * SCALE_X, convert_y(246), 12)
    elif forme == 'ASBL':
        add_text('X', 337 * SCALE_X, convert_y(246), 12)
    elif forme == 'PERSONNE PHYSIQUE':
        add_text('X', 408 * SCALE_X, convert_y(246), 12)
    
    if data.get('nom_societe'):
        add_text(data['nom_societe'], 217 * SCALE_X, convert_y(282))
    
    if data.get('nom_prenom_gerant'):
        add_text(data['nom_prenom_gerant'], 260 * SCALE_X, convert_y(314))
    
    if data.get('niss_gerant'):
        add_text(data['niss_gerant'], 194 * SCALE_X, convert_y(347))
    
    if data.get('adresse_siege_social_1'):
        add_text(data['adresse_siege_social_1'], 249 * SCALE_X, convert_y(380))
    
    if data.get('adresse_siege_social_2'):
        add_text(data['adresse_siege_social_2'], 249 * SCALE_X, convert_y(397))
    
    if data.get('adresse_exploitation_1'):
        add_text(data['adresse_exploitation_1'], 301 * SCALE_X, convert_y(430))
    
    if data.get('adresse_exploitation_2'):
        add_text(data['adresse_exploitation_2'], 301 * SCALE_X, convert_y(447))
    
    if data.get('telephone_gsm'):
        add_text(data['telephone_gsm'], 204 * SCALE_X, convert_y(513))
    
    if data.get('email'):
        add_text(data['email'], 189 * SCALE_X, convert_y(546))
    
    if data.get('num_entreprise'):
        add_text(data['num_entreprise'], 204 * SCALE_X, convert_y(579))
    
    if data.get('num_onss'):
        add_text(data['num_onss'], 185 * SCALE_X, convert_y(612))
    
    if data.get('assurance_loi'):
        add_text(data['assurance_loi'], 264 * SCALE_X, convert_y(645))
    
    if data.get('seppt'):
        add_text(data['seppt'], 135 * SCALE_X, convert_y(678))
    
    if data.get('secteur_activite'):
        add_text(data['secteur_activite'], 204 * SCALE_X, convert_y(711))
    
    # First hire reduction
    reduction = data.get('reduction_premier', '')
    if reduction == 'Oui':
        add_text('X', 69 * SCALE_X, convert_y(773), 12)
    elif reduction == 'Non':
        add_text('X', 106 * SCALE_X, convert_y(773), 12)
    elif reduction == 'Enquete':
        add_text('X', 151 * SCALE_X, convert_y(773), 12)
    
    if data.get('commission_paritaire'):
        add_text(data['commission_paritaire'], 233 * SCALE_X, convert_y(809))
    
    if data.get('indice_onss'):
        add_text(data['indice_onss'], 174 * SCALE_X, convert_y(842))
    
    if data.get('code_nace'):
        add_text(data['code_nace'], 162 * SCALE_X, convert_y(875))
    
    # Save page 1
    can.showPage()
    
    # PAGE 2 FIELDS
    can.setFont("Helvetica", 10)
    
    if data.get('regime_horaire'):
        add_text(data['regime_horaire'], 204 * SCALE_X, convert_y(152))
    
    # Weekly schedule - Monday (using smaller font)
    can.setFont("Helvetica", 9)
    schedule_fields = [
        ('lundi_matin_de', 168, 234),
        ('lundi_matin_a', 221, 234),
        ('lundi_pause_de', 340, 234),
        ('lundi_pause_a', 393, 234),
        ('lundi_apres_de', 540, 234),
        ('lundi_apres_a', 593, 234),
    ]
    
    for field_name, x, y in schedule_fields:
        if data.get(field_name):
            add_text(data[field_name], x * SCALE_X, convert_y(y), 9)
    
    can.setFont("Helvetica", 10)
    
    if data.get('cameras'):
        add_text(data['cameras'], 340 * SCALE_X, convert_y(374))
    
    if data.get('trousse_secours'):
        add_text(data['trousse_secours'], 323 * SCALE_X, convert_y(424))
    
    if data.get('nom_comptable'):
        add_text(data['nom_comptable'], 221 * SCALE_X, convert_y(589))
    
    # Origin checkbox
    origine = data.get('origine', '')
    if origine == 'Internet':
        add_text('X', 138 * SCALE_X, convert_y(668), 12)
    elif origine == 'Comptable':
        add_text('X', 334 * SCALE_X, convert_y(668), 12)
    elif origine == 'Client':
        add_text('X', 138 * SCALE_X, convert_y(702), 12)
    elif origine == 'Autre':
        add_text('X', 334 * SCALE_X, convert_y(702), 12)
    
    if data.get('date_signature'):
        add_text(data['date_signature'], 123 * SCALE_X, convert_y(852))
    
    can.save()
    
    # Merge overlay with template
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
    
    # Write to BytesIO
    output = io.BytesIO()
    writer.write(output)
    output.seek(0)
    
    return output

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
