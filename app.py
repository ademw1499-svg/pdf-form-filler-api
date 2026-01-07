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

# ===== FIXED WITH PROPER BASELINE ADJUSTMENT =====
# Key insight: drawString() draws from text BASELINE, not center
# So we need to subtract font_size/3 from the visual center position

def img_to_pdf(img_x, img_y, img_w=1241, img_h=1754, font_size=9):
    """Convert image coords to PDF with baseline adjustment"""
    pdf_w, pdf_h = 595.32, 841.92
    # Convert X
    pdf_x = (img_x / img_w) * pdf_w
    # Convert Y (flip axis)
    pdf_y_center = pdf_h - ((img_y / img_h) * pdf_h)
    # Adjust for baseline (text draws from baseline, not center)
    pdf_y = pdf_y_center - (font_size / 3)
    return pdf_x, pdf_y

# Page 1 - Measured at CENTER of each red dotted line
EMPLOYER_PAGE1 = {
    'recu_par': img_to_pdf(470, 273),
    'nom_societe': img_to_pdf(470, 378),
    'nom_prenom_gerant': img_to_pdf(470, 425),
    'niss_gerant': img_to_pdf(470, 472),
    'adresse_siege_social_1': img_to_pdf(470, 519),
    'adresse_siege_social_2': img_to_pdf(470, 566),
    'adresse_exploitation_1': img_to_pdf(470, 644),
    'adresse_exploitation_2': img_to_pdf(470, 691),
    'telephone_gsm': img_to_pdf(470, 760),
    'email': img_to_pdf(470, 807),
    'num_entreprise': img_to_pdf(470, 854),
    'num_onss': img_to_pdf(470, 901),
    'assurance_loi': img_to_pdf(470, 948),
    'seppt': img_to_pdf(470, 995),
    'secteur_activite': img_to_pdf(470, 1042),
    'commission_paritaire': img_to_pdf(470, 1159),
    'indice_onss': img_to_pdf(470, 1206),
    'code_nace': img_to_pdf(470, 1253),
}

# Page 2 - Schedule table and other fields
EMPLOYER_PAGE2 = {
    'regime_horaire': img_to_pdf(350, 191),
    # Schedule table rows (measured at CENTER of each row)
    'lundi_matin_de': img_to_pdf(223, 302),
    'lundi_matin_a': img_to_pdf(310, 302),
    'lundi_pause_de': img_to_pdf(433, 302),
    'lundi_pause_a': img_to_pdf(520, 302),
    'lundi_apres_de': img_to_pdf(683, 302),
    'lundi_apres_a': img_to_pdf(770, 302),
    
    'mardi_matin_de': img_to_pdf(223, 346),
    'mardi_matin_a': img_to_pdf(310, 346),
    'mardi_pause_de': img_to_pdf(433, 346),
    'mardi_pause_a': img_to_pdf(520, 346),
    'mardi_apres_de': img_to_pdf(683, 346),
    'mardi_apres_a': img_to_pdf(770, 346),
    
    'mercredi_matin_de': img_to_pdf(223, 390),
    'mercredi_matin_a': img_to_pdf(310, 390),
    'mercredi_pause_de': img_to_pdf(433, 390),
    'mercredi_pause_a': img_to_pdf(520, 390),
    'mercredi_apres_de': img_to_pdf(683, 390),
    'mercredi_apres_a': img_to_pdf(770, 390),
    
    'jeudi_matin_de': img_to_pdf(223, 434),
    'jeudi_matin_a': img_to_pdf(310, 434),
    'jeudi_pause_de': img_to_pdf(433, 434),
    'jeudi_pause_a': img_to_pdf(520, 434),
    'jeudi_apres_de': img_to_pdf(683, 434),
    'jeudi_apres_a': img_to_pdf(770, 434),
    
    'vendredi_matin_de': img_to_pdf(223, 478),
    'vendredi_matin_a': img_to_pdf(310, 478),
    'vendredi_pause_de': img_to_pdf(433, 478),
    'vendredi_pause_a': img_to_pdf(520, 478),
    'vendredi_apres_de': img_to_pdf(683, 478),
    'vendredi_apres_a': img_to_pdf(770, 478),
    
    'samedi_matin_de': img_to_pdf(223, 522),
    'samedi_matin_a': img_to_pdf(310, 522),
    'samedi_pause_de': img_to_pdf(433, 522),
    'samedi_pause_a': img_to_pdf(520, 522),
    'samedi_apres_de': img_to_pdf(683, 522),
    'samedi_apres_a': img_to_pdf(770, 522),
    
    'dimanche_matin_de': img_to_pdf(223, 566),
    'dimanche_matin_a': img_to_pdf(310, 566),
    'dimanche_pause_de': img_to_pdf(433, 566),
    'dimanche_pause_a': img_to_pdf(520, 566),
    'dimanche_apres_de': img_to_pdf(683, 566),
    'dimanche_apres_a': img_to_pdf(770, 566),
    
    'cameras': img_to_pdf(470, 628),
    'trousse_secours': img_to_pdf(470, 746),
    'primes': img_to_pdf(470, 863),
    'secretariat_actuel': img_to_pdf(470, 910),
    'nom_comptable': img_to_pdf(470, 957),
    'coord_comptable': img_to_pdf(470, 1004),
    'date_signature': img_to_pdf(250, 1378),
}

def create_overlay(data, coordinates, font_size=9):
    """Create overlay with text"""
    packet = io.BytesIO()
    can = canvas.Canvas(packet, pagesize=letter)
    can.setFont("Helvetica", font_size)
    
    for field_name, (x, y) in coordinates.items():
        if field_name in data and data[field_name]:
            can.drawString(x, y, str(data[field_name]))
    
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
        
        # Page 1
        page1 = template_pdf.pages[0]
        overlay1 = create_overlay(data, EMPLOYER_PAGE1, font_size=9)
        page1.merge_page(overlay1.pages[0])
        writer.add_page(page1)
        
        # Page 2
        page2 = template_pdf.pages[1]
        overlay2 = create_overlay(data, EMPLOYER_PAGE2, font_size=9)
        page2.merge_page(overlay2.pages[0])
        writer.add_page(page2)
        
        # Save
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
        
        zip_buffer = io.BytesIO()
        
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            if 'employer' in selected_docs:
                pass
            
            if any(doc in selected_docs for doc in ['worker', 'independent', 'seppt', 'accident', 'dispense', 'procuration', 'mensura', 'obligations']):
                return jsonify({"error": "Other documents not implemented yet"}), 501
        
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
