from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
import io
import os
from datetime import datetime

app = Flask(__name__)
CORS(app)

TEMPLATE_PATH = "FICHE_RENSEIGNEMENTS_EMPLOYEUR_FR_2020.pdf"

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy", "timestamp": datetime.now().isoformat()})

@app.route('/fill-employer-form', methods=['POST'])
def fill_employer_form():
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
    reader = PdfReader(TEMPLATE_PATH)
    packet = io.BytesIO()
    can = canvas.Canvas(packet, pagesize=(595, 842))
    
    SCALE_X = 595 / 707
    SCALE_Y = 842 / 1000
    
    def convert_coords(x_img, y_img):
        x_pdf = x_img * SCALE_X
        y_pdf = 842 - (y_img * SCALE_Y)
        return (x_pdf, y_pdf)
    
    def add_text(text, x_img, y_img, font_size=10):
        can.setFont("Helvetica", font_size)
        x_pdf, y_pdf = convert_coords(x_img, y_img)
        can.drawString(x_pdf, y_pdf, str(text))
    
    # PAGE 1 - EXACT COORDINATES FROM COORDINATE PICKER
    if data.get('recu_par'):
        add_text(data['recu_par'], 235, 198)
    
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
        add_text(data['nom_societe'], 469, 277)
    if data.get('nom_prenom_gerant'):
        add_text(data['nom_prenom_gerant'], 469, 310)
    if data.get('niss_gerant'):
        add_text(data['niss_gerant'], 468, 344)
    if data.get('adresse_siege_social_1'):
        add_text(data['adresse_siege_social_1'], 466, 375)
    if data.get('adresse_siege_social_2'):
        add_text(data['adresse_siege_social_2'], 465, 409)
    if data.get('adresse_exploitation_1'):
        add_text(data['adresse_exploitation_1'], 466, 443)
    if data.get('adresse_exploitation_2'):
        add_text(data['adresse_exploitation_2'], 464, 478)
    if data.get('telephone_gsm'):
        add_text(data['telephone_gsm'], 461, 507)
    if data.get('email'):
        add_text(data['email'], 462, 539)
    if data.get('num_entreprise'):
        add_text(data['num_entreprise'], 462, 572)
    if data.get('num_onss'):
        add_text(data['num_onss'], 462, 604)
    if data.get('assurance_loi'):
        add_text(data['assurance_loi'], 464, 638)
    if data.get('seppt'):
        add_text(data['seppt'], 464, 669)
    if data.get('secteur_activite'):
        add_text(data['secteur_activite'], 464, 703)
    
    # Checkboxes and bottom fields - EXACT COORDINATES
    reduction = data.get('reduction_premier', '')
    if reduction == 'Oui':
        add_text('X', 96, 768, 12)
    elif reduction == 'Non':
        add_text('X', 133, 768, 12)
    
    if data.get('commission_paritaire'):
        add_text(data['commission_paritaire'], 462, 802)
    if data.get('indice_onss'):
        add_text(data['indice_onss'], 463, 834)
    if data.get('code_nace'):
        add_text(data['code_nace'], 461, 868)
    
    salaire = data.get('salaire_garanti', '')
    if salaire == 'OUI':
        add_text('X', 581, 899, 12)
    elif salaire == 'NON':
        add_text('X', 618, 899, 12)
    
    can.showPage()
    
    # PAGE 2 - EXACT COORDINATES FROM COORDINATE PICKER
    if data.get('regime_horaire'):
        add_text(data['regime_horaire'], 357, 148)
    
    # Schedule table - Row spacing is ~19-20 pixels
    # Lundi Y=228
    if data.get('lundi_matin_de'):
        add_text(data['lundi_matin_de'], 213, 228, 9)
    if data.get('lundi_matin_a'):
        add_text(data['lundi_matin_a'], 276, 228, 9)
    if data.get('lundi_pause_de'):
        add_text(data['lundi_pause_de'], 363, 228, 9)
    if data.get('lundi_pause_a'):
        add_text(data['lundi_pause_a'], 423, 228, 9)
    if data.get('lundi_apres_de'):
        add_text(data['lundi_apres_de'], 522, 227, 9)
    if data.get('lundi_apres_a'):
        add_text(data['lundi_apres_a'], 585, 228, 9)
    
    # Mardi Y=247
    if data.get('mardi_matin_de'):
        add_text(data['mardi_matin_de'], 211, 247, 9)
    if data.get('mardi_matin_a'):
        add_text(data['mardi_matin_a'], 276, 247, 9)
    if data.get('mardi_pause_de'):
        add_text(data['mardi_pause_de'], 363, 247, 9)
    if data.get('mardi_pause_a'):
        add_text(data['mardi_pause_a'], 423, 247, 9)
    if data.get('mardi_apres_de'):
        add_text(data['mardi_apres_de'], 522, 247, 9)
    if data.get('mardi_apres_a'):
        add_text(data['mardi_apres_a'], 585, 247, 9)
    
    # Mercredi Y=266
    if data.get('mercredi_matin_de'):
        add_text(data['mercredi_matin_de'], 211, 266, 9)
    if data.get('mercredi_matin_a'):
        add_text(data['mercredi_matin_a'], 276, 266, 9)
    if data.get('mercredi_pause_de'):
        add_text(data['mercredi_pause_de'], 363, 266, 9)
    if data.get('mercredi_pause_a'):
        add_text(data['mercredi_pause_a'], 423, 266, 9)
    if data.get('mercredi_apres_de'):
        add_text(data['mercredi_apres_de'], 522, 266, 9)
    if data.get('mercredi_apres_a'):
        add_text(data['mercredi_apres_a'], 585, 266, 9)
    
    # Jeudi Y=285
    if data.get('jeudi_matin_de'):
        add_text(data['jeudi_matin_de'], 211, 285, 9)
    if data.get('jeudi_matin_a'):
        add_text(data['jeudi_matin_a'], 276, 285, 9)
    if data.get('jeudi_pause_de'):
        add_text(data['jeudi_pause_de'], 363, 285, 9)
    if data.get('jeudi_pause_a'):
        add_text(data['jeudi_pause_a'], 423, 285, 9)
    if data.get('jeudi_apres_de'):
        add_text(data['jeudi_apres_de'], 522, 285, 9)
    if data.get('jeudi_apres_a'):
        add_text(data['jeudi_apres_a'], 585, 285, 9)
    
    # Vendredi Y=304
    if data.get('vendredi_matin_de'):
        add_text(data['vendredi_matin_de'], 211, 304, 9)
    if data.get('vendredi_matin_a'):
        add_text(data['vendredi_matin_a'], 276, 304, 9)
    if data.get('vendredi_pause_de'):
        add_text(data['vendredi_pause_de'], 363, 304, 9)
    if data.get('vendredi_pause_a'):
        add_text(data['vendredi_pause_a'], 423, 304, 9)
    if data.get('vendredi_apres_de'):
        add_text(data['vendredi_apres_de'], 522, 304, 9)
    if data.get('vendredi_apres_a'):
        add_text(data['vendredi_apres_a'], 585, 304, 9)
    
    # Samedi Y=331
    if data.get('samedi_matin_de'):
        add_text(data['samedi_matin_de'], 210, 331, 9)
    if data.get('samedi_matin_a'):
        add_text(data['samedi_matin_a'], 276, 331, 9)
    if data.get('samedi_pause_de'):
        add_text(data['samedi_pause_de'], 363, 331, 9)
    if data.get('samedi_pause_a'):
        add_text(data['samedi_pause_a'], 423, 331, 9)
    if data.get('samedi_apres_de'):
        add_text(data['samedi_apres_de'], 522, 331, 9)
    if data.get('samedi_apres_a'):
        add_text(data['samedi_apres_a'], 585, 331, 9)
    
    # Dimanche Y=351
    if data.get('dimanche_matin_de'):
        add_text(data['dimanche_matin_de'], 209, 351, 9)
    if data.get('dimanche_matin_a'):
        add_text(data['dimanche_matin_a'], 276, 351, 9)
    if data.get('dimanche_pause_de'):
        add_text(data['dimanche_pause_de'], 363, 351, 9)
    if data.get('dimanche_pause_a'):
        add_text(data['dimanche_pause_a'], 423, 351, 9)
    if data.get('dimanche_apres_de'):
        add_text(data['dimanche_apres_de'], 522, 351, 9)
    if data.get('dimanche_apres_a'):
        add_text(data['dimanche_apres_a'], 585, 351, 9)
    
    # Other Page 2 fields - EXACT COORDINATES
    if data.get('cameras'):
        add_text(data['cameras'], 427, 387)
    if data.get('trousse_secours'):
        add_text(data['trousse_secours'], 400, 453)
    
    vetements_fourniture = data.get('vetements_fourniture', '')
    if vetements_fourniture == 'Oui':
        add_text('X', 348, 486, 12)
    elif vetements_fourniture == 'Non':
        add_text('X', 385, 485, 12)
    
    vetements_entretien = data.get('vetements_entretien', '')
    if vetements_entretien == 'Oui':
        add_text('X', 347, 518, 12)
    elif vetements_entretien == 'Non':
        add_text('X', 388, 518, 12)
    
    if data.get('primes'):
        add_text(data['primes'], 394, 552)
    if data.get('secretariat_actuel'):
        add_text(data['secretariat_actuel'], 394, 583)
    if data.get('nom_comptable'):
        add_text(data['nom_comptable'], 390, 617)
    if data.get('coord_comptable'):
        add_text(data['coord_comptable'], 390, 648)
    
    origine = data.get('origine', '')
    if origine == 'Internet':
        add_text('X', 173, 683, 12)
    elif origine == 'Comptable':
        add_text('X', 342, 683, 12)
    elif origine == 'Client':
        add_text('X', 174, 716, 12)
    elif origine == 'Autre':
        add_text('X', 341, 716, 12)
    
    if data.get('date_signature'):
        add_text(data['date_signature'], 177, 843)
    
    # Ensure page 2 exists by adding at least a space
    can.drawString(0, 0, " ")
    can.save()
    
    packet.seek(0)
    overlay = PdfReader(packet)
    
    writer = PdfWriter()
    
    # Page 1
    page1 = reader.pages[0]
    if len(overlay.pages) > 0:
        page1.merge_page(overlay.pages[0])
    writer.add_page(page1)
    
    # Page 2
    page2 = reader.pages[1]
    if len(overlay.pages) > 1:
        page2.merge_page(overlay.pages[1])
    writer.add_page(page2)
    
    output = io.BytesIO()
    writer.write(output)
    output.seek(0)
    
    return output

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
