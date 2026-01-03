from flask import Flask, request, jsonify, send_file
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
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
        "forme_juridique": "SRL",  // Will check the right checkbox
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
    """Fill the PDF form with provided data using annotations"""
    
    # Read the template PDF
    reader = PdfReader(TEMPLATE_PATH)
    writer = PdfWriter()
    
    # Copy all pages
    for page in reader.pages:
        writer.add_page(page)
    
    # Create annotations for each field
    annotations = create_annotations(data)
    
    # Add annotations to the appropriate pages
    for page_num, page_annotations in annotations.items():
        page = writer.pages[page_num - 1]  # PDF pages are 0-indexed
        
        for annotation in page_annotations:
            page.add_text_annotation(
                text=annotation['text'],
                rect=annotation['rect'],
                color=(0, 0, 0)
            )
    
    # Write to BytesIO object
    output = io.BytesIO()
    writer.write(output)
    output.seek(0)
    
    return output

def create_annotations(data):
    """
    Create PDF annotations based on input data
    Returns a dict with page numbers as keys and lists of annotations as values
    """
    
    # Get PDF dimensions (707x1000 pixels from our analysis)
    # PDF points are different - typically 1 point = 1/72 inch
    # We need to convert pixel coordinates to PDF points
    
    # For A4 at 72 DPI: width=595pt, height=842pt
    # Our images were 707x1000 pixels
    # Scale factor: PDF_width/image_width = 595/707 ≈ 0.84
    
    SCALE_X = 595 / 707  # Horizontal scale
    SCALE_Y = 842 / 1000  # Vertical scale
    
    annotations = {1: [], 2: []}
    
    # Helper function to convert image coords to PDF coords
    def convert_coords(x1, y1, x2, y2):
        """Convert image pixel coords to PDF points (from bottom-left origin)"""
        pdf_x1 = x1 * SCALE_X
        pdf_y1 = (1000 - y2) * SCALE_Y  # Flip Y axis
        pdf_x2 = x2 * SCALE_X
        pdf_y2 = (1000 - y1) * SCALE_Y  # Flip Y axis
        return [pdf_x1, pdf_y1, pdf_x2, pdf_y2]
    
    # PAGE 1 FIELDS
    if data.get('recu_par'):
        annotations[1].append({
            'text': data['recu_par'],
            'rect': convert_coords(148, 191, 335, 203)
        })
    
    # Legal form checkboxes
    forme = data.get('forme_juridique', '')
    if forme == 'SRL':
        annotations[1].append({'text': 'X', 'rect': convert_coords(190, 232, 202, 246)})
    elif forme == 'SC':
        annotations[1].append({'text': 'X', 'rect': convert_coords(234, 232, 246, 246)})
    elif forme == 'SA':
        annotations[1].append({'text': 'X', 'rect': convert_coords(280, 232, 292, 246)})
    elif forme == 'ASBL':
        annotations[1].append({'text': 'X', 'rect': convert_coords(337, 232, 349, 246)})
    elif forme == 'PERSONNE PHYSIQUE':
        annotations[1].append({'text': 'X', 'rect': convert_coords(408, 232, 420, 246)})
    
    if data.get('nom_societe'):
        annotations[1].append({
            'text': data['nom_societe'],
            'rect': convert_coords(217, 267, 655, 282)
        })
    
    if data.get('nom_prenom_gerant'):
        annotations[1].append({
            'text': data['nom_prenom_gerant'],
            'rect': convert_coords(260, 299, 655, 314)
        })
    
    if data.get('niss_gerant'):
        annotations[1].append({
            'text': data['niss_gerant'],
            'rect': convert_coords(194, 332, 655, 347)
        })
    
    if data.get('adresse_siege_social_1'):
        annotations[1].append({
            'text': data['adresse_siege_social_1'],
            'rect': convert_coords(249, 365, 655, 380)
        })
    
    if data.get('adresse_siege_social_2'):
        annotations[1].append({
            'text': data['adresse_siege_social_2'],
            'rect': convert_coords(249, 382, 655, 397)
        })
    
    if data.get('adresse_exploitation_1'):
        annotations[1].append({
            'text': data['adresse_exploitation_1'],
            'rect': convert_coords(301, 415, 655, 430)
        })
    
    if data.get('adresse_exploitation_2'):
        annotations[1].append({
            'text': data['adresse_exploitation_2'],
            'rect': convert_coords(301, 432, 655, 447)
        })
    
    if data.get('telephone_gsm'):
        annotations[1].append({
            'text': data['telephone_gsm'],
            'rect': convert_coords(204, 498, 655, 513)
        })
    
    if data.get('email'):
        annotations[1].append({
            'text': data['email'],
            'rect': convert_coords(189, 531, 655, 546)
        })
    
    if data.get('num_entreprise'):
        annotations[1].append({
            'text': data['num_entreprise'],
            'rect': convert_coords(204, 564, 655, 579)
        })
    
    if data.get('num_onss'):
        annotations[1].append({
            'text': data['num_onss'],
            'rect': convert_coords(185, 597, 655, 612)
        })
    
    if data.get('assurance_loi'):
        annotations[1].append({
            'text': data['assurance_loi'],
            'rect': convert_coords(264, 630, 655, 645)
        })
    
    if data.get('seppt'):
        annotations[1].append({
            'text': data['seppt'],
            'rect': convert_coords(135, 663, 655, 678)
        })
    
    if data.get('secteur_activite'):
        annotations[1].append({
            'text': data['secteur_activite'],
            'rect': convert_coords(204, 696, 655, 711)
        })
    
    # First hire reduction
    reduction = data.get('reduction_premier', '')
    if reduction == 'Oui':
        annotations[1].append({'text': 'X', 'rect': convert_coords(69, 761, 81, 773)})
    elif reduction == 'Non':
        annotations[1].append({'text': 'X', 'rect': convert_coords(106, 761, 118, 773)})
    elif reduction == 'Enquete':
        annotations[1].append({'text': 'X', 'rect': convert_coords(151, 761, 163, 773)})
    
    if data.get('commission_paritaire'):
        annotations[1].append({
            'text': data['commission_paritaire'],
            'rect': convert_coords(233, 794, 655, 809)
        })
    
    if data.get('indice_onss'):
        annotations[1].append({
            'text': data['indice_onss'],
            'rect': convert_coords(174, 827, 655, 842)
        })
    
    if data.get('code_nace'):
        annotations[1].append({
            'text': data['code_nace'],
            'rect': convert_coords(162, 860, 655, 875)
        })
    
    # PAGE 2 FIELDS
    if data.get('regime_horaire'):
        annotations[2].append({
            'text': data['regime_horaire'],
            'rect': convert_coords(204, 137, 280, 152)
        })
    
    # Weekly schedule - Monday
    schedule_fields = [
        ('lundi_matin_de', 168, 219, 212, 234),
        ('lundi_matin_a', 221, 219, 265, 234),
        ('lundi_pause_de', 340, 219, 384, 234),
        ('lundi_pause_a', 393, 219, 437, 234),
        ('lundi_apres_de', 540, 219, 584, 234),
        ('lundi_apres_a', 593, 219, 637, 234),
    ]
    
    for field_name, x1, y1, x2, y2 in schedule_fields:
        if data.get(field_name):
            annotations[2].append({
                'text': data[field_name],
                'rect': convert_coords(x1, y1, x2, y2)
            })
    
    if data.get('cameras'):
        annotations[2].append({
            'text': data['cameras'],
            'rect': convert_coords(340, 359, 655, 374)
        })
    
    if data.get('trousse_secours'):
        annotations[2].append({
            'text': data['trousse_secours'],
            'rect': convert_coords(323, 409, 655, 424)
        })
    
    if data.get('nom_comptable'):
        annotations[2].append({
            'text': data['nom_comptable'],
            'rect': convert_coords(221, 574, 655, 589)
        })
    
    # Origin checkbox
    origine = data.get('origine', '')
    if origine == 'Internet':
        annotations[2].append({'text': 'X', 'rect': convert_coords(138, 656, 150, 668)})
    elif origine == 'Comptable':
        annotations[2].append({'text': 'X', 'rect': convert_coords(334, 656, 346, 668)})
    elif origine == 'Client':
        annotations[2].append({'text': 'X', 'rect': convert_coords(138, 690, 150, 702)})
    elif origine == 'Autre':
        annotations[2].append({'text': 'X', 'rect': convert_coords(334, 690, 346, 702)})
    
    if data.get('date_signature'):
        annotations[2].append({
            'text': data['date_signature'],
            'rect': convert_coords(123, 840, 330, 852)
        })
    
    return annotations

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
