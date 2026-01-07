from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
import io
import os
import zipfile

app = Flask(__name__)
CORS(app)

# ========== PRECISE COORDINATES - ALIGNED TO DOTTED LINES ==========
# Measured from image centers of dotted lines
# Image: 1241x1754 pixels | PDF: 595.32x841.92 points

EMPLOYER_PAGE1 = {
    'recu_par': (225.46, 710.88),
    'nom_societe': (225.46, 660.48),
    'nom_prenom_gerant': (225.46, 637.92),
    'niss_gerant': (225.46, 615.36),
    'adresse_siege_social_1': (225.46, 592.80),
    'adresse_siege_social_2': (225.46, 570.24),
    'adresse_exploitation_1': (225.46, 532.80),
    'adresse_exploitation_2': (225.46, 510.24),
    'telephone_gsm': (225.46, 477.12),
    'email': (225.46, 454.56),
    'num_entreprise': (225.46, 432.00),
    'num_onss': (225.46, 409.44),
    'assurance_loi': (225.46, 386.88),
    'seppt': (225.46, 364.32),
    'secteur_activite': (225.46, 341.76),
    'commission_paritaire': (225.46, 285.60),
    'indice_onss': (225.46, 263.04),
    'code_nace': (225.46, 240.48),
}

# Checkbox positions for Page 1
EMPLOYER_PAGE1_CHECKBOXES = {
    # Forme juridique checkboxes (Y~380 in image = ~575 in PDF)
    'forme_juridique_srl': (145, 575),
    'forme_juridique_sc': (175, 575),
    'forme_juridique_sa': (210, 575),
    'forme_juridique_asbl': (260, 575),
    'forme_juridique_personne': (340, 575),
    
    # Réduction premier engagement (Y~1095 in image = ~315 in PDF)
    'reduction_oui': (90, 315),
    'reduction_non': (125, 315),
    
    # Salaire garanti (Y~1305 in image = ~215 in PDF)
    'salaire_garanti_oui': (520, 215),
    'salaire_garanti_non': (555, 215),
}

EMPLOYER_PAGE2 = {
    'regime_horaire': (225.46, 750.24),
    # Schedule table
    'lundi_matin_de': (106.98, 696.96),
    'lundi_matin_a': (148.71, 696.96),
    'lundi_pause_de': (207.71, 696.96),
    'lundi_pause_a': (249.45, 696.96),
    'lundi_apres_de': (327.64, 696.96),
    'lundi_apres_a': (369.38, 696.96),
    'mardi_matin_de': (106.98, 675.84),
    'mardi_matin_a': (148.71, 675.84),
    'mardi_pause_de': (207.71, 675.84),
    'mardi_pause_a': (249.45, 675.84),
    'mardi_apres_de': (327.64, 675.84),
    'mardi_apres_a': (369.38, 675.84),
    'mercredi_matin_de': (106.98, 654.72),
    'mercredi_matin_a': (148.71, 654.72),
    'mercredi_pause_de': (207.71, 654.72),
    'mercredi_pause_a': (249.45, 654.72),
    'mercredi_apres_de': (327.64, 654.72),
    'mercredi_apres_a': (369.38, 654.72),
    'jeudi_matin_de': (106.98, 633.60),
    'jeudi_matin_a': (148.71, 633.60),
    'jeudi_pause_de': (207.71, 633.60),
    'jeudi_pause_a': (249.45, 633.60),
    'jeudi_apres_de': (327.64, 633.60),
    'jeudi_apres_a': (369.38, 633.60),
    'vendredi_matin_de': (106.98, 612.48),
    'vendredi_matin_a': (148.71, 612.48),
    'vendredi_pause_de': (207.71, 612.48),
    'vendredi_pause_a': (249.45, 612.48),
    'vendredi_apres_de': (327.64, 612.48),
    'vendredi_apres_a': (369.38, 612.48),
    'samedi_matin_de': (106.98, 591.36),
    'samedi_matin_a': (148.71, 591.36),
    'samedi_pause_de': (207.71, 591.36),
    'samedi_pause_a': (249.45, 591.36),
    'samedi_apres_de': (327.64, 591.36),
    'samedi_apres_a': (369.38, 591.36),
    'dimanche_matin_de': (106.98, 570.24),
    'dimanche_matin_a': (148.71, 570.24),
    'dimanche_pause_de': (207.71, 570.24),
    'dimanche_pause_a': (249.45, 570.24),
    'dimanche_apres_de': (327.64, 570.24),
    'dimanche_apres_a': (369.38, 570.24),
    'cameras': (225.46, 540.48),
    'trousse_secours': (225.46, 483.84),
    'primes': (225.46, 427.68),
    'secretariat_actuel': (225.46, 405.12),
    'nom_comptable': (225.46, 382.56),
    'coord_comptable': (225.46, 360.00),
    'date_signature': (225.46, 180.48),
}

# Checkbox positions for Page 2
EMPLOYER_PAGE2_CHECKBOXES = {
    # Fourniture vêtements (Y~825 in image = ~430 in PDF)
    'vetements_fourniture_oui': (320, 430),
    'vetements_fourniture_non': (355, 430),
    
    # Entretien vêtements (Y~849 in image = ~418 in PDF)
    'vetements_entretien_oui': (320, 418),
    'vetements_entretien_non': (355, 418),
    
    # Origine checkboxes (Y~1050 in image = ~340 in PDF)
    'origine_internet': (145, 340),
    'origine_comptable': (180, 340),
    'origine_client': (145, 325),
    'origine_autre': (180, 325),
}

def create_overlay_with_text_and_circles(data, coordinates, checkboxes, page_size=letter):
    """Create overlay with text and checkbox circles"""
    packet = io.BytesIO()
    can = canvas.Canvas(packet, pagesize=page_size)
    can.setFont("Helvetica", 9)
    
    # Add text fields
    for field_name, (x, y) in coordinates.items():
        if field_name in data and data[field_name]:
            can.drawString(x, y, str(data[field_name]))
    
    # Add circles for checkboxes
    for checkbox_name, (x, y) in checkboxes.items():
        if checkbox_name in data and data[checkbox_name]:
            # Draw a circle around the checkbox
            can.setLineWidth(1.5)
            can.circle(x, y, 5, stroke=1, fill=0)
    
    can.save()
    packet.seek(0)
    return PdfReader(packet)

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "ok"})

@app.route('/fill-employer-form', methods=['POST'])
def fill_employer_form():
    try:
        data = request.json
        template_path = 'FICHE_RENSEIGNEMENTS_EMPLOYEUR_FR_2020.pdf'
        
        if not os.path.exists(template_path):
            return jsonify({"error": f"Template not found: {template_path}"}), 404
        
        template_pdf = PdfReader(template_path)
        writer = PdfWriter()
        
        # Process checkboxes - convert values like "SRL", "Oui", "Non" to checkbox flags
        checkbox_data = {}
        
        # Forme juridique
        forme = data.get('forme_juridique', '').upper()
        if 'SRL' in forme:
            checkbox_data['forme_juridique_srl'] = True
        if 'SC' in forme:
            checkbox_data['forme_juridique_sc'] = True
        if 'SA' in forme:
            checkbox_data['forme_juridique_sa'] = True
        if 'ASBL' in forme:
            checkbox_data['forme_juridique_asbl'] = True
        if 'PERSONNE' in forme or 'PHYSIQUE' in forme:
            checkbox_data['forme_juridique_personne'] = True
        
        # Réduction premier engagement
        reduction = data.get('reduction_premier', '').lower()
        if 'oui' in reduction:
            checkbox_data['reduction_oui'] = True
        elif 'non' in reduction:
            checkbox_data['reduction_non'] = True
        
        # Salaire garanti
        salaire = data.get('salaire_garanti', '').upper()
        if 'OUI' in salaire:
            checkbox_data['salaire_garanti_oui'] = True
        elif 'NON' in salaire:
            checkbox_data['salaire_garanti_non'] = True
        
        # Vêtements
        vet_fourniture = data.get('vetements_fourniture', '').lower()
        if 'oui' in vet_fourniture:
            checkbox_data['vetements_fourniture_oui'] = True
        elif 'non' in vet_fourniture:
            checkbox_data['vetements_fourniture_non'] = True
        
        vet_entretien = data.get('vetements_entretien', '').lower()
        if 'oui' in vet_entretien:
            checkbox_data['vetements_entretien_oui'] = True
        elif 'non' in vet_entretien:
            checkbox_data['vetements_entretien_non'] = True
        
        # Origine
        origine = data.get('origine', '').lower()
        if 'internet' in origine:
            checkbox_data['origine_internet'] = True
        elif 'comptable' in origine:
            checkbox_data['origine_comptable'] = True
        elif 'client' in origine:
            checkbox_data['origine_client'] = True
        elif 'autre' in origine:
            checkbox_data['origine_autre'] = True
        
        # Page 1
        page1 = template_pdf.pages[0]
        overlay1 = create_overlay_with_text_and_circles(
            {**data, **checkbox_data}, 
            EMPLOYER_PAGE1, 
            EMPLOYER_PAGE1_CHECKBOXES
        )
        page1.merge_page(overlay1.pages[0])
        writer.add_page(page1)
        
        # Page 2
        page2 = template_pdf.pages[1]
        overlay2 = create_overlay_with_text_and_circles(
            {**data, **checkbox_data}, 
            EMPLOYER_PAGE2, 
            EMPLOYER_PAGE2_CHECKBOXES
        )
        page2.merge_page(overlay2.pages[0])
        writer.add_page(page2)
        
        # Save to BytesIO
        output = io.BytesIO()
        writer.write(output)
        output.seek(0)
        
        return send_file(
            output,
            mimetype='application/pdf',
            as_attachment=True,
            download_name='fiche_employeur_filled.pdf'
        )
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/fill-multiple-forms', methods=['POST'])
def fill_multiple_forms():
    try:
        data = request.json
        selected_docs = data.get('selected_documents', [])
        
        # Create ZIP file in memory
        zip_buffer = io.BytesIO()
        
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            # For now, only employer works
            if 'employer' in selected_docs:
                # Generate employer PDF
                pass
            
            # TODO: Add other documents
            if any(doc in selected_docs for doc in ['worker', 'independent', 'seppt', 'accident', 'dispense', 'procuration', 'mensura', 'obligations']):
                return jsonify({"error": "Other documents not yet implemented"}), 501
        
        zip_buffer.seek(0)
        
        return send_file(
            zip_buffer,
            mimetype='application/zip',
            as_attachment=True,
            download_name='documents.zip'
        )
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
