"""Assemble le fichier livré au backend : province -> adresse des services de contrôle.

Règle de sûreté : la page FR fait foi. On n'accepte la variante NL que si son CODE
POSTAL concorde avec le FR — sinon c'est que l'une des deux pages est périmée.
Cas réel : le Contrôle des lois sociales de Liège a déménagé le 15/01/2024 ; la page
NL affiche toujours l'ancienne adresse (Rue Natalis 49, 4020) avec un simple avis,
alors que la FR donne la bonne (Rue de Fragnée 2 boîte 205, 4000).
"""
import json
import re

PROVINCES = {
    'Anvers': ('anvers', 'antwerpen'),
    'Brabant wallon': ('brabant wallon', 'waals-brabant'),
    'Brabant flamand': ('brabant flamand', 'vlaams-brabant'),
    'Bruxelles': ('bruxelles', 'brussel'),
    'Flandre occidentale': ('flandre occidentale', 'west-vlaanderen'),
    'Flandre orientale': ('flandre orientale', 'oost-vlaanderen'),
    'Hainaut': ('hainaut', 'henegouwen'),
    'Liège': ('liège', 'liege', 'luik'),
    'Limbourg': ('limbourg', 'limburg'),
    'Luxembourg': ('luxembourg', 'luxemburg'),
    'Namur': ('namur', 'namen'),
}


def provinces_de(ressort):
    r = ressort.lower()
    trouve = []
    for prov, mots in PROVINCES.items():
        if any(m in r for m in mots):
            trouve.append(prov)
    # « Brabant wallon » contient « brabant » mais pas « brabant flamand » : les
    # motifs sont assez spécifiques pour ne pas se marcher dessus.
    return trouve


def charge(fr_json, nl_json):
    FR = {x['fichier'].replace('.html', ''): x for x in json.load(open(fr_json))}
    NL = {x['fichier'].replace('_nl.html', ''): x for x in json.load(open(nl_json))}
    out = {}
    for k, f in FR.items():
        provs = provinces_de(f['ressort'])
        assert provs, f"ressort non reconnu : {f['ressort']!r} ({k})"
        n = NL.get(k)
        # variante NL seulement si les deux pages désignent le MÊME bâtiment
        nl_ok = n and n['cp'] == f['cp'] and n['rue'] and n['localite']
        entree = {
            'fr': {'rue': f['rue'], 'no': f['no'], 'cp': f['cp'], 'localite': f['localite']},
            'nl': ({'rue': n['rue'], 'no': n['no'], 'cp': n['cp'], 'localite': n['localite']}
                   if nl_ok else
                   {'rue': f['rue'], 'no': f['no'], 'cp': f['cp'], 'localite': f['localite']}),
        }
        if n and not nl_ok:
            print(f"  ! {k} : page NL écartée (CP {n['cp']} != {f['cp']}) -> "
                  f"on garde le FR « {f['rue']} {f['no']}, {f['cp']} {f['localite']} »")
        for p in provs:
            out[p] = entree
    return out


data = {'controle_lois': charge('cls.json', 'cls_nl.json'),
        'controle_bienetre': charge('cbe.json', 'cbe_nl.json')}

for svc, d in data.items():
    manque = sorted(set(PROVINCES) - set(d))
    assert not manque, f'{svc} : provinces non couvertes -> {manque}'
    print(f'{svc} : {len(d)}/11 provinces couvertes')

json.dump(data, open('institutions_controle.json', 'w', encoding='utf-8'),
          ensure_ascii=False, indent=1, sort_keys=True)
print('-> institutions_controle.json')
