# File d'atelier : audit et protections

## Constat avant modification

- `fm_file.json` ne contenait que des noms de preselection. Pas d'identifiant de tache, de profil fige ni d'exemplaire en cours persistant.
- `Panneau.nouvel_item` retirait une entree a la pose de l'objet, avant sa reussite. Une signature proche pouvait charger une autre preselection de la file.
- `suite_auto` comptait les objets termines par nom dans `ravito['faits']`, uniquement en memoire, puis choisissait une case d'inventaire par ce compteur. Un changement de tri ou un redemarrage invalidait ce choix.
- La signature naturelle commune ne distinguait pas deux Grithrils. Le lecteur et l'historique pouvaient conserver l'etat de l'exemplaire precedent.
- Des caches d'achat et de runes vues pouvaient survivre au changement d'item. Une rune configuree mais jamais vue pouvait etre assimilee a zero.

## Implementation

`fm_file_atelier.py` gere `fm_file_suivi.json`, cree au premier lancement/besoin. Ce journal est canonique ; `fm_file.json` reste un miroir de noms pour compatibilite. La migration conserve l'ordre et les doublons de l'ancienne liste. Aucun fichier de session ou profil utilisateur n'est rempli par les tests.

Chaque tache a un identifiant distinct, une copie du profil et un etat `attente`, `en_cours`, `suspendu`, `termine` ou `annule`. Une seule tache peut etre en cours. Les profils des taches deja ajoutees sont figes. Modifier la liste n'efface ni la tache en cours ni les reussites. Exception explicite : Enregistrer puis F1 permet de reconfigurer la tache active apres deux lectures fraiches concordantes de l'objet. Meme nom de profil et meme signature naturelle obligatoires ; aucun objet protege ni action incertaine ne peut etre deverrouille. La revision conserve l'ancien profil et le jet dans le journal et ne modifie pas les autres taches. Si un AUTRE profil est explicitement enregistre avec son objet pose, l'ancienne tache est conservee en pause (`suspendu`) et le nouvel objet est active apres les memes controles. Une tache suspendue n'est reprise qu'avec son jet sauvegarde ; ni les reussites ni les actions incertaines ne sont effacees.

Les ecritures utilisent un fichier temporaire, flush/fsync puis remplacement. L'etat memoire n'est publie qu'apres le remplacement reussi. L'intention d'action est sauvegardee avant le clic ; le jet est actualise apres confirmation. Une reussite et ses minimums demandent deux lectures fraiches concordantes, sans action/navigation en attente, puis une sauvegarde avant la transition suivante. Une erreur d'ecriture bloque la suite.

Toute presence de PA/PM/PO/Invo hors jet naturel interdit les runes. Pour la tache en cours, cette protection est memorisee sur disque des son observation, meme si la ligne disparait ensuite de l'OCR. Le jet d'un objet termine est aussi conserve. Les recommandations du moteur FM ne sont pas modifiees ; l'interdiction est un garde d'execution.

Au retour, le jet complet doit correspondre au dernier jet confirme de la tache active. Un candidat est double-clique dans l'atelier pour etre lu, mais ne recoit aucune rune avant cette verification. Les objets proteges sont rendus a l'inventaire. Le prochain indice n'est qu'un candidat a verifier, jamais une preuve d'identite. Les exemplaires termines ne sont pas comptabilises une deuxieme fois.

Les reprises entre taches reutilisent le demarrage et les reperes d'atelier existants. Les memoires de jet, de remise, de rune pointee et de stock sont invalidees pour le nouvel exemplaire, meme de signature identique. Chaque profil charge son propre metier et ses objectifs. Les stocks exo sont verifies a nouveau pour le nouveau profil. Les caches de plan d'achat et de runes vues ne sont pas partages entre taches ; une rune jamais observee n'est pas inferree a zero simplement parce qu'elle figure dans les reglages.

## Limites explicites

- Les identifiants sont ceux des taches, pas des UID internes Dofus. Deux objets inacheves strictement identiques destines au meme profil sont interchangeables ; un autre jet ne l'est pas.
- La selection automatique examine au plus les 15 premieres cases filtrees. Un tri changeant peut conduire a une pause ou a revisiter un candidat ; aucune rune n'est autorisee sur cette seule base.
- Une reprise apres une action dont le resultat est incertain exige une reconciliation manuelle. Le bot ne rejoue pas un achat ou une fusion depuis le journal.
- Un objet deja exo avant la constitution de la file est protege, mais ne valide pas automatiquement une nouvelle tache. Ajouter seulement le nombre d'exemplaires restant a faire.
- Si un exo lourd est present mais que les minimums ne sont pas confirmes, l'objet est protege et la file attend une verification ; elle ne le retouche pas pour reparer le jet.
- Une lecture incomplete, un journal corrompu, des objectifs modifies en cours de tache ou un exemplaire introuvable bloquent l'execution. Il ne faut pas effacer le journal pour contourner ce blocage.
- Les stocks des futurs items restent inconnus tant qu'ils ne sont pas observes. Aucun achat global anticipe pour toute la file n'est implemente.

## Validation

Tests hors jeu dans `test_file_atelier.py` : trois doublons puis un autre profil, retour/reprise, rejet des objets proteges, verrou persistant apres perte de ligne OCR, minimums, profil fige, ordre FIFO, ecritures interrompues, journal corrompu, succes observe avant crash, transition conditionnee a la sauvegarde et separation des stocks. Les tests d'orchestration controlent toujours l'empreinte AST du moteur FM.

La reconnaissance des candidats et les changements d'atelier doivent encore etre valides en jeu : protocole dans `TESTS_A_FAIRE.md`.
