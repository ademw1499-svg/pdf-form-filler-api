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
    json.dump(fr, open(FR_P, 'w', encoding='utf-8'), ensure_ascii=False, indent=1,
              sort_keys=True)
    print(f'{nd} dénomination(s) FR corrigée(s) -> {FR_P}')
