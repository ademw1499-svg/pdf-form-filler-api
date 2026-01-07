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
    
    ALIGN_X = 440
    
    # PAGE 1 - Keep exact Y positions from working version
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
    if data.get('adresse_exploitation_1'):
        add_text(data['adresse_exploitation_1'], ALIGN_X, 423)
    if data.get('adresse_exploitation_2'):
        add_text(data['adresse_exploitation_2'], ALIGN_X, 440)
    if data.get('telephone_gsm'):
        add_text(data['telephone_gsm'], ALIGN_X, 505)
    if data.get('email'):
        add_text(data['email'], ALIGN_X, 538)
    if data.get('num_entreprise'):
        add_text(data['num_entreprise'], ALIGN_X, 571)
    if data.get('num_onss'):
        add_text(data['num_onss'], ALIGN_X, 604)
    if data.get('assurance_loi'):
        add_text(data['assurance_loi'], ALIGN_X, 637)
    if data.get('seppt'):
        add_text(data['seppt'], ALIGN_X, 670)
    if data.get('secteur_activite'):
        add_text(data['secteur_activite'], ALIGN_X, 703)
    
    reduction = data.get('reduction_premier', '')
    if reduction == 'Oui':
        add_text('X', 75, 755, 12)
    elif reduction == 'Non':
        add_text('X', 112, 755, 12)
    
    if data.get('commission_paritaire'):
        add_text(data['commission_paritaire'], 295, 788)
    if data.get('indice_onss'):
        add_text(data['indice_onss'], 220, 821)
    if data.get('code_nace'):
        add_text(data['code_nace'], 210, 854)
    
    salaire = data.get('salaire_garanti', '')
    if salaire == 'OUI':
        add_text('X', 640, 900, 12)
    elif salaire == 'NON':
        add_text('X', 677, 900, 12)
    
    can.showPage()
    
    # PAGE 2 - KEEP SAME Y POSITIONS FROM WORKING VERSION
    PAGE2_ALIGN_X = 440
    
    # Régime horaire - SAME Y as working version
    if data.get('regime_horaire'):
        add_text(data['regime_horaire'], 255, 146)
    
    # Schedule table - KEEP EXACT Y VALUES
    # Lundi - Y=224
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
    
    # Mardi - Y=243
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
    
    # Mercredi - Y=262
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
    
    # Jeudi - Y=281
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
    
    # Vendredi - Y=300
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
    
    # Samedi - Y=319
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
    
    # Dimanche - Y=338
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
    
    # Bottom fields - KEEP SAME Y AS WORKING VERSION
    if data.get('cameras'):
        add_text(data['cameras'], PAGE2_ALIGN_X, 365)  # SAME Y
    
    if data.get('trousse_secours'):
        add_text(data['trousse_secours'], PAGE2_ALIGN_X, 415)  # SAME Y
    
    vetements_fourniture = data.get('vetements_fourniture', '')
    if vetements_fourniture == 'Oui':
        add_text('X', 442, 448, 12)  # SAME Y
    elif vetements_fourniture == 'Non':
        add_text('X', 479, 448, 12)  # SAME Y
    
    vetements_entretien = data.get('vetements_entretien', '')
    if vetements_entretien == 'Oui':
        add_text('X', 442, 481, 12)  # SAME Y
    elif vetements_entretien == 'Non':
        add_text('X', 479, 481, 12)  # SAME Y
    
    if data.get('primes'):
        add_text(data['primes'], PAGE2_ALIGN_X, 514)  # SAME Y
    
    if data.get('secretariat_actuel'):
        add_text(data['secretariat_actuel'], PAGE2_ALIGN_X, 547)  # SAME Y
    
    if data.get('nom_comptable'):
        add_text(data['nom_comptable'], PAGE2_ALIGN_X, 580)  # SAME Y
    
    if data.get('coord_comptable'):
        add_text(data['coord_comptable'], PAGE2_ALIGN_X, 613)  # SAME Y
    
    origine = data.get('origine', '')
    if origine == 'Internet':
        add_text('X', 145, 662, 12)  # SAME Y
    elif origine == 'Comptable':
        add_text('X', 341, 662, 12)  # SAME Y
    elif origine == 'Client':
        add_text('X', 145, 696, 12)  # SAME Y
    elif origine == 'Autre':
        add_text('X', 341, 696, 12)  # SAME Y
    
    if data.get('date_signature'):
        add_text(data['date_signature'], 160, 846)  # SAME Y
    
    can.save()
    
    packet.seek(0)
    overlay = PdfReader(packet)
    
    writer = PdfWriter()
    
    page1 = reader.pages[0]
    page1.merge_page(overlay.pages[0])
    writer.add_page(page1)
    
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
