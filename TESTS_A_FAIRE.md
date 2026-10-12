# Tests à faire (mode automatique F1, patch de clics)

Avant chaque test : relancer `lancer_assistant.bat`, jeu dégagé (aucune fenêtre par-dessus). Après : garder `fm_log.txt`.

## Règle de prix
| # | Cas | Attendu |
|---|-----|---------|
| P1 | Prix max défini, prix du lot ≤ max | achat, log « Achat : … » |
| P2 | Prix max défini, prix du lot > max (ex. Pa Prospe max 1300, prix 1404) | pas d'achat, question sur le téléphone, jamais de clic CONFIRMER |
| P3 | Pas de prix max, prix ≤ prix moyen + marge % | achat sans téléphone |
| P4 | Pas de prix max, prix > prix moyen + marge % | question sur le téléphone |
| P5 | Lot absurde (ex. Do Per So : 100 000 la rune pour un moyen de 24 095) | refusé |
| P6 | Prix unitaire mal lu (« 404 » au lieu de « 1 404 ») | log « Prix unitaire relu … d'après le total » |

## Rune refusée / boucle
| # | Cas | Attendu |
|---|-----|---------|
| R1 | Stock 20 (limite), aucune rune au bon prix | rune sautée, message téléphone « on la saute 30 min », retour à l'atelier |
| R2 | Après R1, rester à l'atelier plusieurs minutes | aucun nouveau « RAVITAILLEMENT 1/7 » pour cette rune |
| R3 | Après R1, changer le stock de la rune (ou attendre 30 min) | la rune revient dans la liste |
| R4 | Stock 0 sans Pa ni Ra en inventaire, prix trop haut | message « FM ANNULÉE », mode manuel, pas de boucle |
| R5 | Liste de plusieurs runes dont une trop chère | les autres sont achetées, la trop chère est sautée |

## Parcours et clics
| # | Cas | Attendu |
|---|-----|---------|
| C1 | Fiche : clic sur la ligne de la rune | fiche ouverte (jusqu'à 4 clics), sinon log « non ouverte » et mode manuel |
| C2 | Clic ACHETER puis fenêtre « Acheter » | fenêtre lue, CONFIRMER cliqué si tout concorde |
| C3 | Fenêtre « Acheter » qui n'apparaît pas | arrêt, mode manuel, message téléphone, rien de racheté en boucle |
| C4 | Étape 7 : clic sur l'épée puis double clic 1re case | item posé, caler le décalage (+70/+40) si ça rate |
| C5 | Mouvement de souris / Échap pendant l'auto | retour en manuel immédiat |
| C6 | F1 dans Dofus | mode automatique, fenêtre minimisée |
| C7 | Une fenêtre couvre le jeu | le ravitaillement se met en pause et reprend |
| C8 | Quantité à acheter atteinte | plus aucun achat de cette rune |

## Téléphone et DofusDB
| # | Cas | Attendu |
|---|-----|---------|
| T1 | Choix de l'item suivant après un exo / objectif atteint | page proposant le prochain item |
| T2 | Ajouter un item à la file depuis le téléphone (limite 13) | item ajouté |
| T3 | Premier lancement sans cache | `fm_dofusdb.json` créé (103 runes) |
| T4 | Sans internet | les noms viennent du cache, sinon anciens noms devinés |
| T5 | Texte de recherche personnalisé dans « Stock de runes » | prioritaire sur DofusDB |

## Limites de l'autre assistant (CONTEXTE_PROJET.md)
1 parcours complet « OK » · 6 cadre CONFIRMER · 12 repères du décor (porte, HDV) · 14 liste de 2-3 runes · 2 atelier (« Réglé ») · 5 autre ville · 10 malus · 7 rune d'un exo pas posé (non codé) · 11 échecs sans perte (non codé) · 16 pas d'arrêt automatique si une étape ne progresse pas : accepté, ça reclique (arrêt manuel : Échap, souris, F1).

## File d'attente (items)
| F1 | File = 3x même item (ex. Ceinture Fulgurante), objectif atteint sur le 1er | l'outil clique Équipement, cherche le nom, double clic sur la case suivante, remet Ressources, message téléphone « passage au suivant » |
| F2 | Même cas, l'item posé est déjà fini | il est détecté fini aussitôt et l'outil passe à la case suivante |
| F3 | File vide | le téléphone propose l'item suivant (comportement d'avant) |
| F4 | Étape 7 avec plusieurs items du même nom | la bonne case est visée (cases comptées de gauche à droite, 5 par ligne) |
