from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
import io
import os
import re
import json
import zipfile
import requests
from datetime import datetime
from html import unescape as _unescape   # décode TOUTES les entités HTML (&Acirc; -> Â, &eacute; -> é…)

app = Flask(__name__)
CORS(app)

# ============== CONFIGURATION ==============
TEMPLATES = {
    'employer': 'FICHE_RENSEIGNEMENTS_EMPLOYEUR_FR_2020.pdf',
    'travailleur': 'FICHE_RENSEIGNEMENTS_TRAVAILLEUR_FR.pdf',
    'independant': 'FICHE_RENSEIGNEMENTS_INDEPENDANT.pdf',
    'att_accident_fr': 'ATTESTATION_ASSURANCE_ACCIDENT_DE_TRAVAIL.pdf',
    'att_seppt_fr': 'ATTESTATION_SEPPT.pdf',
    'dispense': 'Dispense_partielle_de_versement_du_precompte_professionnel.pdf',
    'mensura': 'FOR140106_FR.pdf',
    'procuration': 'PROCURATION.pdf',
    'offre_fr': 'Offre_de_collaboration_FR_2025-2026.pdf',
    'offre_nl': 'Offre_de_collaboration_NL_2025-2026.pdf',
    'att_accident_nl': 'Attestation_accident_travail_NL.pdf',
    'att_seppt_nl': 'Attestation_SEPPT_NL.pdf',
}

# ============== STATIC DOCUMENTS ==============
STATIC_DOCUMENTS = {
    'obligation_employeur': ('Obligation_Employeur_2025.pdf', 'Obligation_Employeur_2025.pdf'),
}

# FIX: obligation_employeur now bundled with employer + travailleur + offre
DOCUMENT_BUNDLES = {
    'offre':       ['obligation_employeur'],
    'employer':    ['obligation_employeur'],
    'travailleur': ['obligation_employeur'],
    'independant': [],
    'seppt':       [],
    'accident':    [],
    'dispense':    [],
    'procuration': [],
    'mensura':     [],
}

# ============== HELPER FUNCTIONS ==============
SCALE_X, SCALE_Y = 595/707, 842/1000

def cvt(x, y):
    return (x * SCALE_X, 842 - (y * SCALE_Y))

_ISO_DATE = re.compile(r'^(\d{4})-(\d{2})-(\d{2})$')
def txt(c, t, x, y, s=10):
    t = str(t)
    # Filet de sécurité : le frontend envoie parfois la date brute AAAA-MM-JJ
    # (input HTML date) au lieu de JJ/MM/AAAA. On la remet à l'endroit.
    m = _ISO_DATE.match(t)
    if m:
        t = f'{m.group(3)}/{m.group(2)}/{m.group(1)}'
    c.setFont("Helvetica", s)
    c.drawString(*cvt(x, y), t)

def newcan():
    p = io.BytesIO()
    return p, canvas.Canvas(p, pagesize=(595, 842))

def merge(tpl, pkt, npg=1):
    pkt.seek(0)
    ov = PdfReader(pkt)
    rd = PdfReader(tpl)
    wr = PdfWriter()
    for i in range(len(rd.pages)):
        pg = rd.pages[i]
        # Si le template est tourné (ex: PROCURATION.pdf en paysage /Rotate 270),
        # on "remet la page droite" avant de fusionner, sinon le texte de l'overlay
        # (dessiné en portrait 595x842) atterrit hors de la zone visible.
        if pg.get('/Rotate'):
            pg.transfer_rotation_to_content()
        if i < len(ov.pages):
            pg.merge_page(ov.pages[i])
        wr.add_page(pg)
    out = io.BytesIO()
    wr.write(out)
    out.seek(0)
    return out

def get_static_document_bytes(doc_key):
    if doc_key not in STATIC_DOCUMENTS:
        return None, None
    filename, display_name = STATIC_DOCUMENTS[doc_key]
    if os.path.exists(filename):
        with open(filename, 'rb') as f:
            return f.read(), display_name
    print(f"WARNING: Static document not found: {filename}")
    return None, None

def get_bundle_for_document(doc_type):
    return DOCUMENT_BUNDLES.get(doc_type, [])

# Compat frontend : pour l'Offre en FR, le frontend envoie 4 morceaux
# (offre1, offre2, offre3, offre4) alors que le backend génère l'Offre en un
# seul document de 20 pages. On regroupe ces morceaux en un unique 'offre'.
OFFRE_PARTS = {'offre1', 'offre2', 'offre3', 'offre4'}
def normalize_documents(documents):
    if any(d in OFFRE_PARTS for d in documents):
        documents = [d for d in documents if d not in OFFRE_PARTS]
        if 'offre' not in documents:
            documents.append('offre')
    return documents

def with_signatory_fallbacks(d):
    """Filet de sécurité : le frontend écrase parfois nom_soussigne / domicile /
    etablie par du vide (bug d'assemblage des données). On les reconstitue depuis
    le nom du gérant et l'adresse du siège social, présents dans les données."""
    d = dict(d)
    if not d.get('nom_soussigne'): d['nom_soussigne'] = d.get('nom_prenom_gerant') or ''
    if not d.get('domicile_1'): d['domicile_1'] = d.get('adresse_siege_social_1') or ''
    if not d.get('domicile_2'): d['domicile_2'] = d.get('adresse_siege_social_2') or ''
    if not d.get('etablie_1'): d['etablie_1'] = d.get('adresse_siege_social_1') or ''
    if not d.get('etablie_2'): d['etablie_2'] = d.get('adresse_siege_social_2') or ''
    return d

# ============== PERSISTANCE SUPABASE ==============
# Connexion lue depuis les variables d'environnement (Railway) — JAMAIS en dur,
# car le repo est public. Si non configuré, la sauvegarde est ignorée silencieusement
# (la génération des PDF continue de marcher normalement).
SUPABASE_URL = (os.environ.get('SUPABASE_URL') or '').rstrip('/')
SUPABASE_KEY = os.environ.get('SUPABASE_SERVICE_KEY') or os.environ.get('SUPABASE_KEY')

def save_employeur(form_data):
    """Enregistre/met à jour un employeur dans Supabase (upsert sur num_entreprise).
    Ne lève jamais d'erreur : un échec de sauvegarde ne doit pas casser la génération."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return  # Supabase pas encore configuré
    num = (str(form_data.get('num_entreprise') or '')).strip()
    if not num:
        print("[SUPABASE] pas de num_entreprise -> employeur non sauvegardé")
        return
    try:
        row = {
            'num_entreprise': num,
            'nom_societe': form_data.get('nom_societe') or '',
            'email': form_data.get('email') or '',
            'data': form_data,
            'updated_at': datetime.now().isoformat(),
        }
        r = requests.post(
            f"{SUPABASE_URL}/rest/v1/employeurs?on_conflict=num_entreprise",
            headers={
                'apikey': SUPABASE_KEY,
                'Authorization': f'Bearer {SUPABASE_KEY}',
                'Content-Type': 'application/json',
                'Prefer': 'resolution=merge-duplicates,return=minimal',
            },
            json=row, timeout=10,
        )
        if r.status_code >= 300:
            print(f"[SUPABASE] échec sauvegarde {r.status_code}: {r.text[:200]}")
        else:
            print(f"[SUPABASE] employeur sauvegardé: {num}")
    except Exception as e:
        print(f"[SUPABASE] erreur: {e}")

# ============== HEALTH & DEBUG ==============
@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        "status": "healthy",
        "ts": datetime.now().isoformat(),
        "bilingual_support": True,
        "bilingual_documents": ["seppt", "accident", "offre"],
        "static_documents": list(STATIC_DOCUMENTS.keys()),
        "document_bundles": {k: v for k, v in DOCUMENT_BUNDLES.items() if v}
    })

@app.route('/debug-config', methods=['GET'])
def debug_config():
    template_status = {}
    for key, filename in TEMPLATES.items():
        template_status[key] = {"filename": filename, "exists": os.path.exists(filename)}
    static_status = {}
    for key, (filename, display) in STATIC_DOCUMENTS.items():
        static_status[key] = {
            "filename": filename, "display_name": display,
            "exists": os.path.exists(filename),
            "size_kb": round(os.path.getsize(filename)/1024, 1) if os.path.exists(filename) else 0
        }
    return jsonify({
        "templates": template_status, "static_documents": static_status,
        "document_bundles": DOCUMENT_BUNDLES, "supported_languages": ["fr", "nl"]
    })

# ============== LECTURE EMPLOYEURS (pour le portail) ==============
def _supabase_headers():
    return {'apikey': SUPABASE_KEY, 'Authorization': f'Bearer {SUPABASE_KEY}'}

def verify_user_token(req):
    """Vérifie le token Supabase de l'utilisateur connecté (login gestionnaire).
    Le frontend envoie 'Authorization: Bearer <access_token>'. On le valide
    auprès de Supabase Auth. Retourne l'email de l'utilisateur si valide, sinon None."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return None
    auth = req.headers.get('Authorization', '')
    if not auth.startswith('Bearer '):
        return None
    token = auth.split(' ', 1)[1].strip()
    if not token:
        return None
    try:
        r = requests.get(
            f"{SUPABASE_URL}/auth/v1/user",
            headers={'apikey': SUPABASE_KEY, 'Authorization': f'Bearer {token}'},
            timeout=10)
        if r.status_code != 200:
            return None
        # Retourne l'email de l'utilisateur (sert de "poste de traitement" par défaut).
        return (r.json() or {}).get('email') or 'inconnu'
    except Exception:
        return None

@app.route('/employeurs', methods=['GET'])
def list_employeurs():
    """Liste/recherche les employeurs enregistrés (pour le portail)."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return jsonify({"error": "Supabase non configuré"}), 503
    if not verify_user_token(request):
        return jsonify({"error": "Non authentifié"}), 401
    q = (request.args.get('q') or '').strip().lower()
    try:
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/employeurs"
            "?select=num_entreprise,nom_societe,email,updated_at&order=updated_at.desc&limit=500",
            headers=_supabase_headers(), timeout=10)
        rows = r.json() if r.status_code < 300 else []
        if q:
            rows = [x for x in rows
                    if q in (x.get('nom_societe') or '').lower()
                    or q in (x.get('num_entreprise') or '').lower()]
        return jsonify(rows[:50]), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/employeurs/<path:num>', methods=['GET'])
def get_employeur(num):
    """Récupère un employeur complet (avec toutes ses données) pour pré-remplir."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return jsonify({"error": "Supabase non configuré"}), 503
    if not verify_user_token(request):
        return jsonify({"error": "Non authentifié"}), 401
    try:
        import urllib.parse
        nq = urllib.parse.quote(num)
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/employeurs?num_entreprise=eq.{nq}&select=*&limit=1",
            headers=_supabase_headers(), timeout=10)
        rows = r.json() if r.status_code < 300 else []
        if not rows:
            return jsonify({"error": "Employeur introuvable"}), 404
        return jsonify(rows[0]), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ============== ÉTAT DE PRESTATIONS (parser) ==============
def parse_etat_prestation(reader):
    """Lit un état de prestation Prisma (PDF texte) -> client, période, travailleurs."""
    lines = []
    for pg in reader.pages:
        lines += [l.rstrip() for l in (pg.extract_text() or '').splitlines()]
    full = "\n".join(lines)
    client = lines[1].strip() if len(lines) > 1 else ""
    onss = (re.search(r"No ONSS:\s*([\d-]+)", full) or [None, ""])[1]
    # Numéro d'employeur Prisma : 1re ligne type "0012/002586" -> 2586
    mnum = re.search(r"^\s*\d+/0*(\d+)", lines[0]) if lines else None
    numero_employeur = mnum.group(1) if mnum else ""
    per = re.search(r"(\d{2}/\d{2}/\d{4})\s*jusqu'au\s*(\d{2}/\d{2}/\d{4})", full)
    periode = {"debut": per.group(1), "fin": per.group(2)} if per else {}
    workers = []
    for i, l in enumerate(lines):
        m = re.match(r"^(\d{4,5})([A-ZÀ-Ÿ][^\d].*)$", l)
        # un vrai travailleur : la ligne suivante commence par "No.rég.nat"
        if not m or i + 1 >= len(lines) or not lines[i + 1].lstrip().startswith("No.rég.nat"):
            continue
        bloc = "\n".join(lines[i:i + 15])
        reg = re.search(r"No\.rég\.nat\.:\s*([\d.]+\s+\d{3}-\d{2})(\d+,\d{2})?", lines[i + 1])
        regime = re.search(r"Mois\s+(\d+)", bloc)
        entree = re.search(r"(\d{2}/\d{2}/\d{4})", "\n".join(lines[i + 2:i + 15]))
        workers.append({
            "matricule": m.group(1), "nom": m.group(2).strip(),
            "niss": reg.group(1) if reg else "",
            "heures_jour": (reg.group(2) if reg and reg.group(2) else ""),
            "regime": regime.group(1) if regime else "",
            "date_entree": entree.group(1) if entree else "",
        })
    return {"client": client, "onss": onss, "numero_employeur": numero_employeur, "periode": periode, "travailleurs": workers}

@app.route('/parse-prestations', methods=['POST'])
def parse_prestations():
    """Reçoit l'état Prisma (PDF) et renvoie les données structurées pour la grille."""
    f = request.files.get('file')
    if not f:
        return jsonify({"error": "Aucun fichier"}), 400
    try:
        return jsonify(parse_etat_prestation(PdfReader(f))), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ============== PRESTATIONS -> PRISMA (pont avec l'automatisation Mode D) ==============
# Correspondance codes portail -> codes paie Prisma.
# ⚠️ À VALIDER avec la conseillère juridique (notamment maladie ouvrier 301 vs employé 305).
PORTAIL_VERS_PRISMA = {
    # Codes validés par la conseillère juridique (questionnaire 2026-06).
    'P':   '0001',  # presté normal
    'HC':  '0002',  # heures complémentaires
    'HS':  '010',   # heures supplémentaires
    'JF':  '100',   # jour férié payé
    'RF':  '103',   # récupération de jour férié
    'VA':  '200',   # vacances légales
    'VX':  '201',   # vacances extra-légales
    'MO1': '301',   # maladie ouvrier J1-7
    'MO2': '302',   # maladie ouvrier J8-14
    'MO3': '303',   # maladie ouvrier J15-30
    'MU':  '304',   # maladie après garanti (mutuelle)
    'M':   '305',   # maladie garanti (employé)
    'ML':  '346',   # maladie longue durée
    'PC':  '110',   # petit chômage
    'MAT': '351',   # maternité
    'PAT1':'0357',  # paternité (employeur, 3j)
    'PAT2':'0532',  # paternité (mutuelle, 17j)
    'AB':  '651',   # absence non payée / congé sans solde
    'INJ': '652',   # absence injustifiée
    # À confirmer avec la juriste : Accident de travail (code Prisma manquant).
}

def _heures_float(h):
    try:
        return round(float(str(h).replace(',', '.')), 2)
    except Exception:
        return 0.0

def construire_etats(travailleurs):
    """travailleurs = { "NOM": { "jour": [ {code, h}, ... ] } }
    -> ETATS Mode D = { "NOM": { jour(str): {"code": <prisma>, "heures": float} } }.
    v1 : on prend le 1er segment du jour (le départage multi-codes sera étendu plus tard)."""
    etats = {}
    for nom, jours in (travailleurs or {}).items():
        plan = {}
        for jour, segs in (jours or {}).items():
            if not segs:
                continue
            seg = segs[0]
            pc = seg.get('code')
            code = PORTAIL_VERS_PRISMA.get(pc, '0001' if pc not in PORTAIL_VERS_PRISMA else pc)
            plan[str(int(jour))] = {"code": code, "heures": _heures_float(seg.get('h'))}
        if plan:
            etats[nom] = plan
    return etats

@app.route('/prestations', methods=['POST'])
def save_prestations():
    """Le portail enregistre les prestations validées (gestionnaire connecté)."""
    user_email = verify_user_token(request)
    if not user_email:
        return jsonify({"error": "Non authentifié"}), 401
    if not SUPABASE_URL or not SUPABASE_KEY:
        return jsonify({"error": "Supabase non configuré"}), 503
    d = request.get_json() or {}
    employeur = str(d.get('employeur') or '').strip()
    periode = str(d.get('periode') or '').strip()
    if not employeur or not periode:
        return jsonify({"error": "employeur et periode requis"}), 400
    etats = construire_etats(d.get('travailleurs') or {})
    # Poste de traitement : par défaut le gestionnaire connecté (sa validation ne sera
    # traitée QUE par le veilleur de SON PC). En "mode test" -> poste 'TEST' (isolé du réel).
    poste = 'TEST' if d.get('test') else user_email
    row = {
        'employeur': employeur, 'periode': periode,
        'client_nom': d.get('client') or '', 'etats': etats,
        'poste': poste,
        'statut': 'a_traiter',  # le veilleur (PC Prisma) traitera puis passera 'traite'
        'updated_at': datetime.now().isoformat(),
    }
    avantages = d.get('avantages')
    if avantages:
        row['avantages'] = avantages  # nécessite la colonne 'avantages' (sinon repli auto ci-dessous)

    def _push(payload):
        return requests.post(
            f"{SUPABASE_URL}/rest/v1/prestations?on_conflict=employeur,periode,poste",
            headers={**_supabase_headers(), 'Content-Type': 'application/json',
                     'Prefer': 'resolution=merge-duplicates,return=minimal'},
            json=payload, timeout=10)
    try:
        r = _push(row)
        # Repli : si la colonne 'avantages' n'existe pas encore, on réessaie sans, pour
        # ne jamais bloquer l'enregistrement des prestations.
        if r.status_code >= 300 and 'avantages' in row and 'avantages' in (r.text or ''):
            row.pop('avantages', None)
            r = _push(row)
        if r.status_code >= 300:
            return jsonify({"error": f"Supabase {r.status_code}: {r.text[:200]}"}), 500
        return jsonify({"ok": True, "employeur": employeur, "periode": periode,
                        "travailleurs": len(etats), "poste": poste}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/prestations', methods=['GET'])
def get_prestations():
    """Lu par le serveur Windows (Mode D). Protégé par un token partagé (env PRESTATIONS_TOKEN)."""
    token_attendu = os.environ.get('PRESTATIONS_TOKEN')
    if not token_attendu:
        return jsonify({"error": "PRESTATIONS_TOKEN non configuré"}), 503
    if request.headers.get('X-Prestations-Token') != token_attendu:
        return jsonify({"error": "Non autorisé"}), 401
    if not SUPABASE_URL or not SUPABASE_KEY:
        return jsonify({"error": "Supabase non configuré"}), 503
    employeur = (request.args.get('employeur') or '').strip()
    periode = (request.args.get('periode') or '').strip()
    if not employeur or not periode:
        return jsonify({"error": "employeur et periode requis"}), 400
    try:
        import urllib.parse
        q = (f"employeur=eq.{urllib.parse.quote(employeur)}"
             f"&periode=eq.{urllib.parse.quote(periode)}&select=*&limit=1")
        r = requests.get(f"{SUPABASE_URL}/rest/v1/prestations?{q}", headers=_supabase_headers(), timeout=10)
        rows = r.json() if r.status_code < 300 else []
        if not rows:
            return jsonify({"error": "Aucune prestation trouvée pour cet employeur/période"}), 404
        return jsonify(rows[0]), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/prestations/mes', methods=['GET'])
def prestations_mes():
    """Tableau de bord : les prestations de la gestionnaire connectée (son poste =
    son email) + celles en mode test. Toutes statuts, plus récentes d'abord."""
    email = verify_user_token(request)
    if not email:
        return jsonify({"error": "Non authentifié"}), 401
    if not SUPABASE_URL or not SUPABASE_KEY:
        return jsonify({"error": "Supabase non configuré"}), 503
    try:
        import urllib.parse
        postes = f'"{email}","TEST"'
        q = (f"poste=in.({urllib.parse.quote(postes)})"
             f"&select=employeur,periode,client_nom,statut,poste,updated_at,etats"
             f"&order=updated_at.desc&limit=200")
        r = requests.get(f"{SUPABASE_URL}/rest/v1/prestations?{q}", headers=_supabase_headers(), timeout=10)
        rows = r.json() if r.status_code < 300 else []
        # allège : nb travailleurs au lieu du détail etats
        for row in (rows if isinstance(rows, list) else []):
            row['nb_travailleurs'] = len(row.pop('etats', {}) or {})
        return jsonify(rows if isinstance(rows, list) else []), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/prestations/a-traiter', methods=['GET'])
def prestations_a_traiter():
    """Lu en boucle par le veilleur (PC Prisma) : liste les prestations validees
    pas encore encodees. Protege par le token partage (PRESTATIONS_TOKEN)."""
    token_attendu = os.environ.get('PRESTATIONS_TOKEN')
    if not token_attendu:
        return jsonify({"error": "PRESTATIONS_TOKEN non configuré"}), 503
    if request.headers.get('X-Prestations-Token') != token_attendu:
        return jsonify({"error": "Non autorisé"}), 401
    if not SUPABASE_URL or not SUPABASE_KEY:
        return jsonify({"error": "Supabase non configuré"}), 503
    # Le veilleur indique SON poste : il ne reçoit QUE les prestations qui lui sont destinées.
    poste = (request.args.get('poste') or '').strip()
    if not poste:
        return jsonify({"error": "poste requis (chaque veilleur doit s'identifier)"}), 400
    try:
        import urllib.parse
        q = (f"statut=eq.a_traiter&poste=eq.{urllib.parse.quote(poste)}"
             f"&select=*&order=updated_at.asc")
        r = requests.get(f"{SUPABASE_URL}/rest/v1/prestations?{q}", headers=_supabase_headers(), timeout=10)
        rows = r.json() if r.status_code < 300 else []
        return jsonify(rows if isinstance(rows, list) else []), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/prestations/traite', methods=['POST'])
def prestations_marquer_traite():
    """Le veilleur marque une prestation comme traitee (ou en erreur) apres encodage.
    Protege par le token partage (PRESTATIONS_TOKEN)."""
    token_attendu = os.environ.get('PRESTATIONS_TOKEN')
    if not token_attendu:
        return jsonify({"error": "PRESTATIONS_TOKEN non configuré"}), 503
    if request.headers.get('X-Prestations-Token') != token_attendu:
        return jsonify({"error": "Non autorisé"}), 401
    if not SUPABASE_URL or not SUPABASE_KEY:
        return jsonify({"error": "Supabase non configuré"}), 503
    d = request.get_json() or {}
    employeur = str(d.get('employeur') or '').strip()
    periode = str(d.get('periode') or '').strip()
    poste = str(d.get('poste') or '').strip()
    statut = str(d.get('statut') or 'traite').strip()
    if statut not in ('traite', 'erreur', 'a_traiter'):
        statut = 'traite'
    if not employeur or not periode or not poste:
        return jsonify({"error": "employeur, periode et poste requis"}), 400
    try:
        import urllib.parse
        q = (f"employeur=eq.{urllib.parse.quote(employeur)}"
             f"&periode=eq.{urllib.parse.quote(periode)}"
             f"&poste=eq.{urllib.parse.quote(poste)}")
        r = requests.patch(
            f"{SUPABASE_URL}/rest/v1/prestations?{q}",
            headers={**_supabase_headers(), 'Content-Type': 'application/json', 'Prefer': 'return=minimal'},
            json={'statut': statut, 'updated_at': datetime.now().isoformat()}, timeout=10)
        if r.status_code >= 300:
            return jsonify({"error": f"Supabase {r.status_code}: {r.text[:200]}"}), 500
        return jsonify({"ok": True, "employeur": employeur, "periode": periode, "statut": statut}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ============== ROSTER (mémoire des travailleurs par employeur) ==============
@app.route('/roster', methods=['POST'])
def save_roster():
    """Mémorise la liste des travailleurs d'un employeur (pour la saisie manuelle
    sans PDF). Gestionnaire connecté."""
    if not verify_user_token(request):
        return jsonify({"error": "Non authentifié"}), 401
    if not SUPABASE_URL or not SUPABASE_KEY:
        return jsonify({"error": "Supabase non configuré"}), 503
    d = request.get_json() or {}
    employeur = str(d.get('employeur') or '').strip()
    travailleurs = d.get('travailleurs') or []
    if not employeur or not isinstance(travailleurs, list) or not travailleurs:
        return jsonify({"error": "employeur et travailleurs requis"}), 400
    row = {'employeur': employeur, 'client_nom': d.get('client') or '',
           'travailleurs': travailleurs, 'updated_at': datetime.now().isoformat()}
    try:
        r = requests.post(
            f"{SUPABASE_URL}/rest/v1/rosters?on_conflict=employeur",
            headers={**_supabase_headers(), 'Content-Type': 'application/json',
                     'Prefer': 'resolution=merge-duplicates,return=minimal'},
            json=row, timeout=10)
        if r.status_code >= 300:
            return jsonify({"error": f"Supabase {r.status_code}: {r.text[:200]}"}), 500
        return jsonify({"ok": True, "employeur": employeur, "travailleurs": len(travailleurs)}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/roster', methods=['GET'])
def get_roster():
    """Renvoie les travailleurs mémorisés d'un employeur (pour pré-remplir la saisie manuelle)."""
    if not verify_user_token(request):
        return jsonify({"error": "Non authentifié"}), 401
    if not SUPABASE_URL or not SUPABASE_KEY:
        return jsonify({"error": "Supabase non configuré"}), 503
    employeur = (request.args.get('employeur') or '').strip()
    if not employeur:
        return jsonify({"error": "employeur requis"}), 400
    try:
        import urllib.parse
        q = f"employeur=eq.{urllib.parse.quote(employeur)}&select=*&limit=1"
        r = requests.get(f"{SUPABASE_URL}/rest/v1/rosters?{q}", headers=_supabase_headers(), timeout=10)
        rows = r.json() if r.status_code < 300 else []
        return jsonify(rows[0] if rows else {"employeur": employeur, "travailleurs": []}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ============== PAIE : jobs pilotés depuis le portail, exécutés par le veilleur ==============
@app.route('/paie/lancer', methods=['POST'])
def paie_lancer():
    """Le portail demande un calcul de paie (module live). Crée un job 'pending'
    que le veilleur du poste (email de la gestionnaire, ou TEST) exécutera."""
    email = verify_user_token(request)
    if not email:
        return jsonify({"error": "Non authentifié"}), 401
    if not SUPABASE_URL or not SUPABASE_KEY:
        return jsonify({"error": "Supabase non configuré"}), 503
    d = request.get_json() or {}
    employeur = str(d.get('employeur') or '').strip()
    if not employeur:
        return jsonify({"error": "employeur requis"}), 400
    row = {
        'employeur': employeur, 'mois': int(d.get('mois') or 0), 'annee': int(d.get('annee') or 0),
        'mode': str(d.get('mode') or 'A').strip()[:1].upper() or 'A',
        'module': str(d.get('module') or 'paie').strip(),
        'poste': 'TEST' if d.get('test') else email,
        'statut': 'pending', 'evenements': [],
    }
    try:
        r = requests.post(
            f"{SUPABASE_URL}/rest/v1/paie_jobs",
            headers={**_supabase_headers(), 'Content-Type': 'application/json', 'Prefer': 'return=representation'},
            json=row, timeout=10)
        if r.status_code >= 300:
            return jsonify({"error": f"Supabase {r.status_code}: {r.text[:200]}"}), 500
        created = (r.json() or [{}])[0]
        return jsonify({"ok": True, "id": created.get('id'), "poste": row['poste']}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/paie/a-traiter', methods=['GET'])
def paie_a_traiter():
    """Le veilleur récupère les jobs paie 'pending' de SON poste."""
    token_attendu = os.environ.get('PRESTATIONS_TOKEN')
    if not token_attendu or request.headers.get('X-Prestations-Token') != token_attendu:
        return jsonify({"error": "Non autorisé"}), 401
    poste = (request.args.get('poste') or '').strip()
    if not poste:
        return jsonify({"error": "poste requis"}), 400
    try:
        import urllib.parse
        q = (f"statut=eq.pending&poste=eq.{urllib.parse.quote(poste)}"
             f"&select=*&order=created_at.asc")
        r = requests.get(f"{SUPABASE_URL}/rest/v1/paie_jobs?{q}", headers=_supabase_headers(), timeout=10)
        return jsonify(r.json() if r.status_code < 300 else []), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/paie/maj', methods=['POST'])
def paie_maj():
    """Le veilleur met à jour un job (statut + liste d'événements travailleur)."""
    token_attendu = os.environ.get('PRESTATIONS_TOKEN')
    if not token_attendu or request.headers.get('X-Prestations-Token') != token_attendu:
        return jsonify({"error": "Non autorisé"}), 401
    d = request.get_json() or {}
    job_id = d.get('id')
    if not job_id:
        return jsonify({"error": "id requis"}), 400
    patch = {'updated_at': datetime.now().isoformat()}
    if 'statut' in d:
        patch['statut'] = str(d['statut'])[:20]
    if 'evenements' in d:
        patch['evenements'] = d['evenements']
    try:
        r = requests.patch(
            f"{SUPABASE_URL}/rest/v1/paie_jobs?id=eq.{int(job_id)}",
            headers={**_supabase_headers(), 'Content-Type': 'application/json', 'Prefer': 'return=minimal'},
            json=patch, timeout=10)
        if r.status_code >= 300:
            return jsonify({"error": f"Supabase {r.status_code}: {r.text[:200]}"}), 500
        return jsonify({"ok": True}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/paie/job/<int:job_id>', methods=['GET'])
def paie_job(job_id):
    """Le portail suit l'avancement d'un job (statut + événements)."""
    if not verify_user_token(request):
        return jsonify({"error": "Non authentifié"}), 401
    try:
        q = f"id=eq.{job_id}&select=*&limit=1"
        r = requests.get(f"{SUPABASE_URL}/rest/v1/paie_jobs?{q}", headers=_supabase_headers(), timeout=10)
        rows = r.json() if r.status_code < 300 else []
        if not rows:
            return jsonify({"error": "Job introuvable"}), 404
        return jsonify(rows[0]), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ============== BCE / BANQUE-CARREFOUR DES ENTREPRISES ==============
def _bce_forme(texte):
    """Texte 'Forme légale' BCE -> valeur du select du portail."""
    t = (texte or '').lower()
    if 'responsabilit' in t and 'limit' in t:
        return 'SRL'
    if 'anonyme' in t:
        return 'SA'
    if 'coop' in t:
        return 'SC'
    if 'sans but lucratif' in t or 'association' in t:
        return 'ASBL'
    if 'personne physique' in t:
        return 'PERSONNE PHYSIQUE'
    return ''

def _bce_data(numero):
    """Interroge VIES (nom+adresse, JSON officiel UE) et la fiche publique BCE
    (dénomination, forme légale, NACE, ONSS, représentants). Données publiques.
    Retourne un dict `out` (avec clé 'trouve'), ou {'error':…, '_status':…}."""
    num = re.sub(r'\D', '', numero or '')
    if len(num) == 9:
        num = '0' + num
    if len(num) != 10:
        return {"error": "Numéro invalide — attendu 10 chiffres (ex : BE 0123.456.789)", "_status": 400}
    fmt = f"{num[0:4]}.{num[4:7]}.{num[7:10]}"
    out = {"num_entreprise": f"BE {fmt}", "num_tva": f"BE {fmt}", "trouve": False}

    # 1) VIES (Commission européenne) : validité + nom + adresse
    try:
        r = requests.get(
            f"https://ec.europa.eu/taxation_customs/vies/rest-api/ms/BE/vat/{num}",
            timeout=12)
        d = r.json() if r.status_code < 300 else {}
        if d.get('isValid'):
            out['trouve'] = True
            name = (d.get('name') or '').strip()
            if name and name != '---':
                out['nom_societe'] = name
            addr = (d.get('address') or '').replace('\r', '')
            lignes = [l.strip() for l in addr.split('\n') if l.strip()]
            if lignes:
                out['adresse_siege_social_1'] = lignes[0]
            if len(lignes) > 1:
                out['adresse_siege_social_2'] = ' '.join(lignes[1:])
    except Exception:
        pass

    # 2) Fiche publique BCE : dénomination officielle + forme légale (best effort)
    try:
        r = requests.get(
            "https://kbopub.economie.fgov.be/kbopub/toonondernemingps.html",
            params={"ondernemingsnummer": num, "lang": "fr"},
            headers={"User-Agent": "Mozilla/5.0"}, timeout=12)
        html = r.text if r.status_code < 300 else ''
        def _cell(pattern):
            m = re.search(pattern + r'.*?<td[^>]*>(.*?)</td>', html, re.S)
            if not m:
                return ''
            t = _unescape(re.sub(r'<[^>]+>|\s+', ' ', m.group(1))).strip()
            return t
        deno = _cell(r'D\S+nomination:')
        if deno:
            # coupe les mentions du type "Dénomination en français, depuis le ..."
            out['nom_societe'] = re.split(r'\s{2,}|D\S+nomination', deno)[0].strip() or out.get('nom_societe', '')
            out['trouve'] = True
        forme_txt = _cell(r'Forme l\S+gale')
        forme = _bce_forme(re.split(r'Depuis', forme_txt)[0] if forme_txt else '')
        if forme:
            out['forme_juridique'] = forme
        # Code NACE + secteur d'activité (priorité ONSS -> TVA -> NACE-BEL 2008).
        # NB : une société a souvent PLUSIEURS codes NACE ; on prend l'activité
        # principale ONSS et le gestionnaire vérifie.
        flat = re.sub(r'\s+', ' ', _unescape(re.sub(r'<[^>]+>', ' ', html)).replace('’', chr(39)))
        for pref in (r'ONSS\s*\d{4}', r'TVA\s*\d{4}', r''):
            mn = re.search(pref + r'\s*(\d{2}\.\d{3})\s*-\s*(.+?)\s+Depuis', flat)
            if mn:
                out['code_nace'] = mn.group(1)
                out['secteur_activite'] = mn.group(2).strip()[:70]
                break
        # Adresse du siège (secours si VIES n'a pas répondu)
        if not out.get('adresse_siege_social_1'):
            m = re.search(r'Adresse du si\S+ge:?(.*?)</tr>', html, re.S)
            if m:
                txt = re.sub(r'<br\s*/?>', '\n', m.group(1))
                txt = _unescape(re.sub(r'<[^>]+>', ' ', txt))
                lignes = [re.sub(r'\s+', ' ', l).strip() for l in txt.split('\n')]
                lignes = [l for l in lignes if l and 'Depuis' not in l]
                if lignes:
                    out['adresse_siege_social_1'] = lignes[0]
                    out['trouve'] = True
                if len(lignes) > 1:
                    out['adresse_siege_social_2'] = lignes[1]
        # Fonctions (représentants légaux) : administrateur délégué / gérant /
        # administrateur… -> pré-remplit le signataire de l'affiliation.
        def _txt(x):
            x = _unescape(re.sub(r'<[^>]+>', ' ', x)).replace('’', chr(39))
            return re.sub(r'\s+', ' ', x).strip()
        # kbopub affiche les fonctions soit repliées dans une table id="toonfctie"
        # (grosses sociétés), soit directement en clair (petites sociétés) -> on
        # scanne TOUTE la section « Fonctions » quelle que soit la mise en page.
        reps = []
        msec = re.search(r'Fonctions</h2>(.*?)(?:<h2>|<td class="I")', html, re.S)
        bloc = msec.group(1) if msec else ''
        for row in re.findall(r'<tr[^>]*>(.*?)</tr>', bloc, re.S):
            if 'Depuis' not in row:  # chaque titulaire a une date « Depuis le … »
                continue
            tds = re.findall(r'<td[^>]*>(.*?)</td>', row, re.S)
            if len(tds) < 2:
                continue
            fonction = _txt(tds[0])
            # la cellule « nom » est celle qui contient une virgule (Nom , Prénom)
            nom_cell = next((t for t in tds[1:] if ',' in _txt(t)), tds[1])
            parts = [p for p in (_txt(p) for p in _txt(nom_cell).split(',')) if p]
            # BCE liste "Nom , Prénom" -> on affiche "Prénom Nom"
            nom = f"{parts[1]} {parts[0]}" if len(parts) >= 2 else (parts[0] if parts else '')
            # ignore les administrateurs qui sont eux-mêmes une société (n° BCE, pas un nom)
            if re.fullmatch(r'[\d.\s]+', nom or ''):
                continue
            if fonction and nom and 'Depuis' not in fonction:
                reps.append({"fonction": fonction, "nom": nom})
        if reps:
            # priorité au représentant qui signe habituellement
            rank = [('administrateur délégué', 0), ('administrateur-délégué', 0),
                    ('administrateur unique', 0), ('gérant', 1), ('gerant', 1),
                    ('administrateur', 2), ('représentant permanent', 3),
                    ('gestion journalière', 3)]
            def _rk(r):
                f = r['fonction'].lower()
                for k, v in rank:
                    if k in f:
                        return v
                return 5
            reps = sorted(reps, key=_rk)
            # dedup par personne (garde la fonction la mieux classée)
            vus, uniq = set(), []
            for r in reps:
                cle = r['nom'].lower()
                if cle in vus:
                    continue
                vus.add(cle)
                uniq.append(r)
            reps = uniq
            main = reps[0]
            out['nom_prenom_gerant'] = main['nom']
            out['qualite'] = main['fonction']
            out['representants'] = reps[:12]
            out['trouve'] = True
    except Exception:
        pass

    # 3) Répertoire des employeurs ONSS (API publique de la sécurité sociale) :
    #    numéro ONSS + catégorie employeur (indice) + NACE officiel + adresse FR.
    try:
        r = requests.get(
            "https://services.socialsecurity.be/REST/employer/identification/v6/employers/search",
            params={"enterpriseNumber": str(int(num)), "history": "true"},
            headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"}, timeout=12)
        d = r.json() if r.status_code < 300 else {}
        if isinstance(d, list):
            d = d[0] if d else {}
        ident = d.get('identity') or {}
        nsso = (ident.get('ids') or {}).get('nssoNumber')
        if nsso:
            s = str(nsso).zfill(9)
            out['num_onss'] = f"{s[:7]}-{s[7:]}"
            out['trouve'] = True
        # Catégorie employeur ONSS = « indice ONSS » (souvent vide pour le secteur public)
        cats = d.get('employerCategories') or []
        if cats and isinstance(cats[0], dict):
            cat = cats[0].get('category') or cats[0].get('code')
            if cat:
                out['indice_onss'] = str(cat)
        # NACE officiel ONSS (version la plus récente, période en cours)
        try:
            codes = ((d.get('economicActivity') or {}).get('activityCodes') or [{}])[0]
            for version in ('nace2025', 'nace2008'):
                actifs = [c for c in (codes.get(version) or []) if not c.get('endDate')]
                if actifs:
                    c = str(actifs[0]['code']).zfill(5)
                    out['code_nace'] = f"{c[:2]}.{c[2:]}"
                    break
        except Exception:
            pass
        # Dénomination + adresse FR structurées (priorité sur VIES/BCE si présentes)
        deno_fr = ((ident.get('denomination') or {}).get('fr') or '').strip()
        if deno_fr:
            out['nom_societe'] = deno_fr
        adr = ident.get('address') or {}
        rue = ((adr.get('streetName') or {}).get('fr') or '').strip()
        if rue:
            out['adresse_siege_social_1'] = f"{rue} {adr.get('houseNumber', '')}".strip()
            commune = ((adr.get('municipalityName') or {}).get('fr') or '').strip()
            out['adresse_siege_social_2'] = f"{adr.get('postCode', '')} {commune}".strip()
    except Exception:
        pass

    return out


def _bce_etablissements(numero):
    """Adresses des unités d'établissement (= vrais sièges d'exploitation) depuis
    la BCE Public Search. Ce n'est PAS le siège social : c'est là où l'activité
    s'exerce réellement (annexe 5 du règlement). Retourne une liste d'adresses
    « rue n°, CP localité » (souvent une seule pour les petits clients)."""
    n = re.sub(r'\D', '', numero or '')
    if len(n) == 10 and n[0] == '0':
        n = n[1:]                                    # kbopub attend le n° sans le 0 initial
    if not n:
        return []
    try:
        r = requests.get(
            "https://kbopub.economie.fgov.be/kbopub/toonvestigingps.html",
            params={"ondernemingsnummer": n, "lang": "fr"},
            headers={"User-Agent": "Mozilla/5.0"}, timeout=12)
        html = r.text if r.status_code < 300 else ''
    except Exception:
        return []
    flat = re.sub(r'\s+', ' ', _unescape(re.sub(r'<[^>]+>', ' ', html)))
    etabs = []
    for m in re.finditer(r"Adresse de l'unit.{0,3} d.{0,3}.tablissement:*\s*(.+?)\s+(?:Depuis|Num.ro|Pas de|Statut)", flat):
        adr = re.sub(r'\s+', ' ', m.group(1)).strip(' :')
        adr = re.sub(r'\s+(\d{4}\s+[A-Za-zÀ-ÿ])', r', \1', adr)   # virgule avant le code postal
        if adr and adr not in etabs:
            etabs.append(adr)
    return etabs


@app.route('/bce/<numero>', methods=['GET'])
def bce_lookup(numero):
    """Pré-remplissage affiliation (données publiques BCE/VIES/ONSS)."""
    d = _bce_data(numero)
    if d.get('error'):
        return jsonify({"error": d['error']}), d.get('_status', 400)
    if not d.get('trouve'):
        return jsonify({"error": "Numéro introuvable à la BCE / TVA non valide."}), 404
    return jsonify(d), 200


# ============== SUIVI FICHES DE PAIE (tableau d'équipe) ==============
# Remplace l'Excel « SUIVI Laure » : une ligne par entreprise et par mois, avec
# statut, infos, GLP, DMFA, confirmation de clôture, gestionnaire et « en ordre ».
FDP_COLS = ['mois', 'entreprise', 'date_fdp', 'statut', 'infos', 'glp',
            'dmfa', 'c4', 'cloture', 'gestionnaire', 'en_ordre']


@app.route('/fdp', methods=['GET'])
def fdp_liste():
    """Lignes du suivi pour un mois (tableau partagé par toute l'équipe)."""
    email = verify_user_token(request)
    if not email:
        return jsonify({"error": "Non authentifié"}), 401
    if not SUPABASE_URL or not SUPABASE_KEY:
        return jsonify({"error": "Supabase non configuré"}), 503
    mois = re.sub(r'[^0-9-]', '', request.args.get('mois', ''))
    try:
        q = "select=*&order=id.asc&limit=500"
        if mois:
            q = f"mois=eq.{mois}&" + q
        r = requests.get(f"{SUPABASE_URL}/rest/v1/suivi_fdp?{q}",
                         headers=_supabase_headers(), timeout=10)
        if r.status_code >= 300:
            return jsonify({"error": r.text[:200]}), 500
        return jsonify(r.json()), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/fdp/upsert', methods=['POST'])
def fdp_upsert():
    """Crée (sans id) ou met à jour (avec id) une ligne du suivi."""
    email = verify_user_token(request)
    if not email:
        return jsonify({"error": "Non authentifié"}), 401
    if not SUPABASE_URL or not SUPABASE_KEY:
        return jsonify({"error": "Supabase non configuré"}), 503
    d = request.get_json(silent=True) or {}
    row = {k: d[k] for k in FDP_COLS if k in d}
    row['maj_par'] = email
    row['updated_at'] = datetime.utcnow().isoformat()
    hdr = {**_supabase_headers(), 'Content-Type': 'application/json',
           'Prefer': 'return=representation'}
    try:
        if d.get('id'):
            r = requests.patch(f"{SUPABASE_URL}/rest/v1/suivi_fdp?id=eq.{int(d['id'])}",
                               json=row, headers=hdr, timeout=10)
        else:
            if not (row.get('mois') and str(row.get('entreprise') or '').strip()):
                return jsonify({"error": "mois et entreprise requis"}), 400
            r = requests.post(f"{SUPABASE_URL}/rest/v1/suivi_fdp",
                              json=row, headers=hdr, timeout=10)
        if r.status_code >= 300:
            return jsonify({"error": r.text[:200]}), 500
        out = r.json()
        return jsonify(out[0] if isinstance(out, list) and out else out), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/fdp/supprimer', methods=['POST'])
def fdp_supprimer():
    """Supprime une ligne du suivi (par id)."""
    email = verify_user_token(request)
    if not email:
        return jsonify({"error": "Non authentifié"}), 401
    d = request.get_json(silent=True) or {}
    if not d.get('id'):
        return jsonify({"error": "id requis"}), 400
    try:
        r = requests.delete(f"{SUPABASE_URL}/rest/v1/suivi_fdp?id=eq.{int(d['id'])}",
                            headers=_supabase_headers(), timeout=10)
        if r.status_code >= 300:
            return jsonify({"error": r.text[:200]}), 500
        return jsonify({"ok": True}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ============== RÉPERTOIRE DES INSTITUTIONS ==============
# Adresses des organismes (caisse vacances, assurance-loi, fonds, SEPPT, bureaux
# de contrôle…), saisies UNE fois, réutilisées dans les règlements par leur nom.
INST_COLS = ['nom', 'type', 'rue', 'numero', 'code_postal', 'localite',
             'num_affiliation', 'province', 'note']


@app.route('/institutions', methods=['GET'])
def institutions_liste():
    email = verify_user_token(request)
    if not email:
        return jsonify({"error": "Non authentifié"}), 401
    if not SUPABASE_URL or not SUPABASE_KEY:
        return jsonify({"error": "Supabase non configuré"}), 503
    try:
        r = requests.get(f"{SUPABASE_URL}/rest/v1/institutions?select=*&order=type.asc,nom.asc&limit=1000",
                         headers=_supabase_headers(), timeout=10)
        if r.status_code >= 300:
            return jsonify({"error": r.text[:200]}), 500
        return jsonify(r.json()), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/institutions/upsert', methods=['POST'])
def institutions_upsert():
    email = verify_user_token(request)
    if not email:
        return jsonify({"error": "Non authentifié"}), 401
    if not SUPABASE_URL or not SUPABASE_KEY:
        return jsonify({"error": "Supabase non configuré"}), 503
    d = request.get_json(silent=True) or {}
    row = {k: d[k] for k in INST_COLS if k in d}
    row['updated_at'] = datetime.utcnow().isoformat()
    hdr = {**_supabase_headers(), 'Content-Type': 'application/json', 'Prefer': 'return=representation'}
    try:
        if d.get('id'):
            r = requests.patch(f"{SUPABASE_URL}/rest/v1/institutions?id=eq.{int(d['id'])}",
                               json=row, headers=hdr, timeout=10)
        else:
            if not str(row.get('nom') or '').strip():
                return jsonify({"error": "nom requis"}), 400
            r = requests.post(f"{SUPABASE_URL}/rest/v1/institutions", json=row, headers=hdr, timeout=10)
        if r.status_code >= 300:
            return jsonify({"error": r.text[:200]}), 500
        out = r.json()
        return jsonify(out[0] if isinstance(out, list) and out else out), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/institutions/supprimer', methods=['POST'])
def institutions_supprimer():
    email = verify_user_token(request)
    if not email:
        return jsonify({"error": "Non authentifié"}), 401
    d = request.get_json(silent=True) or {}
    if not d.get('id'):
        return jsonify({"error": "id requis"}), 400
    try:
        r = requests.delete(f"{SUPABASE_URL}/rest/v1/institutions?id=eq.{int(d['id'])}",
                            headers=_supabase_headers(), timeout=10)
        if r.status_code >= 300:
            return jsonify({"error": r.text[:200]}), 500
        return jsonify({"ok": True}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def _institutions_repertoire():
    """Charge le répertoire (liste de dicts) depuis Supabase, ou []."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return []
    try:
        r = requests.get(f"{SUPABASE_URL}/rest/v1/institutions?select=*&limit=1000",
                         headers=_supabase_headers(), timeout=10)
        return r.json() if r.status_code < 300 and isinstance(r.json(), list) else []
    except Exception:
        return []


# ============== RÉPERTOIRE DES COMMISSIONS PARITAIRES ==============
# Par CP : n° + dénomination + temps plein (heures/semaine). Sert à pré-remplir
# automatiquement le temps plein dans le règlement dès qu'on tape le n° de CP.
CP_COLS = ['cp', 'denomination', 'heures_semaine', 'note']


@app.route('/commissions', methods=['GET'])
def commissions_liste():
    email = verify_user_token(request)
    if not email:
        return jsonify({"error": "Non authentifié"}), 401
    if not SUPABASE_URL or not SUPABASE_KEY:
        return jsonify({"error": "Supabase non configuré"}), 503
    try:
        r = requests.get(f"{SUPABASE_URL}/rest/v1/commissions?select=*&order=cp.asc&limit=1000",
                         headers=_supabase_headers(), timeout=10)
        if r.status_code >= 300:
            return jsonify({"error": r.text[:200]}), 500
        return jsonify(r.json()), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/commissions/upsert', methods=['POST'])
def commissions_upsert():
    email = verify_user_token(request)
    if not email:
        return jsonify({"error": "Non authentifié"}), 401
    if not SUPABASE_URL or not SUPABASE_KEY:
        return jsonify({"error": "Supabase non configuré"}), 503
    d = request.get_json(silent=True) or {}
    row = {k: d[k] for k in CP_COLS if k in d}
    row['updated_at'] = datetime.utcnow().isoformat()
    hdr = {**_supabase_headers(), 'Content-Type': 'application/json', 'Prefer': 'return=representation'}
    try:
        if d.get('id'):
            r = requests.patch(f"{SUPABASE_URL}/rest/v1/commissions?id=eq.{int(d['id'])}",
                               json=row, headers=hdr, timeout=10)
        else:
            if not str(row.get('cp') or '').strip():
                return jsonify({"error": "n° CP requis"}), 400
            r = requests.post(f"{SUPABASE_URL}/rest/v1/commissions", json=row, headers=hdr, timeout=10)
        if r.status_code >= 300:
            return jsonify({"error": r.text[:200]}), 500
        out = r.json()
        return jsonify(out[0] if isinstance(out, list) and out else out), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/commissions/supprimer', methods=['POST'])
def commissions_supprimer():
    email = verify_user_token(request)
    if not email:
        return jsonify({"error": "Non authentifié"}), 401
    d = request.get_json(silent=True) or {}
    if not d.get('id'):
        return jsonify({"error": "id requis"}), 400
    try:
        r = requests.delete(f"{SUPABASE_URL}/rest/v1/commissions?id=eq.{int(d['id'])}",
                            headers=_supabase_headers(), timeout=10)
        if r.status_code >= 300:
            return jsonify({"error": r.text[:200]}), 500
        return jsonify({"ok": True}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def _commissions_repertoire():
    if not SUPABASE_URL or not SUPABASE_KEY:
        return []
    try:
        r = requests.get(f"{SUPABASE_URL}/rest/v1/commissions?select=*&limit=1000",
                         headers=_supabase_headers(), timeout=10)
        return r.json() if r.status_code < 300 and isinstance(r.json(), list) else []
    except Exception:
        return []


# ============== RÈGLEMENT DE TRAVAIL ==============
_HORAIRE_MANIFEST = None


def _horaire_manifest():
    """Charge (et met en cache) le manifeste id_modèle -> nom de fichier storage."""
    global _HORAIRE_MANIFEST
    if _HORAIRE_MANIFEST is None:
        try:
            path = os.path.join(os.path.dirname(__file__), 'horaires_manifest.json')
            with open(path, encoding='utf-8') as f:
                _HORAIRE_MANIFEST = json.load(f)
        except Exception as e:
            print(f"[REGLEMENT] manifeste horaires illisible: {e}")
            _HORAIRE_MANIFEST = {}
    return _HORAIRE_MANIFEST


def _fetch_storage(bucket, fn):
    """Télécharge un objet d'un bucket Supabase Storage privé. Bytes ou None."""
    if not fn or not SUPABASE_URL or not SUPABASE_KEY:
        return None
    try:
        r = requests.get(
            f"{SUPABASE_URL}/storage/v1/object/{bucket}/{fn}",
            headers={'apikey': SUPABASE_KEY, 'Authorization': f'Bearer {SUPABASE_KEY}'},
            timeout=20)
        if r.status_code < 300 and r.content:
            return r.content
        print(f"[REGLEMENT] {bucket}/{fn} -> HTTP {r.status_code}")
    except Exception as e:
        print(f"[REGLEMENT] échec récupération {bucket}/{fn}: {e}")
    return None


def _fetch_horaire_model(model_id):
    """Récupère le .docx du modèle d'horaire (bucket 'horaires')."""
    return _fetch_storage('horaires', _horaire_manifest().get(model_id))


def _fetch_reglement_template(langue):
    """Récupère le modèle officiel FR/NL (bucket 'reglement')."""
    lang = 'NL' if str(langue or 'FR').upper() == 'NL' else 'FR'
    return _fetch_storage('reglement', f'reglement_{lang}.docx')


@app.route('/reglement/generer', methods=['POST'])
def reglement_generer():
    """Génère le règlement de travail (.docx) depuis le contrat §6.
    Identité société via BCE ; horaire sectoriel joint en Annexe 1 si un modèle
    est choisi. Données publiques -> pas d'auth (comme /bce)."""
    payload = request.get_json(silent=True) or {}
    num = payload.get('num_entreprise')
    identity = None
    if num:
        d = _bce_data(num)
        if not d.get('error'):
            identity = d
            # Vrai siège d'exploitation (annexe 5) : unités d'établissement BCE
            try:
                etabs = _bce_etablissements(num)
                if etabs:
                    identity['sieges_exploitation'] = ' ; '.join(etabs)
            except Exception:
                pass
    template_bytes = _fetch_reglement_template(payload.get('reglement_langue'))
    if not template_bytes:
        return jsonify({"error": "Le modèle de règlement n'est pas encore hébergé (upload Supabase à faire)."}), 503
    model_bytes = None
    mid = (payload.get('horaire_modele') or '').strip()
    if mid:
        model_bytes = _fetch_horaire_model(mid)
    cp_rep = _commissions_repertoire()
    try:
        from reglement_gen import build_reglement, generer_doc_horaires
        regl = build_reglement(payload, identity, template_bytes, model_bytes,
                               repertoire=_institutions_repertoire(), cp_repertoire=cp_rep)
    except Exception as e:
        return jsonify({"error": f"Échec de la génération : {e}"}), 500
    # Les horaires générés ne doivent JAMAIS bloquer le règlement : en cas d'échec
    # (données d'ouverture farfelues, etc.), on renvoie quand même le règlement seul.
    horaires = None
    try:
        horaires = generer_doc_horaires(payload, identity, cp_repertoire=cp_rep)
    except Exception as e:
        print(f"[REGLEMENT] horaires ignorés (non bloquant) : {e}")
    base = re.sub(r'\D', '', str(num or '')) or 'employeur'
    DOCX = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    if horaires:
        # règlement + horaires (souvent très longs) dans un ZIP à 2 documents
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
            z.writestr(f'reglement_{base}.docx', regl)
            z.writestr(f'horaires_{base}.docx', horaires)
        buf.seek(0)
        return send_file(buf, mimetype='application/zip', as_attachment=True,
                         download_name=f'reglement_{base}.zip')
    return send_file(io.BytesIO(regl), mimetype=DOCX, as_attachment=True,
                     download_name=f'reglement_{base}.docx')

# ============== INDIVIDUAL ENDPOINTS ==============
@app.route('/fill-employer-form', methods=['POST'])
def fill_employer():
    d = request.get_json()
    if not d: return jsonify({"error": "No data"}), 400
    try:
        return send_file(io.BytesIO(fill_employer_pdf(d)), mimetype='application/pdf',
                        as_attachment=True, download_name='Fiche_employeur.pdf')
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route('/fill-travailleur', methods=['POST'])
def fill_travailleur():
    d = request.get_json()
    if not d: return jsonify({"error": "No data"}), 400
    try:
        return send_file(io.BytesIO(fill_travailleur_pdf(d)), mimetype='application/pdf',
                        as_attachment=True, download_name='Fiche_travailleur.pdf')
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route('/fill-independant', methods=['POST'])
def fill_independant():
    d = request.get_json()
    if not d: return jsonify({"error": "No data"}), 400
    try:
        return send_file(io.BytesIO(fill_independant_pdf(d)), mimetype='application/pdf',
                        as_attachment=True, download_name='Fiche_independant.pdf')
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route('/fill-att-accident', methods=['POST'])
def fill_att_accident():
    d = request.get_json()
    if not d: return jsonify({"error": "No data"}), 400
    try:
        return send_file(io.BytesIO(fill_att_accident_pdf(d, 'fr')), mimetype='application/pdf',
                        as_attachment=True, download_name='Attestation_accident_travail_FR.pdf')
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route('/fill-att-accident-nl', methods=['POST'])
def fill_att_accident_nl():
    d = request.get_json()
    if not d: return jsonify({"error": "No data"}), 400
    try:
        return send_file(io.BytesIO(fill_att_accident_pdf(d, 'nl')), mimetype='application/pdf',
                        as_attachment=True, download_name='Attestation_accident_travail_NL.pdf')
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route('/fill-att-seppt', methods=['POST'])
def fill_att_seppt():
    d = request.get_json()
    if not d: return jsonify({"error": "No data"}), 400
    try:
        return send_file(io.BytesIO(fill_att_seppt_pdf(d, 'fr')), mimetype='application/pdf',
                        as_attachment=True, download_name='Attestation_SEPPT_FR.pdf')
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route('/fill-att-seppt-nl', methods=['POST'])
def fill_att_seppt_nl():
    d = request.get_json()
    if not d: return jsonify({"error": "No data"}), 400
    try:
        return send_file(io.BytesIO(fill_att_seppt_pdf(d, 'nl')), mimetype='application/pdf',
                        as_attachment=True, download_name='Attestation_SEPPT_NL.pdf')
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route('/fill-offre', methods=['POST'])
def fill_offre():
    d = request.get_json()
    if not d: return jsonify({"error": "No data"}), 400
    try:
        return send_file(io.BytesIO(fill_offre_pdf(d, 'fr')), mimetype='application/pdf',
                        as_attachment=True, download_name='Offre_de_collaboration_FR.pdf')
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route('/fill-offre-nl', methods=['POST'])
def fill_offre_nl():
    d = request.get_json()
    if not d: return jsonify({"error": "No data"}), 400
    try:
        return send_file(io.BytesIO(fill_offre_pdf(d, 'nl')), mimetype='application/pdf',
                        as_attachment=True, download_name='Offre_de_collaboration_NL.pdf')
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route('/fill-procuration', methods=['POST'])
def fill_procuration():
    d = request.get_json()
    if not d: return jsonify({"error": "No data"}), 400
    try:
        return send_file(io.BytesIO(fill_procuration_pdf(d)), mimetype='application/pdf',
                        as_attachment=True, download_name='Procuration_ONSS.pdf')
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route('/fill-dispense', methods=['POST'])
def fill_dispense():
    d = request.get_json()
    if not d: return jsonify({"error": "No data"}), 400
    try:
        return send_file(io.BytesIO(fill_dispense_pdf(d)), mimetype='application/pdf',
                        as_attachment=True, download_name='Dispense_precompte.pdf')
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route('/fill-mensura', methods=['POST'])
def fill_mensura():
    d = request.get_json()
    if not d: return jsonify({"error": "No data"}), 400
    try:
        return send_file(io.BytesIO(fill_mensura_pdf(d)), mimetype='application/pdf',
                        as_attachment=True, download_name='Contrat_Mensura.pdf')
    except Exception as e: return jsonify({"error": str(e)}), 500

# ============== PDF GENERATION FUNCTIONS ==============
def fill_employer_pdf(d):
    p, c = newcan()
    if d.get('recu_par'): txt(c, d['recu_par'], 235, 198)
    f = d.get('forme_juridique', '')
    if f == 'SRL': txt(c, 'X', 195, 235, 12)
    elif f == 'SC': txt(c, 'X', 240, 235, 12)
    elif f == 'SA': txt(c, 'X', 285, 235, 12)
    elif f == 'ASBL': txt(c, 'X', 345, 235, 12)
    elif f == 'PERSONNE PHYSIQUE': txt(c, 'X', 415, 235, 12)
    if d.get('nom_societe'): txt(c, d['nom_societe'], 469, 277)
    if d.get('nom_prenom_gerant'): txt(c, d['nom_prenom_gerant'], 469, 310)
    if d.get('niss_gerant'): txt(c, d['niss_gerant'], 468, 344)
    if d.get('adresse_siege_social_1'): txt(c, d['adresse_siege_social_1'], 466, 375)
    if d.get('adresse_siege_social_2'): txt(c, d['adresse_siege_social_2'], 465, 409)
    if d.get('adresse_exploitation_1'): txt(c, d['adresse_exploitation_1'], 466, 443)
    if d.get('adresse_exploitation_2'): txt(c, d['adresse_exploitation_2'], 464, 478)
    if d.get('telephone_gsm'): txt(c, d['telephone_gsm'], 461, 507)
    if d.get('email'): txt(c, d['email'], 462, 539)
    if d.get('num_entreprise'): txt(c, d['num_entreprise'], 462, 572)
    if d.get('num_onss'): txt(c, d['num_onss'], 462, 604)
    if d.get('assurance_loi'): txt(c, d['assurance_loi'], 464, 638)
    if d.get('seppt'): txt(c, d['seppt'], 464, 669)
    if d.get('secteur_activite'): txt(c, d['secteur_activite'], 464, 703)
    r = d.get('reduction_premier', '')
    if r == 'Oui': txt(c, 'X', 96, 768, 12)
    elif r == 'Non': txt(c, 'X', 133, 768, 12)
    if d.get('commission_paritaire'): txt(c, d['commission_paritaire'], 462, 802)
    if d.get('indice_onss'): txt(c, d['indice_onss'], 463, 834)
    if d.get('code_nace'): txt(c, d['code_nace'], 461, 868)
    s = d.get('salaire_garanti', '')
    if s == 'OUI': txt(c, 'X', 581, 899, 12)
    elif s == 'NON': txt(c, 'X', 618, 899, 12)
    c.showPage()
    if d.get('regime_horaire'): txt(c, d['regime_horaire'], 357, 148)
    for day, y in [('lundi',228),('mardi',247),('mercredi',266),('jeudi',285),('vendredi',304),('samedi',331),('dimanche',351)]:
        if d.get(f'{day}_matin_de'): txt(c, d[f'{day}_matin_de'], 213, y, 9)
        if d.get(f'{day}_matin_a'): txt(c, d[f'{day}_matin_a'], 276, y, 9)
        if d.get(f'{day}_pause_de'): txt(c, d[f'{day}_pause_de'], 363, y, 9)
        if d.get(f'{day}_pause_a'): txt(c, d[f'{day}_pause_a'], 423, y, 9)
        if d.get(f'{day}_apres_de'): txt(c, d[f'{day}_apres_de'], 522, y, 9)
        if d.get(f'{day}_apres_a'): txt(c, d[f'{day}_apres_a'], 585, y, 9)
    if d.get('cameras'): txt(c, d['cameras'], 427, 387)
    if d.get('trousse_secours'): txt(c, d['trousse_secours'], 400, 453)
    if d.get('vetements_fourniture') == 'Oui': txt(c, 'X', 348, 486, 12)
    elif d.get('vetements_fourniture') == 'Non': txt(c, 'X', 385, 485, 12)
    if d.get('vetements_entretien') == 'Oui': txt(c, 'X', 347, 518, 12)
    elif d.get('vetements_entretien') == 'Non': txt(c, 'X', 388, 518, 12)
    if d.get('primes'): txt(c, d['primes'], 394, 552)
    if d.get('secretariat_actuel'): txt(c, d['secretariat_actuel'], 394, 583)
    if d.get('nom_comptable'): txt(c, d['nom_comptable'], 390, 617)
    if d.get('coord_comptable'): txt(c, d['coord_comptable'], 390, 648)
    o = d.get('origine', '')
    if o == 'Internet': txt(c, 'X', 173, 683, 12)
    elif o == 'Comptable': txt(c, 'X', 342, 683, 12)
    elif o == 'Client': txt(c, 'X', 174, 716, 12)
    elif o == 'Autre': txt(c, 'X', 341, 716, 12)
    if d.get('date_signature'): txt(c, d['date_signature'], 177, 843)
    c.save()
    return merge(TEMPLATES['employer'], p, 2).getvalue()

def fill_travailleur_pdf(d):
    p, c = newcan()
    if d.get('contrat_email'): txt(c, 'X', 296, 135, 12)
    if d.get('contrat_fax'): txt(c, 'X', 364, 135, 12)
    if d.get('contrat_poste'): txt(c, 'X', 415, 134, 12)
    if d.get('contrat_main'): txt(c, 'X', 477, 136, 12)
    if d.get('nom_employeur'): txt(c, d['nom_employeur'], 384, 203)
    cv = d.get('civilite', '')
    if cv == 'Mr': txt(c, 'X', 141, 259, 12)
    elif cv == 'Mme': txt(c, 'X', 298, 260, 12)
    elif cv == 'Melle': txt(c, 'X', 459, 260, 12)
    if d.get('nom_prenom'): txt(c, d['nom_prenom'], 383, 286)
    if d.get('adresse_1'): txt(c, d['adresse_1'], 378, 313)
    if d.get('adresse_2'): txt(c, d['adresse_2'], 378, 340)
    if d.get('date_lieu_naissance'): txt(c, d['date_lieu_naissance'], 377, 366)
    if d.get('niss'): txt(c, d['niss'], 376, 392)
    if d.get('nationalite'): txt(c, d['nationalite'], 378, 421)
    if d.get('carte_identite'): txt(c, 'X', 133, 449, 12)
    if d.get('permis_travail'): txt(c, 'X', 133, 470, 12)
    if d.get('permis_date'): txt(c, d['permis_date'], 471, 466)
    et = d.get('etat_civil', '')
    if et == 'Marie': txt(c, 'X', 283, 532, 12)
    elif et == 'Veuf': txt(c, 'X', 475, 533, 12)
    elif et == 'Celibataire': txt(c, 'X', 283, 559, 12)
    elif et == 'Separe': txt(c, 'X', 476, 561, 12)
    elif et == 'Divorce': txt(c, 'X', 283, 586, 12)
    elif et == 'Cohabitation': txt(c, 'X', 473, 585, 12)
    if d.get('conjoint_charge'): txt(c, 'X', 90, 634, 12)
    if d.get('enfants_charge'): txt(c, 'X', 289, 635, 12)
    if d.get('autre_charge'): txt(c, 'X', 91, 655, 12)
    if d.get('nb_enfants'): txt(c, d['nb_enfants'], 604, 635)
    if d.get('nb_handicapes'): txt(c, d['nb_handicapes'], 604, 653)
    if d.get('date_entree'): txt(c, d['date_entree'], 223, 729)
    if d.get('date_sortie'): txt(c, d['date_sortie'], 515, 731)
    ct = d.get('categorie', '')
    if ct == 'Employe': txt(c, 'X', 260, 757, 12)
    elif ct == 'Ouvrier': txt(c, 'X', 347, 758, 12)
    elif ct == 'Chef': txt(c, 'X', 428, 757, 12)
    elif ct == 'Autre': txt(c, 'X', 562, 758, 12)
    if d.get('fonction'): txt(c, d['fonction'], 261, 791)
    tc = d.get('type_contrat', '')
    if tc == 'CDD': txt(c, 'X', 283, 826, 12)
    elif tc == 'CDI': txt(c, 'X', 283, 845, 12)
    elif tc == 'Etudiant': txt(c, 'X', 284, 870, 12)
    elif tc == 'Remplacement': txt(c, 'X', 474, 824, 12)
    elif tc == 'Nettement defini': txt(c, 'X', 475, 847, 12)
    rg = d.get('regime_horaire', '')
    if rg == 'Temps plein': txt(c, 'X', 257, 900, 12)
    elif rg == 'Temps partiel': txt(c, 'X', 384, 900, 12)
    c.showPage()
    hr = d.get('horaire_type', '')
    if hr == 'Fixe': txt(c, 'X', 258, 99, 12)
    elif hr == 'Variable': txt(c, 'X', 385, 99, 12)
    if d.get('heures_semaine'): txt(c, d['heures_semaine'], 291, 127)
    sch = [('lundi',202,188,276,355,418,514,584),('mardi',200,205,271,360,412,512,576),
           ('mercredi',200,223,275,362,429,512,577),('jeudi',200,241,271,356,421,513,581),
           ('vendredi',200,258,273,357,421,513,583),('samedi',208,275,276,355,419,512,579),
           ('dimanche',207,294,270,354,424,513,582)]
    for day,x1,y,x2,x3,x4,x5,x6 in sch:
        if d.get(f'{day}_matin_de'): txt(c, d[f'{day}_matin_de'], x1, y, 9)
        if d.get(f'{day}_matin_a'): txt(c, d[f'{day}_matin_a'], x2, y, 9)
        if d.get(f'{day}_pause_de'): txt(c, d[f'{day}_pause_de'], x3, y, 9)
        if d.get(f'{day}_pause_a'): txt(c, d[f'{day}_pause_a'], x4, y, 9)
        if d.get(f'{day}_apres_de'): txt(c, d[f'{day}_apres_de'], x5, y, 9)
        if d.get(f'{day}_apres_a'): txt(c, d[f'{day}_apres_a'], x6, y, 9)
    if d.get('remuneration'): txt(c, d['remuneration'], 335, 319)
    if d.get('compte_bancaire'): txt(c, d['compte_bancaire'], 337, 347)
    if d.get('avantage_nourriture'): txt(c, 'X', 134, 401, 12)
    if d.get('avantage_vetements'): txt(c, 'X', 133, 431, 12)
    if d.get('avantage_voiture'): txt(c, 'X', 134, 455, 12)
    if d.get('avantage_gsm'): txt(c, 'X', 134, 484, 12)
    if d.get('avantage_autre'): txt(c, 'X', 134, 512, 12)
    if d.get('prime_nuit'): txt(c, 'X', 176, 547, 12)
    if d.get('prime_weekend'): txt(c, 'X', 240, 546, 12)
    if d.get('prime_froid'): txt(c, 'X', 345, 547, 12)
    if d.get('prime_autre'): txt(c, d['prime_autre'], 418, 547)
    if d.get('transport_train'): txt(c, 'X', 95, 601, 12)
    if d.get('transport_tram'): txt(c, 'X', 167, 602, 12)
    if d.get('transport_metro'): txt(c, 'X', 235, 602, 12)
    if d.get('transport_bus'): txt(c, 'X', 313, 602, 12)
    if d.get('transport_voiture'): txt(c, 'X', 374, 602, 12)
    if d.get('transport_pieds'): txt(c, 'X', 462, 601, 12)
    if d.get('transport_velo'): txt(c, 'X', 540, 600, 12)
    if d.get('km'): txt(c, d['km'], 331, 627)
    if d.get('chomage_depuis'): txt(c, d['chomage_depuis'], 375, 657)
    if d.get('c131'): txt(c, 'X', 135, 686, 12)
    if d.get('carte_activa'): txt(c, 'X', 136, 716, 12)
    if d.get('carte_recue'): txt(c, 'X', 312, 711, 12)
    if d.get('faire_demande'): txt(c, 'X', 291, 743, 12)
    if d.get('cpas_depuis'): txt(c, d['cpas_depuis'], 355, 768)
    if d.get('date_signature'): txt(c, d['date_signature'], 139, 813)
    c.save()
    return merge(TEMPLATES['travailleur'], p, 2).getvalue()

def fill_independant_pdf(d):
    p, c = newcan()
    if d.get('contrat_email'): txt(c, 'X', 296, 133, 12)
    if d.get('contrat_fax'): txt(c, 'X', 363, 133, 12)
    if d.get('contrat_poste'): txt(c, 'X', 414, 134, 12)
    if d.get('contrat_main'): txt(c, 'X', 476, 133, 12)
    cv = d.get('civilite', '')
    if cv == 'Mr': txt(c, 'X', 139, 203, 12)
    elif cv == 'Mme': txt(c, 'X', 300, 203, 12)
    elif cv == 'Melle': txt(c, 'X', 459, 203, 12)
    if d.get('nom_prenom'): txt(c, d['nom_prenom'], 395, 233)
    if d.get('adresse_1'): txt(c, d['adresse_1'], 392, 258)
    if d.get('adresse_2'): txt(c, d['adresse_2'], 388, 286)
    if d.get('date_lieu_naissance'): txt(c, d['date_lieu_naissance'], 392, 312)
    if d.get('niss'): txt(c, d['niss'], 391, 340)
    if d.get('nationalite'): txt(c, d['nationalite'], 386, 367)
    if d.get('carte_identite'): txt(c, 'X', 133, 396, 12)
    et = d.get('etat_civil', '')
    if et == 'Marie': txt(c, 'X', 283, 457, 12)
    elif et == 'Veuf': txt(c, 'X', 472, 458, 12)
    elif et == 'Celibataire': txt(c, 'X', 281, 484, 12)
    elif et == 'Separe': txt(c, 'X', 475, 483, 12)
    elif et == 'Divorce': txt(c, 'X', 283, 510, 12)
    elif et == 'Cohabitation': txt(c, 'X', 474, 511, 12)
    if d.get('conjoint_charge'): txt(c, 'X', 91, 559, 12)
    if d.get('enfants_charge'): txt(c, 'X', 288, 561, 12)
    if d.get('autre_charge'): txt(c, 'X', 91, 580, 12)
    if d.get('nb_enfants'): txt(c, d['nb_enfants'], 606, 559)
    if d.get('nb_handicapes'): txt(c, d['nb_handicapes'], 607, 579)
    if d.get('remuneration'): txt(c, d['remuneration'], 350, 639)
    if d.get('loi_sociale'): txt(c, 'X', 133, 683, 12)
    if d.get('loi_sociale_val'): txt(c, d['loi_sociale_val'], 322, 682)
    if d.get('cheques_repas'): txt(c, 'X', 133, 709, 12)
    if d.get('cheques_repas_val'): txt(c, d['cheques_repas_val'], 322, 709)
    if d.get('voiture'): txt(c, 'X', 133, 737, 12)
    if d.get('voiture_val'): txt(c, d['voiture_val'], 325, 736)
    if d.get('autre'): txt(c, 'X', 134, 765, 12)
    if d.get('autre_val'): txt(c, d['autre_val'], 325, 763)
    if d.get('date_signature'): txt(c, d['date_signature'], 139, 808)
    c.save()
    return merge(TEMPLATES['independant'], p, 1).getvalue()

def fill_att_accident_pdf(d, lang='fr'):
    d = with_signatory_fallbacks(d)
    p, c = newcan()
    tpl = TEMPLATES['att_accident_nl'] if lang == 'nl' else TEMPLATES['att_accident_fr']
    off = 12 if lang == 'nl' else 0
    if d.get('nom_soussigne'): txt(c, d['nom_soussigne'], 283, 130+off)
    if d.get('niss'): txt(c, d['niss'], 283, 144+off)
    if d.get('domicile_1'): txt(c, d['domicile_1'], 283, 159+off)
    if d.get('domicile_2'): txt(c, d['domicile_2'], 282, 174+off)
    if d.get('qualite'): txt(c, d['qualite'], 284, 204+off)
    if d.get('societe'): txt(c, d['societe'], 284, 222+off)
    if d.get('etablie_1'): txt(c, d['etablie_1'], 284, 235+off)
    if d.get('etablie_2'): txt(c, d['etablie_2'], 283, 251+off)
    if d.get('date_signature'): txt(c, d['date_signature'], 237, 443+off)
    c.save()
    return merge(tpl, p, 1).getvalue()

def fill_att_seppt_pdf(d, lang='fr'):
    d = with_signatory_fallbacks(d)
    p, c = newcan()
    tpl = TEMPLATES['att_seppt_nl'] if lang == 'nl' else TEMPLATES['att_seppt_fr']
    off = 11 if lang == 'nl' else 0
    sig_y = 630 if lang == 'nl' else 548
    if d.get('nom_soussigne'): txt(c, d['nom_soussigne'], 313, 129+off)
    if d.get('niss'): txt(c, d['niss'], 313, 145+off)
    if d.get('domicile_1'): txt(c, d['domicile_1'], 310, 160+off)
    if d.get('domicile_2'): txt(c, d['domicile_2'], 309, 173+off)
    if d.get('qualite'): txt(c, d['qualite'], 311, 205+off)
    if d.get('societe'): txt(c, d['societe'], 311, 220+off)
    if d.get('etablie_1'): txt(c, d['etablie_1'], 311, 236+off)
    if d.get('etablie_2'): txt(c, d['etablie_2'], 309, 252+off)
    if d.get('date_signature'): txt(c, d['date_signature'], 252, sig_y)
    c.save()
    return merge(tpl, p, 1).getvalue()

def make_overlay(draw_fn):
    """Create a single-page PDF overlay by calling draw_fn(canvas)"""
    p = io.BytesIO()
    c = canvas.Canvas(p, pagesize=(595, 842))
    draw_fn(c)
    c.save()
    return p.getvalue()

def merge_selective(tpl_path, overlays):
    """
    Merge overlays only onto specific pages.
    overlays: dict {page_index: pdf_bytes}
    Notre texte est mis PAR-DESSUS le template (ov_page.merge_page(pg)).
    Les pages sans overlay passent intactes.
    """
    rd = PdfReader(tpl_path)
    wr = PdfWriter()
    for i in range(len(rd.pages)):
        pg = rd.pages[i]
        if i in overlays:
            ov = PdfReader(io.BytesIO(overlays[i]))
            ov_page = ov.pages[0]
            ov_page.merge_page(pg)  # template DERRIERE notre texte
            wr.add_page(ov_page)
        else:
            wr.add_page(pg)
    out = io.BytesIO()
    wr.write(out)
    out.seek(0)
    return out

def fill_offre_pdf(d, lang='fr'):
    """
    Offre de collaboration — 20 pages.
    Only pages 1, 13, 14, 15 have fillable fields.
    Pages 2-12 and 16-20 are static — we preserve them untouched.
    """
    tpl = TEMPLATES['offre_nl'] if lang == 'nl' else TEMPLATES['offre_fr']

    def val(primary, fallback):
        return d.get(primary) or d.get(fallback)

    overlays = {}

    # --- Page 1 (index 0): Cover — company info ---
    def draw_p1(c):
        if d.get('nom_societe'): txt(c, d['nom_societe'], 223, 470)
        if val('adresse_1','adresse_siege_social_1'): txt(c, val('adresse_1','adresse_siege_social_1'), 218, 496)
        if val('adresse_2','adresse_siege_social_2'): txt(c, val('adresse_2','adresse_siege_social_2'), 217, 526)
        if d.get('num_tva') or d.get('num_entreprise'): txt(c, d.get('num_tva') or d.get('num_entreprise'), 217, 551)
        if val('represente_par','nom_prenom_gerant'): txt(c, val('represente_par','nom_prenom_gerant'), 217, 577)
    overlays[0] = make_overlay(draw_p1)

    # --- Page 13 (index 12): Conditions particulières ---
    def draw_p13(c):
        if d.get('nom_societe'): txt(c, d['nom_societe'], 210, 222)
        if val('adresse_1','adresse_siege_social_1'): txt(c, val('adresse_1','adresse_siege_social_1'), 207, 238)
        if val('adresse_2','adresse_siege_social_2'): txt(c, val('adresse_2','adresse_siege_social_2'), 202, 258)
        if d.get('num_tva') or d.get('num_entreprise'): txt(c, d.get('num_tva') or d.get('num_entreprise'), 202, 273)
        if val('represente_par','nom_prenom_gerant'): txt(c, val('represente_par','nom_prenom_gerant'), 199, 291)
        if d.get('date_entree_jour'): txt(c, d['date_entree_jour'], 328, 585)
        if d.get('date_entree_mois'): txt(c, d['date_entree_mois'], 370, 585)
        if d.get('date_entree_annee'): txt(c, d['date_entree_annee'], 423, 587)
        if val('date_fait','date_signature'): txt(c, val('date_fait','date_signature'), 189, 640)
    overlays[12] = make_overlay(draw_p13)

    # --- Page 14 (index 13): Procuration ---
    def draw_p14(c):
        if val('nom_soussigne','nom_prenom_gerant'): txt(c, val('nom_soussigne','nom_prenom_gerant'), 257, 183)
        if val('niss','niss_gerant'): txt(c, val('niss','niss_gerant'), 255, 200)
        if val('domicile_1','adresse_siege_social_1'): txt(c, val('domicile_1','adresse_siege_social_1'), 255, 214)
        if val('domicile_2','adresse_siege_social_2'): txt(c, val('domicile_2','adresse_siege_social_2'), 255, 228)
        if d.get('qualite'): txt(c, d['qualite'], 256, 246)
        if val('societe','nom_societe'): txt(c, val('societe','nom_societe'), 253, 263)
        if val('adresse_1','adresse_siege_social_1'): txt(c, val('adresse_1','adresse_siege_social_1'), 252, 280)
        if val('adresse_2','adresse_siege_social_2'): txt(c, val('adresse_2','adresse_siege_social_2'), 252, 295)
        if d.get('num_tva') or d.get('num_entreprise'): txt(c, d.get('num_tva') or d.get('num_entreprise'), 251, 311)
        if d.get('date_signature'): txt(c, d['date_signature'], 205, 801)
    overlays[13] = make_overlay(draw_p14)

    # --- Page 15 (index 14): Contrat de mandat ---
    def draw_p15(c):
        if val('nom_soussigne','nom_prenom_gerant'): txt(c, val('nom_soussigne','nom_prenom_gerant'), 246, 185)
        if val('niss','niss_gerant'): txt(c, val('niss','niss_gerant'), 245, 200)
        if val('domicile_1','adresse_siege_social_1'): txt(c, val('domicile_1','adresse_siege_social_1'), 246, 216)
        if val('domicile_2','adresse_siege_social_2'): txt(c, val('domicile_2','adresse_siege_social_2'), 245, 234)
        if d.get('qualite'): txt(c, d['qualite'], 244, 249)
        if val('societe','nom_societe'): txt(c, val('societe','nom_societe'), 244, 265)
        if val('adresse_1','adresse_siege_social_1'): txt(c, val('adresse_1','adresse_siege_social_1'), 244, 282)
        if val('adresse_2','adresse_siege_social_2'): txt(c, val('adresse_2','adresse_siege_social_2'), 243, 297)
        if d.get('num_tva') or d.get('num_entreprise'): txt(c, d.get('num_tva') or d.get('num_entreprise'), 243, 312)
        if d.get('date_signature'): txt(c, d['date_signature'], 203, 782)
    overlays[14] = make_overlay(draw_p15)

    return merge_selective(tpl, overlays).getvalue()

def fill_procuration_pdf(d):
    p, c = newcan()
    if d.get('num_entreprise'): txt(c, d['num_entreprise'], 215, 115)
    if d.get('denomination'): txt(c, d['denomination'], 184, 135)
    if d.get('rue'): txt(c, d['rue'], 119, 152)
    if d.get('numero'): txt(c, d['numero'], 440, 153)
    if d.get('boite'): txt(c, d['boite'], 571, 153)
    if d.get('code_postal'): txt(c, d['code_postal'], 145, 174)
    if d.get('commune'): txt(c, d['commune'], 286, 173)
    if d.get('pays'): txt(c, d['pays'], 482, 174)
    if d.get('num_onss'): txt(c, d['num_onss'], 476, 118)
    if d.get('num_affiliation_employeur'): txt(c, d['num_affiliation_employeur'], 274, 268)
    if d.get('trimestre_debut'): txt(c, d['trimestre_debut'], 202, 518)
    if d.get('trimestre_fin'): txt(c, d['trimestre_fin'], 462, 520)
    if d.get('date_signature'): txt(c, d['date_signature'], 186, 690)
    if d.get('niss_mandant'): txt(c, d['niss_mandant'], 241, 706)
    if d.get('nom_mandant'): txt(c, d['nom_mandant'], 171, 726)
    c.save()
    return merge(TEMPLATES['procuration'], p, 1).getvalue()

def fill_dispense_pdf(d):
    d = with_signatory_fallbacks(d)
    p, c = newcan()
    if d.get('nom_soussigne'): txt(c, d['nom_soussigne'], 334, 188)
    if d.get('qualite'): txt(c, d['qualite'], 255, 206)
    if d.get('societe'): txt(c, d['societe'], 463, 208)
    if d.get('num_entreprise'): txt(c, d['num_entreprise'], 514, 222)
    if d.get('depuis_date'): txt(c, d['depuis_date'], 187, 238)
    if d.get('checkbox_10pct'): txt(c, 'X', 91, 307, 12)
    c.showPage()
    if d.get('checkbox_20pct'): txt(c, 'X', 90, 312, 12)
    if d.get('etabli_lieu'): txt(c, d['etabli_lieu'], 176, 761)
    if d.get('etabli_date'): txt(c, d['etabli_date'], 329, 761)
    c.save()
    return merge(TEMPLATES['dispense'], p, 2).getvalue()

def fill_mensura_pdf(d):
    p, c = newcan()
    if d.get('nom_entreprise'): txt(c, d['nom_entreprise'], 144, 236)
    if d.get('siege_social_1'): txt(c, d['siege_social_1'], 148, 289)
    if d.get('siege_social_2'): txt(c, d['siege_social_2'], 147, 302)
    if d.get('siege_exploitation'): txt(c, d['siege_exploitation'], 167, 344)
    if d.get('telephone'): txt(c, d['telephone'], 189, 371)
    if d.get('gsm'): txt(c, d['gsm'], 439, 368)
    if d.get('email'): txt(c, d['email'], 184, 410)
    if d.get('tva_bce'): txt(c, d['tva_bce'], 210, 438)
    if d.get('num_onss'): txt(c, d['num_onss'], 476, 437)
    if d.get('compte_bancaire'): txt(c, d['compte_bancaire'], 233, 467)
    if d.get('code_nace'): txt(c, d['code_nace'], 342, 519)
    if d.get('nb_travailleurs'): txt(c, d['nb_travailleurs'], 617, 517)
    c.showPage(); c.showPage(); c.showPage()
    if d.get('date_cours'): txt(c, d['date_cours'], 322, 125)
    if d.get('fait_lieu'): txt(c, d['fait_lieu'], 181, 194)
    if d.get('fait_date'): txt(c, d['fait_date'], 326, 197)
    if d.get('nom_delegue'): txt(c, d['nom_delegue'], 143, 442)
    c.save()
    return merge(TEMPLATES['mensura'], p, 4).getvalue()

# ============== DISPATCHER ==============
def generate_pdf_bytes(doc_type, data, lang_prefs=None):
    if lang_prefs is None: lang_prefs = {}
    if doc_type in ['accident','att_accident']: return fill_att_accident_pdf(data, lang_prefs.get('accident','fr'))
    if doc_type in ['seppt','att_seppt']: return fill_att_seppt_pdf(data, lang_prefs.get('seppt','fr'))
    if doc_type == 'offre': return fill_offre_pdf(data, lang_prefs.get('offre','fr'))
    generators = {
        'employer': fill_employer_pdf, 'travailleur': fill_travailleur_pdf,
        'independant': fill_independant_pdf, 'dispense': fill_dispense_pdf,
        'procuration': fill_procuration_pdf, 'mensura': fill_mensura_pdf,
    }
    if doc_type in generators: return generators[doc_type](data)
    return None

# ============== ZIP ENDPOINT ==============
@app.route('/debug-request', methods=['POST'])
def debug_request():
    """Capture exactement ce que le frontend envoie."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "No JSON body"}), 400
    documents = normalize_documents(data.get('documents', []))
    form_data = data.get('form_data', {})
    lang_prefs = data.get('language_prefs', {})
    results = {}
    for doc in documents:
        pdf = generate_pdf_bytes(doc, form_data, lang_prefs)
        results[doc] = 'OK - ' + str(round(len(pdf)/1024, 1)) + ' KB' if pdf else 'NULL - doc_type inconnu ou erreur'
    return jsonify({
        "documents_reçus": documents,
        "language_prefs": lang_prefs,
        "form_data_keys": list(form_data.keys()),
        "résultats_generation": results
    })

@app.route('/download-all-zip', methods=['POST'])
def download_all_zip():
    try:
        data = request.get_json()
        if not data: return jsonify({"error": "No data provided"}), 400
        documents = normalize_documents(data.get('documents', []))
        form_data = data.get('form_data', {})
        language_prefs = data.get('language_prefs', {})
        if not documents: return jsonify({"error": "No documents selected"}), 400
        # Étape 2A : on mémorise l'employeur (sans bloquer la génération si ça échoue)
        save_employeur(form_data)
        zip_buffer = io.BytesIO()
        static_docs_added = set()
        FILENAMES = {
            'employer': 'Fiche_employeur.pdf', 'travailleur': 'Fiche_travailleur.pdf',
            'independant': 'Fiche_independant.pdf', 'dispense': 'Dispense_precompte.pdf',
            'procuration': 'Procuration_ONSS.pdf', 'mensura': 'Contrat_Mensura.pdf',
        }
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            for doc_type in documents:
                try:
                    pdf_bytes = generate_pdf_bytes(doc_type, form_data, language_prefs)
                    if pdf_bytes:
                        if doc_type == 'offre':
                            lang = language_prefs.get('offre','fr').upper()
                            filename = f"Offre_de_collaboration_{lang}.pdf"
                        elif doc_type in ['accident','att_accident']:
                            lang = language_prefs.get('accident','fr').upper()
                            filename = f"Attestation_accident_travail_{lang}.pdf"
                        elif doc_type in ['seppt','att_seppt']:
                            lang = language_prefs.get('seppt','fr').upper()
                            filename = f"Attestation_SEPPT_{lang}.pdf"
                        else:
                            filename = FILENAMES.get(doc_type, f"{doc_type}.pdf")
                        zf.writestr(filename, pdf_bytes)
                        print(f"[ZIP] Added: {filename}")
                        bundle = get_bundle_for_document(doc_type)
                        for static_key in bundle:
                            if static_key not in static_docs_added:
                                static_bytes, display_name = get_static_document_bytes(static_key)
                                if static_bytes:
                                    zf.writestr(display_name, static_bytes)
                                    static_docs_added.add(static_key)
                                    print(f"[ZIP] Added static: {display_name}")
                except Exception as e:
                    print(f"Error processing {doc_type}: {str(e)}")
                    continue
        zip_buffer.seek(0)
        return send_file(zip_buffer, mimetype='application/zip', as_attachment=True,
                        download_name=f'documents_persoproject_{datetime.now().strftime("%Y%m%d_%H%M%S")}.zip')
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ============== MAIN ==============
@app.route('/debug-offre-raw', methods=['GET'])
def debug_offre_raw():
    """Retourne le template brut sans modification pour diagnostiquer les pages."""
    lang = request.args.get('lang', 'fr')
    tpl = TEMPLATES['offre_nl'] if lang == 'nl' else TEMPLATES['offre_fr']
    rd = PdfReader(tpl)
    nb = len(rd.pages)
    # Retourne aussi le PDF brut
    return send_file(tpl, mimetype='application/pdf',
                    as_attachment=True,
                    download_name=f'offre_template_brut_{lang}_{nb}pages.pdf')

@app.route('/debug-each', methods=['GET'])
def debug_each():
    """Teste chaque doc individuellement, retourne JSON avec status + erreur."""
    fake = {
        'nom_societe':'Test SPRL', 'forme_juridique':'SRL',
        'num_entreprise':'BE 0123.456.789', 'num_tva':'BE0123456789',
        'num_onss':'0123456-78', 'telephone_gsm':'+32 2 123 45 67',
        'email':'test@testsprl.be',
        'adresse_siege_social_1':'Rue de la Loi 123', 'adresse_siege_social_2':'1000 Bruxelles',
        'adresse_exploitation_1':'Rue de la Loi 123', 'adresse_exploitation_2':'1000 Bruxelles',
        'nom_prenom_gerant':'Jean Dupont', 'niss_gerant':'85.01.15-123.45',
        'qualite':'Gérant', 'recu_par':'Bureau', 'assurance_loi':'AXA',
        'secteur_activite':'IT', 'reduction_premier':'Oui', 'commission_paritaire':'CP 200',
        'indice_onss':'218.00', 'code_nace':'62.010', 'salaire_garanti':'NON',
        'regime_horaire':'38',
        'lundi_matin_de':'08:00','lundi_matin_a':'12:00','lundi_apres_de':'13:00','lundi_apres_a':'17:00',
        'civilite':'Mr', 'nom_prenom':'Marie Dubois', 'adresse_1':'Rue Test 1', 'adresse_2':'1000 BXL',
        'date_lieu_naissance':'01/01/1990', 'niss':'90.01.01-123.45', 'nationalite':'Belge',
        'etat_civil':'Celibataire', 'nb_enfants':'0', 'date_entree':'01/01/2026',
        'categorie':'Employe', 'fonction':'Dev', 'type_contrat':'CDI',
        'horaire_type':'Fixe', 'heures_semaine':'38', 'remuneration':'3000',
        'compte_bancaire':'BE12 3456 7890 1234', 'nom_employeur':'Test SPRL',
        'date_signature':'25/03/2026', 'nom_soussigne':'Jean Dupont',
        'depuis_date':'01/01/2026', 'checkbox_10pct':True,
        'etabli_lieu':'Bruxelles', 'etabli_date':'25/03/2026',
        'societe':'Test SPRL', 'denomination':'Test SPRL',
        'rue':'Rue Test', 'numero':'1', 'code_postal':'1000', 'commune':'Bruxelles', 'pays':'Belgique',
        'num_affiliation_employeur':'0123456', 'trimestre_debut':'1/2026', 'trimestre_fin':'4/2026',
        'niss_mandant':'85.01.15-123.45', 'nom_mandant':'Jean Dupont',
        'nom_entreprise':'Test SPRL', 'siege_social_1':'Rue Test 1', 'siege_social_2':'1000 BXL',
        'siege_exploitation':'Rue Test 1', 'telephone':'+32 2 123 45 67', 'gsm':'+32 470 12 34 56',
        'tva_bce':'BE0123456789', 'nb_travailleurs':'5',
        'date_cours':'01/03/2026', 'fait_lieu':'Bruxelles', 'fait_date':'25/03/2026',
        'nom_delegue':'Jean Dupont', 'represente_par':'Jean Dupont',
        'date_entree_jour':'01', 'date_entree_mois':'janvier', 'date_entree_annee':'2026',
        'date_fait':'25/03/2026', 'domicile_1':'Rue Test 1', 'domicile_2':'1000 BXL',
        'etablie_1':'Rue Test 1', 'etablie_2':'1000 BXL',
    }
    lang_prefs = {'seppt':'fr','accident':'fr','offre':'fr'}
    docs = ['employer','travailleur','independant','seppt','accident','dispense','procuration','mensura','offre']
    results = {}
    for doc in docs:
        try:
            pdf_bytes = generate_pdf_bytes(doc, fake, lang_prefs)
            if pdf_bytes:
                results[doc] = {'status':'OK', 'size_kb': round(len(pdf_bytes)/1024, 1)}
            else:
                results[doc] = {'status':'ERROR', 'error': 'generate_pdf_bytes returned None'}
        except Exception as e:
            import traceback
            results[doc] = {'status':'ERROR', 'error': str(e), 'trace': traceback.format_exc()[-500:]}
    return jsonify(results)

@app.route('/test-zip', methods=['GET'])
def test_zip():
    """Test endpoint — generates ZIP with all docs using fake data. No JS needed."""
    fake = {
        'nom_societe':'Test SPRL', 'forme_juridique':'SRL',
        'num_entreprise':'BE 0123.456.789', 'num_tva':'BE0123456789',
        'num_onss':'0123456-78', 'telephone_gsm':'+32 2 123 45 67',
        'email':'test@testsprl.be',
        'adresse_siege_social_1':'Rue de la Loi 123', 'adresse_siege_social_2':'1000 Bruxelles',
        'adresse_exploitation_1':'Rue de la Loi 123', 'adresse_exploitation_2':'1000 Bruxelles',
        'nom_prenom_gerant':'Jean Dupont', 'niss_gerant':'85.01.15-123.45',
        'qualite':'Gérant', 'recu_par':'Bureau',
        'assurance_loi':'AXA', 'seppt':'Mensura', 'secteur_activite':'IT',
        'reduction_premier':'Oui', 'commission_paritaire':'CP 200',
        'indice_onss':'218.00', 'code_nace':'62.010', 'salaire_garanti':'NON',
        'regime_horaire':'38',
        'lundi_matin_de':'08:00','lundi_matin_a':'12:00','lundi_pause_de':'12:00','lundi_pause_a':'13:00','lundi_apres_de':'13:00','lundi_apres_a':'17:00',
        'mardi_matin_de':'08:00','mardi_matin_a':'12:00','mardi_pause_de':'12:00','mardi_pause_a':'13:00','mardi_apres_de':'13:00','mardi_apres_a':'17:00',
        'mercredi_matin_de':'08:00','mercredi_matin_a':'12:00','mercredi_pause_de':'12:00','mercredi_pause_a':'13:00','mercredi_apres_de':'13:00','mercredi_apres_a':'17:00',
        'jeudi_matin_de':'08:00','jeudi_matin_a':'12:00','jeudi_pause_de':'12:00','jeudi_pause_a':'13:00','jeudi_apres_de':'13:00','jeudi_apres_a':'17:00',
        'vendredi_matin_de':'08:00','vendredi_matin_a':'12:00','vendredi_pause_de':'12:00','vendredi_pause_a':'13:00','vendredi_apres_de':'13:00','vendredi_apres_a':'17:00',
        'cameras':'2 caméras entrée', 'trousse_secours':'Bureau accueil',
        'vetements_fourniture':'Oui', 'vetements_entretien':'Non',
        'primes':'Prime nuit 25%', 'secretariat_actuel':'Aucun',
        'nom_comptable':'Pierre Martin', 'coord_comptable':'pierre@compta.be',
        'origine':'Internet', 'civilite':'Mr', 'nom_prenom':'Marie Dubois',
        'adresse_1':'Rue Example 456', 'adresse_2':'1050 Ixelles',
        'date_lieu_naissance':'01/01/1990 à Bruxelles', 'niss':'90.01.01-123.45',
        'nationalite':'Belge', 'carte_identite':True, 'etat_civil':'Celibataire',
        'nb_enfants':'0', 'nb_handicapes':'0', 'date_entree':'01/01/2026',
        'categorie':'Employe', 'fonction':'Développeur', 'type_contrat':'CDI',
        'horaire_type':'Fixe', 'heures_semaine':'38', 'remuneration':'3000 EUR brut/mois',
        'compte_bancaire':'BE12 3456 7890 1234', 'nom_employeur':'Test SPRL',
        'date_signature':'25/03/2026', 'nom_soussigne':'Jean Dupont',
        'depuis_date':'01/01/2026', 'checkbox_10pct':True,
        'etabli_lieu':'Bruxelles', 'etabli_date':'25/03/2026',
        'societe':'Test SPRL', 'denomination':'Test SPRL',
        'rue':'Rue de la Loi', 'numero':'123', 'code_postal':'1000',
        'commune':'Bruxelles', 'pays':'Belgique', 'num_affiliation_employeur':'0123456',
        'trimestre_debut':'1/2026', 'trimestre_fin':'4/2026',
        'niss_mandant':'85.01.15-123.45', 'nom_mandant':'Jean Dupont',
        'nom_entreprise':'Test SPRL', 'siege_social_1':'Rue de la Loi 123',
        'siege_social_2':'1000 Bruxelles', 'siege_exploitation':'Rue de la Loi 123',
        'telephone':'+32 2 123 45 67', 'gsm':'+32 470 12 34 56',
        'tva_bce':'BE0123456789', 'nb_travailleurs':'5',
        'date_cours':'01/03/2026', 'fait_lieu':'Bruxelles', 'fait_date':'25/03/2026',
        'nom_delegue':'Jean Dupont', 'represente_par':'Jean Dupont',
        'date_entree_jour':'01', 'date_entree_mois':'janvier', 'date_entree_annee':'2026',
        'date_fait':'25/03/2026',
        'domicile_1':'Rue de la Loi 123', 'domicile_2':'1000 Bruxelles',
        'etablie_1':'Rue de la Loi 123', 'etablie_2':'1000 Bruxelles',
    }
    lang_prefs = {'seppt':'fr','accident':'fr','offre':'fr'}
    documents = ['employer','travailleur','independant','seppt','accident','dispense','procuration','mensura','offre']
    FILENAMES = {
        'employer':'Fiche_employeur.pdf','travailleur':'Fiche_travailleur.pdf',
        'independant':'Fiche_independant.pdf','dispense':'Dispense_precompte.pdf',
        'procuration':'Procuration_ONSS.pdf','mensura':'Contrat_Mensura.pdf',
    }
    zip_buffer = io.BytesIO()
    static_docs_added = set()
    errors = []
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        for doc_type in documents:
            try:
                pdf_bytes = generate_pdf_bytes(doc_type, fake, lang_prefs)
                if pdf_bytes:
                    if doc_type == 'offre': filename = 'Offre_de_collaboration_FR.pdf'
                    elif doc_type in ['accident','att_accident']: filename = 'Attestation_accident_travail_FR.pdf'
                    elif doc_type in ['seppt','att_seppt']: filename = 'Attestation_SEPPT_FR.pdf'
                    else: filename = FILENAMES.get(doc_type, f'{doc_type}.pdf')
                    zf.writestr(filename, pdf_bytes)
                    for static_key in get_bundle_for_document(doc_type):
                        if static_key not in static_docs_added:
                            static_bytes, display_name = get_static_document_bytes(static_key)
                            if static_bytes:
                                zf.writestr(display_name, static_bytes)
                                static_docs_added.add(static_key)
            except Exception as e:
                errors.append(f'{doc_type}: {str(e)}')
    if errors:
        print('TEST ZIP ERRORS:', errors)
    zip_buffer.seek(0)
    return send_file(zip_buffer, mimetype='application/zip', as_attachment=True,
                    download_name='test_tous_docs_persoproject.zip')

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
