"""Corrige les erreurs connues de la page NL du SPF (à lancer après parse_fse.py).

Pourquoi une table EXPLICITE et pas un appariement automatique FR/NL ?
Parce que l'automatique a été essayé et s'est révélé dangereux : les numéros de voirie
ne sont pas discriminants. « Marlylaan 15 bus 8 » s'apparie à « Stuiversstraat 8 », et
deux immeubles distincts partagent « 15/8 » à l'intérieur d'une même CP (1120 et 1210).
Chaque tentative produisait de NOUVELLES adresses fausses. Sur 128 CP, seules 3 ont un
écart FR/NL sur le fonds réellement imprimé : on les traite nommément.

Chaque correction n'est appliquée QUE si la valeur fautive est encore présente. Si le
SPF corrige sa page, la correction devient un no-op et le script le signale — elle
pourra alors être retirée.

Usage :  python3 reconcilier_fse.py fse_nl.json
"""
import json
import sys

# {CP: (adresse fautive telle que publiée, adresse corrigée, preuve)}
CORRECTIONS_NL = {
    '304': (
        'Square Sainctelette 13-15, 4020 LUIK',
        'Square Sainctelette 13-15, 1000 BRUSSEL',
        "36 entrées FR et 35 entrées NL situent le Square Sainctelette 13-15 à "
        "1000 Bruxelles ; seule la CP 304 en NL dit « 4020 LUIK » (Liège). Ce square "
        "est à Bruxelles.",
    ),
    '152.01': (
        'Anspachlaan 111/014 , 1040 BRUSSEL',
        'Anspachlaan 111/014, 1000 BRUSSEL',
        "toutes les entrées FR du boulevard Anspach 111 disent 1000, et les entrées NL "
        "de l'Anspachlaan 111 (CP 132, 145, 302, 320) aussi ; 1040 = Etterbeek, où ce "
        "boulevard ne passe pas.",
    ),
    '225.01': (
        'Anspachlaan 111/014 , 1040 BRUSSEL',
        'Anspachlaan 111/014, 1000 BRUSSEL',
        "même immeuble et même erreur que la CP 152.01.",
    ),
}

# Coquilles de dénomination sur la page FR du SPF. {CP: (fautif, corrigé)}.
# CP 200 : « employers » (anglais) pour « employés » — visible sur les règlements réels.
CORRECTIONS_DENOM_FR = {
    '200': ('Commission paritaire auxiliaire pour les employers',
            'Commission paritaire auxiliaire pour les employés'),
}

# Fonds rattachés à la MAUVAISE sous-commission : la page « CP 140 » du SPF liste les
# fonds du secteur autobus/autocars (140.01) et le parseur les recopie sur TOUTES les
# sous-commissions 140.xx. Or la 140.03 (transport de choses et logistique pour compte
# de tiers) a son propre fonds : le SFTL. {CP: (marqueur du fonds fautif, nouveaux
# fonds, preuve)} — appliqué uniquement si le fonds fautif est encore présent.
CORRECTIONS_FONDS_NL = {
    '140.03': (
        'autobusdiensten en autocardiensten',
        [{'nom': 'Sociaal Fonds Transport en Logistiek',
          'adresse': 'de Smet de Naeyerlaan 115, 1090 BRUSSEL',
          'tel': '', 'fax': '', 'mail': '', 'web': 'https://www.sftl.be'}],
        "3 sources concordantes (27/07/2026) : le règlement de référence PersoProject "
        "d'un client CP 140.03 (AUTO VIRAGE) imprime « Sociaal Fonds Transport en "
        "Logistiek, de Smet De Nayerlaan 115, 1090 BRUSSEL » ; sftl.be/nl/contact "
        "confirme nom + adresse ; le champ d'application SFTL = transport routier et "
        "logistique. Les fonds autobus/autocars relèvent du secteur 140.01.",
    ),
}
CORRECTIONS_FONDS_FR = {
    '140.03': (
        "d'autobus",
        [{'nom': 'Fonds Social Transport et Logistique',
          'adresse': 'Boulevard de Smet de Naeyer 115, 1090 BRUXELLES',
          'tel': '', 'fax': '', 'mail': '', 'web': 'https://www.fstl.be'}],
        "même correction que NL (fstl.be/fr/contact : Fonds Social Transport et "
        "Logistique, Boulevard de Smet de Naeyer 115, 1090 Bruxelles).",
    ),
}


def _corriger_fonds(data, corrections, label):
    """Remplace la liste de fonds d'une CP quand le fonds fautif y est encore."""
    na = no = 0
    for cp, (marqueur, nouveaux, preuve) in corrections.items():
        v = data.get(cp)
        if not v:
            print(f'  ? CP {cp} absente ({label}) -> correction fonds ignorée')
            continue
        if not any(marqueur in (f.get('nom') or '') for f in v.get('fonds', [])):
            no += 1
            print(f'  = CP {cp} ({label}) : fonds « …{marqueur}… » absent — correction '
                  f'devenue inutile, à retirer')
            continue
        v['fonds'] = [dict(f) for f in nouveaux]
        na += 1
        print(f'  ! CP {cp} ({label}) : fonds remplacés par '
              f'{[f["nom"] for f in nouveaux]}')
        print(f'      motif : {preuve}')
    return na, no

NL_P = sys.argv[1]
FR_P = sys.argv[2] if len(sys.argv) > 2 else None
nl = json.load(open(NL_P, encoding='utf-8'))

applique = obsolete = 0
for cp, (faux, bon, preuve) in CORRECTIONS_NL.items():
    v = nl.get(cp)
    if not v:
        print(f'  ? CP {cp} absente du fichier -> correction ignorée')
        continue
    touche = [f for f in v.get('fonds', []) if f.get('adresse') == faux]
    if not touche:
        obsolete += 1
        print(f'  = CP {cp} : « {faux} » introuvable — le SPF a probablement corrigé sa '
              f'page, cette correction peut être retirée')
        continue
    for f in touche:
        f['adresse'] = bon
        applique += 1
        print(f'  ! CP {cp} : « {faux} » -> « {bon} »')
        print(f'      motif : {preuve}')

fa, fo = _corriger_fonds(nl, CORRECTIONS_FONDS_NL, 'NL')
applique += fa; obsolete += fo
json.dump(nl, open(NL_P, 'w', encoding='utf-8'), ensure_ascii=False, indent=1,
          sort_keys=True)
print(f'{applique} correction(s) NL appliquée(s), {obsolete} devenue(s) inutile(s) -> {NL_P}')

if FR_P:
    fr = json.load(open(FR_P, encoding='utf-8'))
    nd = 0
    for cp, (faux, bon) in CORRECTIONS_DENOM_FR.items():
        v = fr.get(cp)
        if v and v.get('denomination') == faux:
            v['denomination'] = bon
            nd += 1
            print(f'  ! CP {cp} : dénomination « {faux} » -> « {bon} »')
        elif v:
            print(f'  = CP {cp} : « {faux} » introuvable — correction devenue inutile')
    fa, _ = _corriger_fonds(fr, CORRECTIONS_FONDS_FR, 'FR')
    json.dump(fr, open(FR_P, 'w', encoding='utf-8'), ensure_ascii=False, indent=1,
              sort_keys=True)
    print(f'{nd} dénomination(s) FR corrigée(s), {fa} liste(s) de fonds -> {FR_P}')
