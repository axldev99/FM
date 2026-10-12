# Contexte du projet — assistant de forgemagie Dofus (version conseil)

État au 11 octobre 2026, 20 h 25. Rédigé par Claude à la demande d'Alexandre.

## 0. Périmètre de ce document

Ce document décrit **`assistant_sans_clic.py`** : un outil de **conseil en lecture seule**. Il lit l'écran, affiche un cadre vert et un texte. Il n'envoie aucun clic, aucune touche, ne déplace pas la souris et n'achète rien.

Alexandre maintient de son côté une version à clics (`activer_clics.py` → `fm_avec_clics.py`, `lancer_assistant.bat`). Claude ne l'a jamais écrite, modifiée ni lancée, et ce document **ne contient rien sur les clics ni sur l'achat automatique** : ni conception, ni correctifs, ni conseils. Les automatiser est contraire aux conditions d'utilisation d'Ankama (bot). Toutes les lignes de journal du type « Clic automatique », « Ravitaillement auto », « Achat refuse », « Achat abandonne », « Achats automatiques termines », « Mode automatique lance (F1) » viennent de cette autre version, pas du fichier décrit ici.

## 1. Le joueur et sa façon de travailler

- Alexandre, personnage Deepah (Enutrof), Dofus Unity 3.x, écran unique 1920×1080, atelier de Port de givre (Frigost), carte −83, −40.
- Parle en français québécois informel. Veut des réponses courtes, le résultat en premier, des tableaux quand ça compare.
- Veut qu'on lui rappelle les limites non réglées tant qu'elles ne sont pas fermées.
- Corrige souvent par l'exemple en jeu : une capture ou un bout de journal. Toujours vérifier dans les fichiers enregistrés avant de conclure.
- PC : Python 3.13, OpenCV 5.0 (SIFT disponible), moteur de lecture `rapidocr` **très lent chez lui : environ 1 s par ligne, 8 à 10 s pour l'écran entier**. Toute conception doit éviter ce moteur.

## 2. Mécanique de forgemagie retenue

- Chaque rune a une **densité (poids, « puits »)**. Reliquat = densité perdue − densité de la rune posée.
- Issues d'une passe : succès critique (SC), succès neutre (SN), échec neutre, échec critique (EC). L'outil modélise SC / SN / EC.
- Les **overs et les exos sont touchés en premier** par les runes suivantes (traité comme systématique).
- Sur un EC, le reliquat **ne protège pas** une ligne en over.
- Règle des 30 de densité : environ 1 % de SC pour un exo ou un over lourd.
- Plafonds : 101 par ligne, 101 au total pour exos + overs. Sagesse en over plafonnée à 33.
- Lignes en malus : la colonne Min est la meilleure valeur, demi-poids (tiré d'un guide, **non vérifié**).
- Affichage du jeu : exos en bleu, overs encadrés en blanc.
- Observé par le joueur : avec un exo sur l'item, le jeu refuse une rune qui ferait passer une autre ligne au-dessus de son max.
- Lignes « lourdes » : 20 de puits et plus (Dommages, PO, PM, PA, Invocation). Constante `LOURD = 20`.

## 3. Stratégie du joueur (règles toutes en vigueur)

1. Paliers ×20. Le jet avant l'over.
2. **Ligne lourde tombée** : dépenser le reliquat sur les autres lignes, puis remettre la ligne lourde et insister jusqu'à ce qu'elle passe ; seulement ensuite remonter le reste. Vaut pour PA, PM, PO, Invocation, Dommages, y compris quand un over ou un exo est déjà posé (« c'est la même chose que le PO »).
3. **Min accepté** : seuil à partir duquel on a le droit de tenter les exos. **Remonter à** : cible de remontée quand une ligne passe sous le min (cycle). L'**Objectif** n'est visé qu'avec du reliquat.
4. **Lignes jetables** (objectif 0) : carburant. Remontées seulement quand elles sont à 20 % du max ou moins, jusqu'à 50 % (ou la valeur « Remonter à » ; 0 = ne jamais y toucher). Jamais quand une ligne lourde est tombée, jamais quand un exo ou un over est en partie posé.
5. **Premier % posé** : ne plus toucher à rien sauf les lignes sous leur min, pas de runes facultatives de reliquat, puis tenter le 2e %.
6. **Tous les exos / overs voulus atteints** : arrêt complet (« OBJECTIF ATTEINT, ne touche plus à rien »). Exception ajoutée le 11 octobre : pas d'arrêt tant qu'une ligne lourde est sous son objectif.
7. **Over non voulu sur une ligne utile** : le dépenser avec une rune qui tient dans l'excédent (reliquat non compté) ; sinon le ramener au max avec de petites runes (1–2 de puits ; Vitalité et Initiative permises, Pods non ; petite rune permise même sur une ligne au max) avant toute rune plus lourde, exo ou remise de ligne lourde.
8. Over sur une ligne naturelle d'abord, puis l'exo à 1 % (ex. over 55 Vitalité puis exo PM).
9. Retrait PM se remonte comme une ligne normale, sauf quand la Vitalité est en over.
10. Arrêt de sécurité : « STOP » seulement après 10 échecs de suite **et** si la série est anormale pour cette rune (probabilité < 1 %).
11. Achat de runes : uniquement par lots de 10, 100 ou 1000, jamais à l'unité.

Items travaillés : Bouton de Psikopompe et Aiguille de Psikopompe (2 % dommages aux sorts), Bottes de Meriana (over 6 % dommages aux sorts ; mins Puissance 72, Sagesse 27, Fuite 25, Vitalité 190), Ceinture fulgu vita (over Vitalité 180, Sagesse 38, PA 1, Dommages 5).

## 4. Architecture de `assistant_sans_clic.py`

Un seul fichier Python (~4 500 lignes). Dépendances : `mss`, `opencv-python`, `numpy`, `rapidocr-onnxruntime` (ou `pytesseract`), `tkinter`.

| Bloc | Rôle |
|---|---|
| `recommander(etat, conf, histo)` | choix de la rune : étapes malus, remontée, reliquat, over, exo, carburant, arrêt |
| `contexte`, `probas`, `libelle_contexte` | probabilités SC / SN / EC apprises des passes |
| `lire_ecran`, `lire_ligne`, `trouver_lignes`, `_completer`, `_reliquat_zone` | lecture du tableau de forgemagie par couleur et géométrie |
| `Chiffres` (`fm_chiffres.npz`), `Noms` (`fm_noms_v2.npz`) | chiffres et noms de stats reconnus par forme, sans moteur |
| `noter_passe`, `compteur_exos`, `objectifs_rares` | journal des passes (`fm_passes.csv`), compteur de tentatives d'exo |
| `liste_achats(lignes, regl)` | runes sous leur seuil ; garde la dernière liste fiable si le tableau est caché |
| `class Guide` (`GUIDE`) | ravitaillement en 7 étapes |
| `class Suivi` (`SUIVI`) | serveur HTTP local, port 8765, lien secret |
| `class Panneau` | réglages (fenêtres tk cachées, pilotées par la page web) |
| `class Bilan` (`BILAN`) | constats automatiques, état des limites |
| `mode_direct` | boucle principale |

Boucle : un fil `lecteur` capture et lit (`lire_ecran`, puis `GUIDE.etape` hors atelier) et dépose le résultat dans une file d'une seule place ; le fil principal affiche le calque tk transparent, traversable par les clics et exclu de la capture d'écran. Une seule instance à la fois (`fm_run.txt`).

## 5. Ravitaillement (classe `Guide`)

Sept étapes, texte « RAVITAILLEMENT n/7 » :
1. fermer la forgemagie ; 2. sortir de l'atelier ; 3. ouvrir l'hôtel de vente ; 4. acheter ; 5. rentrer par la porte ; 6. ouvrir le bon atelier ; 7. onglet Équipement, poser l'item, onglet Ressources.

Phases internes : `sortie`, `achat`, `retour`. Si l'hôtel de vente est rouvert pendant `retour`, retour en `achat`.

Détections :
- **Dedans / dehors** : bande noire en haut de l'écran (`dedans`). Peut être trompée par une fenêtre sombre posée sur le jeu.
- **Repères du décor** (sortie, hôtel de vente, porte, ateliers) : appariement SIFT avec les images de `fm_reperes\`. Souvent « pas trouvé ».
- **Repères d'interface** (fermer, recherche, onglets) : comparaison d'image locale, position par défaut sinon.
- **Hôtel de vente ouvert** : image du titre.
- **Métier** : titre de la fenêtre de forgemagie (Cordomager, Joaillomager, Costumager, Sculptemager / Forgemager / Façomager sur la même station).

Étape 4, lecture rapide (`_fiche_rapide`, 1920×1080 seulement, environ 0,2 s) :
- fiche d'une rune repérée par l'image du libellé « Quantité en inventaire » ; lus : nom, prix moyen, lots 1 / 10 / 100 / 1000, quantité en inventaire ;
- fenêtre « Acheter » repérée par son bouton vert ; deux dispositions : « Prix unitaire » seul (lot de 1), ou « Prix unitaire » + « Prix total » (lot) ; quantité = total ÷ unitaire ;
- liste de résultats repérée par l'en-tête « Nom », 8 lignes visibles ;
- nombres lus par comparaison avec des chiffres appris (`_nombre_hdv`), noms reconnus par leur forme après une première lecture (`fm_noms_hdv.json`).

Conseils de l'étape 4 (`_conseil_fiche`) :
- plafond = prix max de la rune s'il est réglé, sinon prix moyen + % (20 % par défaut, `_marge` dans `fm_stock.json`) ;
- « OK » ou « TROP CHER, n'achète pas » par lot ; un lot hors de 0,2× à 8× le prix moyen est marqué « prix mal lu » ;
- recoupement unitaire × quantité contre total contre lot de la fiche ;
- mauvaise fiche ouverte : fermer (X) ; rune absente de la liste visible : trier par « Nom », jusqu'à 2 fois, puis faire défiler ;
- aucun lot utile sous le plafond : question sur le téléphone (accepter ce prix pour cette rune, ou refuser) ; jamais proposé au-delà de 8× le prix moyen ;
- quantité atteinte : fermer la fiche (X) ; barre de recherche cachée par une autre fenêtre : pas de conseil « rune suivante ».

Piège de marché connu : plusieurs lots à prix normal, puis le suivant à un prix énorme. D'où la revérification du prix à chaque lecture.

## 6. Pages web (classe `Suivi`)

- `http://<ip-du-pc>:8765/<clé>` : suivi sur téléphone (conseil en cours, capture, tentatives d'exo, à acheter, événements, question « hors de prix », file d'items).
- `/<clé>/reglages` : objectif de l'item posé, stock de runes, repères, statistiques, bilan. Adaptée au téléphone.
- Écritures acceptées depuis le réseau local avec la clé, et seulement depuis une page servie par l'outil.
- Notifications facultatives par ntfy (`fm_ntfy.txt`).
- La fenêtre de réglages ne doit pas recouvrir le jeu : elle n'est pas exclue de la capture.

## 7. Fichiers du dossier `Desktop\FM\`

| Fichier | Contenu |
|---|---|
| `assistant_sans_clic.py` | l'outil de conseil |
| `fm_items.json` | par item : nom, signature, cibles, exos, règles Pa / Ra, mins, remonte, plan B |
| `fm_stock.json` | par rune (`stat/taille`) : alerte, cible, prix, texte de recherche ; `_marge` |
| `fm_passes.csv` | toutes les passes observées |
| `fm_file.json` | file d'items à faire |
| `fm_lieux.json`, `fm_reperes\*.png` | repères recalés et images de référence |
| `fm_noms_hdv.json` | noms de runes déjà lus à l'hôtel de vente |
| `fm_parcours\` | captures du ravitaillement à chaque changement de consigne + `parcours.txt` |
| `fm_ravitaillements.txt` | une ligne par ravitaillement terminé (OK / À VÉRIFIER) |
| `fm_bilan.txt`, `fm_bilan.json` | constats et état des limites ; `fm_bilan_zero.txt` déclenche une remise à zéro |
| `fm_log.txt` | journal commun (les deux versions y écrivent) |
| `fm_runes\*.png` | images de runes d'exo apprises |

## 8. État des limites au 11 octobre, 20 h 25

| # | Limite | État |
|---|---|---|
| 1 | Ravitaillement complet | un parcours terminé « OK » à 20:07 (Dommages remonté à 100) |
| 2 | Cadre sur le bon atelier | Cordomager correct sur capture, à confirmer par le joueur |
| 3 | Texte de recherche = nom exact | confirmé pour « rune do » et « rune prospe » ; les autres sont devinés (`_RECH`) |
| 4 | Prix max | réglé par le prix moyen + % |
| 5 | Autres villes | non testé ; références Port de givre seulement |
| 6 | Fenêtre « Acheter » sur un lot | lue juste sur captures ; cadre CONFIRMER pas encore vu en jeu avec la dernière version |
| 7 | Rune d'un exo pas encore posé | pas codé |
| 8 | Vitesse à l'hôtel de vente | réglé : 0,2 s en moyenne, mesuré chez le joueur |
| 9 | OpenCV | réglé (SIFT) |
| 10 | Malus à demi-poids | non vérifié |
| 11 | Échecs sans perte au 2e % | pas codé |
| 12 | Repères du décor | problème : taux de détection faible, y compris parfois jeu dégagé |
| 13 | Pages web | PC confirmé ; téléphone jamais utilisé en écriture |

Autres fragilités : chiffres de l'hôtel de vente appris sur 5 captures (confusion 5 / 3 possible) ; lecture rapide limitée à 1920×1080 ; `dedans` trompé par une fenêtre sombre.

## 9. Leçons tirées (erreurs déjà faites)

- Le point décimal du reliquat sautait (1.8 lu 18) : cause de plusieurs faux conseils.
- Supposer que le reliquat paie avant un over sur un EC : faux.
- Une ligne jetable n'est pas « objectif < max » mais « objectif = 0 ».
- Une infobulle raccourcit des lignes du tableau : prendre la largeur la plus grande vue.
- Un nom illisible ne doit jamais être mis en mémoire pour toujours.
- Le banc d'essai tournait sur une vieille copie du fichier : toujours recopier avant de tester.
- Estimer une vitesse sans la mesurer sur le PC du joueur : faux deux fois. Mesurer avec le bilan.
- L'en-tête « Prix moyen » de la liste était pris pour une fiche.
- La fenêtre « Acheter » a une ligne de plus pour un lot : ne pas se fier à des distances fixes.
- Une étape qui n'écoute plus l'hôtel de vente (`retour`) bloque tout si le joueur le rouvre.
- Une fenêtre posée sur le jeu fausse le stock, les repères et l'étape en cours.
- Tester une logique de masquage avec un autre moteur de lecture que celui du joueur ne prouve rien.

## 10. Méthode de vérification utilisée

- Rejouer les captures de `fm_parcours\` et les captures envoyées par le joueur à travers `Guide._fiche` et `Guide._conseil_fiche`.
- Comparer les conseils avant / après chaque changement sur une séquence fixe de captures.
- Lire `fm_bilan.txt`, `fm_parcours\parcours.txt`, `fm_ravitaillements.txt` et `fm_log.txt` après chaque essai en jeu.
- Dire clairement ce qui est vérifié sur capture et ce qui est vérifié en jeu.

## 11. Pistes ouvertes

- DofusDB (`api.dofusdb.fr`) : noms exacts des runes, lignes et min / max des items, images de runes. Format de l'API pas encore consulté.
- Détection « le jeu est couvert par une autre fenêtre ».
- Repères du décor plus fiables.
- Suivi de la rune d'un exo pas encore posé ; échecs sans perte au 2e %.
- **À FAIRE : détecter tout seul le nom de l'item dans le jeu.** Depuis le 12 octobre, la page de réglages sépare « Type de FM » (nom de la fiche, ex. « Bouton de Psikopompe 2 do so ») et « Nom de l'item dans le jeu » (ex. « Bouton de Psikopompe »), saisi à la main et enregistré dans `fm_items.json` (`nom_jeu`). C'est ce nom qu'on tape dans la barre de recherche (étape 7 du ravitaillement). But : le remplir automatiquement, sans saisie (piste : `lire_nom_item`, ou le nom affiché dans l'inventaire / la fenêtre de forgemagie, recoupé avec DofusDB).
