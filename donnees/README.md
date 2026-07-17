# Données officielles embarquées (SPF Emploi)

Ces fichiers sont **versionnés avec le code** : le règlement doit sortir correct sans
dépendre d'une table Supabase que personne n'a remplie.

| Fichier | Sert à | Source |
|---|---|---|
| `fse_fr.json` / `fse_nl.json` | point 9 (dénomination officielle de la CP) et point 4 (fonds de sécurité d'existence : nom + adresse) | [Liste des fonds de sécurité d'existence](https://emploi.belgique.be/fr/themes/concertation-sociale/fonds-de-securite-dexistence/liste-des-fonds-de-securite-dexistence) ([NL](https://emploi.belgique.be/nl/themas/sociaal-overleg/fondsen-voor-bestaanszekerheid/lijst-van-de-fondsen-voor-bestaanszekerheid)) |
| `institutions_controle.json` | article 66 (services de contrôle, par province) | Directions régionales [Contrôle des lois sociales](https://emploi.belgique.be/fr/propos-du-spf/structure-du-spf/inspection-du-travail-dg-controle-des-lois-sociales/directions) et [Contrôle du bien-être au travail](https://emploi.belgique.be/fr/propos-du-spf/structure-du-spf/inspection-du-travail-dg-controle-du-bien-etre-au-travail-7) |
| `institutions_nommees.json` | point 2 (caisse de vacances : ONVA/RJV, d'office) et point 6 (adresse du SEPPT saisi) | [ONVA](https://www.onva.fgov.be/fr/contact) / [RJV](https://www.rjv.fgov.be/nl/contact) ; [liste des SEPPT agréés](https://emploi.belgique.be/fr/agrements/agrement-services-externes-pour-la-prevention-et-la-protection-au-travail-seppt) (FR+NL) |

Ce qui reste en saisie manuelle dans le règlement (données non embarquées, pas de source
fiable et automatisable) : point 3 assurance-loi (dépend du contrat de l'employeur),
point 8 bureau des contributions directes (le SPF Finances n'expose pas de liste par code
postal, seulement un sélecteur interactif — découpage plus fin que la commune).

## Régénérer (à refaire si le SPF met ses pages à jour)

```bash
cd /tmp && REPO=~/persoproject/pdf-form-filler-api
B=https://emploi.belgique.be/fr/propos-du-spf/structure-du-spf

# 1) Fonds de sécurité d'existence (FR + NL)
curl -sL -A Mozilla/5.0 "https://emploi.belgique.be/fr/themes/concertation-sociale/fonds-de-securite-dexistence/liste-des-fonds-de-securite-dexistence" -o fse.html
curl -sL -A Mozilla/5.0 "https://emploi.belgique.be/nl/themas/sociaal-overleg/fondsen-voor-bestaanszekerheid/lijst-van-de-fondsen-voor-bestaanszekerheid" -o fse_nl.html
python3 $REPO/donnees/parse_fse.py fse.html    $REPO/donnees/fse_fr.json
python3 $REPO/donnees/parse_fse.py fse_nl.html $REPO/donnees/fse_nl.json
python3 $REPO/donnees/reconcilier_fse.py       $REPO/donnees/fse_nl.json   # erreurs connues de la page NL

# 2) Services de contrôle : 8 directions par service, + leur version NL via <link hreflang>
for i in 0 1 2 3 4 5 6 7; do curl -sL -A Mozilla/5.0 "$B/inspection-du-travail-dg-controle-des-lois-sociales/directions-$i" -o cls_$i.html; done
for i in 0 1 2 3 4 5 6;   do curl -sL -A Mozilla/5.0 "$B/inspection-du-travail-dg-controle-du-bien-etre-au-travail-$i" -o cbe_$i.html; done
curl -sL -A Mozilla/5.0 "$B/inspection-du-travail-dg-controle-du-bien-etre-au-travail/directions" -o cbe_8.html
# (récupérer aussi chaque page NL : <link rel="alternate" hreflang="nl"> de la page FR, -> cls_N_nl.html / cbe_N_nl.html)
python3 $REPO/donnees/parse_controle.py 'cls_[0-7].html'    cls.json
python3 $REPO/donnees/parse_controle.py 'cls_[0-7]_nl.html' cls_nl.json
python3 $REPO/donnees/parse_controle.py 'cbe_[0-8].html'    cbe.json
python3 $REPO/donnees/parse_controle.py 'cbe_[0-8]_nl.html' cbe_nl.json
python3 $REPO/donnees/build_institutions.py   # -> institutions_controle.json

python3 -m pytest $REPO/tests/test_reglement_officiel.py -q
```

## Pièges des pages sources (déjà gérés — ne pas « simplifier » les parseurs)

- **Niveaux de titre incohérents** : les CP **110** et **216** sont en `<h3>`, toutes les
  autres en `<h2>` → on classe par le *texte* du titre, jamais par son niveau.
- **Un titre, plusieurs CP** : « 102.02 & 102.04 … ».
- **Sous-secteurs** : la CP **140** (transport) est découpée en 140.01…140.09, chacun avec
  SON fonds. La CP 140 nue est donc ambiguë : on lui laisse sa dénomination mais **aucun
  fonds**, plutôt que d'imprimer celui d'un autre sous-secteur. En FR le sous-secteur
  s'écrit « Sous-secteur … (140.06) », en NL « 1. Subsector … (140.01) » (numéroté !).
- **Plusieurs fonds par CP** (52 cas) : le point 4 prend le **premier fonds adressable**,
  c.-à-d. le Fonds social / de sécurité d'existence — pas les fonds « 2e pilier » (pension).
- **Page sans titre « Adresse »** : bien-être Liège met l'adresse juste après le ressort.
- **Fonds « 2e pilier » listés EN PREMIER** : la page ne trie pas les fonds. Pour FR 220 /
  327.01 / 329.01 / 331 et NL 118 / 220 / 329.01, le fonds de pension complémentaire est en
  tête — prendre « le premier fonds » imprimait donc le fonds de pension au point 4, et la
  même CP donnait un fonds différent en FR et en NL. `_fonds_principal` les écarte par leur
  NOM (`RE_FONDS_PENSION`), jamais par leur rang. Les SCP 102.01 et 102.09 n'ont QUE ce
  fonds-là : elles restent volontairement en blanc.
- **Erreurs isolées de la page NL** (`reconcilier_fse.py`, table explicite) : CP 304 situe le
  Square Sainctelette à « 4020 LUIK » alors que 36 entrées FR et 35 NL le situent à 1000
  Bruxelles ; CP 152.01/225.01 mettent l'Anspachlaan 111 en 1040 au lieu de 1000. **Ne pas
  remplacer cette table par un appariement automatique FR/NL** : essayé, les numéros de voirie
  ne discriminent pas (« Marlylaan 15 bus 8 » s'apparie à « Stuiversstraat 8 », et deux
  immeubles partagent « 15/8 » dans une même CP) — chaque tentative créait de NOUVELLES
  adresses fausses.
- **Page NL périmée** : le Contrôle des lois sociales de Liège a déménagé le 15/01/2024 ;
  la page NL affiche encore Rue Natalis 49 (4020) avec un simple avis, la FR donne la
  bonne (Rue de Fragnée 2 boîte 205, 4000). `build_institutions.py` **rejette** la
  variante NL dont le code postal ne concorde pas avec le FR. Un test le verrouille.
