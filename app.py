from flask import Flask, request, jsonify, send_file
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
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
    """Fill PDF using ReportLab overlay with CORRECTED POSITIONING"""
    
    reader = PdfReader(TEMPLATE_PATH)
    packet = io.BytesIO()
    can = canvas.Canvas(packet, pagesize=(595, 842))
    
    # Scale factors
    SCALE_X = 595 / 707
    SCALE_Y = 842 / 1000
    
    def convert_coords(x_img, y_img):
        """Convert image coordinates to PDF coordinates"""
        x_pdf = x_img * SCALE_X
        y_pdf = 842 - (y_img * SCALE_Y)
        return (x_pdf, y_pdf)
    
    def add_text(text, x_img, y_img, font_size=10):
        """Add text at specified position"""
        can.setFont("Helvetica", font_size)
        x_pdf, y_pdf = convert_coords(x_img, y_img)
        can.drawString(x_pdf, y_pdf, str(text))
    
    # PAGE 1 - All coordinates adjusted to START AFTER THE LABEL
    
    # "Reçu par :" - text starts after colon
    if data.get('recu_par'):
        add_text(data['recu_par'], 185, 197)
    
    # Legal form checkboxes - BEFORE the label text
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
    
    # "Nom de la société:" - text starts after colon
    if data.get('nom_societe'):
        add_text(data['nom_societe'], 300, 275)
    
    # "Nom & Prénom du gérant" - text starts after label
    if data.get('nom_prenom_gerant'):
        add_text(data['nom_prenom_gerant'], 335, 308)
    
    # "NISS du gérant" - text starts after label
    if data.get('niss_gerant'):
        add_text(data['niss_gerant'], 240, 340)
    
    # "Adresse du siège social" - text starts after label
    if data.get('adresse_siege_social_1'):
        add_text(data['adresse_siege_social_1'], 325, 373)
    
    # Second line of address (no label, just continuation)
    if data.get('adresse_siege_social_2'):
        add_text(data['adresse_siege_social_2'], 325, 390)
    
    # "Adresse du siège d'exploitation" - text starts after label
    if data.get('adresse_exploitation_1'):
        add_text(data['adresse_exploitation_1'], 325, 423)
    
    # Second line
    if data.get('adresse_exploitation_2'):
        add_text(data['adresse_exploitation_2'], 325, 440)
    
    # "Téléphone / GSM" - text starts after label
    if data.get('telephone_gsm'):
        add_text(data['telephone_gsm'], 260, 505)
    
    # "Adresse e-mail" - text starts after label
    if data.get('email'):
        add_text(data['email'], 245, 538)
    
    # "N° d'entreprise." - text starts after label
    if data.get('num_entreprise'):
        add_text(data['num_entreprise'], 280, 571)
    
    # "Numéro ONSS" - text starts after label
    if data.get('num_onss'):
        add_text(data['num_onss'], 240, 604)
    
    # "Assurance loi via le client" - text starts after label
    if data.get('assurance_loi'):
        add_text(data['assurance_loi'], 360, 637)
    
    # "SEPPT" - text starts after label
    if data.get('seppt'):
        add_text(data['seppt'], 180, 670)
    
    # "Secteur d'activité" - text starts after label
    if data.get('secteur_activite'):
        add_text(data['secteur_activite'], 265, 703)
    
    # First hire reduction checkboxes (Oui/Non/Enquete)
    reduction = data.get('reduction_premier', '')
    if reduction == 'Oui':
        add_text('X', 75, 768, 12)
    elif reduction == 'Non':
        add_text('X', 112, 768, 12)
    elif reduction == 'Enquete':
        add_text('X', 157, 768, 12)
    
    # "Commission paritaire" - text starts after label
    if data.get('commission_paritaire'):
        add_text(data['commission_paritaire'], 295, 803)
    
    # "Indice ONSS" - text starts after label
    if data.get('indice_onss'):
        add_text(data['indice_onss'], 220, 836)
    
    # "Code Nace" - text starts after label
    if data.get('code_nace'):
        add_text(data['code_nace'], 210, 869)
    
    # Guaranteed wage checkboxes (OUI/NON)
    salaire = data.get('salaire_garanti', '')
    if salaire == 'OUI':
        add_text('X', 640, 900, 12)
    elif salaire == 'NON':
        add_text('X', 677, 900, 12)
    
    # Save page 1
    can.showPage()
    
    # PAGE 2
    
    # "Régime horaire" - text starts after label
    if data.get('regime_horaire'):
        add_text(data['regime_horaire'], 255, 146)
    
    # Weekly schedule table - small font for times
    can.setFont("Helvetica", 9)
    
    # Monday (Lundi)
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
    
    # Tuesday (Mardi)
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
    
    # Wednesday (Mercredi)
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
    
    # Thursday (Jeudi)
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
    
    # Friday (Vendredi)
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
    
    # Saturday (Samedi)
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
    
    # Sunday (Dimanche)
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
    
    # "Nombre et Situation des caméras" - text starts after label
    if data.get('cameras'):
        add_text(data['cameras'], 430, 365)
    
    # "Situation de la trousse de secours" - text starts after label
    if data.get('trousse_secours'):
        add_text(data['trousse_secours'], 410, 415)
    
    # Work clothes provision checkboxes (Oui/Non)
    vetements_fourniture = data.get('vetements_fourniture', '')
    if vetements_fourniture == 'Oui':
        add_text('X', 442, 448, 12)
    elif vetements_fourniture == 'Non':
        add_text('X', 479, 448, 12)
    
    # Work clothes maintenance checkboxes (Oui/Non)
    vetements_entretien = data.get('vetements_entretien', '')
    if vetements_entretien == 'Oui':
        add_text('X', 442, 481, 12)
    elif vetements_entretien == 'Non':
        add_text('X', 479, 481, 12)
    
    # "Primes nuit / week-end / autres" - text starts after label
    if data.get('primes'):
        add_text(data['primes'], 380, 514)
    
    # "Secrétariat social actuel" - text starts after label
    if data.get('secretariat_actuel'):
        add_text(data['secretariat_actuel'], 310, 547)
    
    # "Nom du comptable" - text starts after label
    if data.get('nom_comptable'):
        add_text(data['nom_comptable'], 265, 580)
    
    # "Coordonnées du comptable" - text starts after label
    if data.get('coord_comptable'):
        add_text(data['coord_comptable'], 330, 613)
    
    # Origin checkboxes (Internet/Comptable/Client/Autre)
    origine = data.get('origine', '')
    if origine == 'Internet':
        add_text('X', 145, 662, 12)
    elif origine == 'Comptable':
        add_text('X', 341, 662, 12)
    elif origine == 'Client':
        add_text('X', 145, 696, 12)
    elif origine == 'Autre':
        add_text('X', 341, 696, 12)
    
    # "Date :" - text starts after colon
    if data.get('date_signature'):
        add_text(data['date_signature'], 160, 846)
    
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
