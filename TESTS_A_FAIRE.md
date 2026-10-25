# Tests à faire (mode automatique F1, patch de clics)

## Reprise apres modification volontaire du profil (25 octobre 2026)

Second retest : l'objet est devenu Anneau Volkorne PA alors que la tache Henual etait toujours active. Enregistrer puis F1 sur un autre profil conserve maintenant l'ancienne tache en `suspendu` et active le nouvel objet, uniquement apres deux lectures completes concordantes et sans action incertaine ni protection. Pour reprendre l'ancienne tache suspendue, reposer son jet sauvegarde, choisir son profil, Enregistrer puis F1 ; son identifiant est conserve. Les autres taches et reussites restent intactes.

Multiecran : F1 selectionne maintenant le moniteur ayant la plus grande intersection avec la fenetre Dofus active (coordonnees negatives prises en compte). Le lecteur partage cette nouvelle source et les anciennes captures sont invalidees. En cas d'ecran ambigu, aucune action. Le delai de preparation de l'atelier repart au F1 de reprise, sans renvoyer une commande de trajet. Tester Dofus sur chacun des moniteurs, puis deplacer sa fenetre et refaire F1 ; verifier le message `F1 : capture sur ecran ...`. Ne pas bouger la souris pendant le mode automatique.

Symptome confirme dans le journal : F1 est recu, puis `FILE : objectifs modifies pendant la tache` remet en manuel. La tache Ponctualite d'henual PA conservait petit_exo=agi ; le profil enregistre demandait petit_exo=None. Le jet sauvegarde avait aussi une sagesse differente du jet actuellement pose.

Correction : Enregistrer cree une demande explicite de reconciliation pour le prochain F1. Deux captures fraiches, completes et concordantes de l'objet sont exigees avant mise a jour de la tache active. Le meme profil et la meme signature naturelle sont requis. L'identifiant, les taches suivantes et les reussites sont conserves ; l'ancienne configuration et l'ancien jet restent dans l'historique. Un objet protege ou une action non confirmee ne peuvent pas etre deverrouilles par Enregistrer. F1 seul ne change pas le journal.

Test en jeu : fermer et relancer l'assistant ; garder l'objet inacheve pose dans l'atelier ; verifier le profil et le petit exo souhaites, cliquer Enregistrer ; remettre Dofus au premier plan puis faire un seul F1. Attendre `FILE : profil et objet en cours reconcilies apres Enregistrer`, puis la reprise automatique. Ne pas supprimer `fm_file_suivi.json`. Une action/navigation en attente ou un objet deja exo protege doit rester bloque.

## File persistante : Grithrill PA puis autre item

Redemarrage complet de l'assistant necessaire. La page de suivi contient la file ; ajouter plusieurs fois la meme preselection est permis. La liste affiche les taches en attente ; la tache en cours est affichee separement et sauvegardee. Ajouter les taches AVANT le premier F1 pour compter exactement trois exemplaires. Si une tache est deja en cours, les entrees ajoutees sont les suivantes.

1. Premier controle court : garder un Grithrill deja PA dans l'inventaire comme temoin et un Grithrill non exo a travailler. Ajouter UNE tache Grithrill PA (le temoin ne compte pas comme travail a faire). F1 une seule fois. Si le temoin est choisi, il peut etre pose pour verification puis rendu a l'inventaire ; aucune rune ne doit etre appliquee dessus. Le non-exo doit ensuite etre selectionne. En cas de doute, Echap.
2. File complete : ajouter trois entrees Grithrill PA si trois exemplaires restent a faire, puis une autre preselection avec son nom exact et son metier. S'il y a deja un PA reussi et seulement deux exemplaires a faire, ajouter DEUX entrees, puis l'autre item. Ne pas ajouter de profils dont l'objet n'est pas present.
3. Apres une reussite obtenue pendant cette file, verifier dans le suivi que la tache est terminee et que la suivante avance. Le PA doit rester a 1 ; aucun clic de rune ne doit le viser. La transition de la file ne doit pas utiliser le compteur d'une ancienne case d'inventaire.
4. Echap, fermer completement l'assistant puis relancer avec le temoin et l'exemplaire en cours toujours presents. F1 : le profil et le dernier jet confirme doivent etre retrouves ; aucun objet termine ne doit etre retravaille. Si une action etait encore en cours au moment de la fermeture, une pause explicite de reconciliation est normale.
5. Ravitaillement de l'exemplaire en cours : utiliser une rune effectivement lue dans SON tableau, avec seuil au-dessus du stock et prix maximal renseigne. Verifier retour sur le meme jet, exclusion du temoin PA et reprise. Aucun achat ne doit partir d'un stock inconnu d'un futur item.
6. Au passage a l'autre item : bon atelier, bonne preselection, aucun ancien jet/ravitaillement reutilise. Seules ses runes observees et ses exos demandes sont controles. La fin de toute la file ne doit provoquer aucune rune supplementaire.

Limites : au plus 15 cases filtrees examinees ; deux jets strictement identiques ne donnent pas une identite interne certaine. Une difference avec le jet sauvegarde, un journal illisible ou un exo protege non relu doivent provoquer une pause, pas une selection au hasard. Ne pas effacer `fm_file_suivi.json` pour reprendre : il contient les protections et l'exemplaire en cours.

## Demarrage automatique depuis une autre map ou un atelier vide

Retest 00:53 : entree et pose reussies, puis pause manuelle causee par huit lectures illisibles du stock PA (environ quinze secondes), pas par la reprise FM. La capture conservee montre 11 Ga Pa : le seuil blanc 200 effacait les traits anticreneles du second 1. Le lecteur isole maintenant la bande de chiffres avec seuil 150, sans inclure les reflets de l'icone. Fixture tests_stock_ga_pa_11.png : lecture reelle 11 avec le modele existant, sans OCR. Lorsque le gabarit appris identifie la rune, suppression de l'OCR du champ a chaque essai ; deux captures concordantes et nettoyage X toujours obligatoires. Test isole : exo et petit exo reconnus, stock publie, X effectue, mode automatique conserve et aucun OCR du champ sur ce chemin. Prochain test en jeu : redemarrage complet, preselection, un seul F1 ; trajet si necessaire, porte, atelier, objet, Ressources, quantite PA affichee dans Stock de runes, filtre vide puis plusieurs runes FM sans intervention. Une vraie lecture incertaine ou une interruption utilisateur conserve la pause de securite.

Retest arrivee 00:45 : voyage termine, personnage encore dehors a -83,-40 ; aucune transition ATELIER dans le journal. La verification lit maintenant d'abord la ligne des coordonnees seule sur une capture locale fraiche, conserve les signes moins espaces par l'OCR, et journalise texte brut/position. Deux lectures fraiches restent obligatoires avant delegation au retour d'atelier existant (porte puis etabli puis objet). Le journal precedent ne contenait pas le texte OCR : la cause exacte entre lecture incorrecte et peremption n'est pas demontree. Tests hors jeu : capture locale distincte, expiration de l'ancienne image pendant la lecture, signes espaces, secours OCR et delegation au guide. Validation en jeu encore requise : redemarrer l'assistant, garder la preselection, F1 depuis l'exterieur a -83,-40 ; verifier entree sans nouvelle commande /travel puis preparation et FM autonome.

Retest 00:40 : la commande etait correctement saisie, mais Entree bloquee par la relecture. Capture tests_chat_travel_saisi.png : texte cyan /travel -83,-40, curseur blanc et X gris eloigne dans un champ tres large. La lecture isole maintenant le texte cyan et exclut curseur/X. Reconnaissance exacte du masque de cette commande verifiee avant le secours OCR sur image serree ; aucun seuil tolerant autorisant une autre destination. Le test remplace le 3 par un 8 et retire un signe moins : ces variantes sont refusees. La capture reelle doit valider meme avec un OCR de secours indisponible. Entree maintenue utilise aussi son scan clavier et relache toujours la touche sur interruption. Aucun changement de choix de rune.

Retest de saisie : la preselection est chargee et le journal annoncait /travel envoye, mais l'utilisateur ne voyait aucun texte dans le chat. Le chat utilise maintenant un chemin distinct de la frappe Unicode des recherches HDV/inventaire : touches physiques et scans correspondant a la disposition clavier de la fenetre Dofus, Espace puis Ctrl+A et texte. Le champ du chat est ensuite relu (trois essais maximum). Entree est interdit tant que la commande complete /travel -83,-40 n'a pas ete reconnue exactement. En cas d'echec, pause avec capture locale du champ dans fm_demarrage_saisie.png si le champ est reperable et Dofus actif. Aucun diagnostic « commande lue » sur simple appel clavier. Tests : modificateurs relaches meme sur interruption, mauvaise disposition refusee avant frappe, aucune touche sans autorisation, texte incomplet/autre destination rejete, absence de lecture interdit Entree et le passage a TRAJET. La frappe reelle dans Dofus reste a valider.

Selection hors atelier : le menu Preselection charge maintenant les lignes naturelles depuis la signature sauvegardee, ainsi que objectifs, minima, remontees et plages existantes, sans recalcul ni ecriture du profil. Actuel et stocks non observes restent inconnus. La selection reste affichee apres rafraichissement et le pied de page indique « Objet prevu au prochain F1 ». Aucun Enregistrer n'est requis pour lancer un profil deja sauvegarde et inchange ; Enregistrer reste requis pour conserver des modifications. Choisir la preselection, verifier nom du jeu/atelier, revenir dans Dofus et F1. A l'interieur d'une interface FM avec tableau reconnu, le chargement conserve le comportement existant et ne reconstruit pas les valeurs actuelles. Tests hors jeu sur les deux versions : chargement complet hors atelier, plages/minima conserves, valeurs inconnues, profil non modifie et tableau reel preserve.

Preparation separee du moteur FM, lancee avant sa boucle de decisions. Choisir une preselection enregistree dans Objectif de l'item, verifier son nom dans le jeu. Nouveau champ Atelier de depart : automatique pour un nom de type explicite (anneau, sandales, cape, marteau...), choix manuel pour un nom ambigu. Enregistrer les reglages du profil avant F1. Les anciennes prelections restent compatibles et aucun profil existant n'est migre automatiquement.

Hors destination : fermer l'inventaire/HDV reconnu, sortir d'un interieur seulement si le repere Sortie est reconnu, puis ouvrir le chat avec Espace, remplacer sa saisie par /travel -83,-40, Entree pour envoyer, puis une seconde Entree uniquement si le dialogue de voyage est reconnu. Sans popup, attendre directement le trajet ; un popup tardif est encore detecte sans retaper /travel. La confirmation ne peut etre envoyee qu'une fois. Des captures reelles sont reprises avant les touches car la lecture OCR de la position peut depasser la limite de fraicheur. L'arrivee reste a prouver ; l'envoi du second Entree n'est pas une preuve de trajet termine. Deux lectures fraiches des coordonnees confirment l'arrivee. Le guide valide est reutilise pour porte, metier, Equipement, recherche et double clic. L'objet doit correspondre a la signature naturelle de la preselection, sur deux captures stables. Le profil choisi est conserve meme si plusieurs objectifs ressemblent a l'objet ; la file d'attente n'est pas consommee par ce chargement initial. Puis relire les stocks exo/petit exo et reprendre la FM avec le meme F1.

Un objet deja pose et compatible ne declenche pas de trajet. Un objet incompatible est rendu a l'inventaire par le X reconnu. Un ravitaillement deja engage dans la session conserve son controleur. Une pause apres l'envoi du trajet ne renvoie pas la commande ; un nouveau F1 hors atelier apres une session terminee rearme la preparation. Saisie ou confirmation interrompue, profil/metier manquant, coordonnees illisibles ou reperes inconnus : pause, jamais de clic approximatif ni de commande repetee. Trajet non confirme sous 15 minutes ou atelier non prepare sous 2 minutes : pause. Les menus, combats, dialogues et interieurs inconnus ne sont pas recuperes automatiquement. /travel doit etre utilisable par le personnage ; ses eventuels nouveaux dialogues restent a valider en jeu.

Tests hors jeu : test_demarrage (arrivee, commande unique, captures rejouees/perimees, interruption, profil conserve, file intacte, garde FM, menu commun, raccourci Espace/commande/Entree, popup absent ou tardif confirme une seule fois, rejet des achats et autres destinations, interruption avant la confirmation et captures avant touches). Tests en jeu, apres redemarrage complet de l'assistant :

1. File vide, objet present dans l'inventaire, preselection choisie et nom exact, stock suffisant pour eviter un voyage d'achat immediat. Depuis une autre map exterieure Dofus au premier plan, un seul F1. Verifier ouverture du chat par Espace, commande unique, popup confirme par le second Entree seulement s'il apparait, arrivee, entree, bon atelier, double clic sur l'objet, X du filtre, Ressources, stock exo, puis premiere rune FM.
2. Refaire depuis -83,-40 devant la porte : aucun /travel inutile, meme preparation.
3. Refaire atelier vide deja ouvert, puis avec le bon objet deja pose : pas de depart inutile et aucun autre objet choisi.
4. Interrompre pendant le trajet et reprendre : pas de seconde commande. En cas de blocage, conserver l'ecran et le message DEMARRAGE pour diagnostic.

La navigation et la saisie reelles n'ont pas encore ete validees en jeu. La signature distingue les types d'objets ; elle ne distingue pas deux exemplaires physiques identiques. Limiter le premier essai a un seul exemplaire de l'objet vise.

## Achats successifs Do Terre : popup facultatif a chaque lot

Retest 23:49 : achats, fermeture HDV, retour et selection du Joaillomager valides en jeu ; pose de l'objet echouee. Recherche deja remplie (« grit »), ancien repere textuel Recherche introuvable : repli fixe puis double clic sur la quatrieme case vide au lieu de la premiere case occupee. La pose utilise maintenant la geometrie de la barre d'inventaire reconnue meme remplie, relue apres filtrage. Sans barre ou nom connu, arret sans clic approximatif. Deux captures fraiches du lecteur doivent confirmer le jet pose avant Ressources ; au retour, les valeurs memorisees avant le depart doivent correspondre. Un jet different impose une pause, sans essayer un autre objet a l'aveugle. Cette comparaison ne prouve pas l'identite physique entre deux objets de jet identique. Le X du filtre est nettoye apres l'essai. Tests : capture reelle avec trois anneaux, case attendue (1290,308), mauvais jet, tableau vide, ancienne capture, absence de barre et pas de Ressources avant confirmation.

Retest 23:40 : neuf lots confirmes, stock 14 -> 104, mais fermeture HDV echouee. La fermeture utilise maintenant d'abord le X du titre Inventaire, reconnu par son image et ancre sur la barre de recherche avec ses deux menus. Ni l'engrenage HDV ni le X du filtre ne sont des cibles possibles. Sans reconnaissance, repli Echap existant. Deux captures sans titre HDV restent obligatoires avant la phase retour ; une interruption garde la phase achat. Tests sur capture utilisateur, fenetre deplacee, X masque, controle des coordonnees avec decalage d'ecran et interruption. Retester avec un seul F1 jusqu'au retour et a la reprise FM ; pas besoin de racheter neuf lots si le stock actuel suffit.

Retest 23:30 : meme refus au troisieme lot, prix lu 134999. La relecture OCR seule ne suffisait pas : le decoupage des glyphes 4/9 colles pouvait creer trois chiffres au lieu de deux, parfois avec une confiance trompeuse. Correction du nombre de decoupes dans le lecteur HDV seulement. La capture reelle 13497 et la variante 13499 passent maintenant sans OCR de secours, y compris avec plusieurs compressions JPEG. Les tests de secours OCR restent distincts. Les captures de clic sont aussi conservees par date de modification pour eviter que celles d'une ancienne journee a une heure plus tardive suppriment les nouvelles traces.

Le journal du 17 octobre confirme premier achat avec popup, deuxieme sans popup, puis refus du troisieme sur prix mal lu (134997 au lieu de 13497). La relecture OCR peut maintenant corriger le nombre de chiffres ; sans relecture exploitable, le prix douteux est inconnu et interdit le clic. Apres chaque clic Acheter, observer soit le popup (nom exact, taille et prix controles, bouton Confirmer repere), soit le stock augmente exactement du lot sur deux captures. Le popup peut revenir meme apres un achat direct ; aucun reclic Acheter pendant une attente ambigue.

Tests hors jeu : capture Do Terre avec chiffres colles, capture du popup x100, neuf lots avec popup/direct/popup retarde, neuf achats directs, neuf achats avec confirmation, annulation sur mauvaise rune ou mauvais lot. Test en jeu : si le stock est toujours 30, activer uniquement Do Terre avec alerte 31, cible 100 et prix max choisi. Relancer completement, un seul F1 : sept lots de 10 attendus, puis fermeture HDV et retour/reprise FM. Relever le stock avant toute consommation a l'atelier et restaurer les reglages apres le test. Le parcours complet reste a valider en jeu.

## Selection exo puis Fusionner : relecture fraiche intermediaire

Le test en jeu a montre selection par double clic, puis refus Fusionner pour lecture perimee : la capture de debug et l'attente de selection vieillissaient la lecture FM initiale au-dela de deux secondes. La sequence ne rafraichit plus artificiellement l'horodatage. Apres selection et degagement de la souris, elle consomme une lecture du lecteur existant, capturee apres la selection, fraiche et provenant du meme ecran. Signature naturelle et valeurs/reliquat doivent correspondre au jet initial sans valeurs reprises (rate). Le bouton est localise sur cette image appariee a la lecture validee. Seul cet horodatage valide alimente le controle FM avant Fusionner.

Delai maximum d'attente de quatre secondes, Echap/mode manuel/fenetre active toujours controles ; un changement d'item, de profil ou de jet interdit la fusion. Aucun changement des regles ou probabilites FM, ni de l'age maximal autorise. La confirmation du resultat apres fusion reste active.

Tests test_confirmation : ancienne image rejetee, capture fraiche, jet modifie, lecture perimee et commande composee simulant plus de deux secondes entre selection et fusion. Test d'empreinte FM conserve. Test en jeu : redemarrer completement, F1 une fois ; attendre selection puis Fusionner, sans recliquer F1 en boucle. En cas d'arret, conserver la rune selectionnee et les traces pour diagnostic.

## Premier % do sorts : revalider le jet apres le passage

Le modele existant distingue deja le premier % (contexte exo, SN possible) du deuxieme (exo+, SN nul dans ce modele) ; aucune probabilite n'est modifiee. Pour un objectif de exactement 1 % do sorts, sa presence ne suffit plus a declarer OBJECTIF ATTEINT : toutes les lignes naturelles utiles doivent atteindre leur minimum accepte (objectif par defaut), et les lignes structurelles doivent etre remises selon les regles existantes.

Un jet abime reprend les remontees deja prevues par le moteur, avec le risque de perdre le %. Pas de finition facultative ni de carburant pour une simple descente apres ce passage. Si les lignes sous le minimum sont bloquees ou sans rune jouable, JET A REPRENDRE avec stop, jamais OBJECTIF ATTEINT. Le retour dans les minima suffit : on ne retouche pas toutes les lignes a leur objectif maximal pour conserver le %.

La file ne se declenche plus sur le seul evenement de passe d'exo : elle attend une recommandation OBJECTIF ATTEINT sans stop et aucune action encore en attente de confirmation. Cela ne fournit toujours pas d'identifiant physique certain entre deux objets identiques.

Tests : test_exo_puits (SN suivi d'un jet abime, remise PA, minima, jet bloque, pas de carburant) et test_confirmation (pas de suite sur EXO/JET A REPRENDRE ni pendant une action non confirmee). Empreinte FM mise a jour apres verification que le seul delta moteur concerne la validation et reprise du premier %.

## Premier et seul % dommages aux sorts avant remise structurelle

Correction demandee sur Tourthon : PA absent, reliquat 98,2, autres remontees jouables finies ou bloquees. Un profil demandant exactement 1 % do sorts doit exploiter le puits avant de remettre PA/PM/PO/Invo, tant qu'au moins 15 de reliquat paient la rune. Aucun verrou n'est engage par le conseil EXO DANS LE PUITS. Une fois le % pose, ou le reliquat inferieur au cout, la remise structurelle reprend et peut engager le verrou. Une remise deja engagee reste prioritaire.

Les lignes utiles encore jouables et payees restent traitees avant cette phase. Pas de carburant force, pas de regle nouvelle pour les objectifs 2 %, pas d'extension du verrou aux Dommages. Le passage de l'exo ne garantit pas sa conservation lors de la remise : les valeurs observees sont reevaluees a chaque passe. L'exo utilise la meme selection et les memes probabilites que l'existant.

Tests `test_exo_puits` : replay du Tourthon enregistre dans `tests_tourthon_puits.json`, seuil 15 / 14,9, % pose puis remise, retour de PA et arret, puits superieur au poids du gros jet, quatre lignes structurelles, Dommages exclus, remontee utile et verrou deja engage. Delta syntaxique verifie avant mise a jour de l'empreinte FM.

Redemarrage complet pour ne pas garder en memoire une ancienne phase de remise deja engagee. Valider en manuel le conseil EXO DANS LE PUITS lors d'une prochaine chute naturelle avant F1. La confirmation d'un exo rate sans changement de tableau ni stock lisible reste une limite connue et provoque une pause, jamais une relance aveugle.

## Protection de la finition Pa Do a 17 pour objectif 20

Les branches de reliquat et de recyclage ne doivent pas jouer une petite rune qui ferme la derniere finition configuree : Do elementaire 17 + simple -> 18 interdit si Pa a 17 permet 20 et Pa a 18 depasse le plafond 20. Le moteur peut finir a la Pa ou jouer une autre ligne, sans obligation de consommer le reliquat sur cette ligne. Pa absente : demander l'achat au lieu de casser l'alignement. Les simples 16 -> 17 et 19 -> 20 restent possibles quand le profil les autorise. Le controle est generique et utilise les plages, le gain de rune et le plafond, sans regle speciale de nom d'item.

Tests `test_phases` sur les cinq dommages elementaires et plusieurs reliquats, stock manquant, simples utiles. Seules la protection de finition et ses deux points de filtrage sont ajoutes au moteur ; delta syntaxique verifie avant mise a jour d'empreinte.

## Corrections du test en jeu : survol et petit over de Re crit

Session e82fd41864424cdd8b7c21b2fe164cf7 : les passes etaient appliquees mais le marqueur occulte sur la ligne survolee invalidait toutes les valeurs pour la confirmation. Ce marqueur signale la detection hors couleur/survol ; les valeurs effectivement relues restent exploitables tant que rate est nul et les nombres valides. Les stocks des lignes occultees restent exclus. La souris est maintenant degagee avec le helper existant avant de commencer l'attente. `tests_confirmation_session.json` conserve trois passes reelles qui doivent chacune etre confirmees sur deux captures posterieures a leur envoi.

Correction FM explicitement demandee pendant ce test : Re crit 26/25 offre 2 de poids, donc pas de Ra Vi a 10 si une rune plus petite tient. Le seuil gerer_over protege maintenant tout excedent positif ; auparavant les petits overs de lignes a poids >1 etaient ignores. Test sur Re crit, Puissance et Re %, avec plusieurs reliquats. La nouvelle empreinte du moteur ne differe de la precedente que par cette affectation ; cette equivalence a ete verifiee syntaxiquement avant mise a jour.

Relancer completement apres ce correctif (le simple rechargement de la logique ne recharge pas les clics). Tester 10-20 passes sans bouger la souris ; Echap reste disponible. Verifier action_confirmee et la protection du petit over si ce cas survient naturellement.

## Confirmation des actions avant enchainement

`fm_confirmation.py` ne choisit aucune rune. Le generateur utilise ses attentes pour les passes FM et les transitions du guide. Apres un clic de rune ou une fusion exo envoyee, toute nouvelle entree automatique attend deux captures distinctes, fraiches et prises apres l'envoi. Preuves admises : stock de la rune diminue exactement de 1, ou valeurs/reliquat du tableau modifies et stables. Une disparition du reliquat lu n'est pas une preuve. Une variation inattendue du stock ou un item/profil different laisse l'action ambigue. Aucun SC/SN/EC n'est deduit de cette confirmation.

Sans preuve apres 10 secondes, passage en manuel ; aucune relance automatique au delai ni touche Entree de relance. Une selection/fusion exo non envoyee passe egalement en manuel. La navigation attend une nouvelle consigne reconnue du guide ou le tableau de retour, sur deux captures ; delai de 15 secondes. La fermeture d'un ecran seule, sans prochaine etape lisible, ne suffit pas. Ces contrats couvrent les transitions du guide ; les sequences internes clavier/souris restent des commandes composees, pas des confirmations de chaque touche.

Un achat ne compte plus a l'envoi du clic : quantite initiale obligatoire puis deux lectures de la bonne fiche montrant exactement l'ajout du lot, sous 4 secondes. Sans preuve, arret en manuel avant un nouvel achat. Les plafonds de prix restent ceux de l'existant. Les attentes sont en memoire : pas de reprise d'une action non confirmee au redemarrage.

Reprise F1 depuis le manuel : abandon explicite de l'attente, trace de resynchronisation, nouvelle lecture du jeu. Verifier l'ecran avant F1 ; une attente n'est pas un ordre a rejouer. Un exo rate sans changement du tableau ET sans stock lisible ne peut pas etre confirme : le bot s'arretera. L'identification de deux objets physiques identiques en file reste une limite ; aucun identifiant certain n'est invente.

Tests hors jeu : `python -B -m unittest -v test_confirmation test_securite test_orchestration`. Stock consomme sans changement de jet, anciennes captures, double lecture de la meme capture, OCR instable/perime, delai, mauvaise fiche, transition non reconnue, guard central et generation. Les tests d'empreinte protegent la logique FM validee.

Test en jeu : redemarrer le lanceur ; surveiller d'abord quelques passes ordinaires, puis Echap/F1. Verifier dans le diagnostic action_en_attente puis action_confirmee, sans double clic de relance. Au prochain ravitaillement naturel, verifier navigation_confirmee et achat_confirme. Si arret non confirme, garder la capture et le journal, verifier le jeu avant F1. Cadence et OCR de ces preuves restent a confirmer sur la session reelle.

## Orchestration persistante en observation (15 octobre)

`fm_orchestration.py` suit FM, SORTIE, ACHAT, RETOUR, ATTENTE, PAUSE et TERMINE. Le mode manuel conserve la phase observee sous PAUSE. Le profil et la liste ordonnee des prochains items sont conserves, y compris les doublons ; ils ne constituent pas une identification certaine d'un objet physique identique.

Le diagnostic ecrit `fm_diagnostic/etat_orchestration.json` uniquement lors d'un changement, via remplacement atomique et sur son fil d'ecriture. Les transitions sont egalement tracees dans le journal JSONL borne. Le checkpoint est une trace au mieux : saturation, erreur disque ou fermeture brutale peuvent le rendre ancien. Aucun pilote ne le consomme pour agir. Au redemarrage, l'etat precedent reste une information a verifier ; aucune reprise d'achat, aucun clic, aucune modification de file ou de verrou FM ne sont declenches depuis ce fichier. FM_DIAGNOSTIC=0 desactive aussi ce suivi. La surveillance ne confirme pas encore le resultat des actions.

Tests : `python -B -m unittest -v test_orchestration`. Parcours, pause, fin, stock/file avec doublons, redemarrage apres achat, corruption/schema, absence de reecriture sans changement et panne disque. Une empreinte syntaxique fige les fonctions FM validees ; ne pas la regenerer pour faire passer une modification de strategie.

Verification en jeu au prochain lancement : session normale, une pause Echap et une reprise F1 ; verifier etat/phase_observee dans le checkpoint. Si un ravitaillement survient naturellement, observer SORTIE/ACHAT/RETOUR puis FM. Ne pas provoquer une interruption d'achat pour ce test. Le controleur unique et la reprise securisee restent a brancher apres validation de ce suivi passif.

## Restauration des priorites d'origine (15 octobre)

Le moteur fourni dans `Desktop/FM/assistant_sans_clic.py` est la reference. Les ajouts depensant systematiquement le reliquat avant une ligne lourde, FINIS LA CARAC et le secours du critique sont retires. Le verrou `PhaseRemise` est reactive uniquement pour Invocation, PA, PM et PO, apres une decision REMETS du moteur. Il insiste jusqu'a observation de la cible naturelle, meme apres EC et retour d'un petit reliquat. Dommages ne peut jamais engager ce verrou. Avant engagement, les priorites restent celles d'origine. La finition bonus explicite reste une option apres le jet principal, sans changer ses cibles.

`tests_fm_origine.json` conserve 168 decisions de la source d'origine (chemin et SHA-256 inclus), a objectifs, stock et historique identiques. Les tests les rejouent sur les deux versions. L'attente historique PA avec puits est retablie depuis cette source. Les tests qui exigeaient les nouvelles priorites retirees sont remplaces par cette comparaison ; cela ne prouve pas que toutes les decisions d'origine sont optimales.

Verification en jeu : redemarrer le lanceur, rester en manuel et verifier plusieurs conseils sur l'item courant avant F1. Observer notamment les resistances basses, la remise PM et l'absence des messages FINIS LA CARAC / plages suspendues. Garder le journal et une capture complete si une priorite semble incorrecte. Les clics et achats reels ne sont pas valides par les tests hors jeu.

## Verrou limite Invo / PA / PM / PO

Etat en memoire seulement : changement d'item ou redemarrage efface le verrou. Ligne verrouillee non relue : attente avec stop ; rune absente : demande d'achat sans selection d'une autre ligne. La remise achevee libere le moteur. Cela n'impose aucune nouvelle depense du reliquat avant de choisir REMETS.

Tests `test_phases` : quatre remises apres echec, liberation, changement d'item, lecture manquante, stock absent, exclusion Dommages, 168 etats initiaux identiques a l'origine. Overs controles sur Force/Intelligence/Chance/Agilite : 65 -> Ra -> 75 pour max 70, puis recyclage Pa Vi et Vi simples. Pas de priorite forcee FINIS LA CARAC.

En jeu : redemarrer le lanceur. Apres REMETS PM (ou PA/PO/Invo), un echec doit conserver cette ligne ; son retour autorise les autres conseils. REMETS Dommages ne doit pas afficher remise engagee. Les remises ne sont pas persistees au redemarrage.

## Recyclage de l'over : max naturel protege

Toute rune disponible adaptee peut recycler un over, dont Do elementaire, Puissance et Vitalite. Le budget est l'excedent au-dessus du max naturel, meme si la cible est plus basse : Chance 75/70 et cible 69 donnent 5, pas 6. Si une rune tient dans cet excedent, ne pas choisir une rune qui le depasse. Sans rune qui tient, les anciens recours aux petites runes restent possibles, notamment pour un petit over de Vitalite. Il s'agit d'un budget de risque, pas d'une prediction garantie des pertes de la passe.

Tests `test_phases` : Do Eau sur 75/70, Puissance/Puissance/Vi sur 75/73/71, rejet de Re % a 6 tant qu'une rune a 2 tient, cible 69 comme cible 70 ; memes verifications sur les deux versions et les quatre caracteristiques.

## Finition au reliquat d'un item naturel

Reglage `Ligne bonus — reliquat` (page Objectif, aussi disponible en Tk) : la ligne choisie garde son objectif principal et son role de carburant (si objectif a 0). Le bonus est une seconde etape, apres atteinte de tous les objectifs, y compris celui de la ligne bonus, seules les runes en stock entierement payees par le reliquat et ne depassant pas le max naturel sont proposees. Les plages Pa/Ra ne bloquent pas cette finition. Si plus aucune rune ne tient, stock absent ou max atteint : objectif termine. Pas de finition quand un exo/over est pose ; option inactive si un exo/over est demande dans le profil. Atteindre seulement les minima des autres lignes ne suffit pas pour lancer le bonus.

Profil `Sandales Circulaires du Kimbo TBJ` : option initialisee a Prospection, plafond naturel 20. Aucun autre objectif ni autre profil modifie. Sauvegarde avant activation : `fm_items_avant_finition.json`.

Tests hors jeu : `python -B -m unittest -v test_finition`. En jeu, redemarrer, verifier Ligne bonus = Prospection, lancer le jet normal. Atteindre tout le jet, y compris PP 10, puis attendre `FINITION RELIQUAT` si le puits paie encore une rune. PP au-dela de 10 reste facultative, jusqu'au max naturel 20. Controle web/Tk reel encore a confirmer.

## Diagnostic commun passif

Au prochain redemarrage, `fm_diagnostic/evenements.jsonl` relie session, capture, decision et derniere action envoyee. Les passes restent marquees `passe_inferee` : ce mecanisme ne confirme pas encore chaque action et ne constitue pas une reprise persistante. La confiance OCR globale est `null` (non disponible) ; valeurs, occultations et compteurs de lecture perimee sont conserves.

Ecriture en arriere-plan, file de 64 entrees au maximum ; en saturation les traces sont perdues et comptees, la FM ne doit pas attendre. Trois fichiers JSONL de 5 Mo maximum chacun et 40 captures JPEG plafonnees a 1 Mo chacune ; ces limites concernent uniquement le nouveau dossier. Captures au plus toutes les deux secondes, seulement si Dofus est au premier plan, une seule image en attente. Une capture proposee peut manquer si l'ecriture echoue ; les erreurs sont comptees. `PERF diagnostic` rapporte le cout d'emission des evenements et les compteurs (pas une mesure complete du temps de traitement d'image).

Retour arriere sans changer les regles : variable d'environnement `FM_DIAGNOSTIC=0` avant lancement. Verification en jeu : redemarrer, FM normale une minute, Echap ; verifier la cadence, les traces/captures et les compteurs du journal. Les anciennes captures de debug restent gerees comme avant.

Tests : `python -B -m unittest -v test_diagnostic test_fm_reference test_securite test_fichiers`. Couverture diagnostic : correlation, donnees figees, saturation, panne disque, rotation, fenetre inactive et desactivation. Aucun test n'envoie d'entree au jeu.

## Lancement deterministe

L'ecriture du jeton `fm_run.txt` et du script genere utilise `fm_fichiers.ecrire_texte` : fichier temporaire dans le meme dossier, remplacement apres ecriture complete, six essais maximum sur erreurs transitoires (dont errno 22). Un echec persistant reste une erreur ; on ne demarre pas sans jeton. Tests isoles : `python -B -m unittest -v test_fichiers`. Verification en jeu : relancer normalement et confirmer l'absence du plantage a l'ecriture du jeton. La cause externe exacte de l'erreur Windows n'est pas determinee.

`lancer_assistant.bat` utilise explicitement `assistant_sans_clic.py`. Le generateur sans argument utilise aussi cette source, sans examiner les dates des sauvegardes. Une source absente provoque un echec avant execution du bot ; un chemin explicite reste accepte. Les arguments du lanceur sont toujours transmis au bot.

Tests hors jeu : `python -B -m unittest -v test_lancement test_fm_reference test_securite`. Les tests de lancement utilisent des dossiers temporaires isoles ; aucun assistant n'est lance. Verification manuelle au prochain demarrage habituel : la console doit afficher `assistant_sans_clic.py -> fm_avec_clics.py`.

## Reference du moteur FM (hors jeu)

Les changements de priorite experimentaux sont annules ; voir Restauration des priorites d'origine ci-dessus.

Commande : `python -B -m unittest -v test_fm_reference test_securite`.

`test_fm_reference.py` charge uniquement les regles et fonctions du moteur par analyse syntaxique, sans importer l'application, l'OCR ou l'interface. Aucun clic ni ecriture des donnees metier. Les 17 attentes fixes de `tests_fm_reference.json` caracterisent la version du 15 octobre 2026 ; elles ne sont jamais regenerees par les tests.

Couverture initiale : remontee, objectif naturel, stock epuise, remise PA avec/sans puits, exo virtuel, gros exo deja pose avec jet incomplet, deuxieme pourcent, objectif exo, bonus d'over, over atteint sans puits, malus, petit exo, plan B, over parasite, carburant et minimum avant exo. Les deux bases sont comparees aux memes attentes. Des sequences verifient le cycle minimum/remontee, le carburant et l'interruption du cycle apres un exo commence ; les probabilites et la non-mutation des entrees sont egalement controlees.

Une attente qui change doit etre examinee : ne pas la remplacer automatiquement par le nouveau resultat. Ce socle ne couvre pas encore toutes les combinaisons de profils, l'OCR sur captures, les clics reels, les achats ou les reprises apres redemarrage. Il preserve des comportements actuels sans les declarer tous souhaitables (notamment l'arret apres un gros exo meme si le jet est incomplet).

Avant chaque test : relancer `lancer_assistant.bat`, jeu dégagé (aucune fenêtre par-dessus). Après : garder `fm_log.txt`.

## Validation ravitaillement du 17 octobre

Corrections suite a la session Do terre : tous les besoins sont recalcules sur la quantite en inventaire relue a l'HDV avant les achats (pas seulement les exos). La lecture rapide exige que le label du lot corresponde a sa ligne ; un 100 mal lu 10 ne doit pas remplacer le prix du vrai lot 10. Le lecteur complet rejette les doublons de taille de lot. Un prix au-dessus du plafond est relu deux fois avant refus ; aucun clic Acheter si la relecture reste trop chere ou incertaine. Les achats partiels sont journalises avec confirme/demande/reste.

Fermeture : premier Echap, observation ; un second Echap est permis uniquement si l'HDV est encore positivement reconnu apres une seconde. Deux captures sans HDV sont requises avant retour. Au maximum deux Echap ; sinon manuel. Tester fiche + HDV ouverts, puis HDV seul.

Profil Anneau en Grithrill EXO PA, objectif sagesse 32 : plage Ra limitee a 0..22 au lieu de 0..30. Teste : 15 -> Ra, 22 -> Ra (32), 30 -> Pa. Aucun changement de recommander ni des regles generales des overs.

Regression Ga Pa : la lecture rapide du prix moyen s'arrete maintenant avant l'icone des kamas pour exclure le graphique blanc suivant. Capture `tests_hdv_ga_pa.png` : prix moyen 29603, stock 0, lots 29898 / 319992 / 3099965 / 33999999 pour 1/10/100/1000. Verification numerique sur les deux versions, sans OCR de noms ni modification des caches utilisateur. Avant ce correctif, le prix moyen etait lu 12 et la fiche rejetee comme incoherente.

Chaque rune a maintenant une case Reapprovisionner dans les interfaces locale et telephone. La decocher conserve les seuils et le prix mais exclut la rune des achats ; alerte 0 reste compatible. Les exos demandes apparaissent aussi dans Stock de runes. Hors tableau, leur stock est inconnu (pas un zero prouve). Au premier F1, une recherche inventaire verifie chaque exo et le petit exo configure, avec deux captures concordantes. Une lecture incertaine remet en manuel ; elle ne declenche plus un voyage HDV sur un zero suppose. Le filtre est nettoye par son X et les captures datant du filtrage sont rejetees avant reprise. Sur la bonne fiche, la quantite reelle est relue avant de recalculer les lots. Stock suffisant = aucun achat ; stock illisible ou mauvaise fiche = manuel. Tester Ga Pa avec objectif exo PA, alerte 1/cible 10/prix max explicite, puis verifier qu'un stock reel deja suffisant ne provoque aucun achat. Tester aussi la case decochee : aucun ravitaillement pour cette rune. Le moteur FM recoit toujours les seules lignes originales.

Controle hors jeu : `python -B -m unittest -q test_ravitaillement test_confirmation test_orchestration test_securite`.
Le nom normalise de la fiche et l'augmentation exacte du stock doivent concorder deux fois. Une fiche d'une autre rune, un stock inchange ou une augmentation incorrecte ne confirment pas l'achat. Une interruption n'autorise pas l'achat suivant. Aucun changement du moteur FM.

Premier essai en jeu : un seul exemplaire de l'item, file vide, parcours deja calibre, une rune peu couteuse. Noter ses reglages Stock de runes et son stock N. Desactiver temporairement les alertes des autres runes (alerte 0), mettre pour la rune test alerte N+1, cible N+10 et un prix maximum unitaire choisi. Activer les conseils de ravitaillement, relancer l'assistant et lancer un seul F1 dans Dofus, sans toucher ensuite. Le lot attendu est 10, pas 100. Observer sortie, HDV, achat confirme, retour, item repose, Ressources et reprise FM sans F1. Noter la quantite recue au HDV avant toute consommation de runes a l'atelier. Restaurer les reglages Stock apres le test.

Second essai distinct : interrompre avec Echap pendant le parcours. Aucun clic suivant ne doit etre emis apres la prise en compte de l'arret. Verifier l'ecran et le stock reel avant toute reprise ; ne pas supposer un achat annule si le clic d'achat etait deja parti.

Limites ouvertes : le retour reconnait un tableau avec runes, sans preuve stricte d'identite physique de l'item. Depuis le correctif du 17 octobre, chaque achat (premier compris) relit la fiche et refuse avant clic un nom different, un prix absent/invalide, un plafond absent ou un total de lot au-dessus du plafond unitaire multiplie par la taille du lot. Aucun repli sur une ancienne fiche. Prix trop eleve : refus du lot ; lecture incertaine : mode manuel. La protection de prix est testee hors jeu ; elle reste a confirmer en jeu. Ne pas declarer l’identite physique valide avec ce seul essai. Les anciens textes annoncant une reprise automatique apres changement de fenetre ne remplacent pas la protection actuelle qui repasse en manuel.

## Protections d'execution (ajoutees le 14 octobre)

Tests hors jeu : `python -B -m unittest -v test_securite`.
Le generateur et la version produite doivent rester identiques. Ces tests n'envoient aucun clic.

- Un conseil `stop=True` bloque souris et clavier automatiques, y compris les exos.
- Une lecture datant de plus de 2 secondes bloque l'action qui s'appuie dessus.
- Passer sur une autre fenetre pendant l'automatique remet le mode manuel ; aucun clic ne doit atteindre cette fenetre.
- F1 hors Dofus ne doit pas activer l'automatique. Revenir dans Dofus et utiliser F1 pour reprendre.
- Les observations en file conservent l'heure de capture, meme si leur traitement est retarde.

La fenetre active est identifiee par son executable (Dofus.exe ou Dofus Unity.exe), independamment de son titre. Un refus de F1 ou une erreur de verification est journalise. Les controles de fenetre et le parcours complet restent a confirmer en jeu. Un redemarrage est necessaire : le rechargement de la logique FM ne recharge pas ces protections.

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

Cas limites ajoutes : petit reliquat a 1,8/2,6 et Vita 267 -> pas de Vi simple pour la remontee ; Chance 65/70 -> Ra 75 puis Pa Vi et petites Vi pour recycler ; Intelligence 92/100 -> attendre une descente compatible avec la plage, jamais Ra vers 102 ; a 91, Ra vers 101 possible selon le profil, puis recyclage. Les petites runes hors palier restent permises pour une descente ou la consommation explicite dun over, pas pour bruler inutilement du puits en remontee.

Test stock exo en inventaire : garder 20 Ga Pa et configurer alerte 1/cible 10. Un seul F1 doit chercher la rune, afficher 20, cliquer le X, verifier le retour a Recherche puis reprendre sans voyage HDV. Refaire avec petit exo configure et verifier sa recherche distincte. Avec stock reel 0 et categorie Toutes categories, deux vues vides apres confirmation du filtre peuvent conclure 0 et declencher le ravitaillement. Une interruption ne doit jamais provoquer une reprise FM avec le filtre encore actif.
