#!/usr/bin/env python3
"""Réapplique le mode de clics au fichier assistant indiqué."""
import argparse
import re
import sys
from pathlib import Path
from fm_fichiers import ecrire_texte


RUNTIME_ECRAN = r'''
    def cibler_ecran_dofus():
        nonlocal mon,i_mon
        from fm_securite import rectangle_dofus_actif,ecran_de_rectangle
        try:
            indice=ecran_de_rectangle(rectangle_dofus_actif(),mons)
            if indice is None:
                log('F1 : ecran de Dofus non confirme ; aucune action envoyee')
                return False
            if mon is not mons[indice]:
                i_mon=indice
                mon=partage['mon']=mons[indice]
                _COUL[0]=None
                securite['capture']=securite['lecture']=None
                securite['reprise_apres']=time.monotonic()
                file_runtime.update(valide=None,preuve=None,n=0,capture=-1.,reprise_n=0,reprise_preuve=None)
                GUIDE.vue=(None,None)
                root.geometry(f"{mon['width']}x{mon['height']}{mon['left']:+d}{mon['top']:+d}")
                diagnostic.evenement('ecran_dofus_selectionne',ecran=indice+1,rectangle=mon)
                log(f'F1 : capture sur ecran {indice+1}, fenetre Dofus active')
            if demarrage.phase=='ATELIER':
                demarrage.t_atelier=time.monotonic()
            return True
        except Exception as err:
            log('F1 : selection de l ecran impossible : '+str(err))
            return False

'''

RUNTIME_SECURITE = r'''
    # FM_CLICK_PATCH:SECURITE_V1
    from fm_securite import motif_blocage, fenetre_dofus_active
    securite = {"capture": None, "lecture": None, "motif": None}
    mesures_securite = {"debut": time.monotonic(), "n": 0, "total": 0., "max": 0., "blocages": {}}
    from fm_confirmation import ConfirmationActions, ConfirmationTransition
    confirmation = ConfirmationActions()
    confirmation_navigation = ConfirmationTransition()
    confirmation_signalee = [None]
    fin_signalee = [None]

    def signaler_objectif_confirme(recommandation):
        if not recommandation.get("texte", "").startswith("OBJECTIF ATTEINT") or recommandation.get("stop"):
            fin_signalee[0] = None
            return
        if confirmation.attente is not None or confirmation_navigation.attente is not None:
            return
        if getattr(panneau,'journal_file',None) is not None and not confirmer_fin_file(recommandation):
            return
        item = panneau.nom.get().strip()
        if fin_signalee[0] != item:
            conf_fin = panneau.conf or {}
            lignes_fin = (etat or {}).get("lignes", {})
            if lignes_fin and all(
                    s in lignes_fin and not lignes_fin[s].get("rate")
                    and lignes_fin[s]["val"] >= min(conf_fin.get("mins", {}).get(s, cible), cible, lignes_fin[s]["max"])
                    for s, cible in conf_fin.get("cibles", {}).items() if cible > 0):
                placer_souris_haut_gauche()
            proposer_suite("Objectif atteint", item)
            fin_signalee[0] = item

    def observer_confirmation(etat, capture):
        action_avant = confirmation.attente
        resultat = confirmation.observer(etat, capture, panneau.nom.get().strip(), time.monotonic())
        if resultat:
            if resultat['type']=='action_confirmee' and getattr(panneau,'journal_file',None) is not None:
                try:
                    panneau.journal_file.observer((etat or {}).get('lignes',{}))
                except Exception as err:
                    bloquer_file('confirmation non sauvegardee : '+str(err))
            if resultat["type"] == "action_confirmee" and action_avant and action_avant["stat"] in stock_exos.valeurs:
                stock_exos.consommer(action_avant["stat"])
                panneau.stock_exos = dict(stock_exos.valeurs)
            cle_signal = (resultat["id"], resultat["type"], resultat.get("motif"))
            if cle_signal != confirmation_signalee[0]:
                diagnostic.evenement(resultat["type"], **{k: v for k, v in resultat.items() if k != "type"})
                confirmation_signalee[0] = cle_signal
            if resultat["type"] != "action_confirmee":
                if panneau.mode.get() == "automatique":
                    panneau.mode.set("manuel")
                    panneau._mode_change()
                    log("Action non confirmee : " + resultat["motif"] + ". Verifie le jeu puis F1 pour resynchroniser.")

    def debut_confirmation():
        identifiant = confirmation.commencer(etat, reco, panneau.nom.get().strip(), time.monotonic())
        diagnostic.evenement("action_en_attente", id_confirmation=identifiant,
                             stat=reco.get("stat"), taille=reco.get("taille"))

    def dofus_actif():
        if not windows:
            return False
        debut = time.perf_counter()
        try:
            return fenetre_dofus_active()
        except Exception as err:
            motif = "controle de la fenetre impossible : " + str(err)
            if securite.get("erreur_fenetre") != motif:
                log(motif)
                securite["erreur_fenetre"] = motif
            return False
        finally:
            duree = time.perf_counter() - debut
            mesures_securite["n"] += 1
            mesures_securite["total"] += duree
            mesures_securite["max"] = max(mesures_securite["max"], duree)
            maintenant = time.monotonic()
            if maintenant - mesures_securite["debut"] >= 30:
                n = mesures_securite["n"]
                log(f"PERF securite : {n} controles ; moyenne {1000 * mesures_securite['total'] / n:.3f} ms ; "
                    f"max {1000 * mesures_securite['max']:.3f} ms ; blocages {mesures_securite['blocages']}")
                mesures_securite.update(debut=maintenant, n=0, total=0., max=0., blocages={})

    def action_autorisee(fm=False):
        verifier_mode_clic()
        if confirmation.attente is not None or confirmation_navigation.attente is not None:
            return False
        if fm and getattr(panneau,'journal_file',None) is not None and not autoriser_file():
            return False
        motif = motif_blocage(
            automatique=panneau.mode.get() == "automatique",
            dofus_actif=dofus_actif(),
            capture=securite["lecture" if fm else "capture"],
            maintenant=time.monotonic(),
            stop=bool(reco.get("stop")) and (fm or not securite.get("preparation",False)))
        if motif and motif != securite["motif"]:
            log("Action automatique bloquee : " + motif)
        if motif:
            blocages = mesures_securite["blocages"]
            blocages[motif] = blocages.get(motif, 0) + 1
        if motif and motif != securite["motif"]:
            diagnostic.evenement("action_bloquee", motif=motif, fm=fm)
        securite["motif"] = motif
        return motif is None

'''

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
    from fm_stock_exos import StockExos, runes_a_verifier, barre_inventaire, zone_filtre, quantite_filtrage, chiffres_stock, recherche_effacee, point_ressources, nettoyage_confirme, point_fermeture_inventaire, case_inventaire
    stock_exos = StockExos()
    stock_session = [None]
    chiffres_inventaire = Chiffres()  # independant du lecteur de tableau en arriere-plan

    def vider_recherche_inventaire():
        image = capturer(mon)
        barre = barre_inventaire(image)
        if barre is None:
            return False
        x,y,w,h=barre
        confirmations_vides=0
        if not clic_point(mon["left"]+x+w-17, mon["top"]+y+h//2):
            return False
        avant=image
        for _ in range(4):
            if not pause_auto(.2):
                return False
            image=capturer(mon)
            b=barre_inventaire(image)
            if b:
                if nettoyage_confirme(avant,barre,image,b):
                    confirmations_vides += 1
                    if confirmations_vides >= 2:
                        diagnostic.evenement("recherche_inventaire_videe",preuve="croix_disparue_et_champ_modifie")
                        return True
                    continue
                confirmations_vides=0
                if recherche_effacee(image,b):
                    diagnostic.evenement("recherche_inventaire_videe",preuve="placeholder_reconnu")
                    return True
                zone=zone_filtre(image,b)
                texte=norm(ocr.ligne(zone))
                if texte == "recherche" or (texte == "" and zone.size and float(zone.std(axis=(0,1)).max()) < 3):
                    return True
        return False

    def verifier_stock_exos():
        codes=runes_a_verifier(panneau.conf, etat["lignes"])
        cle=(panneau.nom.get().strip(), tuple(codes), tuple(sorted(signature(etat["lignes"]))))
        if not codes or stock_session[0] == cle or panneau.mode.get() != "automatique":
            return False
        if confirmation.attente is not None or confirmation_navigation.attente is not None:
            return False
        stock_exos.session(cle)
        panneau.stock_exos = {}
        calque_ravitaillement(True)
        ok=False
        nettoyage=False
        try:
            for code in codes:
                image=capturer(mon)
                barre=barre_inventaire(image)
                if barre is None:
                    raise ValueError("barre de recherche inventaire non reperee")
                x,y,w,h=barre
                nettoyage=False
                ressources=point_ressources(image,barre)
                if ressources is None:
                    raise ValueError("icone Ressources non reconnue")
                if not clic_point(mon["left"]+ressources[0],mon["top"]+ressources[1]) or not pause_auto(.2):
                    raise ValueError("onglet Ressources non confirme")
                image=capturer(mon)
                barre=barre_inventaire(image)
                if barre is None:
                    raise ValueError("inventaire non relu")
                x,y,w,h=barre
                if not clic_point(mon["left"]+x+w//2,mon["top"]+y+h//2):
                    raise ValueError("recherche interrompue")
                ctrl_a()
                taper_texte(recherche_rune(code,"base"))
                if not pause_auto(.6):
                    raise ValueError("filtrage interrompu")
                termine=False
                for _ in range(8):
                    if not pause_auto(.3):
                        raise ValueError("verification interrompue")
                    image=capturer(mon)
                    capture=time.monotonic()
                    b=barre_inventaire(image)
                    if b is None:
                        continue
                    texte_filtre=""
                    filtre=False
                    # Le gabarit deja appris peut prouver l'identite de la premiere
                    # rune meme si l'OCR du champ de recherche saute une lettre.
                    rune_reconnue=False
                    gab=runes.get(code)
                    if gab is not None:
                        bx,by,bw,bh=b
                        k=bw/260
                        case=image[round(by+75*k):round(by+135*k),bx:round(bx+65*k)]
                        if case.shape[0] >= gab.shape[0] and case.shape[1] >= gab.shape[1]:
                            rune_reconnue=trouver_rune(case,gab,None) is not None
                    # Le gabarit appris constitue deja une preuve d'identite.
                    # Eviter l'OCR du champ a chaque capture dans ce cas.
                    if not rune_reconnue:
                        texte_filtre=ocr.ligne(zone_filtre(image,b))
                        filtre=norm(texte_filtre) == norm(recherche_rune(code,"base"))
                    def lire_nombre(z):
                        return chiffres_stock(z,chiffres_inventaire) or ocr.ligne(z,chiffres=True)
                    n=quantite_filtrage(image,b,lire_nombre) if filtre or rune_reconnue else None
                    if n == 0:
                        if not filtre:
                            texte_filtre=ocr.ligne(zone_filtre(image,b))
                            filtre=norm(texte_filtre) == norm(recherche_rune(code,"base"))
                        bx,by,bw,bh=b
                        k=bw/260
                        categorie=image[round(by+33*k):round(by+62*k),round(bx+170*k):round(bx+340*k)]
                        if not filtre or norm(ocr.ligne(categorie)) != norm("Toutes catégories"):
                            n=None
                    diagnostic.evenement("stock_exo_lecture",rune=code,filtre=texte_filtre,quantite=n,rune_reconnue=rune_reconnue)
                    if stock_exos.observer(code,filtre or rune_reconnue,n,capture):
                        panneau.stock_exos=dict(stock_exos.valeurs)
                        for ligne_stock in getattr(SUIVI,"reglages",{}).get("stock",{}).get("rows",[]):
                            if ligne_stock.get("cle") == code + "/base":
                                ligne_stock["n"]=n
                        log(f"Stock inventaire confirme : {nom_code(code)} = {n}")
                        diagnostic.evenement("stock_exo_inventaire",rune=code,stock=n)
                        termine=True
                        break
                if not termine:
                    raise ValueError("stock illisible pour " + nom_code(code))
                nettoyage=vider_recherche_inventaire()
                if not nettoyage:
                    raise ValueError("recherche inventaire non videe")
            panneau.stock_exos=dict(stock_exos.valeurs)
            stock_session[0]=cle
            ok=True
        except Exception as err:
            log("Verification stock exo arretee : " + str(err))
        finally:
            if not nettoyage and panneau.mode.get() == "automatique":
                nettoyage=vider_recherche_inventaire()
            if not ok or not nettoyage:
                panneau.mode.set("manuel")
                panneau._mode_change()
                log("Verification inventaire interrompue ; les stocks deja confirmes sont conserves. Verifie le X avant de reprendre.")
        # Le tableau et ses stocks ont ete filtres : abandonner les captures
        # accumulees et relire avant toute decision ou action FM.
        securite["reprise_apres"] = time.monotonic()
        while True:
            try:
                ancien=boite.get_nowait()
                if ancien is None:
                    boite.put(None)
                    break
            except queue.Empty:
                break
        return True

    def calque_ravitaillement(actif):
        if actif and not ravito.get("calque_masque"):
            root.withdraw()
            root.update_idletasks()
            ravito["calque_masque"] = True
        elif not actif and ravito.get("calque_masque"):
            root.deiconify()
            root.update_idletasks()
            ravito["calque_masque"] = False

    def preparer_stock_exo(a, fiche):
        if not a.get("verifier_stock"):
            return True
        f = fiche["fiches"][0] if fiche and fiche.get("fiches") else None
        n = f.get("qte") if f else None
        if not f or norm(f.get("nom", "")) != norm(a["recherche"]) \
                or not isinstance(n, int) or isinstance(n, bool) or n < 0:
            log("Stock exo non verifie : arret avant achat de " + a["rune"])
            panneau.mode.set("manuel")
            panneau._mode_change()
            return False
        besoin = max(0, a["cible"] - n) if n < a["alerte"] else 0
        q = ((besoin + 9) // 10) * 10
        a.update(stock=n, acheter=q, lots=" + ".join(f"{k}×{taille}" for k, taille in
                 ((q // 1000, 1000), (q % 1000 // 100, 100), (q % 100 // 10, 10)) if k))
        diagnostic.evenement("stock_exo_verifie", rune=a["rune"], stock=n, acheter=q)
        return True

    def pause_auto(s):
        # attente interrompue si le mode repasse en manuel (souris bougee ou Echap) ; False = abandon
        fin = time.time() + s
        while time.time() < fin:
            verifier_mode_clic()
            if panneau.mode.get() != "automatique":
                return False
            time.sleep(0.05)
        return True

    def touche(vk, duree=0.):
        if not action_autorisee():
            return False
        user32 = ctypes.windll.user32
        scan = user32.MapVirtualKeyW(vk,0) if duree else 0
        user32.keybd_event(vk, scan, 0, 0)
        try:
            if duree:
                time.sleep(duree)
        finally:
            user32.keybd_event(vk, scan, 2, 0)
        diagnostic.action_envoyee("touche", vk=vk)
        return True

    def ctrl_a():
        if not action_autorisee():
            return False
        user32 = ctypes.windll.user32
        user32.keybd_event(0x11, 0, 0, 0)
        user32.keybd_event(0x41, 0, 0, 0)
        user32.keybd_event(0x41, 0, 2, 0)
        user32.keybd_event(0x11, 0, 2, 0)
        diagnostic.action_envoyee("ctrl_a")

    def taper_texte(txt):
        # frappe Unicode (accents compris), independante de la disposition du clavier
        if not action_autorisee():
            return False
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
            if not action_autorisee():
                return False
            for flags in (0x0004, 0x0004 | 0x0002):
                e = _IN(1, _U(ki=_KI(0, ord(ch), flags, 0, 0)))
                ctypes.windll.user32.SendInput(1, ctypes.byref(e), ctypes.sizeof(_IN))
            time.sleep(0.012)
        diagnostic.action_envoyee("texte", texte=txt)

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

    def lire_dialogue(img):
        # fenetre ? Acheter ? lue par le guide (lecture de chiffres appris, plus fiable que l'OCR) : meme tuple que lire_confirmation
        ravito["dialogue_pt"] = None
        try:
            GUIDE.t_fiche, GUIDE.empreinte = 0, None
            GUIDE._fiche(img, ocr)
            d = (GUIDE.fiche or {}).get("dial")
            if d and d.get("n") and d.get("prix"):
                ravito["dialogue_pt"] = d.get("pt")
                return norm(d.get("nom") or ""), int(d["n"]), int(d["prix"]), int(d.get("total") or 0)
        except Exception as err:
            log(f"lecture de la fenetre Acheter par le guide impossible : {err}")
        return None

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
        # Chaque clic peut acheter sans dialogue, y compris le premier.
        # Aucune ancienne fiche ne sert de repli si la relecture echoue.
        f0 = None
        try:
            im0, fi0 = lire_fiche()
            if fi0 and fi0.get("fiches"):
                f0 = fi0["fiches"][0]
        except Exception as err:
            log(f"lecture de la fiche impossible : {err}")
        a["_f"] = f0
        import math
        total_lu = (f0 or {}).get("lots", {}).get(n_lot)
        bon_nom = bool(f0 and norm(f0.get("nom", "")) == norm(a["recherche"]))
        prix_lisible = (isinstance(total_lu, (int, float)) and not isinstance(total_lu, bool)
                        and math.isfinite(total_lu) and total_lu > 0)
        if not plafond and f0:
            moyen = f0.get("moyen")
            if isinstance(moyen, (int, float)) and not isinstance(moyen, bool) and math.isfinite(moyen) and moyen > 0:
                marge = (GUIDE.regl or {}).get("_marge", {}).get("pct", 20)
                plafond = int(moyen * (1 + marge / 100))
        if not bon_nom or not prix_lisible or plafond <= 0:
            log("Achat bloque avant clic : nom, prix du lot ou plafond non verifie pour " + a["rune"])
            diagnostic.evenement("achat_prix_non_verifie", rune=a["rune"], lot=n_lot)
            panneau.mode.set("manuel")
            panneau._mode_change()
            return None
        for tentative_prix in range(2):
            if total_lu <= plafond * n_lot:
                break
            if not pause_auto(.2):
                return None
            try:
                im0, fi0 = lire_fiche()
                f0 = fi0["fiches"][0] if fi0 and fi0.get("fiches") else None
                total_lu = (f0 or {}).get("lots", {}).get(n_lot)
                valide = (f0 and norm(f0.get("nom", "")) == norm(a["recherche"])
                          and isinstance(total_lu, (int,float)) and not isinstance(total_lu,bool)
                          and math.isfinite(total_lu) and total_lu > 0)
                if not valide:
                    raise ValueError("nom ou prix du lot non relu")
                a["_f"] = f0
            except Exception as err:
                log(f"Relecture prix non confirmee : {err}")
                panneau.mode.set("manuel")
                panneau._mode_change()
                return None
        if total_lu > plafond * n_lot:
            log(f"Achat refuse avant clic : {a['rune']} x{taille}, total {total_lu:g} > plafond {plafond * n_lot}")
            diagnostic.evenement("achat_prix_refuse", rune=a["rune"], lot=n_lot, total=total_lu, plafond=plafond)
            SUIVI.evenement("cher " + a["rune"], f"Achat refusé avant clic : {a['rune']} x{taille} au-dessus du prix maximum", 300)
            return False
        qte_avant = f0.get("qte") if f0 else None
        if not isinstance(qte_avant, int) or isinstance(qte_avant, bool) or qte_avant < 0:
            log("Achat bloque : inventaire initial illisible pour " + a["rune"])
            panneau.mode.set("manuel")
            panneau._mode_change()
            return None
        if direct and qte_avant is not None and a.get("_attendu") is not None and qte_avant < a["_attendu"]:
            log(f"Achat direct non confirme : {qte_avant} en inventaire, {a['_attendu']} attendu : arret, mode manuel")
            SUIVI.evenement("abandon " + a["rune"], f"Achat automatique arrêté : l'achat de {a['rune']} n'a pas augmenté l'inventaire.", 120)
            panneau.mode.set("manuel")
            panneau._mode_change()
            return None
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
        conf, fin = None, time.time() + 4.
        stocks_confirmes = 0
        while conf is None and time.time() < fin:      # sonde la fenetre au lieu d'attendre a l'aveugle
            if not pause_auto(0.1):
                return None
            img_c = capturer(mon)
            conf = lire_dialogue(img_c) or lire_confirmation(img_c)
            # Le popup peut revenir apres plusieurs achats directs (prix change, notamment).
            # Aucun second clic ACHETER tant que ce clic n'a pas produit un resultat prouve.
            fi = GUIDE.fiche or {}
            f = next((f for f in fi.get("fiches", [])
                      if norm(f.get("nom", "")) == norm(a["recherche"])), {})
            stocks_confirmes = stocks_confirmes + 1 if f.get("qte") == qte_avant + n_lot else 0
            if conf is None and stocks_confirmes >= 2:
                break
        if conf is None:
            if not confirmer_achat(a, qte_avant, n_lot):
                return None
            ravito["direct"] = True
            ravito["achete"][a["rune"]] = ravito["achete"].get(a["rune"], 0) + n_lot
            log(f"Achat sans confirmation : {a['rune']} x{taille}, stock {qte_avant} -> {qte_avant + n_lot} confirme")
            return True
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
        # le ? Prix unitaire ? de la fenetre fait foi (il est lu en premier et il est arrondi : 236 pour un lot a 2 364) ;
        # un total mal lu ne bloque pas l'achat quand l'unitaire concorde avec le lot de la fiche
        ref_u = (ref_lot / qte) if ref_lot and qte else None
        unit_confirme = bool(ref_u and unit and abs(unit - ref_u) <= max(2, .02 * ref_u))
        cible = norm(a["recherche"])
        erreurs = []
        if qte != int(taille):
            erreurs.append(f"quantite {qte} au lieu de {taille}")
        if not nom or norm(nom) != cible:
            erreurs.append(f"rune lue « {nom} » au lieu de « {cible} »")
        if unit <= 0:
            erreurs.append("prix illisible")
        if total and unit and not unit_confirme and abs(total - unit * qte) > max(10 * qte, total // 10):
            erreurs.append(f"total {total} incoherent avec {unit} x {qte}")
        if total and total > plafond * n_lot:
            erreurs.append(f"prix total {total} > max {plafond * n_lot}")
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
            touche(0x1B)                    # ferme uniquement la confirmation ouverte
            pause_auto(0.2)
            if not any("max" in e for e in erreurs):
                return "lecture"      # lecture douteuse, pas un refus de prix : a retenter
            return False
        pt_dialogue = ravito.get("dialogue_pt")
        if not (clic_point(mon["left"] + pt_dialogue[0], mon["top"] + pt_dialogue[1]) if pt_dialogue
                else clic_fr(741 / 1366, 427 / 768)):
            return None
        if not confirmer_achat(a, qte_avant, n_lot):
            return None
        ravito["achete"][a["rune"]] = ravito["achete"].get(a["rune"], 0) + int(taille)
        log(f"Achat : {a['rune']} x{taille} a {unit} l'unite (total {total}, max {plafond})")
        return pause_auto(0.3) or None

    def confirmer_achat(a, avant, quantite):
        fin, confirmations = time.monotonic() + 4., 0
        while time.monotonic() < fin:
            if not pause_auto(.1):
                return False
            try:
                _, fiche = lire_fiche()
                f = fiche["fiches"][0] if fiche and fiche.get("fiches") else None
                n = f.get("qte") if f else None
                # Ne pas confirmer avec le stock d'une autre fiche.
                nom = norm(f.get("nom", "")) if f else ""
                bon_nom = bool(nom and nom == norm(a["recherche"]))
                confirmations = confirmations + 1 if bon_nom and n == avant + quantite else 0
                if confirmations >= 2:
                    a["_f"], a["_attendu"] = f, n
                    diagnostic.evenement("achat_confirme", rune=a["rune"], avant=avant, apres=n, quantite=quantite)
                    code=a.get("cle", "").split("/")[0]
                    if code and code in stock_exos.valeurs:
                        stock_exos.valeurs[code]=n
                        panneau.stock_exos=dict(stock_exos.valeurs)
                    return True
            except Exception as err:
                confirmations = 0
        diagnostic.evenement("achat_non_confirme", rune=a["rune"], avant=avant, quantite=quantite)
        log("Achat non confirme par l'inventaire : " + a["rune"] + ". Arret avant tout nouvel achat.")
        panneau.mode.set("manuel")
        panneau._mode_change()
        return False

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

    def fermer_hdv():
        # Le X du titre Inventaire ferme l'ensemble HDV/inventaire.
        # Sans X positivement reconnu, conserver le repli Echap.
        if not dofus_actif():
            return False
        image = capturer(mon)
        pt = point_fermeture_inventaire(image)
        if pt:
            log(f"Fermeture HDV : X Inventaire repere en {pt}")
            envoye = clic_point(mon["left"]+pt[0],mon["top"]+pt[1])
        else:
            envoye = touche(0x1B)
        if envoye is False:
            return False
        dernier_echap = time.monotonic()
        fin, absences, echaps = dernier_echap + 5., 0, 1
        while time.monotonic() < fin:
            if not pause_auto(.2) or not dofus_actif():
                return False
            try:
                image = capturer(mon)
                GUIDE.t_ocr = 0  # reconnaissance sur cette capture, sans ancien resultat
                ouvert = GUIDE._hdv_ouvert(image, ocr)
                if ouvert and echaps < 2 and time.monotonic() - dernier_echap >= 1:
                    if touche(0x1B) is False:
                        return False
                    echaps += 1
                    dernier_echap = time.monotonic()
                    absences = 0
                    continue
                absences = 0 if ouvert else absences + 1
                if absences >= 2:
                    GUIDE.phase, GUIDE.vu_hdv = "retour", False
                    GUIDE.fiche, GUIDE.empreinte = None, None
                    GUIDE.t_vu_hdv = GUIDE.t_vu_fiche = 0
                    diagnostic.evenement("hdv_fermeture_confirmee")
                    return True
            except Exception as err:
                absences = 0
                log(f"Verification fermeture HDV impossible : {err}")
        log("HDV encore ouvert apres Echap : arret avant le retour atelier")
        panneau.mode.set("manuel")
        panneau._mode_change()
        return False

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

    def noter_achat_incomplet(a):
        achete=ravito.get("achete",{}).get(a["rune"],0)
        demande=int(a.get("acheter") or 0)
        if achete >= demande:
            return False
        log(f"Achat incomplet : {a['rune']} {achete}/{demande} confirmees ; reste {demande-achete}")
        diagnostic.evenement("achat_incomplet",rune=a["rune"],achete=achete,demande=demande,reste=demande-achete)
        return True

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
            if a.get("verifier_stock"):
                try:
                    _, fiche_exo = lire_fiche()
                except Exception:
                    fiche_exo = None
                if not preparer_stock_exo(a, fiche_exo):
                    return False
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
                        if noter_achat_incomplet(a) and not a.pop("_lecture", False):
                            ravito["refus"][a["rune"]] = a
                        break
                else:
                    continue
                break
            # rune finie : Echap ferme la fiche, puis on repart de la barre de recherche pour la rune suivante
            fermer_fiche()
            log(f"Fiche de {a['rune']} fermee")
        if not fermer_hdv():
            return False
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

    def attendre_item_pose(apres, attendu=None):
        fin, precedent, nombre, derniere = time.monotonic()+5., None, 0, apres
        while time.monotonic() < fin:
            if not pause_auto(.05):
                return False
            try:
                lecture = boite.get(timeout=.25)
            except queue.Empty:
                continue
            if lecture is None:
                boite.put(None)
                break
            m, image, e, _, capture = lecture
            if m is not mon or capture <= derniere or time.monotonic()-capture > 2:
                continue
            derniere = capture
            lignes = (e or {}).get("lignes", {})
            jet = {s:l.get("val") for s,l in lignes.items()}
            valide = bool(lignes) and all(not l.get("rate") and isinstance(l.get("val"), (int,float))
                                          for l in lignes.values())
            if e and 'rows' in e and len(e['rows'])!=len(lignes):
                valide=False
            if attendu and any(jet.get(s) != v for s,v in attendu.items()):
                valide = False
            cle = tuple(sorted(jet.items())) if valide else None
            nombre = nombre+1 if cle is not None and cle == precedent else (1 if cle is not None else 0)
            precedent = cle
            if nombre >= 2:
                ravito['lignes_pose'] = lignes
                ravito['etat_pose'] = e
                diagnostic.evenement("item_pose_confirme", lignes=len(lignes), jet_retour_verifie=bool(attendu))
                return True
        log("Objet non confirme dans l'atelier : arret avant Ressources et reprise FM")
        return False

    def poser_item(pt, img, nom=None, idx=0, retour=False):
        # onglet Equipement ouvert : on cherche le nom de l'item dans la barre de recherche de l'inventaire (position
        # lue a l'ecran, jamais fixe), puis double clic sur la case n? idx (la 1re case apres la recherche en general)
        if nom is None:
            try:
                nom = (nom_item or "").strip()
            except NameError:
                nom = ""
        im = capturer(mon)
        b = barre_inventaire(im)
        if b is None:
            panneau.mode.set("manuel")
            panneau._mode_change()
            log("Recherche inventaire non reperee : arret avant la pose de l'objet")
            return False
        barre = (mon["left"]+b[0]+30,mon["top"]+b[1]+b[3]//2)
        if not nom or nom.startswith("("):
            panneau.mode.set("manuel")
            panneau._mode_change()
            log("Nom de l'objet inconnu : arret avant toute selection")
            return False
        idx = max(0, min(int(idx), 14))
        if not clic_point(*barre) or not pause_auto(0.2):
            return
        ctrl_a()
        taper_texte(nom)
        if not pause_auto(0.9):
            return
        im = capturer(mon)
        b = barre_inventaire(im)
        if b is None:
            panneau.mode.set("manuel")
            panneau._mode_change()
            log("Recherche inventaire perdue apres filtrage : arret avant le double clic")
            return False
        x,y = case_inventaire(b,idx)
        case = (mon["left"]+x,mon["top"]+y)
        marquer(case, f"item {nom}")
        if not clic_point(*case, True):
            return False
        pose_envoyee = time.monotonic()
        log(f"Ravitaillement auto : item {nom} cherche dans l'inventaire, double clic sur la case {idx + 1}")
        ravito.pop('lignes_pose',None)
        pose_confirmee = attendre_item_pose(pose_envoyee,
            ravito.get('jet_retour') if retour and getattr(panneau,'journal_file',None) is None else None)
        if not vider_recherche_inventaire():
            panneau.mode.set("manuel")
            panneau._mode_change()
            log("Recherche inventaire non videe par le X : arret avant reprise")
            return
        if not pose_confirmee:
            panneau.mode.set("manuel")
            panneau._mode_change()
            return False
        if getattr(panneau,'journal_file',None) is not None:
            if not verifier_candidat_pose(retour):
                return False
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
        return True
    def suite_auto(img):
        # La transition est geree avant le demarrage, depuis le journal durable.
        # Aucun compteur par nom ni indice historique ne prouve l'identite.
        return

    def nom_jeu_ui():
        # nom de l'item dans le jeu, saisi dans la page web (champ ? Nom de l'item dans le jeu ?)
        return ((getattr(SUIVI, "reglages", None) or {}).get("nom_jeu") or "").strip()

    def reel_de(nom):
        # nom dans le jeu de l'objectif enregistre ; a defaut le nom de l'objectif
        try:
            with open(os.path.join(ICI, "fm_items.json"), encoding="utf-8") as f:
                for it in json.load(f).get("items", []):
                    if it.get("nom") == nom and (it.get("nom_jeu") or "").strip():
                        return it["nom_jeu"].strip()
        except Exception:
            pass
        return nom

    def lire_nom_survol():
        return nom_jeu_ui()

    def menu_hdv_consulter(img):
        # Le titre ET l'action sont dans le gabarit, pour exclure les autres menus.
        chemin = os.path.join(ICI, "fm_reperes", "hdv_consulter.png")
        ref = cv2.imread(chemin, cv2.IMREAD_GRAYSCALE)
        if ref is None:
            return None
        gris = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        meilleur = None
        for echelle in (.8, 1., 1.25):
            gabarit = cv2.resize(ref, None, fx=echelle, fy=echelle)
            h, w = gabarit.shape
            if h > gris.shape[0] or w > gris.shape[1]:
                continue
            _, score, _, pos = cv2.minMaxLoc(cv2.matchTemplate(gris, gabarit, cv2.TM_CCOEFF_NORMED))
            if score >= .90 and (meilleur is None or score > meilleur[0]):
                meilleur = (score, (pos[0] + w // 2, pos[1] + int(.76 * h)))
        return meilleur[1] if meilleur else None

    def auto_ravitaillement(g, img):
        calque_ravitaillement(bool(g) and panneau.mode.get() == "automatique")
        menu_hdv = menu_hdv_consulter(img) if g and g[0].startswith("RAVITAILLEMENT 3/7") else None
        cle_navigation = ("menu_hdv",) if menu_hdv else (("guide", g[0]) if g else (("atelier",) if etat else None))
        resultat_navigation = confirmation_navigation.observer(cle_navigation, t_capture, time.monotonic())
        if resultat_navigation:
            diagnostic.evenement(resultat_navigation["type"], resultat=resultat_navigation)
            if resultat_navigation["type"] != "navigation_confirmee" and panneau.mode.get() == "automatique":
                panneau.mode.set("manuel")
                panneau._mode_change()
                log("Navigation non confirmee : verifie l'ecran puis F1 pour resynchroniser.")
        if confirmation.attente is not None or confirmation_navigation.attente is not None:
            return g
        SUIVI.nom_reel = nom_jeu_ui() or getattr(SUIVI, "nom_reel", "")
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
        if n <= 3:
            ravito["t_pose"] = 0
            ravito["fait"] = False
            if n == 1 and etat and etat.get("lignes") and all(not l.get("rate") for l in etat["lignes"].values()):
                ravito["jet_retour"] = {s:l["val"] for s,l in etat["lignes"].items()}
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
            cible_navigation = menu_hdv or g[1]
            if cible_navigation is None:
                return g
            if ravito.get("etape") != n:
                ravito["etape"], ravito["vu"] = n, maintenant   # laisse finir le changement de carte
            if maintenant - ravito["vu"] < (0.5 if n == 2 else 1.5) or maintenant - ravito["t"] < (1.0 if n == 2 else 2.5):
                return g
            if n == 6 and METIERS.get(GUIDE.metier) == "multi":
                if maintenant - ravito["multi"] < 30:
                    return g
                ravito["multi"] = maintenant
            if n == 7 and "pose ton item" in g[0] and maintenant - ravito.get("t_pose", 0) < 4:
                return g        # item pose et feuille Ressources cliquee : on laisse l'ecran se mettre a jour, sans retourner sur Equipement
            ravito["t"] = maintenant
            if clic_point(mon["left"] + cible_navigation[0], mon["top"] + cible_navigation[1]):
                log(f"Ravitaillement auto : etape {n}/7")
                if menu_hdv:
                    diagnostic.evenement("hdv_consulter_envoye")
                if n == 7 and "pose ton item" in g[0] and maintenant - ravito.get("t_pose", 0) > 6 and pause_auto(0.5):
                    ravito["t_pose"] = maintenant
                    posee = poser_item(g[1], img, nom_jeu_ui() or getattr(GUIDE,"nom_item","") or None, ravito.get("indice_selection",0), True)
                    ravito["t_pose"] = time.time()
                    if not posee:
                        return g
                confirmation_navigation.commencer(cle_navigation, time.monotonic())
                diagnostic.evenement("navigation_en_attente", etape=g[0])
        except Exception as err:
            log(f"ravitaillement automatique en erreur : {err}")
        return g

'''

RUNTIME_FILE = r'''
    from fm_file_atelier import empreinte, correspond, minimums, exo_protege, lecture_complete, FileIncertaine
    file_runtime = {'profil':None,'valide':None,'preuve':None,'n':0,'capture':-1.,'fermer':False,'absences':0}

    def bloquer_file(motif):
        panneau.mode.set('manuel')
        panneau._mode_change()
        SUIVI.texte,SUIVI.stop,SUIVI.t = 'FILE : '+motif,True,time.time()
        diagnostic.evenement('file_bloquee',motif=motif)
        log('FILE : '+motif)

    def actualiser_file():
        panneau.file = [t['profil']['nom'] for t in panneau.journal_file.attentes]
        # Le journal est canonique. Cette liste reste un miroir pour les anciens outils.
        from fm_fichiers import ecrire_texte
        ecrire_texte(F_FILE,json.dumps(panneau.file,ensure_ascii=False))
        panneau.rev = getattr(panneau,'rev',0)+1
        SUIVI.file = list(panneau.file)

    def charger_profil_file(profil,cle):
        automatique = panneau.mode.get()=='automatique'
        panneau.tableau_visible=False
        panneau.charger_preselection(profil)
        panneau.profil_file=profil
        panneau.profil_demarrage=profil
        if automatique:
            panneau.mode.set('automatique')
            panneau._mode_change()
        file_runtime.update(profil=cle,valide=None,preuve=None,n=0,capture=-1.)
        fin_signalee[0]=None
        stock_session[0]=None
        panneau.stock_exos={}
        _RUNES_VUES.clear()
        _ACHATS_PREC.clear()
        GUIDE.phase,GUIDE.liste,GUIDE.vu_hdv=None,[],False
        GUIDE.fiche,GUIDE.demande,GUIDE.derog=None,None,{}
        GUIDE.t_fiche,GUIDE.t_vu_fiche,GUIDE.t_vu_hdv=0.,0.,0.
        ravito.update(fait=False,achete={},etape=None,multi=0.,t_pose=0.)
        file_runtime['nouvel_exemplaire']=True
        ravito.pop('jet_retour',None)
        ravito['indice_selection']=0
        demarrage.choisir(None)
        diagnostic.evenement('file_profil_charge',tache=cle,profil=profil['nom'])

    def preparer_file(image,lecture,capture):
        j=getattr(panneau,'journal_file',None)
        if j is None or panneau.mode.get()!='automatique':
            return False
        try:
            a=j.active
            reprise=getattr(panneau,'reconciliation_file',None)
            if reprise and a:
                if confirmation.attente is not None or confirmation_navigation.attente is not None:
                    raise FileIncertaine('une action/navigation attend sa confirmation avant la reprise')
                if GUIDE.phase not in (None,'retour','sortie'):
                    raise FileIncertaine('termine ou verifie la navigation avant de reconfigurer l objet')
                if not lecture_complete(lecture):
                    message='FILE : reprise demandee ; pose le bon objet dans l atelier et attends la lecture complete du jet'
                    SUIVI.texte,SUIVI.stop,SUIVI.t=message,False,time.time()
                    if file_runtime.get('attente_reprise')!=reprise['id']:
                        log(message)
                        file_runtime['attente_reprise']=reprise['id']
                    return True
                if not 0<=time.monotonic()-capture<=2:return True
                profil_reprise=reprise['profil']
                if panneau.nom.get().strip()!=profil_reprise['nom'] or panneau.conf!=panneau._conf(profil_reprise):
                    raise FileIncertaine('selection modifiee depuis Enregistrer : enregistre le profil voulu a nouveau')
                preuve=(reprise['id'],a['id'],empreinte(lecture['lignes']))
                if capture<=file_runtime.get('reprise_capture',-1):return True
                file_runtime['reprise_capture']=capture
                file_runtime['reprise_n']=file_runtime.get('reprise_n',0)+1 if preuve==file_runtime.get('reprise_preuve') else 1
                file_runtime['reprise_preuve']=preuve
                if file_runtime['reprise_n']<2:return True
                if profil_reprise['nom']==a['profil']['nom']:
                    a=j.reconfigurer(profil_reprise,lecture['lignes'])
                else:
                    a=j.changer_objet(profil_reprise,lecture['lignes'])
                    log('FILE : ancienne tache conservee en pause ; nouvel objet confirme')
                panneau.reconciliation_file=None
                file_runtime.update(profil=None,fermer=False,absences=0,essais_fermeture=0)
                actualiser_file()
                diagnostic.evenement('file_reconfiguration_confirmee',tache=a['id'],profil=a['profil']['nom'],jet=a['jet'])
                log('FILE : profil et objet en cours reconcilies apres Enregistrer')
            elif reprise:
                panneau.reconciliation_file=None
            attentes=j.attentes
            t=a or (attentes[0] if attentes else None)
            if t and file_runtime['profil']!=t['id']:
                charger_profil_file(t['profil'],t['id'])
            if file_runtime['fermer']:
                # Le X rend l'objet a l'inventaire ; aucune rune n'est permise
                # pendant cette transition, meme si l'ancien tableau reste visible.
                securite['preparation']=True
                if lecture:
                    file_runtime['absences']=0
                    if time.monotonic()-file_runtime.get('fermeture_t',-10)<1.5:
                        return True
                    pt=point_fermeture_inventaire(image)
                    if not pt:raise FileIncertaine('X de fermeture non reconnu')
                    if file_runtime.get('essais_fermeture',0)>=3:
                        raise FileIncertaine('fermeture de l ancien atelier non confirmee')
                    if clic_point(mon['left']+pt[0],mon['top']+pt[1]):
                        file_runtime['fermeture_t']=time.monotonic()
                        file_runtime['essais_fermeture']=file_runtime.get('essais_fermeture',0)+1
                    return True
                if capture>file_runtime.get('capture_absence',-1):
                    file_runtime['capture_absence']=capture
                    file_runtime['absences']+=1
                if file_runtime['absences']<2:return True
                file_runtime.update(fermer=False,essais_fermeture=0,absences=0)
                demarrage.choisir(None)
                GUIDE.phase,GUIDE.liste,GUIDE.vu_hdv=None,[],False
                ravito.pop('jet_retour',None)
                ravito['t_pose']=0
            if not lecture or demarrage.phase!='PRET' or GUIDE.phase is not None:
                return False
            if not lecture_complete(lecture):return True
            lignes=lecture.get('lignes',{})
            profil=(a or t or {}).get('profil') or next((p for p in panneau.items if p['nom']==panneau.nom.get().strip()),None)
            if not profil:return False  # apprentissage d'un nouvel objet non enregistre
            if not correspond(profil,lignes):
                if a:raise FileIncertaine('objet ou lecture different du profil en cours')
                return True
            if a and a.get('protege') and not exo_protege(lignes):
                raise FileIncertaine('exo deja observe puis non relu : protection conservee, verification requise')
            if j.protege(lignes):
                if a:
                    if exo_protege(lignes):j.proteger(lignes)
                    # Laisser le moteur signaler la fin ; le garde d'action interdit
                    # toute rune des la premiere lecture de l'exo protege.
                    return False
                if t:
                    file_runtime.update(fermer=True,valide=None)
                    diagnostic.evenement('file_objet_protege_ecarte',exo=exo_protege(lignes))
                    return True
                bloquer_file('objet deja reussi/protege : aucune rune ne sera envoyee')
                return True
            if a and file_runtime['valide']==a['id']:
                if panneau.conf!=panneau._conf(a['profil']):
                    raise FileIncertaine('objectifs modifies : clique Enregistrer puis F1 pour verifier l objet et mettre a jour la tache')
                return False
            jet=empreinte(lignes)
            preuve=(profil['nom'],jet)
            if capture<=file_runtime['capture'] or time.monotonic()-capture>2:return True
            file_runtime['capture']=capture
            file_runtime['n']=file_runtime['n']+1 if preuve==file_runtime['preuve'] else 1
            file_runtime['preuve']=preuve
            if file_runtime['n']<2:return True
            if a:
                if a.get('action'):
                    raise FileIncertaine('action interrompue au redemarrage : reconciliation manuelle requise')
                if a.get('jet')!=jet:
                    raise FileIncertaine('jet sauvegarde non retrouve : verifie l objet, puis Enregistrer et F1 pour une reprise explicite')
            else:
                a=j.commencer(profil,lignes)
                file_runtime['profil']=a['id']
                panneau.profil_file=profil
                actualiser_file()
            file_runtime['valide']=a['id']
            diagnostic.evenement('file_objet_confirme',tache=a['id'],jet=jet)
            return False
        except Exception as err:
            bloquer_file(str(err))
            return True

    def autoriser_file():
        try:
            j=panneau.journal_file
            a=j.active
            lignes=(etat or {}).get('lignes',{})
            if not lecture_complete(etat) or file_runtime['fermer'] or j.protege(lignes) or a and a.get('protege'):
                return False
            if not a or file_runtime['valide']!=a['id'] or not correspond(a['profil'],lignes):
                return False
            if panneau.nom.get().strip()!=a['profil']['nom']:
                raise FileIncertaine('profil modifie pendant une tache en cours')
            if panneau.conf!=panneau._conf(a['profil']):
                raise FileIncertaine('objectifs differents : clique Enregistrer puis F1 pour reconcilier la tache')
            # L'intention precede le clic. Apres un crash, aucune reemission aveugle.
            j.observer(lignes,action={'stat':reco.get('stat'),'taille':reco.get('taille')})
            return True
        except Exception as err:
            bloquer_file(str(err))
            return False

    def filtrer_achats_file(achats):
        j=getattr(panneau,'journal_file',None)
        if j is None:return achats
        try:
            a=j.active
            lignes=(etat or {}).get('lignes',{})
            if a and (a.get('protege') or j.protege(lignes) or minimums(a['profil'],lignes)):
                # La reussite prime sur un seuil de stock bas. Ne pas fermer
                # l'atelier pour acheter avant de sauvegarder le resultat.
                if GUIDE.phase in (None,'sortie'):
                    GUIDE.phase,GUIDE.liste=None,[]
                return []
            return achats
        except Exception as err:
            bloquer_file('verification des achats impossible : '+str(err))
            return []

    def confirmer_fin_file(recommandation):
        try:
            j=panneau.journal_file
            a=j.active
            if not a:return False
            if panneau.nom.get().strip()!=a['profil']['nom'] or panneau.conf!=panneau._conf(a['profil']):
                raise FileIncertaine('profil de fin different de la tache')
            if time.monotonic()-t_capture>2:return False
            lignes=(etat or {}).get('lignes',{})
            if not lecture_complete(etat):return False
            if not minimums(a['profil'],lignes):
                if exo_protege(lignes):bloquer_file('exo protege, mais minimums non confirmes : verification requise')
                return False
            preuve=(a['id'],empreinte(lignes))
            if t_capture<=file_runtime.get('fin_capture',-1):return False
            file_runtime['fin_capture']=t_capture
            file_runtime['fin_n']=file_runtime.get('fin_n',0)+1 if preuve==file_runtime.get('fin_preuve') else 1
            file_runtime['fin_preuve']=preuve
            if file_runtime['fin_n']<2:return False
            identifiant=j.terminer(lignes)
            actualiser_file()
            diagnostic.evenement('file_reussite_sauvegardee',tache=identifiant,jet=preuve[1])
            if j.attentes:
                file_runtime.update(fermer=True,valide=None)
            return True
        except Exception as err:
            bloquer_file('reussite non sauvegardee : '+str(err))
            return False

    def verifier_candidat_pose(retour):
        j=panneau.journal_file
        a=j.active
        profil=(a or {}).get('profil') or getattr(panneau,'profil_file',None)
        if profil is None:
            profil=next((p for p in panneau.items if p['nom']==panneau.nom.get().strip()),None)
        lignes=ravito.get('lignes_pose',{})
        if profil and lecture_complete(ravito.get('etat_pose')) and j.candidat(profil,lignes,retour=bool(a)):
            # Exiger une nouvelle liaison sur les lectures du tableau reel.
            file_runtime.update(valide=None,preuve=None,n=0)
            return True
        idx=ravito.get('indice_selection',0)+1
        diagnostic.evenement('file_candidat_ecarte',case=idx,protege=j.protege(lignes),retour=bool(a))
        if idx>=15:
            bloquer_file('aucun exemplaire admissible dans les 15 premieres cases ; selection manuelle requise')
        else:
            ravito['indice_selection']=idx
            file_runtime.update(fermer=True,valide=None)
        return False

'''

RUNTIME_DEMARRAGE = r'''
    from fm_demarrage import DemarrageAtelier, COMMANDE, DESTINATION, metier_pour_objet, position_depuis_texte, profil_correspond, profil_incompatible, texte_confirmation_trajet, point_saisie_chat, commande_chat_lue, commande_chat_reconnue, preparer_lecture_chat
    demarrage = DemarrageAtelier()

    def message_demarrage(texte, erreur=False):
        texte = "DEMARRAGE : " + texte
        SUIVI.texte, SUIVI.stop, SUIVI.t = texte, erreur, time.time()
        if texte != getattr(demarrage,"message",None):
            log(texte)
            diagnostic.evenement("demarrage_atelier",phase=demarrage.phase,message=texte)
            demarrage.message = texte
        if erreur:
            panneau.mode.set("manuel")
            panneau._mode_change()

    def position_demarrage(image):
        h,w = image.shape[:2]
        # Lire la ligne des coordonnees seule, sans le nom de map ni le blason.
        zone = image[int(.087*h):int(.108*h),:int(.16*w)]
        texte = ocr.ligne(zone)
        position = position_depuis_texte(texte)
        if position is None:
            zone = image[int(.065*h):int(.135*h),:int(.23*w)]
            texte = " ".join(t for t,_,_ in ocr.tout(zone))
            position = position_depuis_texte(texte)
        diagnostic.evenement("position_demarrage",texte=texte,position=position)
        return position

    def popup_confirmation_trajet(image):
        h,w = image.shape[:2]
        zone = image[int(.2*h):int(.8*h),int(.25*w):int(.75*w)]
        return texte_confirmation_trajet(" ".join(t for t,_,_ in ocr.tout(zone)))

    def taper_commande_chat():
        from fm_clavier_chat import remplacer_ascii
        u = ctypes.windll.user32
        u.GetForegroundWindow.restype = wintypes.HWND
        u.GetWindowThreadProcessId.argtypes = [wintypes.HWND,ctypes.POINTER(wintypes.DWORD)]
        u.GetWindowThreadProcessId.restype = wintypes.DWORD
        u.GetKeyboardLayout.argtypes = [wintypes.DWORD]
        u.GetKeyboardLayout.restype = wintypes.HANDLE
        u.VkKeyScanExW.argtypes = [wintypes.WCHAR,wintypes.HANDLE]
        u.VkKeyScanExW.restype = wintypes.SHORT
        u.MapVirtualKeyExW.argtypes = [wintypes.UINT,wintypes.UINT,wintypes.HANDLE]
        u.MapVirtualKeyExW.restype = wintypes.UINT
        fil = u.GetWindowThreadProcessId(u.GetForegroundWindow(),None)
        disposition = u.GetKeyboardLayout(fil)
        ok = remplacer_ascii(COMMANDE,u,disposition,action_autorisee,
                             lambda:capturer(mon),time.sleep)
        if ok:
            diagnostic.action_envoyee("texte_chat_clavier",texte=COMMANDE)
        return ok

    def verifier_commande_chat():
        for _ in range(3):
            if not pause_auto(.2):
                return False
            image = capturer(mon)
            barre = point_saisie_chat(image,rectangle=True)
            if barre is None:
                continue
            x,y,w,h = barre
            champ = image[y+2:y+h-2,x+3:x+w-3]
            reconnue = commande_chat_reconnue(champ)
            if reconnue or commande_chat_lue(ocr.ligne(preparer_lecture_chat(champ))):
                diagnostic.evenement("commande_trajet_lue",commande=COMMANDE,
                                     preuve="image_exacte" if reconnue else "ocr")
                return True
            # Une seule capture locale de la saisie pour diagnostiquer un echec.
            if dofus_actif():
                cv2.imwrite(os.path.join(ICI,"fm_demarrage_saisie.png"),champ)
        return False

    def preparer_demarrage(image, lecture, capture):
        securite["preparation"] = False
        verifier_mode_clic()
        if panneau.mode.get() != "automatique":
            demarrage.mode_precedent = 'manuel'
            return False
        if getattr(demarrage,'mode_precedent',None) == 'manuel' and demarrage.phase == 'PRET' and not lecture and GUIDE.phase is None:
            demarrage.choisir(None)   # nouveau F1 hors atelier apres une session deja prete
        demarrage.mode_precedent = 'automatique'
        choix = panneau.nom.get().strip()
        demarrage.choisir(choix)
        if demarrage.phase == 'PRET':
            return False
        if demarrage.phase == 'SAISIE':
            message_demarrage("saisie du trajet interrompue ; verifie le chat puis relance l'assistant",True)
            return True
        # Une pause d'un ravitaillement deja engage garde son controleur actuel.
        if GUIDE.phase is not None and demarrage.phase == 'VERIFICATION':
            demarrage.phase = 'PRET'
            return False
        if confirmation.attente is not None or confirmation_navigation.attente is not None:
            # Le guide reutilise doit aussi recevoir les observations de confirmation.
            if demarrage.phase == 'ATELIER':
                g = GUIDE.etape(image,lecture,[],ocr)
                auto_ravitaillement(g,image)
            return True
        fiche = getattr(panneau,'profil_file',None) or next((it for it in panneau.items if it.get("nom") == choix),None)
        if not fiche:
            if lecture:               # conserver l'apprentissage habituel d'un nouvel objet deja pose
                demarrage.phase = 'PRET'
                return False
            message_demarrage("choisis une preselection enregistree dans Objectif de l'item, puis F1",True)
            return True
        nom = (getattr(panneau,"nom_jeu","") or fiche.get("nom_jeu") or '').strip()
        metier = metier_pour_objet(nom,getattr(panneau,"metier_depart",'') or fiche.get("metier_depart",''))
        maintenant = time.monotonic()
        if maintenant-capture > 2 or capture > maintenant:
            return True
        if lecture and profil_correspond(fiche,lecture.get("lignes",{})):
            if capture > getattr(demarrage,'tableau_capture',-1):
                jet = tuple(sorted((s,l.get('val')) for s,l in lecture['lignes'].items()))
                demarrage.tableau_capture = capture
                demarrage.tableaux = getattr(demarrage,'tableaux',0)+1 if jet == getattr(demarrage,'jet',None) else 1
                demarrage.jet = jet
            if demarrage.tableaux < 2:
                return True
            demarrage.phase = 'PRET'
            panneau.profil_demarrage = fiche
            stock_session[0] = None   # premiere lecture d'exos apres la pose, avant toute FM
            if GUIDE.phase == 'retour':
                GUIDE.phase,GUIDE.liste,GUIDE.vu_hdv = None,[],False
            message_demarrage("objet confirme ; verification des stocks exo puis FM")
            return False
        demarrage.tableaux = 0
        if not nom or not metier:
            message_demarrage("renseigne le nom dans le jeu et l'Atelier de depart du profil, puis enregistre",True)
            return True
        securite["preparation"] = True
        if maintenant < getattr(demarrage,'attendre_jusqua',0):
            return True
        calque_ravitaillement(True)
        if lecture:
            lignes = lecture.get('lignes',{})
            if not profil_incompatible(fiche,lignes):
                debut = getattr(demarrage,'t_lecture_incomplete',maintenant)
                demarrage.t_lecture_incomplete = debut
                message_demarrage("lecture incomplete de l'objet ; attente avant toute fermeture",maintenant-debut>5)
                return True
            signature_lue = tuple(sorted((s,l.get('min'),l.get('max')) for s,l in lignes.items()))
            if capture > getattr(demarrage,'capture_incompatible',-1):
                demarrage.capture_incompatible = capture
                demarrage.incompatibles = getattr(demarrage,'incompatibles',0)+1 if signature_lue == getattr(demarrage,'signature_incompatible',None) else 1
                demarrage.signature_incompatible = signature_lue
            if demarrage.incompatibles < 2:
                return True
            # Objet different : le fermer le rend a l'inventaire, sans tenter de rune.
            pt = point_fermeture_inventaire(image)
            if not pt:
                message_demarrage("objet different dans l'atelier et fermeture non reconnue",True)
                return True
            if clic_point(mon['left']+pt[0],mon['top']+pt[1]):
                demarrage.attendre_jusqua = time.monotonic()+1.5
                message_demarrage("objet different rendu a l'inventaire avant preparation")
            return True
        if demarrage.phase == 'ATELIER':
            if maintenant-getattr(demarrage,'t_atelier',maintenant)>120:
                message_demarrage("atelier non prepare apres deux minutes ; verifie les reperes et l'objet",True)
                return True
            GUIDE.metier = metier
            GUIDE.nom_item = nom
            GUIDE.phase = 'retour'
            # Le nom vient du profil selectionne, pas d'un ancien item lu.
            SUIVI.nom_reel = nom
            panneau.conf = panneau._conf(fiche)
            ravito.pop('jet_retour',None)
            g = GUIDE.etape(image,None,[],ocr)
            if METIERS.get(metier) == 'multi' and not barre_inventaire(image):
                # Le menu de l'etabli commun exige un choix de metier apres le clic decor.
                choix_menu = trouver_texte(image,metier)
                if choix_menu and maintenant-getattr(demarrage,'t_menu',0)>2:
                    if clic_point(mon['left']+choix_menu[0],mon['top']+choix_menu[1]):
                        demarrage.t_menu = maintenant
                        demarrage.attendre_jusqua = time.monotonic()+1.5
                    return True
            message_demarrage("entree et preparation de " + nom)
            auto_ravitaillement(g,image)
            return True
        if maintenant-getattr(demarrage,'t_position',-10) < 1:
            return True
        demarrage.t_position = maintenant
        # La lecture du tableau en arriere-plan et celle du popup peuvent dater
        # l'image initiale. Les deux confirmations portent sur de vraies captures
        # prises ici, jamais sur un ancien ecran rebaptise avec une date recente.
        capture_position = time.monotonic()
        image_position = capturer(mon)
        position = position_demarrage(image_position)
        if demarrage.observer_position(position,capture_position,time.monotonic()):
            demarrage.t_atelier = time.monotonic()
            message_demarrage("arrivee -83,-40 confirmee ; entree dans l'atelier")
            return True
        if demarrage.phase == 'TRAJET':
            if not getattr(demarrage,'popup_confirme',False):
                popup = capturer(mon)
                if popup_confirmation_trajet(popup):
                    capturer(mon)   # relecture OCR terminee : fraicheur reelle avant la touche
                    if touche(0x0D,.06):
                        demarrage.popup_confirme = True
                        message_demarrage("popup de voyage reconnu ; confirmation Entree envoyee")
                    return True
            message_demarrage("trajet vers -83,-40 ; attente de l'arrivee confirmee")
            if demarrage.expire(maintenant):
                message_demarrage("arrivee non confirmee apres 15 minutes ; verifie le trajet",True)
            return True
        # Une premiere lecture a destination doit etre confirmee, sans commande de trajet inutile.
        if position == DESTINATION:
            message_demarrage("verification de la position -83,-40")
            return True
        pt = point_fermeture_inventaire(image)
        if pt:                       # atelier vide, HDV, inventaire : fermer avant de saisir /travel
            if clic_point(mon['left']+pt[0],mon['top']+pt[1]):
                demarrage.attendre_jusqua = time.monotonic()+1.5
            return True
        if GUIDE.dedans(image):       # autre interieur : utiliser sa sortie uniquement si reconnue
            sortie = GUIDE._point(image,'sortie')
            if not sortie:
                message_demarrage("interieur inconnu ; sortie non reconnue",True)
                return True
            if clic_point(mon['left']+sortie[0],mon['top']+sortie[1]):
                demarrage.attendre_jusqua = time.monotonic()+2.
            return True
        if position is None:
            demarrage.positions_vides = getattr(demarrage,'positions_vides',0)+1
            message_demarrage("coordonnees de la map illisibles ; aucune commande envoyee",demarrage.positions_vides>=3)
            return True
        demarrage.positions_vides = 0
        demarrage.phase = 'SAISIE'
        # Raccourci Dofus valide par l'utilisateur : Espace ouvre la saisie du chat.
        # L'OCR des coordonnees peut avoir vieilli la capture ; en reprendre une vraie.
        capturer(mon)
        if not taper_commande_chat():
            message_demarrage("saisie clavier interrompue ; aucune commande validee",True)
            return True
        if not verifier_commande_chat():
            message_demarrage("/travel absent ou illisible dans la saisie du chat ; Entree non envoyee",True)
            return True
        capturer(mon)
        if not touche(0x0D,.06):
            return True
        demarrage.trajet_envoye(time.monotonic())
        message_demarrage(COMMANDE + " envoye ; popup facultatif, attente de l'arrivee")
        return True
'''

RAVITO_HOOK = (
    "                if g:\n"
    "                    diagnostic.decision({\"texte\": g[0], \"guide\": True, \"phase\": GUIDE.phase}, etat, panneau.mode.get(), 0.)\n"
    "                g = auto_ravitaillement(g, bgr)\n"
)

RUNTIME_EXO = r'''
    # FM_CLICK_PATCH:EXO_RUNTIME
    def placer_souris_haut_gauche():
        if not windows or not action_autorisee():
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
            cv2.imwrite(os.path.join(d, f"{time.strftime('%Y%m%d_%H%M%S')}_{ravito['n_clic']:03d}_{quoi}.jpg"), img,
                        [cv2.IMWRITE_JPEG_QUALITY, 70])
            vieux = sorted(os.listdir(d), key=lambda n: os.path.getmtime(os.path.join(d, n)))[:-80]
            for v in vieux:
                os.remove(os.path.join(d, v))
            log(f"clic {quoi} en ({px},{py}) : capture fm_debug_clics")
        except Exception as err:
            log(f"capture de debug impossible : {err}")

    def clic_point(x, y, double=False):
        if not action_autorisee():
            return False
        user32 = ctypes.windll.user32
        if not user32.SetCursorPos(x, y):
            log(f"clic automatique impossible : {ctypes.WinError()}")
            return False
        position_souris_ref[0] = (x, y)
        for _ in range(2 if double else 1):
            if not action_autorisee():
                return False
            user32.mouse_event(0x0002, 0, 0, 0, 0)
            time.sleep(0.04)
            user32.mouse_event(0x0004, 0, 0, 0, 0)
            time.sleep(0.06)
        diagnostic.action_envoyee("double_clic" if double else "clic", x=x, y=y)
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
        # bouton Fusionner : petit rectangle vert dans la zone de l'atelier
        m = cv2.inRange(img, np.array([0, 120, 90], np.uint8), np.array([70, 230, 200], np.uint8))
        m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
        n, _, st, _ = cv2.connectedComponentsWithStats(m, connectivity=8)
        meilleur = None
        for i in range(1, n):
            x, y, w, h, aire = (int(v) for v in st[i])
            if 80 <= w <= .12 * img.shape[1] and 22 <= h <= .06 * img.shape[0] \
                    and y < .6 * img.shape[0] and 2 <= w / h <= 10 and aire > .6 * w * h:
                if meilleur is None or aire < meilleur[0]:
                    meilleur = (aire, x + w // 2, y + h // 2)
        return (meilleur[1], meilleur[2]) if meilleur else None

    def tenter_exo(gab, ou):
        if not action_autorisee(fm=True):
            return False
        # double clic sur la rune de l'inventaire, puis clic sur le bouton Fusionner
        x = mon["left"] + ou[0] + gab.shape[1] // 2
        y = mon["top"] + ou[1] + gab.shape[0] // 2
        if not clic_point(x, y, double=True):
            return False
        from fm_confirmation import revalider_fusion
        selection = time.monotonic()
        fin = selection + 4.
        profil_selection = panneau.nom.get().strip()
        while time.monotonic() < fin:
            verifier_mode_clic()
            if panneau.mode.get() != "automatique" or not dofus_actif():
                return False
            try:
                recu_exo = boite.get(timeout=.25)
            except queue.Empty:
                continue
            if recu_exo is None:
                boite.put(None)
                return False
            mon_exo, img, etat_exo, _, capture_exo = recu_exo
            if mon_exo is not mon or panneau.nom.get().strip() != profil_selection:
                return False
            if not revalider_fusion(etat, etat_exo, capture_exo, time.monotonic(), selection):
                continue
            # Le bouton peut encore etre gris sur la premiere capture.
            # Attendre le vert sur une nouvelle lecture plutot que lancer
            # un OCR bloquant qui perime la capture avant le clic.
            pos = trouver_bouton_vert(img)
            if pos:
                # Horodatage de la lecture effectivement validee, pas celui
                # d'une capture sans analyse. Les autres protections restent actives.
                securite["lecture"] = securite["capture"] = capture_exo
                if not action_autorisee(fm=True):
                    return False
                diagnostic.evenement("fusion_revalidee", capture_t=capture_exo)
                return clic_point(mon["left"] + pos[0], mon["top"] + pos[1])
        log("Bouton Fusionner introuvable apres le double clic")
        return False

'''

EXO_HOOK = r'''                                # FM_CLICK_PATCH:EXO_HOOK
                                verifier_mode_clic()
                                cle_exo = (tuple(sorted(sig_item)), resume(etat), reco.get("stat"), "exo")
                                if panneau.mode.get() == "automatique" and not reco.get("stop") and n_vu >= 2 \
                                        and confirmation.attente is None:
                                    dernier_clic, t_clic = cle_exo, time.time()
                                    if tenter_exo(gab, ou):
                                        debut_confirmation()
                                        t_clic = time.time()
                                        log(f"Exo tente : {reco['texte']}")
                                    else:
                                        panneau.mode.set("manuel")
                                        panneau._mode_change()
                                        diagnostic.evenement("exo_non_envoye", motif="selection ou fusion non confirmee")
                                        log("Exo interrompu : selection ou fusion non confirmee. Verifie puis F1.")
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
        if "# FM_CLICK_PATCH:SECURITE_V1" not in source:
            raise ValueError("Ancien patch : regenerer depuis assistant_sans_clic.py.")
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
        "        self.items = [it for it in self.items if it[\"nom\"] != nom]\n",
        "        # FM_CLICK_PATCH:MODE_SAVE\n"
        "        fiche[\"mode\"] = self.mode.get()\n"
        "        self.items = [it for it in self.items if it[\"nom\"] != nom]\n",
        "enregistrement du mode",
    )

    runtime = (
        RUNTIME_SECURITE + RUNTIME_ECRAN + "    # FM_CLICK_PATCH:CLICK_RUNTIME\n"
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
        "        if not action_autorisee(fm=True):\n"
        "            return False\n"
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
        "        diagnostic.action_envoyee(\"rune\", stat=reco.get(\"stat\"), taille=reco.get(\"taille\"), x=x, y=y)\n"
        "        debut_confirmation()\n"
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
        "        if f1_neuf and not dofus_actif():\n"
        "            log(\"F1 refuse : la fenetre active n'appartient pas a Dofus (ou verification impossible).\")\n"
        "            return\n"
        "        if f1_neuf and dofus_actif():\n"
        "            if not cibler_ecran_dofus():\n"
        "                return\n"
        "            if panneau.mode.get() != \"automatique\" and confirmation_navigation.attente is not None:\n"
        "                confirmation_navigation.abandonner()\n"
        "                diagnostic.evenement(\"navigation_resynchronisee_manuellement\")\n"
        "            if panneau.mode.get() != \"automatique\" and confirmation.attente is not None:\n"
        "                ancienne = confirmation.abandonner()\n"
        "                diagnostic.evenement(\"action_resynchronisee_manuellement\", id_confirmation=ancienne[\"id\"])\n"
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
        "        if not dofus_actif():\n"
        "            panneau.mode.set(\"manuel\")\n"
        "            panneau._mode_change()\n"
        "            mode_suivi[0] = \"manuel\"\n"
        "            log(\"Mode manuel active : Dofus n'est plus au premier plan.\")\n"
        "            return\n"
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
    ) + RUNTIME_EXO + RUNTIME_RAVITO + RUNTIME_DEMARRAGE + RUNTIME_FILE
    source = replace_once(
        source,
        "                g = GUIDE.etape(bgr, etat, achats, ocr, regl_stock)\n",
        "                if verifier_stock_exos():\n"
        "                    continue\n"
        "                achats = filtrer_achats_file(achats)\n"
        "                calque_ravitaillement(panneau.mode.get() == \"automatique\" and (GUIDE.phase is not None or bool(achats)))\n"
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
        "                if nom_jeu_ui() and nom_jeu_ui() != getattr(SUIVI, \"nom_reel\", \"\"):\n"
        "                    SUIVI.nom_reel = nom_jeu_ui()\n"
        "                    nom_item = SUIVI.nom_reel\n"
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
        "                        if panneau.mode.get() == \"automatique\" and not reco.get(\"stop\") and n_vu >= 2 \\\n"
        "                                and confirmation.attente is None:\n"
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
        ,
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
        "            self.evenement(\"fini\", \"Objectif atteint sur \" + (item or \"l'item\"), 600)\n",
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
        "<div id=q></div><img id=i alt=\"\">",
        "<div id=q></div><div id=s></div><img id=i alt=\"\">",
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
    source = replace_once(source,
        '            panneau.image, panneau.ecran = bgr,',
        '            if t_capture <= securite.get("reprise_apres", 0):\n'
        '                continue\n'
        '            securite["capture"] = securite["lecture"] = t_capture\n'
        '            observer_confirmation(etat, t_capture)\n'
        '            panneau.image, panneau.ecran = bgr,',
        "fraicheur de la lecture")
    source = replace_once(source,
        '                    return np.ascontiguousarray(np.array(sct.grab(m))[:, :, :3])\n',
        '                    t_capture = time.monotonic()\n'
        '                    image = np.ascontiguousarray(np.array(sct.grab(m))[:, :, :3])\n'
        '                    securite["capture"] = t_capture\n'
        '                    return image\n',
        "fraicheur des captures de navigation")
    source = replace_once(source,
        '            return cv2.cvtColor(np.array(ImageGrab.grab()), cv2.COLOR_RGB2BGR)\n',
        '            t_capture = time.monotonic()\n'
        '            image = cv2.cvtColor(np.array(ImageGrab.grab()), cv2.COLOR_RGB2BGR)\n'
        '            securite["capture"] = t_capture\n'
        '            return image\n',
        "fraicheur des captures PIL")
    source = replace_once(source,
        '                    diagnostic.decision(reco, etat, mode_diag, duree_decision_ms)\n',
        '                    diagnostic.decision(reco, etat, mode_diag, duree_decision_ms)\n'
        '                    signaler_objectif_confirme(reco)\n',
        "fin validee avant passage de la file")
    source = replace_once(source,
        '                # --- meme item ou nouvel item ?\n',
        '                if file_runtime.pop("nouvel_exemplaire",False):\n'
        '                    sig_item,n_autre,memo,stable,dernier_rel = set(),2,{},None,None\n'
        '                    vu,n_vu = None,0\n'
        '                    phase_remise.reinitialiser()\n'
        '                    vu_rune.clear()\n'
        '                # --- meme item ou nouvel item ?\n',
        "nouvel exemplaire meme signature sans reutiliser la derniere passe")
    source = replace_once(source,
        '            cv.delete("all")\n',
        '            cv.delete("all")\n'
        '            if preparer_file(bgr, etat, t_capture):\n'
        '                root.update()\n'
        '                continue\n'
        '            if preparer_demarrage(bgr, etat, t_capture):\n'
        '                root.update()\n'
        '                continue\n',
        "preparation de l'atelier avant toute FM")
    return source, True

SORTIE = "fm_avec_clics.py"
SOURCE_DEFAUT = "assistant_sans_clic.py"


def choisir_source(dossier, source=None):
    """Source stable ; un chemin explicite reste relatif au repertoire courant."""
    return Path(source).resolve() if source else dossier / SOURCE_DEFAUT


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", nargs="?", help=f"script source (par defaut : {SOURCE_DEFAUT})")
    args = parser.parse_args()
    dossier = Path(__file__).resolve().parent
    source = choisir_source(dossier, args.source)
    if not source.is_file():
        print(f"ERREUR : source introuvable : {source}", file=sys.stderr)
        return 1

    try:
        updated, _ = patch(source.read_text(encoding="utf-8"))
        compile(updated, SORTIE, "exec")
    except (OSError, SyntaxError, ValueError) as error:
        print(f"ERREUR avec {source.name} : {error}", file=sys.stderr)
        print("Le code de cette version a chang? : le patch doit ?tre mis ? jour.", file=sys.stderr)
        return 1

    try:
        ecrire_texte(dossier / SORTIE, updated)
    except OSError as error:
        print(f"ERREUR d'ecriture de {SORTIE} : {error}", file=sys.stderr)
        return 1
    print(f"Version utilis?e : {source.name} -> {SORTIE} (clics ajout?s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
