#!/usr/bin/env python3
"""Réapplique le mode de clics au fichier assistant indiqué."""
import argparse
import re
import sys
from pathlib import Path


MARKERS = (
    "# FM_CLICK_PATCH:WINTYPES",
    "# FM_CLICK_PATCH:MODE_INIT",
    "# FM_CLICK_PATCH:MODE_UI",
    "# FM_CLICK_PATCH:MODE_HELP",
    "# FM_CLICK_PATCH:MODE_CONFIG",
    "# FM_CLICK_PATCH:MODE_APPLY",
    "# FM_CLICK_PATCH:MODE_SAVE",
    "# FM_CLICK_PATCH:CLICK_RUNTIME",
    "# FM_CLICK_PATCH:LOOP",
    "# FM_CLICK_PATCH:CLICK_HOOK",
    "# FM_CLICK_PATCH:MANUAL_LABEL",
    "# FM_CLICK_PATCH:EXO_RUNTIME",
    "# FM_CLICK_PATCH:EXO_HOOK",
    "# FM_CLICK_PATCH:RAVITO_RUNTIME",
    "# FM_CLICK_PATCH:RAVITO_HOOK",
)

RUNTIME_RAVITO = r'''
    # FM_CLICK_PATCH:RAVITO_RUNTIME
    ravito = {"t": 0.0, "fait": False, "multi": 0.0, "avert": ""}

    def pause_auto(s):
        # attente interrompue si le mode repasse en manuel (souris bougee ou Echap) ; False = abandon
        fin = time.time() + s
        while time.time() < fin:
            verifier_mode_clic()
            if panneau.mode.get() != "automatique":
                return False
            time.sleep(0.05)
        return True

    def touche(vk):
        user32 = ctypes.windll.user32
        user32.keybd_event(vk, 0, 0, 0)
        user32.keybd_event(vk, 0, 2, 0)

    def ctrl_a():
        user32 = ctypes.windll.user32
        user32.keybd_event(0x11, 0, 0, 0)
        user32.keybd_event(0x41, 0, 0, 0)
        user32.keybd_event(0x41, 0, 2, 0)
        user32.keybd_event(0x11, 0, 2, 0)

    def taper_texte(txt):
        # frappe Unicode (accents compris), independante de la disposition du clavier
        class _MI(ctypes.Structure):
            _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                        ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]

        class _KI(ctypes.Structure):
            _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                        ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]

        class _U(ctypes.Union):
            _fields_ = [("mi", _MI), ("ki", _KI)]

        class _IN(ctypes.Structure):
            _fields_ = [("type", wintypes.DWORD), ("u", _U)]

        for ch in txt:
            for flags in (0x0004, 0x0004 | 0x0002):
                e = _IN(1, _U(ki=_KI(0, ord(ch), flags, 0, 0)))
                ctypes.windll.user32.SendInput(1, ctypes.byref(e), ctypes.sizeof(_IN))
            time.sleep(0.012)

    def pos_fr(img, fx, fy):
        return mon["left"] + int(fx * img.shape[1]), mon["top"] + int(fy * img.shape[0])

    def clic_fr(fx, fy):
        x, y = pos_fr(capturer(mon), fx, fy)
        return clic_point(x, y)

    def lire_confirmation(img):
        # fenetre « Acheter » : (nom, quantite, prix unitaire, prix total) ou None si elle n'est pas ouverte
        H, W = img.shape[:2]

        def zone(x0, x1, y0, y1):
            return img[int(y0 / 768 * H):int(y1 / 768 * H), int(x0 / 1366 * W):int(x1 / 1366 * W)]

        titre = norm(ocr.ligne(zone(640, 730, 306, 324)))
        if "achet" not in titre and difflib.SequenceMatcher(None, titre, "acheter").ratio() < .7:
            return None
        nom = norm(ocr.ligne(zone(590, 760, 341, 357)))
        qte = ocr.ligne(zone(762, 806, 341, 357), chiffres=True)
        unit = ocr.ligne(zone(715, 800, 371, 387), chiffres=True)
        total = ocr.ligne(zone(705, 800, 388, 404), chiffres=True)
        return nom, int(qte or 0), int(unit or 0), int(total or 0)

    def demander_telephone(a, taille, unit):
        # prix au-dessus du max : le telephone propose d'accepter ce prix (ou de refuser) ; attend la reponse
        cle = norm(a["rune"])
        GUIDE.derog.pop(cle, None)
        GUIDE.demande = {"nom": a["rune"], "moyen": float(a.get("plafond") or a.get("prix") or unit), "max": float(a.get("prix") or a.get("plafond") or 0),
                         "manque": a.get("acheter", 0), "lots": {int(taille): float(unit)},
                         "t": time.time()}
        SUIVI.evenement("hors prix " + a["rune"], f"HORS DE PRIX : {a['rune']} — à toi de décider (accepter ou refuser)", 120)
        fin = time.time() + 120
        while time.time() < fin:
            if not pause_auto(0.5):
                GUIDE.demande = None
                return None
            if GUIDE.derog.get(cle) is not None:
                return GUIDE.derog[cle]
            if GUIDE.demande is None:
                return False
            GUIDE.demande["t"] = time.time()
        GUIDE.demande = None
        return False

    def lire_fiche():
        # lecture forcee de la fiche ouverte (le guide limite sinon ses lectures)
        GUIDE.t_fiche, GUIDE.empreinte = 0, None
        im = capturer(mon)
        GUIDE._fiche(im, ocr)
        return im, GUIDE.fiche

    def acheter_lot(a, taille):
        # ACHETER sur la ligne du lot, controle de la fenetre de confirmation, puis CONFIRMER ou ANNULER
        i = {"1": 0, "10": 1, "100": 2, "1000": 3}[taille]
        if ravito.setdefault("achete", {}).get(a["rune"], 0) >= int(a.get("acheter") or 0):
            log(f"Quantite a acheter atteinte pour {a['rune']} ({ravito['achete'][a['rune']]}) : plus d'achat")
            return False
        n_lot = int(taille)
        plafond = int(float(a.get("prix") or a.get("plafond_moy") or a.get("plafond") or 0))
        direct = bool(ravito.get("direct"))
        _f_moy = (a.get("_f") or {}).get("moyen")
        if not plafond and _f_moy:
            marge = (GUIDE.regl or {}).get("_marge", {}).get("pct", 20)
            plafond = int(float(_f_moy) * (1 + marge / 100))
            a["plafond_moy"] = float(plafond)
        # fiche : relue a neuf en achat direct (le prix change apres chaque achat), sinon reprise de la lecture d'ouverture
        f0 = a.get("_f")
        try:
            if direct or not f0:
                im0, fi0 = lire_fiche()
                f0 = fi0["fiches"][0] if fi0 and fi0.get("fiches") else f0
                a["_f"] = f0
            else:
                im0 = capturer(mon)
        except Exception as err:
            log(f"lecture de la fiche impossible : {err}")
            im0 = capturer(mon)
        qte_avant = f0.get("qte") if f0 else None
        if direct and qte_avant is not None and a.get("_attendu") is not None and qte_avant < a["_attendu"]:
            log(f"Achat direct non confirme : {qte_avant} en inventaire, {a['_attendu']} attendu : arret, mode manuel")
            SUIVI.evenement("abandon " + a["rune"], f"Achat automatique arrêté : l'achat de {a['rune']} n'a pas augmenté l'inventaire.", 120)
            panneau.mode.set("manuel")
            panneau._mode_change()
            return None
        if direct and f0 and n_lot in f0["lots"]:
            u0 = f0["lots"][n_lot] / n_lot
            if not plafond or u0 > plafond:
                log(f"Achat direct refuse : {a['rune']} x{taille} a {u0:.0f} l'unite > max {plafond} (lu avant le clic)")
                SUIVI.evenement("cher " + a["rune"], f"Achat refusé : {a['rune']} x{taille} ({u0:.0f} > max {plafond})", 300)
                return False
        # bouton ACHETER : position lue sur la fiche ouverte (comme le cadre vert du guide) ; repli sur la position fixe
        cible_xy = None
        if f0 and n_lot in f0["ys"]:
            k0 = im0.shape[1] / 1917
            cible_xy = (mon["left"] + int(f0["mx"] + 247 * k0), mon["top"] + int(f0["ys"][n_lot]))
        if cible_xy:
            if not clic_point(*cible_xy):
                return None
        else:
            log(f"ACHETER lot x{taille} : fiche non lue, position fixe")
            if not clic_fr(365 / 1366, (257 + 27 * i) / 768):
                return None
        conf, fin = None, time.time() + (0.6 if direct else 1.6)
        while conf is None and time.time() < fin:      # sonde la fenetre au lieu d'attendre a l'aveugle
            if not pause_auto(0.1):
                return None
            conf = lire_confirmation(capturer(mon))
        if conf is None:
            # pas de fenetre : l'hotel de vente achete peut-etre directement au clic. On le prouve par l'inventaire.
            if direct:
                a["_attendu"] = (qte_avant + n_lot) if qte_avant is not None else None
                ravito["achete"][a["rune"]] = ravito["achete"].get(a["rune"], 0) + n_lot
                log(f"Achat direct : {a['rune']} x{taille} (inventaire {qte_avant} avant)")
                return pause_auto(0.15) or None
            try:
                _, fi2 = lire_fiche()
                f2 = fi2["fiches"][0] if fi2 and fi2.get("fiches") else None
            except Exception:
                f2 = None
            q2 = f2.get("qte") if f2 else None
            if qte_avant is not None and q2 is not None and q2 >= qte_avant + n_lot:
                ravito["direct"] = True
                a["_f"], a["_attendu"] = f2, q2
                ravito["achete"][a["rune"]] = ravito["achete"].get(a["rune"], 0) + n_lot
                log(f"Achat sans fenetre de confirmation : inventaire {qte_avant} -> {q2}. Mode achat direct "
                    "(prix relu avant chaque clic, inventaire controle a chaque lot)")
                return True
            log(f"Achat abandonne : fenetre de confirmation absente ({a['rune']} x{taille}, inventaire {qte_avant} -> {q2}) : arret, mode manuel")
            SUIVI.evenement("abandon " + a["rune"], f"Achat automatique arrêté : fenêtre de confirmation absente ({a['rune']}). Vérifie l'inventaire.", 120)
            panneau.mode.set("manuel")
            panneau._mode_change()
            return None
        a["_attendu"] = None
        nom, qte, unit, total = conf
        # prix max de la rune, sinon plafond du guide (prix moyen de l'hotel de vente + marge %)
        # prix max = limite stricte ; sans prix max : prix moyen + marge % (reglee dans l'interface)
        plafond = int(float(a.get("prix") or a.get("plafond_moy") or a.get("plafond") or 0))
        if unit and total and qte and abs(total - unit * qte) > max(10 * qte, total // 10):
            # le separateur de milliers fait parfois perdre le 1er chiffre du prix unitaire (310 au lieu de 1 310) :
            # on le reprend du total, seulement si les derniers chiffres lus concordent
            u2 = round(total / qte)
            if str(u2).endswith(str(unit)) and abs(total - u2 * qte) <= max(10 * qte, total // 50):
                log(f"Prix unitaire relu {unit} -> {u2} d'apres le total {total} x{qte}")
                unit = u2
        ref_lot = (f0["lots"].get(n_lot) if f0 else None)
        if ref_lot and unit and qte and total and abs(total - unit * qte) > max(10 * qte, total // 10) \
                and abs(unit * qte - ref_lot) <= max(10 * qte, ref_lot // 50):
            log(f"Total lu {total} incoherent, remplace par le prix du lot lu sur la fiche : {ref_lot}")
            total = ref_lot
        if unit and qte and total and abs(total - unit * qte) > max(10 * qte, total // 10) \
                and str(unit * qte).endswith(str(total)):
            log(f"Total lu {total} = fin de {unit * qte} (chiffre des milliers perdu par la lecture) : total corrige")
            total = unit * qte
        log(f"Fenetre Acheter lue : nom={nom} qte={qte} unitaire={unit} total={total}")
        cible = norm(a["recherche"])
        erreurs = []
        if qte != int(taille):
            erreurs.append(f"quantite {qte} au lieu de {taille}")
        if not nom or difflib.SequenceMatcher(None, nom, cible).ratio() < .7:
            erreurs.append(f"rune lue « {nom} » au lieu de « {cible} »")
        if unit <= 0:
            erreurs.append("prix illisible")
        if total and unit and abs(total - unit * qte) > max(10 * qte, total // 10):
            erreurs.append(f"total {total} incoherent avec {unit} x {qte}")
        if not erreurs and unit > plafond:   # sans prix max (plafond 0), tout prix passe par le telephone
            accepte = demander_telephone(a, taille, unit)
            if accepte is None:
                return None
            if not accepte or unit > accepte:
                erreurs.append(f"prix unitaire {unit} > max {plafond}, refuse depuis le telephone")
        if erreurs:
            quoi = ", ".join(erreurs)
            log(f"Achat refuse : {a['rune']} lot x{taille} ({quoi})")
            SUIVI.evenement("cher " + a["rune"], f"Achat refusé : {a['rune']} x{taille} ({quoi})", 300)
            clic_fr(626 / 1366, 427 / 768)
            pause_auto(0.2)
            if not any("max" in e for e in erreurs):
                return "lecture"      # lecture douteuse, pas un refus de prix : a retenter
            return False
        if not clic_fr(741 / 1366, 427 / 768):
            return None
        ravito["achete"][a["rune"]] = ravito["achete"].get(a["rune"], 0) + int(taille)
        log(f"Achat : {a['rune']} x{taille} a {unit} l'unite (total {total}, max {plafond})")
        return pause_auto(0.3) or None

    def signaler_refus():
        # runes non achetees (trop cheres) : on les saute et on previent le telephone ; bloque si plus rien d'utilisable
        refus = ravito.get("refus") or {}
        if not refus:
            return
        def famille(nom):
            return re.sub(r"^(Pa|Ra) ", "", nom)
        bloquees = []
        for nom, a in refus.items():
            if int(a.get("stock") or 0) > 0 or ravito["achete"].get(nom):
                continue
            freres = [b for b in GUIDE.liste if b["rune"] != nom and famille(b["rune"]) == famille(nom)]
            if not any(int(b.get("stock") or 0) > 0 or ravito["achete"].get(b["rune"]) for b in freres):
                bloquees.append(nom)
        liste = ", ".join(refus)
        for nom, a in refus.items():
            RUNES_SAUTEES[nom] = (a.get("stock"), time.time())
        if bloquees:
            SUIVI.evenement("ravito bloque", f"FM ANNULÉE : {' ; '.join(bloquees)} trop chère et plus aucune en stock (ni Pa/Ra). "
                            "Ravitaillement bloqué pour le moment.", 900)
            log(f"FM annulee : plus de runes utilisables ({', '.join(bloquees)})")
            panneau.mode.set("manuel")
            panneau._mode_change()
        else:
            SUIVI.evenement("ravito refus", f"Ravitaillement : {liste} trop chère, on la saute 30 min (il en reste en stock).", 600)
            log(f"Runes sautees (trop cheres) : {liste}")
        ravito["refus"] = {}

    def marquer(pt, txt):
        # capture avec un carre vert autour du point qu'on va cliquer (fm_debug_clics)
        try:
            img = capturer(mon).copy()
            px, py = pt[0] - mon["left"], pt[1] - mon["top"]
            cv2.rectangle(img, (px - 70, py - 22), (px + 70, py + 22), (0, 255, 0), 3)
            cv2.putText(img, "AVANT " + txt, (20, img.shape[0] - 60), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2)
            d = os.path.join(ICI, "fm_debug_clics")
            os.makedirs(d, exist_ok=True)
            cv2.imwrite(os.path.join(d, f"{time.strftime('%H%M%S')}_avant_{re.sub(r'\W', '_', txt)}.jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 70])
        except Exception as err:
            log(f"marquage impossible : {err}")

    def fermer_fiche():
        # Echap, puis clic sur le X de la fiche si elle est encore ouverte (Echap seul ne la ferme pas toujours)
        touche(0x1B)
        pause_auto(0.35)
        for _ in range(2):
            try:
                im, fi = lire_fiche()
            except Exception:
                return
            if not (fi and fi.get("fiches")):
                return
            f = fi["fiches"][0]
            k = im.shape[1] / 1917
            x, y = mon["left"] + int(f["mx"] + 300 * k), mon["top"] + int(f["my"] - 82 * k)
            log(f"Fiche encore ouverte apres Echap : clic sur son X ({x - mon['left']},{y - mon['top']})")
            clic_point(x, y)
            pause_auto(0.35)

    def clic_nom():
        # clique l'en-tete « Nom » de la liste, trouve par lecture du texte (l'ecran change de taille) ; repli : position relative
        im = capturer(mon)
        H, W = im.shape[:2]
        x0, y0, x1, y1 = int(W * .42), int(H * .20), int(W * .66), int(H * .31)
        pos = None
        try:
            c = trouver_texte(im[y0:y1, x0:x1], "nom")
            if c:
                pos = (mon["left"] + x0 + c[0], mon["top"] + y0 + c[1])
        except Exception as err:
            log(f"lecture de l'en-tete Nom impossible : {err}")
        if not pos:
            pos = pos_fr(im, 919 / 1920, 272 / 1080)
            log("En-tete Nom non lu : position relative")
        return clic_point(*pos)

    def fiche_voulue(fi, cib):
        return bool(fi and fi.get("fiches") and
                    difflib.SequenceMatcher(None, norm(fi["fiches"][0]["nom"]), cib).ratio() >= .85)

    def acheter_liste():
        ravito["refus"] = {}
        for a in list(GUIDE.liste[:10]):
            if not pause_auto(0.1) or not GUIDE._hdv_ouvert(capturer(mon), ocr):
                return False
            if not a.get("prix"):
                log(f"Pas de prix max pour {a['rune']} : prix moyen de l'hotel de vente + marge")

            a.pop("plafond", None)
            fermer_fiche()
            img = capturer(mon)
            p = GUIDE._point(img, "recherche")
            if not clic_point(mon["left"] + p[0], mon["top"] + p[1]) or not pause_auto(0.2):
                return False
            ctrl_a()
            taper_texte(a["recherche"])
            touche(0x0D)
            if not pause_auto(0.6):
                return False
            ouverte = False
            nb_tri = 0
            cib1 = norm(a["recherche"])
            for _essai in range(5):
                # 1) attendre que la rune apparaisse dans la liste (ou qu'une fiche soit deja ouverte)
                pos_ligne, fin_l = None, time.time() + 4.0
                while time.time() < fin_l:
                    if not pause_auto(0.1):
                        return False
                    try:
                        im_l, fi1 = lire_fiche()
                    except Exception:
                        im_l, fi1 = capturer(mon), None
                    if fi1 and fi1.get("fiches"):
                        if fiche_voulue(fi1, cib1):
                            ouverte = True
                            break
                        log(f"Fiche d'une autre rune ouverte ({fi1['fiches'][0]['nom']}) : je la ferme")
                        fermer_fiche()
                        continue
                    res1 = (fi1 or {}).get("res") or []
                    if time.time() > fin_l - 2.6 and not res1 and not pos_ligne:
                        # rien reconnu par la lecture : repli sur la position habituelle de la 1re ligne de resultat
                        pos_ligne = pos_fr(im_l, 700 / 1366, 229 / 768)
                        log(f"Liste non lue pour {a['rune']} : clic sur la 1re ligne ({pos_ligne})")
                        break
                    r1 = max(res1, key=lambda r: difflib.SequenceMatcher(None, norm(r[0]), cib1).ratio(), default=None)
                    if res1:
                        log(f"Lignes lues dans la liste : {[r[0] for r in res1]} (cherche {cib1})")
                    if r1 and difflib.SequenceMatcher(None, norm(r1[0]), cib1).ratio() >= .85:
                        pos_ligne = (mon["left"] + int(r1[1]), mon["top"] + int(r1[2]))
                        break
                    if res1 and time.time() > fin_l - 3.2 and nb_tri < 2:
                        # la bonne rune n'est pas dans les lignes visibles : on change le tri en cliquant sur « Nom »
                        nb_tri += 1
                        log(f"« {a['recherche']} » absente des lignes lues : clic sur « Nom » pour changer le tri ({nb_tri}/2)")
                        clic_nom()
                        pause_auto(0.5)
                        fin_l = time.time() + 3.2
                if ouverte:
                    break
                if not pos_ligne:
                    log(f"Rune {a['rune']} pas visible dans la liste (essai {_essai + 1}) : j'attends")
                    continue
                # 2) cliquer la ligne, puis attendre la fiche ; sans fiche, on reclique
                marquer(pos_ligne, f"ligne {a['rune']}")
                if not clic_point(*pos_ligne):
                    return False
                fin_f = time.time() + 1.6
                while time.time() < fin_f and not ouverte:
                    if not pause_auto(0.15):
                        return False
                    try:
                        _, fi2 = lire_fiche()
                    except Exception:
                        fi2 = None
                    ouverte = fiche_voulue(fi2, cib1)
                if ouverte:
                    break
                log(f"Fiche de {a['rune']} pas ouverte apres le clic (essai {_essai + 1}) : je reclique")
            if not ouverte:
                log(f"Fiche de {a['rune']} non ouverte apres 5 essais : arret, passe en manuel")
                panneau.mode.set("manuel")
                return False
            a.pop("plafond_moy", None)
            a.pop("_f", None)
            a.pop("_attendu", None)
            try:
                im = capturer(mon)
                if GUIDE.fiche and GUIDE.fiche.get("fiches"):
                    a["_f"] = GUIDE.fiche["fiches"][0]
                    GUIDE._conseil_fiche(GUIDE.fiche, im.shape[1] / 1917)    # fixe a["moyen"] (prix moyen de la fiche)
                if a.get("moyen"):
                    marge = (GUIDE.regl or {}).get("_marge", {}).get("pct", 20)
                    a["plafond_moy"] = float(a["moyen"]) * (1 + marge / 100)
            except Exception as err:
                log(f"lecture du prix moyen impossible : {err}")
            for k, taille in re.findall(r"(\d+)×(\d+)", a["lots"]):
                for _ in range(int(k)):
                    r = acheter_lot(a, taille)
                    for _re in range(2):
                        if r != "lecture":
                            break
                        log(f"Lecture douteuse pour {a['rune']} x{taille} : je retente")
                        pause_auto(0.4)
                        a.pop("_f", None)
                        r = acheter_lot(a, taille)
                    if r == "lecture":
                        r = False
                        a["_lecture"] = True
                    if r is None:
                        return False
                    if r is False:
                        if not ravito["achete"].get(a["rune"]) and not a.pop("_lecture", False):
                            ravito["refus"][a["rune"]] = a
                        break
                else:
                    continue
                break
            # rune finie : Echap ferme la fiche, puis on repart de la barre de recherche pour la rune suivante
            fermer_fiche()
            log(f"Fiche de {a['rune']} fermee")
        clic_fr(928 / 1366, 127 / 768)
        ravito["fait"] = True
        log("Achats automatiques termines")
        signaler_refus()
        return True
    def trouver_gabarit(img, nom, seuil=0.45):
        # centre (x, y) de l'icone fm_reperes/<nom>.png dans la moitie droite de l'ecran, a plusieurs echelles
        g = cv2.imread(os.path.join(ICI, "fm_reperes", nom + ".png"))
        if g is None:
            return None
        H, W = img.shape[:2]
        x0 = W // 2
        zone = img[:, x0:]
        meilleur = (0, None)
        for f in (0.3, 0.35, 0.4, 0.45, 0.5, 0.6, 0.7, 0.85, 1.0):
            s = f * W / 1920 / 0.4
            gg = cv2.resize(g, None, fx=s, fy=s)
            if gg.shape[0] >= zone.shape[0] or gg.shape[1] >= zone.shape[1] or gg.shape[0] < 12:
                continue
            r = cv2.matchTemplate(zone, gg, cv2.TM_CCOEFF_NORMED)
            _, mx, _, loc = cv2.minMaxLoc(r)
            if mx > meilleur[0]:
                meilleur = (mx, (x0 + loc[0] + gg.shape[1] // 2, loc[1] + gg.shape[0] // 2))
        return meilleur[1] if meilleur[0] >= seuil else None

    def poser_item(pt, img, nom=None, idx=0, retour=False):
        # onglet Equipement ouvert : on cherche le nom de l'item dans la barre de recherche de l'inventaire (position
        # lue a l'ecran, jamais fixe), puis double clic sur la case n? idx (la 1re case apres la recherche en general)
        if nom is None:
            try:
                nom = (nom_item or "").strip()
            except NameError:
                nom = ""
        im = capturer(mon)
        H, W = im.shape[:2]
        k = W / 1366
        c = None
        try:
            c = trouver_texte(im[int(H * .12):int(H * .30), int(W * .60):], "recherche")
        except Exception as err:
            log(f"lecture de la barre de recherche impossible : {err}")
        if c:
            barre = (mon["left"] + int(W * .60) + c[0], mon["top"] + int(H * .12) + c[1])
        else:
            barre = pos_fr(im, 1085 / 1366, 156 / 768)
            log("Barre de recherche de l'inventaire non lue : position relative")
        if not nom or nom.startswith("("):
            clic_point(barre[0] - int(18 * k), barre[1] + int(63 * k), True)
            log("Ravitaillement auto : nom de l'item inconnu, double clic sur la 1re case de l'inventaire")
            return
        idx = max(0, min(int(idx), 14))
        case = (barre[0] - int(18 * k) + int(45.3 * k * (idx % 5)), barre[1] + int(63 * k) + int(46.3 * k * (idx // 5)))
        if not clic_point(*barre) or not pause_auto(0.2):
            return
        ctrl_a()
        taper_texte(nom)
        if not pause_auto(0.9):
            return
        marquer(case, f"item {nom}")
        clic_point(*case, True)
        log(f"Ravitaillement auto : item {nom} cherche dans l'inventaire, double clic sur la case {idx + 1}")
        if pause_auto(0.5) and clic_point(*barre) and pause_auto(0.15):
            ctrl_a()
            touche(0x08)
        if retour and pause_auto(0.3):
            im2 = capturer(mon)
            r = trouver_gabarit(im2, "ressources")
            if r:
                clic_point(mon["left"] + r[0], mon["top"] + r[1])
                log("Onglet Ressources (feuille) clique")
            else:
                r = GUIDE._point(im2, "ressources")
                clic_point(mon["left"] + r[0], mon["top"] + r[1])
                log("Icone feuille non retrouvee : repere Ressources du guide")
    def suite_auto(img):
        # un item vient d'etre fini : s'il y a une file d'attente, on pose le suivant sans passer par le telephone
        fin = getattr(SUIVI, "fin", None)
        if not fin or panneau.mode.get() != "automatique":
            return
        if time.time() - fin[1] > 120:
            SUIVI.fin = None
            return
        file = list(getattr(panneau, "file", None) or [])
        SUIVI.fin = None
        if not file or time.time() - ravito.get("t_suite", 0) < 20:
            return
        ravito["t_suite"] = time.time()
        faits = ravito.setdefault("faits", {})
        if fin[0]:
            faits[fin[0]] = faits.get(fin[0], 0) + 1
        nom = file[0]
        SUIVI.evenement("file suite", f"Item fini : passage au suivant de la file ({nom})", 15)
        log(f"File d'attente : item suivant {nom} (deja finis : {faits.get(nom, 0)})")
        try:
            e = GUIDE._point(img, "equipement")
            if clic_point(mon["left"] + e[0], mon["top"] + e[1]) and pause_auto(0.5):
                poser_item(e, img, reel_de(nom), faits.get(nom, 0), True)
        except Exception as err:
            log(f"file d'attente en erreur : {err}")

    F_NOMS_REELS = os.path.join(ICI, "fm_noms_reels.json")

    def charger_noms_reels():
        try:
            with open(F_NOMS_REELS, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def reel_de(nom):
        # nom reel de l'objet (celui de l'infobulle) pour un objectif enregistre ; a defaut le nom de l'objectif
        return charger_noms_reels().get(nom) or nom

    def memo_nom_reel():
        # relie l'objectif affiche dans le panneau au nom reel lu sur l'objet
        reel, obj = getattr(SUIVI, "nom_reel", ""), panneau.nom.get().strip()
        if reel and obj:
            m = charger_noms_reels()
            if m.get(obj) != reel:
                m[obj] = reel
                try:
                    with open(F_NOMS_REELS, "w", encoding="utf-8") as f:
                        json.dump(m, f, indent=1, ensure_ascii=False)
                except Exception as err:
                    log(f"noms reels non sauvegardes : {err}")

    def lire_nom_survol():
        # curseur sur l'icone de l'objet (a gauche de l'icone des runes, en haut de l'atelier) : l'infobulle donne son nom
        if not windows or panneau.mode.get() != "automatique":
            return ""
        try:
            im = capturer(mon)
            H, W = im.shape[:2]
            g0 = cv2.imread(os.path.join(ICI, "fm_reperes", "onglet_rune.png"))
            if g0 is None:
                return ""
            zone = im[:int(H * .5)]
            meilleur = (0.0, 1.0, None)
            for s in np.arange(0.5, 1.6, 0.05):
                g = cv2.resize(g0, None, fx=s, fy=s)
                if g.shape[0] >= zone.shape[0] or g.shape[1] >= zone.shape[1]:
                    continue
                r = cv2.matchTemplate(zone, g, cv2.TM_CCOEFF_NORMED)
                _, mx, _, loc = cv2.minMaxLoc(r)
                if mx > meilleur[0]:
                    meilleur = (mx, float(s), (loc[0] + g.shape[1] // 2, loc[1] + g.shape[0] // 2))
            mx, s, c = meilleur
            if c is None or mx < 0.6:
                log(f"Icone des runes de l'atelier non retrouvee (ressemblance {mx:.2f}) : nom de l'objet non lu")
                return ""
            ix, iy = c[0] - int(49 * s), c[1]
            user32 = ctypes.windll.user32
            ancien = wintypes.POINT()
            user32.GetCursorPos(ctypes.byref(ancien))
            if panneau.mode.get() != "automatique":
                return ""
            cx0, cy0 = ancien.x, ancien.y
            cx1, cy1 = mon["left"] + ix, mon["top"] + iy
            for i in range(1, 31):
                f = i / 30.0
                f = f * f * (3 - 2 * f)
                px, py = int(cx0 + (cx1 - cx0) * f), int(cy0 + (cy1 - cy0) * f)
                user32.SetCursorPos(px, py)
                position_souris_ref[0] = (px, py)
                time.sleep(0.02)
            for dx in (-2, 0, 2, 0):
                user32.SetCursorPos(cx1 + dx, cy1)
                position_souris_ref[0] = (cx1 + dx, cy1)
                time.sleep(0.08)
            time.sleep(0.4)
            pt = wintypes.POINT()
            user32.GetCursorPos(ctypes.byref(pt))
            if (panneau.mode.get() != "automatique" or abs(pt.x - (mon["left"] + ix)) > 5
                    or abs(pt.y - (mon["top"] + iy)) > 5):
                log("Lecture du nom annulee : mode manuel ou souris deplacee, aucune touche")
                return ""
            user32.keybd_event(0x12, 0x38, 0, 0)
            time.sleep(0.08)
            user32.keybd_event(0x12, 0x38, 2, 0)
            time.sleep(0.3)
            nom = ""
            k = W / 1920.0
            x0, x1 = max(0, ix - int(40 * s)), min(W, ix + int(700 * s))
            y0, y1 = max(0, iy - int(150 * s)), min(H, iy + int(300 * s))
            ancre = None
            try:
                for _ in range(3):
                    time.sleep(0.5)
                    im2 = capturer(mon)
                    lignes = ocr.tout(im2[y0:y1, x0:x1])
                    niv = [(y, x) for t, x, y in lignes if re.match(r"\s*niveau\s*\d", t, re.I)]
                    if not niv:
                        continue
                    ny, nx = min(niv)
                    ancre = (nx, ny)
                    cands = []
                    for t, x, y in lignes:
                        if ny - 55 * k < y < ny - 8 * k and x > nx - 30 * k:
                            t = re.sub(r"[^A-Za-z?-?'? -]", "", t).strip(" -'?")
                            if len(t) >= 2:
                                cands.append((x, t))
                    nom = " ".join(t for _, t in sorted(cands))
                    nom = re.sub(r"(?<=[a-z?-?])(?=[A-Z?-?])", " ", nom)
                    try:
                        os.makedirs(os.path.join(ICI, "fm_debug_clics"), exist_ok=True)
                        cv2.imwrite(os.path.join(ICI, "fm_debug_clics", "survol_infobulle.png"), im2)
                    except Exception:
                        pass
                    if len(nom) >= 4:
                        break
                    log(f"Infobulle rejetee (texte douteux) : {nom}")
                    nom = ""
                if ancre is not None and panneau.mode.get() == "automatique":
                    touche(0x1B)
                    time.sleep(0.5)
                    encore = [1 for t, x, y in ocr.tout(capturer(mon)[y0:y1, x0:x1])
                              if re.match(r"\s*niveau\s*\d", t, re.I)]
                    if encore:
                        cx = mon["left"] + x0 + int(ancre[0] + 234 * k)
                        cy = mon["top"] + y0 + int(ancre[1] - 62 * k)
                        log("Infobulle encore ouverte apres Echap : clic sur son X")
                        user32.SetCursorPos(cx, cy)
                        position_souris_ref[0] = (cx, cy)
                        time.sleep(0.2)
                        user32.mouse_event(0x0002, 0, 0, 0, 0)
                        time.sleep(0.05)
                        user32.mouse_event(0x0004, 0, 0, 0, 0)
                        time.sleep(0.3)
            finally:
                if panneau.mode.get() == "automatique":
                    user32.SetCursorPos(ancien.x, ancien.y)
                    position_souris_ref[0] = (ancien.x, ancien.y)
            if nom:
                log(f"Objet lu par son infobulle : {nom}")
            else:
                log("Infobulle de l'objet non lue (curseur sur l'icone, rien de lisible)")
            return nom
        except Exception as err:
            log(f"lecture de l'infobulle impossible : {err}")
            return ""

    def auto_ravitaillement(g, img):
        memo_nom_reel()
        suite_auto(img)
        # execute l'etape du guide de ravitaillement affichee (clics, recherche, achat) en mode automatique
        if not g or not windows:
            return g
        m = re.match(r"RAVITAILLEMENT (\d)/7", g[0])
        if not m:
            return g
        verifier_mode_clic()
        if panneau.mode.get() != "automatique":
            return g
        n, maintenant = int(m.group(1)), time.time()
        if n == 1 and not getattr(SUIVI, "nom_reel", "") and ravito.get("essais_nom", 0) < 3 \
                and maintenant - ravito.get("t_nom", 0) > 3:
            ravito["essais_nom"] = ravito.get("essais_nom", 0) + 1
            ravito["t_nom"] = maintenant
            log("Avant le ravitaillement : lecture du nom de l'objet par survol")
            SUIVI.nom_reel = lire_nom_survol()
            if not SUIVI.nom_reel:
                return g
            memo_nom_reel()
        if n == 1 and getattr(SUIVI, "nom_reel", ""):
            ravito["essais_nom"] = 0
        if n <= 3:
            ravito["fait"] = False
            ravito["achete"] = {}
        try:
            if n == 4:
                if ravito["fait"] or maintenant - ravito["t"] < 1:
                    return g
                ravito["t"] = maintenant
                acheter_liste()
                if ravito["avert"] and not ravito["fait"]:
                    return g[0] + "\n[AUTO] calibre dans « Repères » : " + ravito["avert"].replace(",", ", "), g[1]
                return g
            if g[1] is None:
                return g
            if ravito.get("etape") != n:
                ravito["etape"], ravito["vu"] = n, maintenant   # laisse finir le changement de carte
            if maintenant - ravito["vu"] < (0.5 if n == 2 else 1.5) or maintenant - ravito["t"] < (1.0 if n == 2 else 2.5):
                return g
            if n == 6 and METIERS.get(GUIDE.metier) == "multi":
                if maintenant - ravito["multi"] < 30:
                    return g
                ravito["multi"] = maintenant
            ravito["t"] = maintenant
            if clic_point(mon["left"] + g[1][0], mon["top"] + g[1][1]):
                log(f"Ravitaillement auto : etape {n}/7")
                if n == 7 and pause_auto(0.5):
                    poser_item(g[1], img, None, ravito.get("faits", {}).get(panneau.nom.get().strip(), 0), True)
        except Exception as err:
            log(f"ravitaillement automatique en erreur : {err}")
        return g

'''

RAVITO_HOOK = "                g = auto_ravitaillement(g, bgr)\n"

RUNTIME_EXO = r'''
    # FM_CLICK_PATCH:EXO_RUNTIME
    def placer_souris_haut_gauche():
        if not windows:
            return
        user32 = ctypes.windll.user32
        if not user32.SetCursorPos(0, 0):
            log(f"placement de la souris impossible : {ctypes.WinError()}")
            return
        position_souris_ref[0] = (0, 0)

    def trace_clic(x, y, double=False, apres=0.0):
        # capture d'ecran apres chaque clic automatique, avec le point clique marque : fm_debug_clics/
        try:
            f = sys._getframe(1)
            while f and f.f_code.co_name in ("clic_point", "clic_fr", "trace_clic"):
                f = f.f_back
            quoi = f"{f.f_code.co_name}_l{f.f_lineno}" if f else "clic"
            time.sleep(apres)
            img = capturer(mon).copy()
            px, py = x - mon["left"], y - mon["top"]
            cv2.circle(img, (px, py), 18, (0, 0, 255), 3)
            cv2.line(img, (px - 28, py), (px + 28, py), (0, 255, 0), 2)
            cv2.line(img, (px, py - 28), (px, py + 28), (0, 255, 0), 2)
            cv2.putText(img, f"{quoi} ({px},{py}) {'double' if double else ''}", (20, img.shape[0] - 20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 255), 2)
            d = os.path.join(ICI, "fm_debug_clics")
            os.makedirs(d, exist_ok=True)
            ravito["n_clic"] = ravito.get("n_clic", 0) + 1
            cv2.imwrite(os.path.join(d, f"{time.strftime('%H%M%S')}_{ravito['n_clic']:03d}_{quoi}.jpg"), img,
                        [cv2.IMWRITE_JPEG_QUALITY, 70])
            vieux = sorted(os.listdir(d))[:-80]
            for v in vieux:
                os.remove(os.path.join(d, v))
            log(f"clic {quoi} en ({px},{py}) : capture fm_debug_clics")
        except Exception as err:
            log(f"capture de debug impossible : {err}")

    def clic_point(x, y, double=False):
        user32 = ctypes.windll.user32
        if not user32.SetCursorPos(x, y):
            log(f"clic automatique impossible : {ctypes.WinError()}")
            return False
        position_souris_ref[0] = (x, y)
        for _ in range(2 if double else 1):
            user32.mouse_event(0x0002, 0, 0, 0, 0)
            time.sleep(0.04)
            user32.mouse_event(0x0004, 0, 0, 0, 0)
            time.sleep(0.06)
        trace_clic(x, y, double)
        return True

    def trouver_texte(img, mot):
        # centre (x, y) du premier texte contenant `mot` dans l'image, ou None
        mot = mot.lower()
        try:
            if ocr.mode == "tess":
                d = ocr.eng.image_to_data(img, output_type=ocr.eng.Output.DICT)
                for i, t in enumerate(d["text"]):
                    if mot in t.lower():
                        return d["left"][i] + d["width"][i] // 2, d["top"][i] + d["height"][i] // 2
                return None
            res = ocr.eng(img)
            if hasattr(res, "txts"):
                boxes, txts = res.boxes, res.txts
            else:
                lst = res[0] if isinstance(res, tuple) else res
                boxes, txts = [e[0] for e in lst or []], [e[1] for e in lst or []]
            if boxes is None or txts is None:
                return None
            for b, t in zip(boxes, txts):
                if mot in str(t).lower():
                    pts = np.array(b, dtype=float).reshape(-1, 2)
                    return int(pts[:, 0].mean()), int(pts[:, 1].mean())
        except Exception as err:
            log(f"lecture du bouton impossible : {err}")
        return None

    def trouver_bouton_vert(img):
        # plus gros rectangle vert plein (bouton Fusionner), centre (x, y) ou None
        m = cv2.inRange(img, np.array([0, 120, 90], np.uint8), np.array([70, 230, 200], np.uint8))
        m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
        n, _, st, _ = cv2.connectedComponentsWithStats(m, connectivity=8)
        meilleur = None
        for i in range(1, n):
            x, y, w, h, aire = (int(v) for v in st[i])
            if w >= 80 and h >= 22 and 2 <= w / h <= 10 and aire > .6 * w * h:
                if meilleur is None or aire > meilleur[0]:
                    meilleur = (aire, x + w // 2, y + h // 2)
        return (meilleur[1], meilleur[2]) if meilleur else None

    def tenter_exo(gab, ou):
        # double clic sur la rune de l'inventaire, puis clic sur le bouton Fusionner
        x = mon["left"] + ou[0] + gab.shape[1] // 2
        y = mon["top"] + ou[1] + gab.shape[0] // 2
        if not clic_point(x, y, double=True):
            return False
        for _ in range(4):
            time.sleep(0.5)
            img = capturer(mon)
            pos = trouver_bouton_vert(img) or trouver_texte(img, "fusion")
            if pos:
                return clic_point(mon["left"] + pos[0], mon["top"] + pos[1])
        log("Bouton Fusionner introuvable apres le double clic")
        return False

'''

EXO_HOOK = r'''                                # FM_CLICK_PATCH:EXO_HOOK
                                verifier_mode_clic()
                                cle_exo = (tuple(sorted(sig_item)), resume(etat), reco.get("stat"), "exo")
                                if panneau.mode.get() == "automatique" and n_vu >= 2 \
                                        and (cle_exo != dernier_clic or time.time() - t_clic > 3):
                                    dernier_clic, t_clic = cle_exo, time.time()
                                    if tenter_exo(gab, ou):
                                        t_clic = time.time()
                                        log(f"Exo tente : {reco['texte']}")
'''


SUITE_HELPER = r"""
def proposer_suite(motif, item=""):
    SUIVI.fin = (item or "", time.time())
    if getattr(SUIVI, "file", None):
        return                      # file d'attente : l'item suivant est deja choisi
    if time.time() - getattr(SUIVI, "t_suite", 0) < 600:
        return
    noms = [it["nom"] for it in charger_items() if it["nom"] != item]
    if noms:
        SUIVI.t_suite = time.time()
        SUIVI.suite = {"motif": motif, "item": item, "items": noms}
        SUIVI.evenement("suite", f"{motif} : choisis l'item suivant sur ton téléphone", 20)


"""

SUITE_POST = r"""                if chemin[0] == suivi.cle and chemin[1:] == ["suivant"]:
                    try:
                        c = json.loads(self.rfile.read(min(int(self.headers.get("Content-Length", 0)), 2000)))
                        s = getattr(suivi, "suite", None)
                        assert s
                        if c.get("nom") is not None:
                            assert c["nom"] in s["items"]
                            suivi.suivant = c["nom"]
                            suivi.evenement("suivant " + c["nom"], f"Item suivant choisi : {c['nom']}", 5)
                        suivi.suite = None
                    except Exception:
                        self.send_error(400)
                        return
                    self.send_response(204)
                    self.end_headers()
                    return
"""

SUITE_APPLIQUER = r"""                    if getattr(SUIVI, "suivant", None):
                        panneau.cmds.put({"cmd": "preselection", "nom": SUIVI.suivant})
                        panneau.cmds.put({"cmd": "enregistrer"})
                        log(f"item suivant choisi sur le telephone : objectifs de {SUIVI.suivant} appliques")
                        SUIVI.evenement("suivant ok", f"Objectifs de {SUIVI.suivant} appliqués au nouvel item", 5)
                        SUIVI.suivant = None
"""

SUITE_JS = r"""
function suite(s,v){const e=document.getElementById('s');if(!s){if(v){e.style.display='block';
 e.innerHTML='<b>Prochain item : '+esc(v)+'</b><br>Place-le dans la fenêtre : ses objectifs seront appliqués tout seuls.'}else e.style.display='none';sv='';return}
 const cle=JSON.stringify(s);if(cle==sv)return;sv=cle;e.style.display='block';
 e.innerHTML='<b>'+esc(s.motif)+(s.item?' : '+esc(s.item):'')+'</b><br>Quel item charger ensuite ?'+
  s.items.map((n,i)=>'<button data-i="'+i+'">'+esc(n)+'</button>').join('')+'<button class=non data-i="-1">Plus tard</button>';
 e.querySelectorAll('button').forEach(b=>b.onclick=()=>{const i=+b.dataset.i;
  fetch('/'+K+'/suivant',{method:'POST',body:JSON.stringify({nom:i<0?null:s.items[i]})});e.style.display='none'})}
let sv='';
"""
def replace_once(source, old, new, label):
    count = source.count(old)
    if count != 1:
        raise ValueError(f"Point d'insertion « {label} » introuvable ou ambigu ({count} occurrence(s)).")
    return source.replace(old, new, 1)


def patch(source):
    found = [marker in source for marker in MARKERS]
    if all(found):
        updated = source.replace("sct = mss.mss()", "sct = mss.MSS()", 1)
        return updated, updated != source
    if any(found):
        raise ValueError("Une partie du patch est déjà présente. Vérifie le fichier avant de continuer.")

    if "        import ctypes\n        from ctypes import wintypes\n" in source:
        source = replace_once(
            source,
            "        import ctypes\n        from ctypes import wintypes\n",
            "        import ctypes\n"
            "        # FM_CLICK_PATCH:WINTYPES\n"
            "        from ctypes import wintypes\n",
            "import Windows",
        )
    else:
        source = replace_once(
            source,
            "        import ctypes\n        try:\n",
            "        import ctypes\n"
            "        # FM_CLICK_PATCH:WINTYPES\n"
            "        from ctypes import wintypes\n\n"
            "        try:\n",
            "import Windows",
        )
    source = source.replace("sct = mss.mss()", "sct = mss.MSS()", 1)
    source = replace_once(
        source,
        "        def capturer(m):\n            return np.ascontiguousarray(np.array(sct.grab(m))[:, :, :3])\n",
        "        def capturer(m):\n"
        "            nonlocal sct\n"
        "            for essai in range(60):\n"
        "                try:\n"
        "                    return np.ascontiguousarray(np.array(sct.grab(m))[:, :, :3])\n"
        "                except mss.exception.ScreenShotError:\n"
        "                    time.sleep(0.5)\n"
        "                    try:\n"
        "                        sct = mss.MSS()\n"
        "                    except Exception:\n"
        "                        pass\n"
        "            raise RuntimeError(\"capture d'ecran impossible depuis 30 s\")\n",
        "capture r?siliente",
    )
    source = replace_once(
        source,
        "        self.lignes, self.rangs, self.n_rang = {}, {}, 0\n",
        "        self.lignes, self.rangs, self.n_rang = {}, {}, 0\n"
        "        # FM_CLICK_PATCH:MODE_INIT\n"
        "        self.mode = tk.StringVar(value=\"automatique\")\n",
        "initialisation du mode",
    )
    source = replace_once(
        source,
        "        self.choix.bind(\"<<ComboboxSelected>>\", self._choisi)\n",
        "        self.choix.bind(\"<<ComboboxSelected>>\", self._choisi)\n"
        "        # FM_CLICK_PATCH:MODE_UI\n"
        "        mode = tk.Frame(w, bg=F)\n"
        "        mode.pack(fill=\"x\", padx=10, pady=(6, 0))\n"
        "        tk.Label(mode, text=\"Mode de clics\", bg=F, fg=self.GRIS).pack(side=\"left\")\n"
        "        for valeur, libelle in ((\"automatique\", \"Automatique\"), (\"manuel\", \"Manuel\")):\n"
        "            tk.Radiobutton(mode, text=libelle, variable=self.mode, value=valeur,\n"
        "                           command=self._mode_change, bg=F, fg=self.TXT, selectcolor=self.CARTE,\n"
        "                           activebackground=F, activeforeground=self.TXT).pack(side=\"left\", padx=5)\n"
        "        # FM_CLICK_PATCH:MODE_HELP\n"
        "        tk.Label(w, text=\"Automatique clique la rune recommandée. Bouger la souris ou appuyer sur Echap \"\n"
        "                 \"passe en Manuel ; choisis Automatique pour reprendre.\",\n"
        "                 bg=F, fg=self.GRIS, anchor=\"w\", justify=\"left\", wraplength=600).pack(fill=\"x\", padx=10)\n",
        "sélecteur de mode",
    )
    source = replace_once(
        source,
        "    @staticmethod\n"
        "    def _conf(it):\n",
        "    @staticmethod\n"
        "    def _conf(it):\n"
        "        # FM_CLICK_PATCH:MODE_CONFIG\n"
        "        conf = Panneau._conf_base(it)\n"
        "        mode = it.get(\"mode\", \"automatique\")\n"
        "        conf[\"mode\"] = mode if mode in (\"automatique\", \"manuel\") else \"automatique\"\n"
        "        return conf\n"
        "\n"
        "    def _mode_change(self):\n"
        "        if self.conf is not None:\n"
        "            self.conf[\"mode\"] = self.mode.get()\n"
        "\n"
        "    @staticmethod\n"
        "    def _conf_base(it):\n",
        "configuration de mode",
    )
    source = replace_once(
        source,
        "        else:\n"
        "            self.conf = None\n"
        "            self.etat.config(text=\"NOUVEL ITEM : règle l'objectif puis ENREGISTRER\", fg=self.ROUGE)\n",
        "        else:\n"
        "            self.mode.set(\"manuel\")\n"
        "            self.conf = None\n"
        "            self.etat.config(text=\"NOUVEL ITEM : règle l'objectif puis ENREGISTRER\", fg=self.ROUGE)\n",
        "mode par défaut des nouveaux items",
    )
    source = replace_once(
        source,
        "    def appliquer(self, it):\n"
        "        self._met(self.nom, it[\"nom\"])\n",
        "    def appliquer(self, it):\n"
        "        self._met(self.nom, it[\"nom\"])\n"
        "        # FM_CLICK_PATCH:MODE_APPLY\n"
        "        self.mode.set(\"manuel\")\n",
        "chargement du mode de l'item",
    )
    source = replace_once(
        source,
        "        self.items = [it for it in self.items if it[\"nom\"] != nom and proche(it[\"sig\"], self.sig) < .7]\n",
        "        # FM_CLICK_PATCH:MODE_SAVE\n"
        "        fiche[\"mode\"] = self.mode.get()\n"
        "        self.items = [it for it in self.items if it[\"nom\"] != nom and proche(it[\"sig\"], self.sig) < .7]\n",
        "enregistrement du mode",
    )

    runtime = (
        "    # FM_CLICK_PATCH:CLICK_RUNTIME\n"
        "    def position_souris():\n"
        "        point = wintypes.POINT()\n"
        "        user32 = ctypes.windll.user32\n"
        "        if not user32.GetCursorPos(ctypes.byref(point)):\n"
        "            log(f\"lecture de la position de la souris impossible : {ctypes.WinError()}\")\n"
        "            return None\n"
        "        return point.x, point.y\n"
        "\n"
        "    position_souris_ref = [position_souris() if windows else None]\n"
        "    mode_suivi = [panneau.mode.get()]\n"
        "\n"
        "    def cliquer_case(rect):\n"
        "        x1, y1, x2, y2 = rect\n"
        "        x, y = mon[\"left\"] + (x1 + x2) // 2, mon[\"top\"] + (y1 + y2) // 2\n"
        "        user32 = ctypes.windll.user32\n"
        "        if not user32.SetCursorPos(x, y):\n"
        "            log(f\"clic automatique impossible : {ctypes.WinError()}\")\n"
        "            return False\n"
        "        position_souris_ref[0] = (x, y)\n"
        "        user32.mouse_event(0x0002, 0, 0, 0, 0)\n"
        "        time.sleep(0.05)\n"
        "        user32.mouse_event(0x0004, 0, 0, 0, 0)\n"
        "        return True\n"
        "\n"
        "    f1_ref = [False]\n"
        "\n"
        "    def minimiser_ui():\n"
        "        user32 = ctypes.windll.user32\n"
        "        user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]\n"
        "        user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]\n"
        "        user32.IsWindowVisible.argtypes = [wintypes.HWND]\n"
        "        proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)\n"
        "\n"
        "        def vers(h, _):\n"
        "            buf = ctypes.create_unicode_buffer(256)\n"
        "            user32.GetWindowTextW(h, buf, 256)\n"
        "            if buf.value.startswith(\"Forgemagie\") and user32.IsWindowVisible(h):\n"
        "                user32.ShowWindow(h, 6)\n"
        "            return True\n"
        "\n"
        "        user32.EnumWindows(proc(vers), 0)\n"
        "\n"
        "    def verifier_mode_clic():\n"
        "        if not windows:\n"
        "            return\n"
        "        f1 = bool(ctypes.windll.user32.GetAsyncKeyState(0x70) & 0x8000)\n"
        "        f1_neuf, f1_ref[0] = f1 and not f1_ref[0], f1\n"
        "        if f1_neuf:\n"
        "            panneau.mode.set(\"automatique\")\n"
        "            panneau._mode_change()\n"
        "            mode_suivi[0] = \"automatique\"\n"
        "            position_souris_ref[0] = position_souris()\n"
        "            log(\"Mode automatique lance (F1). Echap pour arreter.\")\n"
        "            try:\n"
        "                minimiser_ui()\n"
        "            except Exception as err:\n"
        "                log(f\"minimisation de la page impossible : {err}\")\n"
        "            return\n"
        "        mode = panneau.mode.get()\n"
        "        if mode != mode_suivi[0]:\n"
        "            mode_suivi[0] = mode\n"
        "            position_souris_ref[0] = position_souris()\n"
        "            return\n"
        "        if mode != \"automatique\":\n"
        "            position_souris_ref[0] = position_souris()\n"
        "            return\n"
        "        user32 = ctypes.windll.user32\n"
        "        if user32.GetAsyncKeyState(0x1B) & 0x8000:\n"
        "            panneau.mode.set(\"manuel\")\n"
        "            panneau._mode_change()\n"
        "            mode_suivi[0] = \"manuel\"\n"
        "            log(\"Mode manuel active (Echap). L'analyse continue.\")\n"
        "            return\n"
        "        position = position_souris()\n"
        "        reference = position_souris_ref[0]\n"
        "        if position is not None and reference is not None:\n"
        "            dx, dy = position[0] - reference[0], position[1] - reference[1]\n"
        "            if dx * dx + dy * dy >= 30 * 30:\n"
        "                panneau.mode.set(\"manuel\")\n"
        "                panneau._mode_change()\n"
        "                mode_suivi[0] = \"manuel\"\n"
        "                log(\"Mode manuel active (mouvement de souris). L'analyse continue.\")\n"
        "\n"
        "    if windows:\n"
        "        log(\"F1 : mode automatique et page minimisee. Mouvement de souris (>30 px) ou Echap : passe en mode manuel.\")\n"
    ) + RUNTIME_EXO + RUNTIME_RAVITO
    source = replace_once(
        source,
        "                g = GUIDE.etape(bgr, etat, achats, ocr, regl_stock)\n",
        "                g = GUIDE.etape(bgr, etat, achats, ocr, regl_stock)\n"
        "                # FM_CLICK_PATCH:RAVITO_HOOK\n" + RAVITO_HOOK,
        "ravitaillement automatique (atelier)",
    )
    source = replace_once(
        source,
        "                        nom_item = lire_nom_item(bgr, etat[\"rows\"], ocr)\n",
        "                        SUIVI.n_survol, SUIVI.t_survol = 0, time.time()\n"
        "                        SUIVI.nom_reel = lire_nom_survol() if windows else \"\"\n"
        "                        nom_item = SUIVI.nom_reel or lire_nom_item(bgr, etat[\"rows\"], ocr)\n",
        "nom reel de l objet par son infobulle",
    )
    source = replace_once(
        source,
        "                        nom_item = connu[\"nom\"] if connu else nom_item\n",
        "                        nom_item = SUIVI.nom_reel or (connu[\"nom\"] if connu else nom_item)\n",
        "le nom de l objet reste le nom reel",
    )
    source = replace_once(
        source,
        "                vues = etat[\"lignes\"]\n                sig = signature(vues)\n",
        "                vues = etat[\"lignes\"]\n"
        "                if windows and panneau.mode.get() == \"automatique\" and not getattr(SUIVI, \"nom_reel\", \"\") and getattr(SUIVI, \"n_survol\", 3) < 3 \\\n"
        "                        and time.time() - getattr(SUIVI, \"t_survol\", 0) > 8:\n"
        "                    SUIVI.n_survol, SUIVI.t_survol = getattr(SUIVI, \"n_survol\", 0) + 1, time.time()\n"
        "                    SUIVI.nom_reel = lire_nom_survol()\n"
        "                    nom_item = SUIVI.nom_reel or nom_item\n"
        "                sig = signature(vues)\n",
        "nouvel essai de lecture du nom de l objet",
    )
    source = replace_once(
        source,
        "\"texte\": self.texte, \"stop\": self.stop, \"item\": self.item,",
        "\"texte\": self.texte, \"stop\": self.stop, \"item\": (f\"{self.nom_reel} — objectif : {self.item}\" if getattr(self, \"nom_reel\", \"\") and self.item and self.nom_reel.lower() != self.item.lower() else (getattr(self, \"nom_reel\", \"\") or self.item)),",
        "telephone : nom reel et objectif",
    )
    source = replace_once(
        source,
        "                g = g_hors\n",
        "                g = g_hors\n" + RAVITO_HOOK,
        "ravitaillement automatique (hors atelier)",
    )
    source = replace_once(
        source,
        "    panneau = Panneau(root, cacher)\n",
        "    panneau = Panneau(root, cacher)\n" + runtime,
        "mécanisme de clic",
    )
    source, n_boucle = re.subn(
        r"^( {8}while True:\n)( {12}root\.update\(\)\n)",
        lambda m: m.group(1) + "            # FM_CLICK_PATCH:LOOP\n            verifier_mode_clic()\n" + m.group(2),
        source, count=1, flags=re.M,
    )
    if n_boucle != 1:
        raise ValueError("Point d'insertion « boucle principale » introuvable.")

    source = replace_once(
        source,
        "                        cv.create_rectangle(*c, outline=\"#ff3b30\" if reco.get(\"stop\") else \"#00ff66\", width=3)\n",
        "                        cv.create_rectangle(*c, outline=\"#ff3b30\" if reco.get(\"stop\") else \"#00ff66\", width=3)\n"
        "                        # FM_CLICK_PATCH:CLICK_HOOK\n"
        "                        verifier_mode_clic()\n"
        "                        cle_clic = (tuple(sorted(sig_item)), resume(etat),\n"
        "                                    reco.get(\"stat\"), reco.get(\"taille\"))\n"
        "                        relance = False\n"
        "                        if cle_clic != dernier_clic:\n"
        "                            n_relance = 0\n"
        "                        elif time.time() - t_clic > 1.5:\n"
        "                            relance, n_relance = True, n_relance + 1\n"
        "                        if panneau.mode.get() == \"automatique\" and n_vu >= 2 and not reco.get(\"stop\") \\\n"
        "                                and (cle_clic != dernier_clic or relance):\n"
        "                            if relance and n_relance >= 2:\n"
        "                                ctypes.windll.user32.keybd_event(0x0D, 0, 0, 0)\n"
        "                                ctypes.windll.user32.keybd_event(0x0D, 0, 2, 0)\n"
        "                                time.sleep(0.15)\n"
        "                            dernier_clic, t_clic = cle_clic, time.time()\n"
        "                            if cliquer_case(c):\n"
        "                                log(f\"Clic automatique : {reco['texte']}\")\n",
        "clic sur la rune",
    )
    source = replace_once(
        source,
        "                                txt += \"   (exo : rune encadrée dans l'inventaire)\"\n",
        "                                txt += \"   (exo : rune encadrée dans l'inventaire)\"\n" + EXO_HOOK,
        "exo : double clic et fusion",
    )
    source = replace_once(
        source,
        "                                                f\"à {l_res.get('val')} sur {item_ or 'l item'}\", 5)\n",
        "                                                f\"à {l_res.get('val')} sur {item_ or 'l item'}\", 5)\n"
        "                                placer_souris_haut_gauche()\n"
        "                                proposer_suite(\"Exo passé\", item_)\n",
        "déplacement de la souris après un exo réussi",
    )
    source = re.sub(
        r"^( +sig_item, n_autre, nom_item[^\n]*\n)",
        lambda m: m.group(1) + "    dernier_clic, t_clic, n_relance = None, 0.0, 0\n",
        source, count=1, flags=re.M,
    )
    if "t_clic, n_relance = None, 0.0, 0" not in source:
        raise ValueError("Point d'insertion « mémorisation du clic » introuvable.")
    source = replace_once(
        source,
        "                cv.create_text(x + 4, y - int(1.15 * h)",
        "                # FM_CLICK_PATCH:MANUAL_LABEL\n"
        "                if panneau.mode.get() == \"manuel\":\n"
        "                    txt += \"   | MODE MANUEL\"\n"
        "                cv.create_text(x + 4, y - int(1.15 * h)",
        "indicateur du mode manuel",
    )
    source = replace_once(
        source,
        '    """Texte a taper pour trouver cette rune a l\'hotel de vente."""\n'
        '    perso = ((regl or {}).get(f"{s}/{t}") or {}).get("recherche")\n'
        '    if perso:\n'
        '        return perso\n',
        '    """Texte a taper pour trouver cette rune a l\'hotel de vente."""\n'
        '    perso = ((regl or {}).get(f"{s}/{t}") or {}).get("recherche")\n'
        '    if perso:\n'
        '        return perso\n'
        '    try:\n'
        '        import dofusdb\n'
        '        exact = dofusdb.charger().get(f"{s}/{t}")\n'
        '        if exact:\n'
        '            return exact.lower()\n'
        '    except Exception:\n'
        '        pass\n',
        "noms exacts des runes (DofusDB)",
    )
    source = replace_once(
        source,
        "def liste_achats(lignes, regl):\n",
        "RUNES_SAUTEES = {}      # rune -> (stock au moment du refus, heure) : pas de nouveau ravitaillement tant que rien ne change\n"
        "SAUT_DUREE = 1800\n\n\n"
        "def liste_achats(lignes, regl):\n"
        "    out = []\n"
        "    for x in _liste_achats_brut(lignes, regl):\n"
        "        s = RUNES_SAUTEES.get(x[\"rune\"])\n"
        "        if s and s[0] == x[\"stock\"] and time.time() - s[1] < SAUT_DUREE:\n"
        "            continue\n"
        "        RUNES_SAUTEES.pop(x[\"rune\"], None)\n"
        "        out.append(x)\n"
        "    return out\n\n\n"
        "def _liste_achats_brut(lignes, regl):\n",
        "runes sautees : pas de boucle de ravitaillement",
    )
    source = replace_once(
        source,
        "SUIVI = Suivi()\n",
        SUITE_HELPER + "SUIVI = Suivi()\n",
        "choix de l'item suivant : fonctions",
    )
    source = replace_once(
        source,
        "                \"achats\": self.achats}\n",
        "                \"achats\": self.achats, \"suite\": getattr(self, \"suite\", None),\n"
        "                \"suivant\": getattr(self, \"suivant\", None)}\n",
        "choix de l'item suivant : etat",
    )
    source = replace_once(
        source,
        "            self.evenement(\"fini\", \"Objectif atteint sur \" + (item or \"l'item\"), 600)\n",
        "            self.evenement(\"fini\", \"Objectif atteint sur \" + (item or \"l'item\"), 600)\n"
        "            proposer_suite(\"Objectif atteint\", item)\n",
        "choix de l'item suivant : objectif atteint",
    )
    source = replace_once(
        source,
        "        self.texte, self.stop, self.item, self.t = txt, bool(reco.get(\"stop\")), item, time.time()\n",
        "        self.texte, self.stop, self.item, self.t = txt, bool(reco.get(\"stop\")), item, time.time()\n"
        "        if getattr(self, \"suivant\", None) and self.suivant == item:\n"
        "            self.suivant = None\n",
        "choix de l'item suivant : item en place",
    )
    source = replace_once(
        source,
        "                if chemin[0] == suivi.cle and chemin[1:] == [\"decision\"]:\n",
        SUITE_POST + "                if chemin[0] == suivi.cle and chemin[1:] == [\"decision\"]:\n",
        "choix de l'item suivant : reponse du telephone",
    )
    source = replace_once(
        source,
        "                    txt = \"NOUVEL ITEM : regle l'objectif dans la fenetre FM\"\n",
        "                    txt = \"NOUVEL ITEM : regle l'objectif dans la fenetre FM\"\n" + SUITE_APPLIQUER,
        "choix de l'item suivant : application",
    )
    source = replace_once(
        source,
        "<div id=c>connexion...</div><div id=m></div><div id=q></div>",
        "<div id=c>connexion...</div><div id=m></div><div id=q></div><div id=s></div>",
        "choix de l'item suivant : zone de la page",
    )
    source = replace_once(
        source,
        "#q b{color:#ffd166}",
        "#s{display:none;margin:8px 14px;padding:12px;border:1px solid #3ddc84;border-radius:8px;background:#102218}"
        "#s b{color:#3ddc84}#s button{display:block;width:100%;margin:8px 0 0;padding:12px;font-size:15px;text-align:left}"
        "#s button.non{background:#2a2d36}#q b{color:#ffd166}",
        "choix de l'item suivant : style",
    )
    source = replace_once(
        source,
        "function esc(t){",
        SUITE_JS + "function esc(t){",
        "choix de l'item suivant : script",
    )
    source = replace_once(
        source,
        " question(d.demande);",
        " question(d.demande);suite(d.suite,d.suivant);",
        "choix de l'item suivant : appel",
    )
    source = replace_once(
        source,
        "<span id=\"lien\" class=\"pastille\">hors ligne</span></div>",
        "<button id=\"modeclic\" class=\"pastille\" style=\"cursor:pointer;font:inherit;font-size:12px\" "
        "title=\"Automatique : clique la rune et gère le ravitaillement. Souris bougée ou Échap : repasse en manuel.\">"
        "Mode : …</button>\n<span class=\"pastille\">F1 dans Dofus : Automatique · Échap : Manuel</span>\n<span id=\"lien\" class=\"pastille\">hors ligne</span></div>",
        "mode de clics : bouton de la page",
    )
    source = replace_once(
        source,
        " $('lien').textContent='en ligne';",
        " (()=>{const b=$('modeclic'),a=d.mode==='automatique';b.textContent='Mode : '+(a?'AUTOMATIQUE':'MANUEL');\n"
        "  b.className='pastille '+(a?'ok':'ko');b.dataset.m=d.mode})();\n"
        " $('lien').textContent='en ligne';",
        "mode de clics : affichage",
    )
    source = replace_once(
        source,
        "setInterval(maj,400);maj();\n",
        "$('modeclic').onclick=e=>cmd('mode',{mode:e.target.dataset.m==='automatique'?'manuel':'automatique'},false);\n"
        "setInterval(maj,400);maj();\n",
        "mode de clics : bouton",
    )
    source = replace_once(
        source,
        "        elif quoi == \"stock\":\n",
        "        elif quoi == \"mode\" and c.get(\"mode\") in (\"automatique\", \"manuel\"):\n"
        "            self.mode.set(c[\"mode\"])\n"
        "            self._mode_change()\n"
        "            log(f\"Mode {c['mode']} choisi depuis la page.\")\n"
        "        elif quoi == \"stock\":\n",
        "mode de clics : commande",
    )
    source = replace_once(
        source,
        "\"calib\": self.msg_calib[0], \"calib_ok\": self.msg_calib[1]}",
        "\"calib\": self.msg_calib[0], \"calib_ok\": self.msg_calib[1], \"mode\": self.mode.get()}",
        "mode de clics : etat",
    )
    return source, True

SORTIE = "fm_avec_clics.py"
EXCLUS = {SORTIE, "activer_clics.py", "diag.py", "fm_live.py"}


def plus_recent(dossier):
    candidats = []
    for f in dossier.glob("*.py"):
        if f.name in EXCLUS:
            continue
        try:
            if "def mode_direct(" in f.read_text(encoding="utf-8"):
                candidats.append(f)
        except (OSError, UnicodeDecodeError):
            pass
    return max(candidats, key=lambda f: f.stat().st_mtime, default=None)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", nargs="?", help="script source (par d?faut : le plus r?cent du dossier)")
    args = parser.parse_args()
    dossier = Path(__file__).resolve().parent
    source = Path(args.source).resolve() if args.source else plus_recent(dossier)
    if source is None or not source.is_file():
        print("ERREUR : aucune version de l'assistant trouv?e.", file=sys.stderr)
        return 1

    try:
        updated, _ = patch(source.read_text(encoding="utf-8"))
        compile(updated, SORTIE, "exec")
    except (OSError, SyntaxError, ValueError) as error:
        print(f"ERREUR avec {source.name} : {error}", file=sys.stderr)
        print("Le code de cette version a chang? : le patch doit ?tre mis ? jour.", file=sys.stderr)
        return 1

    (dossier / SORTIE).write_text(updated, encoding="utf-8", newline="")
    print(f"Version utilis?e : {source.name} -> {SORTIE} (clics ajout?s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
