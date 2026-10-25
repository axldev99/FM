#!/usr/bin/env python3
"""Assistant de forgemagie Dofus en direct : lit l'ecran, encadre la rune a cliquer.

Il ne touche ni a la souris ni au clavier ni au jeu : il regarde l'ecran et dessine par-dessus.

Installation (Windows) :
    pip install mss opencv-python numpy rapidocr-onnxruntime
    (si rapidocr-onnxruntime refuse de s'installer : pip install rapidocr onnxruntime)

Lancer :
    python fm_live.py                 # en direct, jeu en mode fenetre ou fenetre sans bordure
    python fm_live.py --ecran 2       # force un moniteur (par defaut : cherche sur tous)
    python fm_live.py --image cap.png # teste la lecture sur une capture (ecrit cap_debug.png)
    python fm_live.py --codes         # liste les codes de stats pour fm_cibles.json

Objectifs : quand un item inconnu est pose, la fenetre "FM - objectif" demande quoi viser
    (objectif par ligne, exos). C'est enregistre dans fm_items.json et recharge tout seul la
    prochaine fois que le meme type d'item est pose ; le menu Preselection reapplique un objectif.
    Objectif sous le max = ligne sacrifiable ; au-dessus du max = over (plafond : poids 101).
"""
import argparse
import difflib
import hashlib
import json
import os
import random
import re
import queue
import sys
import threading
import time
import unicodedata

import cv2
import numpy as np

try:
    import tkinter as tk
    from tkinter import ttk
except ImportError:          # mode --image sans interface
    tk = ttk = None

ICI = os.path.dirname(os.path.abspath(__file__))
F_HISTO = os.path.join(ICI, "fm_historique.json")
F_NOMS = os.path.join(ICI, "fm_noms_v2.npz")
F_ITEMS = os.path.join(ICI, "fm_items.json")
F_PASSES = os.path.join(ICI, "fm_passes.csv")

# ---------------------------------------------------------------- regles
ELEMS = ["neutre", "terre", "feu", "eau", "air"]
POIDS = {"ini": 0.1, "vi": 0.2, "pods": 0.25, "fo": 1, "int": 1, "cha": 1, "agi": 1,
         "pui": 2, "re_cri": 2, "re_pou": 2, "sa": 3, "pp": 3, "tacle": 4, "fuite": 4,
         "do_cri": 5, "do_pou": 5, "ret_pa": 7, "ret_pm": 7, "esq_pa": 7, "esq_pm": 7,
         "cri": 10, "soin": 10, "do_per_so": 15, "do_per_ar": 15, "do_per_di": 15,
         "do_per_me": 15, "do": 20, "invo": 30, "po": 51, "pm": 90, "pa": 100}
for _e in ELEMS:
    POIDS["re_" + _e], POIDS["do_" + _e], POIDS["re_per_" + _e] = 2, 5, 6
POIDS.update({"do_pieges": 5, "pui_pieges": 2, "renvoi": 10, "re_per_me": 15, "re_per_di": 15})
UNITE = {"vi": 5, "ini": 10, "pods": 10}          # gain de la rune de base
MULT = {"base": 1, "pa": 3, "ra": 10}
# Tailles de runes qui existent dans le jeu, par stat (tout le reste : rune normale seulement)
_EL = ("neutre", "terre", "feu", "eau", "air")
AVEC_RA = {"vi", "ini", "pods", "fo", "int", "cha", "agi", "sa", "pui", "pui_pieges", "do_pou", "re_pou"} | \
          {"re_" + e for e in _EL}
AVEC_PA = AVEC_RA | {"pp", "tacle", "fuite", "do_cri", "do_pieges", "re_cri", "re_pou",
                     "ret_pa", "ret_pm", "esq_pa", "esq_pm"} | {"do_" + e for e in _EL}


def tailles(s):
    return ["base", "pa", "ra"] if s in AVEC_RA else ["base", "pa"] if s in AVEC_PA else ["base"]
SEUIL_HORS_PALIER = .5                            # chance de passer (SC + SN) exigee d'une Pa hors palier
OVER_TAMPON = 20                                  # poids d'over au-dela duquel une grosse rune passe mal
SEUIL_PUITS = 10                                  # reliquat a partir duquel on FM « avec puits »
SEUIL_ATTENTE = .30                               # sous cette chance de reussite, on prefere attendre
SEUIL_RA = 60                                     # Fo/Int/Cha/Agi : au-dela de 60, seules les Ra passent bien
CARBU_BAS, CARBU_HAUT = .20, .50                  # ligne jetable : on la remonte a partir de 20 % du max, jusqu'a 50 %
_CYCLE = [False]                                  # True = on remonte le jet jusqu'a « Remonter a »
_EN_REMONTEE = set()                              # lignes jetables en cours de remontee
LOURD = 20                                        # poids par point : Dommages, Invocation, PO, PM, PA
PLAFOND = 101                                     # poids maximal d'une ligne (505 vita, 101 intel...)
# A priori [SC, SN, EC] par situation, corriges ensuite par tes propres passes (fm_historique.json)


NOMS = {"vitalite": "vi", "initiative": "ini", "pods": "pods", "force": "fo",
        "intelligence": "int", "chance": "cha", "agilite": "agi", "sagesse": "sa",
        "prospection": "pp", "puissance": "pui", "tacle": "tacle", "fuite": "fuite",
        "critique": "cri", "soins": "soin", "soin": "soin", "dommages": "do",
        "dommage": "do", "invocations": "invo", "invocation": "invo", "portee": "po",
        "pa": "pa", "pm": "pm", "retraitpa": "ret_pa", "retraitpm": "ret_pm",
        "esquivepa": "esq_pa", "esquivepm": "esq_pm",
        "dommagescritiques": "do_cri", "dommagespoussee": "do_pou",
        "resistancecritiques": "re_cri", "resistancescritiques": "re_cri",
        "resistancepoussee": "re_pou", "resistancespoussee": "re_pou",
        "dommagesauxsorts": "do_per_so", "dommagessorts": "do_per_so",
        "dommagesdarmes": "do_per_ar", "dommagesauxarmes": "do_per_ar",
        "dommagesdistance": "do_per_di", "dommagesadistance": "do_per_di",
        "dommagesmelee": "do_per_me", "dommagesdemelee": "do_per_me"}
NOMS.update({"dommagespieges": "do_pieges", "dommagesauxpieges": "do_pieges",
             "puissancepieges": "pui_pieges", "puissancedespieges": "pui_pieges",
             "renvoiedommages": "renvoi", "dommagesrenvoyes": "renvoi", "renvoidedommages": "renvoi",
             "resistancemelee": "re_per_me", "resistancedistance": "re_per_di",
             "resistanceamelee": "re_per_me", "resistanceadistance": "re_per_di"})
for _e in ELEMS:
    NOMS["dommages" + _e] = "do_" + _e
    NOMS["resistances" + _e] = NOMS["resistance" + _e] = "re_" + _e


NOM_PROPRE = {"vi": "Vitalité", "ini": "Initiative", "fo": "Force", "int": "Intelligence",
              "cha": "Chance", "agi": "Agilité", "sa": "Sagesse", "pp": "Prospection",
              "pui": "Puissance", "cri": "Critique", "invo": "Invocation", "po": "Portée",
              "ret_pa": "Retrait PA", "ret_pm": "Retrait PM", "do_per_so": "Do % sorts"}


def norm(s):
    s = unicodedata.normalize("NFD", s.lower())
    return re.sub(r"[^a-z]", "", s)


_BULLE = re.compile(r"quantit|prix|moyen|cet+e|rune|augment")


def code_stat(nom, pct):
    n = norm(nom)
    code = NOMS.get(n)
    if not code:
        # une infobulle du jeu collee au nom ("SagesseQUANTITE", "Puissance Cette rune augmente...")
        m = _BULLE.search(n)
        if m and m.start() >= 2:
            n = n[:m.start()]
            code = NOMS.get(n)
    if not code:
        proches = difflib.get_close_matches(n, list(NOMS), n=6, cutoff=0.8)
        if proches:
            r0 = difflib.SequenceMatcher(None, n, proches[0]).ratio()
            # « Résistance » tout court est aussi proche de Feu que d'Eau ou d'Air : nom incomplet, on ne
            # devine pas (sinon la ligne Eau devient une 2e ligne Feu)
            ambigu = any(NOMS[p_] != NOMS[proches[0]] and difflib.SequenceMatcher(None, n, p_).ratio() >= r0 - .04
                         for p_ in proches[1:])
            code = None if ambigu else NOMS[proches[0]]
    if code and pct and code.startswith("re_") and code[3:] in ELEMS:
        code = "re_per_" + code[3:]
    return code


def qte(s, t):
    return UNITE.get(s, 1) * MULT[t]


def pds(s, q):
    return POIDS.get(s, 1) * q


def plafond(s, maxi=0):
    """Valeur maximale d'une ligne : poids 101, sauf si son max naturel est deja plus haut."""
    return max(maxi, int(PLAFOND / POIDS.get(s, 1) + 1e-9))


def grosse(s, t):
    """La plus grosse rune qui existe pour cette stat (Ra Agilite, mais Pa Dommages Feu)."""
    return t != "base" and t == tailles(s)[-1]


CARAC = ("fo", "int", "cha", "agi")


def palier(s, t):
    """Valeur de ligne jusqu'ou une taille de rune reste efficace : 20 fois son effet.
    Rune normale : 20 (100 vita) ; Pa : 60 (300 vita) ; Ra : 200 (1000 vita), c'est-a-dire toujours."""
    return 20 * qte(s, t)


def contexte(s, t, l):
    """Situation d'une passe, cle de l'apprentissage : taille de la rune, position de la ligne par rapport
    au palier de cette rune (0 : moins de la moitie ... 4 : plus de 120 %), et 'f' si la rune fait franchir
    le max de la ligne, 'o' si la ligne est deja au max ou au-dessus."""
    if l["max"] < 0 or l.get("min", 0) < 0:
        return "malus"                     # ligne negative : appris a part, ne se melange pas aux exos
    if l["max"] <= 0:
        # exo : au-dela de 20 de puits pour la rune, ou de 30 de puits cumules sur la ligne (2e % do sorts),
        # il n'y a plus de succes neutre et 1 % de critique
        return "exo+" if pds(s, qte(s, t)) > 20 or pds(s, l["val"] + qte(s, t)) >= 30 else "exo"
    if pds(s, l["val"] + qte(s, t) - l["max"]) > 20:
        return "over+"                     # over de plus de 20 de puits (ex. +100 vita) : meme regle
    r = max(l["val"], 0) / palier(s, t)
    n = 0 if r < .5 else 1 if r < .8 else 2 if r < 1 else 3 if r < 1.2 else 4
    suite = "o" if l["val"] >= l["max"] else "f" if l["val"] + qte(s, t) > l["max"] else ""
    return f"{t[0]}{n}{suite}"


def libelle_contexte(ctx):
    if ctx in ("exo", "exo+", "over+", "malus"):
        return {"exo": "exo léger", "exo+": "exo à 1 % (plus de 20 de puits)", "malus": "ligne négative",
                "over+": "over à 1 % (plus de 20 de puits)"}[ctx]
    base = ("sous 50 %", "à 50-80 %", "à 80-100 %", "à 100-120 %", "au-delà de 120 %")[int(ctx[1])] \
        + " du palier de la rune"
    return base + (", déjà en over" if ctx.endswith("o") else ", franchit le max" if ctx.endswith("f") else "")


# Reussite de depart (SC + SN) selon la position dans le palier.  Points de depart seulement : chaque passe
# observee les corrige.  Au-dela de son palier une rune ne passe presque plus (Pa Vi a 360 : jamais).
_DEPART = [.90, .85, .70, .35, .10]
_CONFIANCE = 12          # poids du point de depart, en nombre de passes
POIDS_PERTE = .5         # importance des pertes face au gain dans le choix de la rune
K_STAT = 40              # poids des taux de la situation face a ceux de la stat (en passes)


def probas(histo, s, t, l):
    """([SC, SN, EC], nombre de passes observees) pour cette rune dans cette situation."""
    ctx = contexte(s, t, l)
    if ctx in ("exo+", "over+"):
        h = histo.get(ctx, [0, 0, 0])
        c = [.01 * 100 + h[0], 0.0, .99 * 100 + h[1] + h[2]]
        return [x / sum(c) for x in c], sum(h)
    if ctx == "malus":
        ok, part_sc = .8, .6                # demi-poids : estimation de depart, corrigee par les passes
    elif ctx == "exo":
        ok, part_sc = .15, .33              # premier exo leger (1er % do sorts) : environ 15 %
    else:
        n = int(ctx[1])
        ok = _DEPART[n] * (.35 if ctx.endswith("o") else .45 if ctx.endswith("f") else 1)
        part_sc = .45 if n < 3 else .3
    depart = [ok * part_sc * _CONFIANCE, ok * (1 - part_sc) * _CONFIANCE, (1 - ok) * _CONFIANCE]
    h = histo.get(ctx, [0, 0, 0])
    c = [a + b for a, b in zip(depart, h)]
    p = [x / sum(c) for x in c]
    # Chaque stat a ses propres taux dans une meme situation (tes passes : Pa Do critiques 44 % d'echecs
    # critiques, Pa Agilite 7 %). On part des taux de la situation et on les corrige par ceux de la stat.
    hs = histo.get(s + "|" + ctx)
    if hs and sum(hs):
        p = [(a + K_STAT * b) / (sum(hs) + K_STAT) for a, b in zip(hs, p)]
    return p, sum(h)


def histo_depuis_passes():
    """Reconstruit l'apprentissage a partir de fm_passes.csv (toutes les passes observees)."""
    histo = {}
    try:
        with open(F_PASSES, encoding="utf-8") as f:
            for ligne in list(f)[1:]:
                c = ligne.rstrip("\n").split(";")
                if len(c) < 8 or c[2] not in POIDS or c[3] not in MULT or c[7] not in ("SC", "SN", "EC"):
                    continue
                try:
                    l = {"val": int(c[5]), "max": int(c[6])}
                except ValueError:
                    continue
                ctx_ = contexte(c[2], c[3], l)
                i_ = ("SC", "SN", "EC").index(c[7])
                histo.setdefault(ctx_, [0, 0, 0])[i_] += 1
                histo.setdefault(c[2] + "|" + ctx_, [0, 0, 0])[i_] += 1     # la meme situation, pour cette stat
    except OSError:
        pass
    return histo


_ALGO = {"mtime": None, "vu": 0.0, "fn": None}


def recommander_live(etat, conf, histo):
    """recommander(), recharge a chaud : quand assistant_sans_clic.py change sur le disque (correctif deploye),
    la nouvelle logique de conseil est prise au prochain conseil, sans relancer l'assistant. Seule la logique
    de conseil est rechargee (pas la lecture d'ecran ni la fenetre). Si le nouveau fichier plante au
    chargement, on garde l'ancienne version."""
    import importlib.util
    maintenant = time.time()
    if maintenant - _ALGO["vu"] > 2:
        _ALGO["vu"] = maintenant
        try:
            mt = os.path.getmtime(__file__)
            if _ALGO["mtime"] is None:
                _ALGO["mtime"] = mt
            elif mt != _ALGO["mtime"]:
                _ALGO["mtime"] = mt
                spec = importlib.util.spec_from_file_location("fm_algo_live", __file__)
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                # memes etats partages : runes apprises, cycle de remontee, carburant en cours
                mod.RUNES_APPRISES, mod._CYCLE, mod._EN_REMONTEE = RUNES_APPRISES, _CYCLE, _EN_REMONTEE
                _ALGO["fn"] = mod.recommander
                log("Logique de conseil rechargée (nouvelle version du fichier)")
        except Exception as e:
            log(f"Rechargement de la logique impossible, on garde l'ancienne : {e!r}"[:300])
    fn = _ALGO["fn"] or recommander
    try:
        return fn(etat, conf, histo)
    except Exception as e:
        if fn is recommander:
            raise
        log(f"Nouvelle logique en erreur, retour a l'ancienne : {e!r}"[:300])
        return recommander(etat, conf, histo)


def recommander(etat, conf, histo):
    """Retourne {stat, taille, texte} ou {texte} seulement."""
    finition = conf.get("finition")
    naturelles = etat["lignes"]
    # Option explicite, seulement sur un jet naturel sans exo/over demande ou pose.
    if finition not in naturelles or naturelles[finition]["max"] <= 0 \
            or any(c > 0 for c in conf.get("exos", {}).values()) \
            or any(c > naturelles.get(s, {}).get("max", 0) for s, c in conf.get("cibles", {}).items()):
        finition = None
    L = {}
    for s, l in etat["lignes"].items():
        if l["max"] < 0 or l["val"] < 0 and l["max"] == 0:
            continue                                   # malus : on n'y touche pas
        L[s] = dict(l, cible=min(conf.get("cibles", {}).get(s, l["max"]), plafond(s, l["max"])))
    for s, c in conf.get("exos", {}).items():
        if c <= 0 or s not in POIDS:
            continue
        if s in L:
            L[s]["cible"] = min(plafond(s, L[s]["max"]), max(c, L[s]["cible"]) if L[s]["max"] else c)
            if L[s]["max"] <= 0 and not L[s]["dispo"]:
                L[s].update(dispo=["base"], virtuel=True)        # rune a prendre dans l'inventaire
        else:
            L[s] = {"nom": nom_code(s), "min": 0, "max": 0, "val": 0, "cible": min(c, plafond(s)),
                    "dispo": ["base"], "virtuel": True}
    rel = etat["reliquat"] or 0.0
    # Insister seulement apres une remise decidee d'Invo/PA/PM/PO.
    remise = conf.get("_remise_lourde")
    if remise in ("invo", "pa", "pm", "po"):
        if remise not in L:
            return {"texte": f"ATTENDS : {nom_code(remise)} non relu pendant sa remise", "stop": True}
        l = L[remise]
        if l["max"] > 0 and l["val"] < min(l["cible"], l["max"]):
            if "base" not in l["dispo"]:
                return {"texte": f"A ACHETER : {nom_rune(remise, 'base')} (remise de la ligne en cours)"}
            (psc, psn, _), _n = probas(histo, remise, "base", l)
            return {"stat": remise, "taille": "base", "virtuel": False,
                    "texte": f"REMETS {nom_rune(remise, 'base')} +{qte(remise, 'base')}"
                             f"   SC {psc:.0%} SN {psn:.0%}   | remise engagee : insister avant toute autre ligne"}
    # Item a puits (gros reliquat, souvent apres des essais d'exo) ou item sans puits : deux facons de FM.
    #  - avec puits : le reliquat paie les echecs. On remplit au plus juste, toutes tailles de rune, les
    #    lignes lourdes d'abord (la facon qui marche sur les Psikopompe).
    #  - sans puits : chaque echec coute des lignes. Grosses runes tot (un succes remonte le jet d'un coup),
    #    jamais de rune hors de son palier, la ligne la plus basse dans son jet d'abord, over gere.
    avec_puits = rel >= SEUIL_PUITS

    # Tous les exos demandes sont poses (ex. les 2 % dommages aux sorts) : on ne propose PLUS RIEN, quels
    # que soient le reliquat et l'etat du jet. Toute rune de plus pourrait piocher dans l'exo et le casser.
    # (un over voulu sur une ligne de l'item compte pareil : 6 % dommages aux sorts sur une ligne a 4 max)
    # Le gros exo (PA, PM, PO...) est passe : l'item est fini. On ne tente plus RIEN d'autre (ni l'Ini du
    # double exo, ni une ligne a remonter) : n'importe quelle rune ratee peut le faire tomber.
    gros_poses = [x for x, c in conf.get("exos", {}).items() if c > 0 and POIDS.get(x, 0) >= LOURD
                  and x in etat["lignes"] and L.get(x, {}).get("val", 0) >= min(c, L[x]["cible"])]
    if gros_poses:
        bas_ = [f"{l['nom']} {l['val']}" for x, l in L.items() if 0 < l["max"] and l["val"] < min(l["cible"], l["max"])]
        return {"texte": "OBJECTIF ATTEINT : " + ", ".join(f"{L[x]['nom']} à {L[x]['val']}" for x in gros_poses)
                + " passé — ne touche plus à rien"
                + ("   | (sous l'objectif, on laisse : " + ", ".join(bas_) + ")" if bas_ else "")
                + (f"   | {rel:g} de reliquat : il est perdu si tu équipes ou mets en vente l'item" if rel >= 1 else "")}
    voulus = [s for s, c in conf.get("exos", {}).items() if c > 0 and s in L] \
        + [s for s, l in L.items() if l["cible"] > l["max"] > 0 and s not in conf.get("exos", {})]
    # Exception : une ligne lourde du jet (PA, PM, PO, Invo, Dommages...) tombee sous son objectif. L'item n'est
    # pas fini sans elle : on ne s'arrete pas, la suite la remet (quitte a refaire l'over ensuite).
    lourdes_bas = [s for s, l in L.items() if l["max"] > 0 and POIDS.get(s, 0) >= LOURD
                   and l["val"] < min(l["cible"], l["max"])]
    # Le premier % sorts peut passer en SN : sa presence seule ne valide pas
    # le jet. Reprendre les lignes sous le minimum, sans finition facultative.
    exo_leger_pose = conf.get("exos", {}).get("do_per_so") == 1 \
        and L.get("do_per_so", {}).get("max", 1) <= 0 \
        and L["do_per_so"]["val"] >= 1
    jet_leger_incomplet = [s for s, l in L.items() if exo_leger_pose
        and 0 < l["max"] and 0 < l["cible"] <= l["max"]
        and l["val"] < min(conf.get("mins", {}).get(s, l["cible"]), l["cible"], l["max"])]
    if voulus and not lourdes_bas and not jet_leger_incomplet and all(L[s]["val"] >= L[s]["cible"] > 0 for s in voulus) \
            and all(s in etat["lignes"] for s in voulus):
        bas = [f"{l['nom']} {l['val']} (min {conf['mins'][s]})" for s, l in L.items()
               if l["max"] > 0 and l["val"] < min(conf.get("mins", {}).get(s, 0), l["max"])]
        # Bonus : il reste assez de reliquat pour payer la grosse rune d'un over (10 pour une Ra Vita) et
        # elle tient sous le plafond (Vita 450 -> 500, plafond 505) : on la tente, le reliquat paie.
        jet_ok = all(l["val"] >= min(conf.get("mins", {}).get(x, l["cible"]), l["cible"], l["max"])
                     for x, l in L.items() if l["max"] > 0 and x not in voulus)
        if jet_ok and not any(l["max"] <= 0 < l["val"] for l in L.values()):
            for x in voulus:
                # la plus grosse rune que le reliquat paie et qui tient sous le plafond (Ra Vita avec 10 et plus ;
                # avec 5 de reliquat, Pa Vita ou Vita +5 pour l'epuiser)
                g_ = next((t_ for t_ in reversed(tailles(x)) if t_ in L[x].get("dispo", ())
                           and rel >= pds(x, qte(x, t_)) and L[x]["val"] + qte(x, t_) <= plafond(x, L[x]["max"])), None)
                if g_ and 0 < L[x]["max"] < L[x]["cible"]:
                    return {"stat": x, "taille": g_, "virtuel": False,
                            "texte": f"BONUS dans le reliquat : {nom_rune(x, g_)} +{qte(x, g_)}   | "
                                     f"{L[x]['nom']} {L[x]['val']} (objectif {L[x]['cible']} atteint), {rel:g} de "
                                     f"reliquat paie la rune ; un échec critique peut quand même entamer l'over"}
        return {"texte": "OBJECTIF ATTEINT : " + ", ".join(f"{L[s]['nom']} à {L[s]['val']}" for s in voulus)
                + " — ne touche plus à rien" + ("   | sous le minimum : " + ", ".join(bas) if bas else "")
                + (f"   | {rel:g} de reliquat : il est perdu si tu équipes ou mets en vente l'item" if rel >= 1 else "")}
    # Ligne haute coincee entre la fin de sa plage Ra et son objectif (ex. Puissance a 113 pour 118,
    # Ra permise jusqu'a 110) : les petites runes n'y passent plus. On n'y touche pas, on continue de
    # runer les autres lignes pour qu'elle redescende dans la plage de la Ra.
    exo_pose = any(l["max"] <= 0 and l["val"] > 0 and not l.get("virtuel") for l in L.values())

    def deborde_ok(s, l):
        """Ligne coincee entre sa derniere Ra et son objectif (Vita 362 pour 390, max 400) mais qui peut etre
        over (plafond 505) : on passe la Ra quand meme (412) et on gere l'over, au lieu d'attendre qu'elle
        redescende. Pas pour une ligne qui ne peut pas etre over (Puissance 80, 20 Dommages, 500 Vita)."""
        g_ = tailles(s)[-1]
        if g_ == "base" or exo_pose or not (0 < l["max"] < plafond(s, l["max"])):
            return False
        q_ = qte(s, g_)
        if any(l["val"] < palier(s, t_) for t_ in tailles(s)[:-1]):
            return False                # une rune plus petite passe encore bien (Ré cri 13/15 : +1, pas de Pa)
        return l["max"] - q_ < l["val"] < min(l["cible"], l["max"]) and l["val"] + q_ <= plafond(s, l["max"]) \
            and g_ in l.get("dispo", ())

    bloquees = {}
    for s, l in L.items():
        g = tailles(s)[-1]
        plage = conf.get("regles", {}).get(s, {}).get(g) if g != "base" else None
        if not plage or l["max"] <= 0:
            continue
        fin = min(plage[1], plafond(s, l["max"]) - qte(s, g))        # derniere valeur ou la grosse rune tient
        autre = any(t != g and p_[0] <= l["val"] <= p_[1] and l["val"] + qte(s, t) <= plafond(s, l["max"])
                    for t, p_ in conf.get("regles", {}).get(s, {}).items())   # la Pa prend le relais
        if pds(s, l["val"]) >= SEUIL_RA and fin < l["val"] < l["cible"] and not autre and not deborde_ok(s, l):
            bloquees[s] = fin
    # Over a la grosse rune mal aligne : a 417 vita (max 400, plafond 505) une Ra mene a 467, la suivante
    # depasserait 505.  Il faut d'abord redescendre a 405 avec des runes a 1 de puits, puis 405 -> 455 -> 505.
    alignes = {}
    for s, l in L.items():
        g = tailles(s)[-1]
        if g == "base" or s in bloquees or not (0 < l["max"] < l["val"] < l["cible"]):
            continue
        q, haut = qte(s, g), plafond(s, l["max"])
        # on aligne sur le plafond (Vita 355 -> 405 -> 455 -> 505), comme sur les Psikopompe : l'over voulu
        # se finit puis le reliquat qui reste part en bonus jusqu'au plafond
        but = haut
        n = int((haut - l["val"]) // q)                      # nombre de grosses runes qui rentrent encore
        obj_ = conf.get("mins", {}).get(s, l["cible"])
        if l["val"] + q * n >= but - .4 * q or l["val"] + q >= obj_:   # (432 -> 482 : une Ra finit l'objectif)
            continue        # on arrive au but (ou presque : 404 -> 454 -> 504, on ne redescend pas 49 vita pour 1)
        v = haut - q * (n + 1)
        if l["val"] - v < .2 * q:
            continue        # (356 pour 355 : on ne fait pas une descente pour 1 vita)
        if v >= l["max"] and v + q * (n + 1) >= but:
            bloquees[s] = v
            alignes[s] = n + 1
    def cadre(s, l):
        q = qte(s, tailles(s)[-1])
        return q, conf.get("mins", {}).get(s, l["cible"]), plafond(s, l["max"])

    def place(s, l, v):
        """v est-elle une valeur d'ou les grosses runes menent au but sans depasser le plafond ?"""
        q, but, haut = cadre(s, l)
        return v + q * max(0, -(-(but - v) // q)) <= haut

    def note_blocage():
        tous = dict(bloquees, **attente)
        return "".join(
            f"   | {L[s]['nom']} à {L[s]['val']} : la descendre à {v}, puis {alignes[s]} "
            f"{tailles(s)[-1].capitalize()} jusqu'à {v + alignes[s] * qte(s, tailles(s)[-1])}" if s in alignes else
            f"   | {L[s]['nom']} à {L[s]['val']} : la laisser redescendre à {v} pour la "
            f"{tailles(s)[-1].capitalize()}" for s, v in tous.items()
            if s in alignes or L[s]["val"] < L[s].get("bas", L[s]["cible"]))   # ligne a son minimum : rien a dire

    attente = {}

    def descente():
        """Plus rien d'autre a monter, ou un over a realigner (Vita 380 -> 355, puis 405, 455, 505) : la plus
        petite rune jouable ailleurs, juste pour faire des pertes (Force ou Agilite +1, 1 de puits)."""
        petites = [((x in ("vi", "ini", "pods"), pds(x, qte(x, "base"))), x) for x, y in L.items()
                   if x not in bloquees and x not in attente and "base" in y["dispo"] and y["max"] > 0
                   and not (exo_leger_pose and (y["cible"] <= 0 or y["val"] >=
                       min(conf.get("mins", {}).get(x, y["cible"]), y["cible"], y["max"])))
                   and not (exo_leger_pose and (y["cible"] <= 0 or y["val"] >=
                       min(conf.get("mins", {}).get(x, y["cible"]), y["cible"], y["max"])))
                   and (pds(x, qte(x, "base")) <= 1 or not inutile(x, "base", y["val"], y["max"]))
                   and y["val"] + qte(x, "base") <= plafond(x, y["max"])]
        if petites and (min(petites)[0][1] <= 2 or not alignes):
            x = min(petites)[1]
            return {"stat": x, "taille": "base", "virtuel": False,
                    "texte": f"DESCENTE {L[x]['nom']} +{qte(x, 'base')}{note_blocage()}"}
        if alignes:                                # aucune petite rune sur l'item : une rune a 1 de puits en exo
            x = next((c for c in CARAC if c not in L), "ini")
            return {"stat": x, "taille": "base", "virtuel": True,
                    "texte": f"DESCENTE {nom_code(x)} +{qte(x, 'base')} (exo à 1 de puits){note_blocage()}"}
        return None

    def coince(s, l, v):
        """Si, a la valeur v, la ligne est sous son objectif, trop haute pour sa grosse rune et que les
        petites runes n'y ont presque aucune chance : valeur ou la laisser redescendre. Sinon None."""
        g = tailles(s)[-1]
        if g == "base" or l["max"] <= 0 or not (l["cible"] - qte(s, g) < v < l["cible"]):
            return None
        if l["cible"] - v < qte(s, g) / 4:
            return None                             # il manque trop peu pour casser la ligne expres
        if v + qte(s, g) <= plafond(s, l["max"]):
            return None                             # la grosse rune rentre encore
        ici = dict(l, val=v)
        adaptee = next((t for t in tailles(s) if v < 1.2 * palier(s, t)), g)
        chances = [sum(probas(histo, s, t, ici)[0][:2]) for t in tailles(s) if t != g
                   and (v + qte(s, t) <= max(l["cible"], l["max"]) or t == adaptee)
                   and v + qte(s, t) <= plafond(s, l["max"])]
        if chances and max(chances) >= SEUIL_ATTENTE:
            return None
        return max(0, l["cible"] - qte(s, g))

    # Over non voulu (ligne au-dessus de son max alors qu'on ne vise pas d'over dessus) : la rune suivante
    # pioche dedans en premier, par points entiers, et peut la faire retomber sous son max.
    # Ex. Puissance 41/40 (over de 1, 2 de puits) : une rune a 3 de puits retire 2 Puissance -> 39, +1 reliquat.
    parasites = {x: l["val"] - max(l["cible"], l["max"]) for x, l in L.items()
                 if l["max"] > 0 and l["val"] > max(l["cible"], l["max"])}
    # Tout over non voulu peut etre recycle : meme Re cri 26/25 n'offre que
    # 2 de poids et doit etre protege d'une rune a 10 si une petite rune tient.
    _exc = sum(pds(x, n) for x, n in parasites.items())
    # (une ligne a petit poids par point, meme a peine over : Vita 402/400 + une Ra Sagesse ratee = Vita 252,
    #  tout le poids de la rune tombe d'abord sur l'over. Il faut le gerer avant toute rune lourde.)
    gerer_over = _exc > 0

    def degat(s, t):
        """Lignes en over non voulu que cette rune ferait retomber sous leur max."""
        # Le reliquat ne protege pas : sur un echec critique la perte tombe sur les lignes, l'over en premier
        # (vu en jeu : Retrait PM rate avec 12 de reliquat, vita 458 -> 423, reliquat inchange).
        w = pds(s, qte(s, t))
        if not gerer_over:
            return []               # aucun over non voulu
        return [x for x, k in parasites.items() if x != s and -(-w // POIDS.get(x, 1)) > k]

    def meilleur(cands, cle=None):
        """Le meilleur candidat, en evitant d'abord ceux qui cassent un over non voulu."""
        sains = [k for k in cands if not degat(k[2], k[3])]
        return max(sains or cands, key=cle) if cle else max(sains or cands)

    def recycle(k):
        """La rune tient dans l'excedent des lignes en over non voulu : elle le reutilise sans rien casser."""
        # (sans compter le reliquat : sur un echec critique il ne paie rien, tout tombe sur la ligne en over)
        w = pds(k[2], qte(k[2], k[3]))
        return w <= sum(pds(x, n) for x, n in parasites.items() if x != k[2]) and not degat(k[2], k[3])

    def par_poids(k):
        return pds(k[2], qte(k[2], k[3])), k[0]

    def peut_franchir(s, l):
        """Pendant la remontee du jet, la grosse rune peut franchir le max si l'over est voulu sur cette
        ligne, qu'aucune rune plus petite n'a de pas utile sous le max (hors palier : Pa Vi a 367 jamais ;
        ou elle depasserait le max), et que c'est la seule ligne legere encore incomplete."""
        ts = tailles(s)
        if len(ts) < 2 or l["cible"] <= l["max"] or [x for x in jet if x != s and POIDS.get(x, 0) < LOURD]:
            return False
        return all(l["val"] + qte(s, t) > l["max"] or l["val"] >= palier(s, t) for t in ts[:-1])

    # Un exo est pose sur l'item (1er % dommages aux sorts...) : le jeu refuse toute rune qui ferait passer une
    # ligne normale au-dessus de son max (constate : Ra Vi impossible au-dessus de 400/450 avec le % pose).

    def inutile(x, t, val, maxi):
        """Rune normale hors de son palier alors qu'une plus grosse existe (Puissance +1 a 61 : 3 % de reussite),
        ou rune normale de Sagesse sur une ligne a 40 : jamais. Elle ne fait que bruler du puits."""
        mn_ = conf.get("mins", {}).get(x)
        if mn_ is not None and L.get(x, {}).get("cible", 0) > val >= mn_ and val >= palier(x, t) \
                and not (L[x]["cible"] > L[x]["max"] > 0):
            return True                 # Do poussee 23 (min 23) : jamais une rune hors palier pour finir a 25
        if t == "pa" and x in CARAC and val + qte(x, "pa") <= maxi:
            return False                # Agilite 63 -> 66 : la Pa reste la bonne rune sous le max (pas une Ra a 73)
        if t == "pa" and "ra" in tailles(x) and val >= palier(x, "pa"):
            # Pa hors palier : seulement si tes passes disent qu'elle passe encore (Pa Vita a 300+ avec
            # reliquat : 0 sur 7 -> non). On juge sur le taux appris pour cette stat dans cette situation.
            # Avec puits, un neutre est paye par le reliquat (le reliquat devient de la stat) : on compte SC + SN.
            # Sans puits, un neutre casse d'autres lignes : seule la reussite complete compte.
            (psc_, psn_, _), _n = probas(histo, x, "pa", dict(L.get(x, {}), val=val, max=maxi))
            return (psc_ + psn_ if avec_puits else 2.5 * psc_) < SEUIL_HORS_PALIER
        if t != "base" or len(tailles(x)) == 1:
            return False
        if avec_puits:
            # avec puits, la rune normale hors palier se juge pareil, sur tes stats (Do poussee +1 a 24 :
            # 3 % de reussite, 29 % de neutres -> elle brule le reliquat pour rien)
            if val < palier(x, "base"):
                return False
            (psc_, psn_, _), _n = probas(histo, x, "base", dict(L.get(x, {}), val=val, max=maxi))
            return psc_ + psn_ < SEUIL_HORS_PALIER
        return val >= palier(x, "base") or (x == "sa" and maxi > palier(x, "base"))

    def ferme_finition(s, t):
        """Ne pas quitter la plage de finition si la grosse rune ne tiendrait plus."""
        l = L[s]
        g = tailles(s)[-1]
        plage = conf.get("regles", {}).get(s, {}).get(g)
        if not plage or t == g or l["max"] <= 0:
            return False
        v, q, qg = l["val"], qte(s, t), qte(s, g)
        return plage[0] <= v <= plage[1] and v + q < min(l["cible"], l["max"]) \
            and v + qg <= plafond(s, l["max"]) < v + q + qg

    def essais(lignes, borne, over=True, libre=False, plages=True):
        """Tous les couples (ligne, taille) jouables, notes par gain espere moins perte esperee.
        over=False : aucune rune ne fait passer la ligne au-dessus de son max (on remonte le jet).
        libre=True : toutes les tailles en stock, sans plage ni attente (pour depenser le reliquat)."""
        out, sans_rune = [], []
        for s in lignes:
            if s in bloquees and not (libre and s in alignes):
                continue
            l = L[s]
            besoin = borne(l) - l["val"]
            if not l["dispo"]:
                sans_rune.append(l["nom"])
                continue
            autres = sum(pds(x, y["val"]) for x, y in L.items() if x != s and y["val"] > 0)
            utiles = sum(pds(x, min(y["val"], y["cible"])) for x, y in L.items() if x != s and y["val"] > 0)
            regle = None if libre else conf.get("regles", {}).get(s)
            permis = l["dispo"]
            limite = plafond(s, l["max"])
            grosse_t = tailles(s)[-1]
            # taille adaptee : la plus petite rune encore dans son palier (20 x son effet, a 20 % pres).
            # A 38 d'agilite la rune normale a depasse le sien : c'est la Pa qui passe, quitte a finir a 41.
            tp = next((t for t in tailles(s) if l["val"] < 1.2 * palier(s, t)), grosse_t)
            vise_over = l["cible"] > l["max"] > 0
            sous_max = l["max"] > 0 and l["val"] < l["max"]
            if regle:                              # plages choisies par l'utilisateur, sinon la taille adaptee
                voulu = next((t for t in ("ra", "pa", "base") if t in regle
                              and regle[t][0] <= l["val"] <= regle[t][1]
                              and l["val"] + qte(s, t) <= limite), tp)
                deborde = deborde_ok(s, l) and not any(p_[0] <= l["val"] <= p_[1] for p_ in regle.values())
                if deborde:
                    voulu = grosse_t                # hors de tes plages, coincee sous le max : Ra et over gere
                elif not over and sous_max and l["val"] + qte(s, voulu) > l["max"]:
                    if vise_over:
                        if not peut_franchir(s, l):
                            continue               # l'over de cette ligne attend que le jet soit remonte
                        voulu = grosse_t
                    else:
                        voulu = tp
                if exo_pose and l["max"] > 0 and l["val"] + qte(s, voulu) > l["max"]:
                    # exo pose sur l'item : le jeu refuse une rune qui ferait depasser le max d'une ligne
                    tient_ = [t for t in l["dispo"] if l["val"] + qte(s, t) <= l["max"]]
                    if not tient_:
                        continue
                    voulu = max(tient_, key=MULT.get)
                if degat(s, voulu):                # casserait un over non voulu : une taille en dessous
                    plus_petit = [t for t in l["dispo"] if MULT[t] < MULT[voulu] and not degat(s, t)
                                  and not inutile(s, t, l["val"], l["max"])
                                  and not (t != "base" and not avec_puits and l["val"] >= palier(s, t))]
                    if plus_petit:
                        voulu = max(plus_petit, key=MULT.get)
                if voulu not in l["dispo"]:
                    # plus de cette rune en stock : on le signale et on continue avec la taille la plus proche
                    sans_rune.append(("" if voulu == "base" else voulu.capitalize() + " ") + l["nom"])
                    reste = [t for t in l["dispo"] if l["val"] + qte(s, t) <= limite]
                    if not reste:
                        continue
                    voulu = min(reste, key=lambda t: (abs(tailles(s).index(t) - tailles(s).index(voulu)), MULT[t]))
                permis = [voulu]
            if not regle and not libre:
                bas = coince(s, l, l["val"])
                if bas is not None:                 # aucune rune n'a de vraies chances ici : on attend
                    attente[s] = bas
                    continue
            if not regle and "base" in permis and max(l["max"], l["cible"]) <= palier(s, "base"):
                permis = ["base"]                   # petite ligne (Re cri 15...) : la rune normale passe bien partout
            if libre and sous_max and plages and not avec_puits:
                # reliquat a depenser sur une ligne du jet : les plages que tu as choisies tiennent toujours
                # (vita 342 avec « Pa jusqu'a 299 » : pas de Pa Vita, meme payee par le reliquat)
                plages_ = conf.get("regles", {}).get(s) or {}
                dedans_ = [t for t in permis if t in plages_ and plages_[t][0] <= l["val"] <= plages_[t][1]]
                if plages_ and dedans_:
                    # une rune plus grosse que celle de ta plage reste permise : si le reliquat la paie, c'est
                    # mieux (Ra Puissance dans 40 de reliquat sur la Psikopompe)
                    permis = [t for t in permis if t in dedans_ or MULT[t] > max(MULT[d] for d in dedans_)]
            ligne = []
            en_over = libre and grosse_t != "base" and 0 < l["max"] <= l["val"] < l["cible"]
            for t in permis:
                q = qte(s, t)
                if ferme_finition(s, t):
                    continue
                if l["val"] + q > limite:
                    continue
                if inutile(s, t, l["val"], l["max"]):
                    continue
                if exo_pose and l["max"] > 0 and l["val"] + q > l["max"]:
                    continue                        # exo pose : impossible de depasser le max (vita 405 + Ra refusee)
                if en_over:
                    # dans le reliquat, on garde l'over aligne sur les grosses runes : la grosse rune
                    # seulement si elle atterrit bien, les petites pour rejoindre la bonne valeur
                    _, _, haut_ = cadre(s, l)
                    qg = qte(s, grosse_t)
                    if grosse(s, t) and not place(s, l, l["val"] + q):
                        continue
                    if not grosse(s, t) and not place(s, l, l["val"] + q) and (
                            place(s, l, l["val"]) or l["val"] + q > haut_ - qg * int((haut_ - l["val"]) // qg)):
                        continue
                elif not regle:
                    # hors palier : pas de rune plus petite que la taille adaptee si celle-ci est en stock
                    if MULT[t] < MULT[tp] and tp in l["dispo"] and l["val"] + qte(s, tp) <= limite \
                            and not (not vise_over and degat(s, tp) and not degat(s, t)):
                        continue
                    # depasser l'objectif : seulement avec la taille adaptee, pour finir la ligne
                    # (over voulu : la grosse rune peut finir au-dessus de l'objectif, sous le plafond ;
                    #  Vita 350 pour 390 -> Ra 400, plutot que de rester coincee et passer a l'exo)
                    if l["val"] + q > max(l["cible"], l["max"]) and not (t == tp and l["val"] < l["cible"]) \
                            and not (grosse(s, t) and (deborde_ok(s, l) or vise_over and l["val"] < l["cible"])):
                        continue
                if not over and sous_max and l["val"] + q > l["max"]:
                    # franchir le max pendant la remontee du jet : la grosse rune d'un over voulu quand
                    # c'est son tour, ou la taille adaptee qui finit une ligne sans over
                    if vise_over and not (grosse(s, t) and peut_franchir(s, l)):
                        continue
                    if not vise_over and t not in (tp, "base") and not (grosse(s, t) and deborde_ok(s, l)):
                        continue
                (psc, psn, pec), n = probas(histo, s, t, l)
                cout = min(max(0.0, pds(s, q) - rel), autres)
                perte = cout * (utiles / autres if autres else 0)
                # poids des pertes cale sur tes passes (oct. 2026) : 0.5 colle le mieux a ce qui s'est vraiment
                # passe (correlation 0.41 contre 0.34 avec l'ancien 0.15, qui sous-estimait les pertes)
                note = (psc + psn) * pds(s, min(q, besoin)) - POIDS_PERTE * (psn + pec) * perte
                ligne.append((note, MULT[t], s, t, psc, psn, n, perte))
            out += ligne
        return out, sans_rune

    def sortie(c, prefixe, sans_rune):
        _, _, s, t, psc, psn, n, perte = c
        nom = ("" if t == "base" else t.capitalize() + " ") + L[s]["nom"]
        txt = f"{prefixe} {nom} +{qte(s, t)}   SC {psc:.0%} SN {psn:.0%}"
        if perte >= 1:
            txt += f"  perte utile ~{perte:.0f}"
        if n:
            txt += f"  ({n} passes)"
        if sans_rune:
            txt += "   | A ACHETER : " + ", ".join(sans_rune)
        casse = degat(s, t)
        if casse:
            txt += "   | ATTENTION : fera retomber " + ", ".join(
                f"{L[x]['nom']} sous son " + ("objectif" if L[x]["cible"] > L[x]["max"] else "max")
                + f" (over de {parasites[x]})" for x in casse)
        txt += note_blocage()
        return {"stat": s, "taille": t, "virtuel": L[s].get("virtuel", False), "texte": txt}

    # 0) Lignes negatives (malus : Initiative -310, plage -301 a -400). La colonne Min du jeu donne la
    #    meilleure valeur. Runer un malus coute la moitie du poids et, une fois a sa meilleure valeur, la
    #    ligne ne bouge plus : on le fait en premier, si un objectif plus haut que la valeur est regle.
    if not any(l["val"] > 0 and l["cible"] > 0 if l["max"] <= 0 else l["cible"] > l["max"] < l["val"] for l in L.values()):
        for s, l in etat["lignes"].items():
            if s not in POIDS or not (l["max"] < 0 or l["min"] < 0) or s not in conf.get("cibles", {}):
                continue
            but = min(conf["cibles"][s], max(l["min"], l["max"]))
            for t in sorted(l["dispo"], key=MULT.get, reverse=True):
                if l["val"] + qte(s, t) <= but:
                    return {"stat": s, "taille": t, "virtuel": False,
                            "texte": f"MALUS {nom_rune(s, t)} +{qte(s, t)} (demi-poids)   | {l['nom']} "
                                     f"{l['val']} → objectif {but}"}
    # 1) remonter le jet : les lignes sous leur max, sans jamais franchir le max a ce stade
    #    On ne paie (en pertes sur les autres lignes) que jusqu'au minimum accepte ; l'objectif complet
    #    ne se vise qu'avec du reliquat. Jet au minimum = on passe aux over / exos.
    #    Cycle : des qu'une ligne passe sous son minimum accepte, on remonte TOUT le jet jusqu'a la colonne
    #    « Remonter a » (plus haute que le minimum). Ensuite on enchaine les exos / over sans rien remonter
    #    tant qu'aucune ligne ne retombe sous son minimum. Ce coussin evite de remonter apres chaque essai,
    #    et laisse tenter le 2e % tout de suite quand le 1er passe en SN.
    #    Un exo ou un over deja en partie pose : on ne remonte que jusqu'au minimum, pour ne pas le casser.
    deja = any(l["val"] > 0 and l["cible"] > 0 if l["max"] <= 0 else l["cible"] > l["max"] < l["val"]
               for l in L.values())
    for s, l in L.items():
        l["bas"] = min(conf.get("mins", {}).get(s, l["cible"]), l["cible"], l["max"])
        milieu = -(-(l["bas"] + min(l["cible"], l["max"])) // 2)
        l["haut"] = max(l["bas"], min(conf.get("remonte", {}).get(s, milieu), l["cible"], l["max"]))
        # sans puits : une ligne encore dans le premier quart de son jet (Puissance 62 sur 61-80) se remonte
        # tout de suite avec sa grosse rune, meme si elle a atteint son minimum accepte
        g_ = tailles(s)[-1]
        p_ = conf.get("regles", {}).get(s, {}).get(g_)
        if not avec_puits and g_ != "base" and l["max"] > l.get("min", 0) and p_ and p_[0] <= l["val"] <= p_[1] \
                and (l["val"] - l.get("min", 0)) / (l["max"] - l.get("min", 0)) < .25:
            l["bas"] = l["haut"] = max(l["bas"], min(l["cible"], l["max"]))
    if deja:
        _CYCLE[0] = False
    elif any(l["max"] > 0 and l["val"] < l["bas"] for l in L.values()):
        _CYCLE[0] = True
    if _CYCLE[0]:
        if any(l["max"] > 0 and l["val"] < l["haut"] for l in L.values()):
            for l in L.values():
                l["bas"] = l["haut"]
        else:
            _CYCLE[0] = False                       # tout est remonte : place aux exos
    jet = [s for s, l in L.items() if l["max"] > 0 and l["val"] < l["bas"]]
    jet_obj = [s for s, l in L.items() if l["max"] > 0 and l["val"] < min(l["cible"], l["max"])]
    c, sans = essais(jet, lambda l: l["bas"], over=False)

    def dans_reliquat(complet=False):
        """Over voulu paye en entier par le reliquat : la plus grosse rune qui rentre (Ra tant qu'il reste
        10, Pa a 3, normales pour finir a 0), quelles que soient les plages."""
        # tant qu'une ligne lourde manque, l'over s'arrete a son minimum accepte (puis on remet le PO) ;
        # jet complet, le reste du reliquat continue l'over jusqu'a l'objectif
        v, _ = essais([s for s, l in L.items()
                       if l["val"] < (l["cible"] if complet else conf.get("mins", {}).get(s, l["cible"]))
                       and POIDS.get(s, 0) < LOURD and l["val"] >= l["max"] > 0],
                      lambda l: l["cible"], libre=True)
        p = [k for k in v if pds(k[2], qte(k[2], k[3])) <= rel]
        if complet:                          # passe le minimum accepte, on finit sans depasser l'objectif
            p = [k for k in p if L[k[2]]["val"] < conf.get("mins", {}).get(k[2], 0)
                 or L[k[2]]["val"] + qte(k[2], k[3]) <= L[k[2]]["cible"]]
        return meilleur(p, par_poids) if p else None

    # Un over voulu ou un exo deja en partie passe (1er % do sorts, vita au-dessus du max) : chaque rune
    # posee ailleurs pioche dedans en premier. Ce n'est plus le moment de remonter une ligne jetable.
    entame = any(l["val"] > 0 and l["cible"] > 0 if l["max"] <= 0 else l["cible"] > l["max"] < l["val"]
                 for l in L.values())

    # ligne jetable avec « Remonter a » = 0 : on n'y pose jamais aucune rune
    intouchables = {x for x, y in L.items() if y["cible"] <= 0 < y["max"] and conf.get("remonte", {}).get(x) == 0}

    def bruler():
        """Une ligne utile est au-dessus de son max sans over voulu (vita 458/450). Toute rune qui ne passe pas
        en SC pioche TOUT son poids dans cette ligne (un Re % air a 6 de puits : vita -30). Avant une rune plus
        lourde que l'excedent, on vide donc l'over avec de petites runes : la plus grosse qui tient dans
        l'excedent, sinon la plus petite possible (1 ou 2 de puits), jusqu'a ce que la ligne soit a son max."""
        if (entame and not all(x in CARAC for x in parasites)) or not any(L[x]["cible"] > 0 for x in parasites):
            return None
        exc = sum(pds(x, n) for x, n in parasites.items())
        if not gerer_over:
            return None                 # petit over gratuit (Ré feu 8/7) : il sert de tampon, on ne le brule pas
        cands = []
        for x, y in L.items():
            if x in parasites or y["max"] <= 0 or x == "pods" or x in intouchables:
                continue                             # (Vi et Ini a 1 de densite sont permises ; l'over lui-meme non)
            for t in y["dispo"]:
                if ferme_finition(x, t):
                    continue
                # (ici une rune qui rate est ce qu'on cherche : Puissance +1 a 2 de puits ramene Vita 402 a 392 ;
                #  une rune normale hors palier est donc permise, mais pas une Pa hors palier)
                if t == "pa" and "ra" in tailles(x) and y["val"] >= palier(x, "pa") \
                        and not (x in CARAC and y["val"] + qte(x, "pa") <= y["max"]):   # (Pa Agi 63 -> 66 : oui)
                    continue
                # ligne a son minimum accepte : jamais une rune hors palier (Do poussee 23, min 23 : pas de Do pou)
                # (une rune de 2 de puits ou moins reste permise : Puissance +1 a 71 pour gerer la Vita)
                if y["cible"] > y["val"] >= conf.get("mins", {}).get(x, 10 ** 9) and y["val"] >= palier(x, t) \
                        and pds(x, qte(x, t)) > 2:
                    continue
                # une ligne deja a son max peut quand meme recevoir une petite rune normale (+1 agi, +1 re cri) :
                # elle ne passera presque jamais, et c'est justement ce qui fait descendre l'over
                if y["val"] + qte(x, t) <= y["max"] or (t == "base" and pds(x, qte(x, t)) <= 2
                                                        and y["val"] + qte(x, t) <= plafond(x, y["max"])):
                    (psc, psn, _), n = probas(histo, x, t, y)
                    cands.append((0, MULT[t], x, t, psc, psn, n, 0))
        dedans = lambda k: L[k[2]]["val"] + qte(k[2], k[3]) <= L[k[2]]["max"]
        if [k for k in cands if dedans(k) and par_poids(k)[0] <= max(exc, 2)]:
            cands = [k for k in cands if dedans(k)]          # tant qu'une ligne sous son max peut servir, elle d'abord
        tient = [k for k in cands if par_poids(k)[0] <= exc]
        if tient:
            # Recycler l'excedent sans entamer le jet naturel tant qu'une rune
            # disponible le permet, meme si l'objectif est inferieur au max.
            cands = tient
        # (une ligne deja a son minimum accepte n'est pas « utile » : Do poussee 23, min 23 -> pas de Do pou ici)
        utile = lambda k: L[k[2]]["val"] < L[k[2]]["cible"] and L[k[2]]["val"] < conf.get("mins", {}).get(k[2], 10 ** 9)
        # la rune dont le poids ramene l'over le plus pres du max (Vita 411 : 2.2 de puits -> une rune a 3,
        # Vita 396 ; plutot qu'une rune a 1, Vita 406, qu'il faudrait refaire)
        # d'abord la plus petite rune qui ramene sous le max en un coup (poids >= excedent), sinon la plus
        # grosse qui tient dans l'excedent
        # Proteger le max naturel, y compris si l'objectif accepte un jet plus bas.
        # Les petits depassements ne sont envisages qu'en l'absence de rune qui tient.
        marge = exc  # le max naturel est le plancher, pas l'objectif du profil
        # 0) petit over sur une carac (Force 72/70) : les petites runes d'une carac a monter le kickent
        #    (Agilite +1 puis Pa Agilite), pas une Sagesse ni une Ra Agilite
        if all(x in CARAC for x in parasites):
            kick = [k for k in cands if utile(k) and k[2] in CARAC and par_poids(k)[0] <= marge + 1e-9]
            if kick:                # (Force 74/70, Agi 67 : Pa Agi -> 70, kicke l'over de 3 ; Agi +1 si la Pa depasse)
                return max(kick, key=lambda k: (par_poids(k)[0], k[4]))
            # (aucune carac a monter : la plus grosse rune utile qui tient dans l'over, Force 76 -> Pa Vita (3)
            #  -> 73 -> Pa Vita -> 70 ; pas une Ra Vita (10) qui la ferait tomber a 66)
            kick = [k for k in cands if utile(k) and par_poids(k)[0] <= marge + 1e-9]
            if kick:
                return max(kick, key=lambda k: (par_poids(k)[0], k[4]))
        # 0b) over sur une ligne legere (Vita 215/200) : une petite rune d'une ligne a monter dont l'echec reste
        #     au-dessus du max naturel (Puissance +1, 2 de puits = 10 vita), la plus lourde qui tient ; on la
        #     repete si besoin. Pas une Sagesse a 3 sur une ligne deja a son objectif.
        if all(POIDS.get(x, 1) < 1 for x in parasites):
            kick = [k for k in cands if L[k[2]]["val"] < L[k[2]]["cible"] and k[3] == "base"
                    and par_poids(k)[0] <= min(marge, 2) + 1e-9]
            if kick:
                return max(kick, key=lambda k: (par_poids(k)[0], k[4]))
            # (Puissance deja a 80 : une rune simple d'une autre ligne, Sagesse +1 a 3, qui ne fait pas
            #  retomber la Vita sous son objectif ; pas une Pa Sagesse a 9)
            kick = [k for k in cands if k[3] == "base" and par_poids(k)[0] <= min(marge, 3) + 1e-9]
            if kick:
                return max(kick, key=lambda k: (par_poids(k)[0], k[4]))
        dans_obj = [k for k in cands if exc <= par_poids(k)[0] <= marge + 1e-9]
        if dans_obj:
            return min(dans_obj, key=lambda k: (par_poids(k)[0], not utile(k), -k[4]))
        # 2) sinon une rune d'exo a 1 de puits (Agi, Fo, Int, Cha +1) si elle tient : joue() la propose
        if exc <= 1 <= marge and not exo_pose and any(c_ not in L for c_ in CARAC):
            return None
        # 3) sinon la plus petite rune qui ramene sous le max en un coup
        assez = [k for k in cands if exc <= par_poids(k)[0] <= exc + 8]
        if assez:
            return min(assez, key=lambda k: (par_poids(k)[0], not utile(k), -k[4]))
        if tient:
            return max(tient, key=lambda k: (utile(k), par_poids(k)[0], k[4]))
        petit = [k for k in cands if par_poids(k)[0] <= 2]
        return min(petit, key=lambda k: (not utile(k), par_poids(k)[0], -k[4])) if petit else None

    def tampon(k):
        """REGLE GENERALE de l'over, sans puits. Toute rune ratee pioche d'abord dans ce qui depasse le max
        (l'over, voulu ou non), puis dans le reliquat. Ce « tampon » vaut : poids de l'over + reliquat.
        Si la rune prevue pese plus que le tampon (Ré neutre 6 sur un over de Vita 362 = 2.4), son echec casse
        l'over ET d'autres lignes. On joue d'abord la rune utile dont le poids colle le mieux au tampon
        (Pa Force 3) : si elle passe, une ligne monte ; si elle rate, c'est l'over qui paie, pas le jet.
        Ensuite la rune prevue. Vaut pour tous les items : Force 72/70 -> Pa Agi, Vita 362 -> Pa Force...
        Pas avec puits (le reliquat paie), pas pour la rune de l'over lui-meme ni pour un gros exo (PO, PM),
        et pas quand l'over a atteint son minimum accepte (on le garde pour l'exo)."""
        if avec_puits or L[k[2]]["max"] <= 0 or POIDS.get(k[2], 0) >= LOURD:
            return None
        overs = [x for x, l_ in L.items() if 0 < l_["max"] < l_["val"] and x != k[2] and x not in parasites
                 and l_["val"] < conf.get("mins", {}).get(x, l_["cible"])]
        if not overs:
            return None
        t_ = sum(pds(x, L[x]["val"] - L[x]["max"]) for x in overs) + rel
        w = pds(k[2], qte(k[2], k[3]))
        if w <= t_ + 1e-9:
            return None
        ex, _ = essais([x for x, l_ in L.items() if 0 < l_["max"] and x not in overs and x not in parasites
                        and l_["val"] < l_["cible"] and POIDS.get(x, 0) < LOURD], lambda l: l["cible"])
        ex = [c_ for c_ in ex if par_poids(c_)[0] < w and L[c_[2]]["val"] + qte(c_[2], c_[3]) <= L[c_[2]]["max"]]
        if not ex:
            return None
        b = min(ex, key=lambda c_: (abs(par_poids(c_)[0] - t_), -c_[4]))
        r = sortie(b, "GÈRE L'OVER", sans)
        r["texte"] += (f"   | over de {', '.join(L[x]['nom'] + ' ' + str(L[x]['val']) for x in overs)} trop petit "
                       f"pour {nom_rune(k[2], k[3])} : on le dépense d'abord sur une rune utile")
        return r

    def joue(k, prefixe):
        """Sortie normale, sauf si cette rune casserait un over non voulu : on gere l'over d'abord."""
        r_ = tampon(k)
        if r_:
            return r_
        if degat(k[2], k[3]) and gerer_over:
            b = bruler()
            suite = ", ".join(f"{L[x]['nom']} {L[x]['val']}/{L[x]['max']}" for x in parasites) \
                + f" à ramener au max avant {('' if k[3] == 'base' else k[3].capitalize() + ' ') + L[k[2]]['nom']}"
            if b is None and not entame and any(L[x]["cible"] > 0 for x in parasites):
                x = next((c_ for c_ in CARAC if c_ not in L), None)      # aucune petite rune sur l'item
                if x:
                    return {"stat": x, "taille": "base", "virtuel": True,
                            "texte": f"GÈRE L'OVER {nom_code(x)} +{qte(x, 'base')} (exo à 1 de puits)   | {suite}"}
            if b:
                r = sortie(b, "GÈRE L'OVER", sans)
                r["texte"] = re.sub(r"   \| ATTENTION : fera retomber[^|]*", "", r["texte"])
                r["texte"] += "   | " + ", ".join(f"{L[x]['nom']} {L[x]['val']}/{L[x]['max']}" for x in parasites) \
                    + f" à ramener au max avant {('' if k[3] == 'base' else k[3].capitalize() + ' ') + L[k[2]]['nom']}"
                return r
        return sortie(k, prefixe, sans)

    def carburant():
        """Ligne jetable tombee bas : on la remonte quand meme. A basse valeur la rune passe bien, et quand
        les runes suivantes la refont sauter c'est du reliquat gratuit a la place de pertes sur les lignes
        utiles. On commence quand elle est a 20 % de son max ou moins, on s'arrete a la moitie, puis on
        l'ignore jusqu'a ce qu'elle retombe a 20 %."""
        for x, y in L.items():
            if y["cible"] <= 0 < y["max"]:               # jetable = objectif a 0
                jusqua = conf.get("remonte", {}).get(x)  # vide : moitie du max ; 0 : on n'y touche jamais
                if jusqua == 0:
                    _EN_REMONTEE.discard(x)
                elif y["val"] >= (jusqua or CARBU_HAUT * y["max"]):
                    _EN_REMONTEE.discard(x)
                elif y["val"] <= CARBU_BAS * y["max"]:
                    _EN_REMONTEE.add(x)
        f, _ = essais([x for x in _EN_REMONTEE if x in L and L[x]["cible"] <= 0 < L[x]["max"]], lambda l: l["max"])
        f = [k for k in f if L[k[2]]["val"] + qte(k[2], k[3]) <= L[k[2]]["max"]]
        return max(f, key=lambda k: (round(k[4] + k[5], 1), -par_poids(k)[0])) if f else None   # la moins chere

    def lourdes_d_abord(k):
        """Les lignes a gros poids par point (Re %, Retrait, Tacle, Do elem...) passent avant les legeres :
        ce sont elles qui coutent cher a passer en dernier."""
        return POIDS.get(k[2], 0) >= 4

    lourd = [k for k in c if POIDS.get(k[2], 0) >= LOURD]
    leger = [k for k in c if POIDS.get(k[2], 0) < LOURD]
    # Premier et seul % sorts demande : exploiter le puits avant la remise
    # d'une ligne structurelle, une fois les remontees jouables terminees.
    exo_puits = []
    if not leger and not sans and not deja and conf.get("exos", {}).get("do_per_so") == 1 \
            and any(k[2] in ("pa", "pm", "po", "invo") for k in lourd) \
            and L.get("do_per_so", {}).get("max", 1) <= 0 \
            and L["do_per_so"]["val"] == 0 and rel >= pds("do_per_so", 1):
        exo_puits, _ = essais(["do_per_so"], lambda l: l["cible"])
    # Une ligne lourde vient de tomber (PM, PO...) : sa chute a mis son poids dans le reliquat (PM -> ~85).
    # On la remet TOUT DE SUITE avec ce puits. Avant, on le depensait sur les petites lignes, puis on remettait
    # le PM avec 1 de reliquat : la reussite prenait 90 de poids sur l'item (tes bottes : Vita 314 -> 35).
    # (puits >= poids de la rune : elle passe a coup sur. PM 90 : il faut 90 de reliquat)
    # Sans over deja monte a proteger, le puits de sa chute (PM tombe -> ~87) suffit : on le remet tout de suite.
    over_en_place = any(0 < l["max"] < l["val"] and l["cible"] > l["max"] for l in L.values())
    # (jamais sur un item avec un over voulu : le gros puits remis alourdit l'item et l'over ne passe plus ;
    #  il se remet APRES l'over)
    over_voulu = any(0 < l["max"] < l["cible"] for l in L.values())
    tout_de_suite = [k for k in lourd if not exo_puits and not over_voulu and rel >= pds(k[2], qte(k[2], k[3]))
                     and L[k[2]]["max"] - L[k[2]]["val"] <= qte(k[2], k[3])]   # une seule rune la remet (PA, PM, PO)
    if tout_de_suite:
        r = joue(meilleur(tout_de_suite), "REMETS")
        r["texte"] += f"   | avec le puits de sa chute ({rel:g} de reliquat)"
        return r
    if c or jet_obj:
        # a) ce que le reliquat paie en entier sur les lignes du jet, la plus grosse rune d'abord
        #    (1 Dommage a 20 de puits passe dans 98 de reliquat ; le PA a 100 attend)
        #    Un over non voulu (vita 480 pour un max de 450) se depense pareil : la rune suivante pioche
        #    dedans en premier. On choisit donc une rune qui tient dans reliquat + excedent, la plus grosse
        #    d'abord (un Do air a 5 de puits ramene la vita a 455), et jamais une rune plus grosse que ce qui
        #    reste (a 451, un Do air la ferait retomber a 426 : une petite rune a la place).
        def payables(plages_):
            return [k for k in essais(jet_obj, lambda l: min(l["cible"], l["max"]), over=False, libre=True,
                                      plages=plages_)[0]
                    if (pds(k[2], qte(k[2], k[3])) <= rel or recycle(k))
                    # ligne deja a son minimum accepte (Do poussee 23, min 23, objectif 25) : on ne la finit
                    # qu'avec une rune qui passe bien, jamais avec une rune hors palier
                    and not (L[k[2]]["val"] >= conf.get("mins", {}).get(k[2], 10 ** 9)
                             and L[k[2]]["val"] >= palier(k[2], k[3]))
                 and (k[2] in jet or not degat(k[2], k[3]))     # rune facultative : jamais si elle peut casser un over
                 and (k[2] in jet or not deja)      # exo/over deja pose : aucune rune facultative, meme payee par le
                                                    # reliquat (son echec critique tomberait sur l'exo)
                 and (POIDS.get(k[2], 0) <= LOURD or not leger)   # PO/PM/PA : jamais tant qu'une ligne legere manque
                 and not (exo_puits and k[2] in ("pa", "pm", "po", "invo"))
                 # ligne a over voulu (Vita 330, max 350) : pas de Pa pour la caler au max, c'est la Ra qui
                 # passe le max (330 -> 380), geree par l'over plus bas
                 and not (L[k[2]]["cible"] > L[k[2]]["max"] > 0 and k[3] != tailles(k[2])[-1]
                          and L[k[2]]["val"] + qte(k[2], tailles(k[2])[-1]) <= plafond(k[2], L[k[2]]["max"]))]
        payes = payables(True)
        hors_plage = False
        if not [k for k in payes if pds(k[2], qte(k[2], k[3])) <= rel]:
            # rien dans tes plages que le reliquat paie : on tente quand meme hors plage (Pa Puissance a 64
            # dans 7 de reliquat). Ca passe rarement, mais l'echec est paye par le reliquat.
            # ... sauf sur une ligne ou ta grosse rune est prevue a cette valeur (Vita 347, Ra de 200 a 365) :
            # une Pa la monterait a 362 et la Ra suivante deviendrait un over qui ne passe plus
            def ra_prevue(k):
                pl = conf.get("regles", {}).get(k[2]) or {}
                v = L[k[2]]["val"]
                return any(t_ != k[3] and MULT[t_] > MULT[k[3]] and p_[0] <= v <= p_[1] for t_, p_ in pl.items())
            payes_hp = [k for k in payables(False) if pds(k[2], qte(k[2], k[3])) <= rel and not ra_prevue(k)]
            if payes_hp:
                payes, hors_plage = payes_hp, True
        if [k for k in payes if POIDS.get(k[2], 0) < LOURD]:    # le PO attend que tout le reste soit utilise
            payes = [k for k in payes if POIDS.get(k[2], 0) < LOURD]
        if payes:
            # d'abord les lignes encore sous leur minimum, puis celles qu'on finit vers l'objectif
            # (une ligne a over voulu, Vita 306, passe apres les autres : Force 66 -> Pa Force d'abord)
            k = meilleur(payes, lambda k: (k[2] in jet, lourdes_d_abord(k),
                                           not (L[k[2]]["cible"] > L[k[2]]["max"] > 0), par_poids(k)))
            if pds(k[2], qte(k[2], k[3])) <= rel:
                r = joue(k, "DANS LE RELIQUAT")
                if hors_plage:
                    r["texte"] += "   | hors de tes plages : ça passe rarement, seulement parce que le reliquat paie"
                return r
            if degat(k[2], k[3]):                    # ligne sous son min mais rune trop lourde pour l'over
                return joue(k, "REMONTE")
            r = sortie(k, "DANS L'OVER", sans)
            r["texte"] = re.sub(r"  perte utile ~\d+", "", r["texte"])      # c'est l'excedent qui paie
            r["texte"] += "   | payé par l'excédent de " + ", ".join(
                f"{L[x]['nom']} ({L[x]['val']}/{L[x]['max']})" for x in parasites if x != k[2])
            return r
    if c:
        # b) Une grosse ligne a saute (Dommages, PO, PM, PA, Invo : 20 de puits et plus) : une fois le reliquat
        #    depense, on la remet AVANT de remonter le reste, et on insiste tant qu'elle ne passe pas. La
        #    remettre casse des lignes de toute facon : inutile de les remonter avant, on le fera une seule
        #    fois apres.
        if leger and not lourd:
            rec = [k for k in leger if recycle(k)]
            if rec:                          # l'excedent d'une ligne en over non voulu paie cette rune
                r = joue(max(rec, key=par_poids), "REMONTE")
                r["texte"] += "   | réutilise l'excédent de " + ", ".join(L[x]["nom"] for x in parasites if x != r["stat"])
                return r
            if [k for k in leger if not degat(k[2], k[3])]:      # pas de rune qui casse un over si une autre existe
                leger = [k for k in leger if not degat(k[2], k[3])]
            # jet presque fini (il manque peu de poids sur les lignes utiles) : pas de carburant, on finit
            # le jet et on passe a l'over / l'objectif (Cape : Do neutre jetable remontee a 2 runes de la fin)
            manque_ = sum(pds(x, max(0, min(l_.get("bas", l_["cible"]), l_["max"]) - l_["val"]))
                          for x, l_ in L.items() if l_["cible"] > 0 < l_["max"] and POIDS.get(x, 0) < LOURD)
            k = None if lourd or entame or manque_ <= 25 else carburant()   # (pas quand PO/PM/PA a saute)
            # on jongle : une jetable tombee bas remonte avant les lignes utiles
            if k:
                return sortie(k, "CARBURANT (ligne jetable basse)", sans)
            # remonter toutes les lignes petit a petit plutot qu'une ligne a fond : la moins remplie d'abord
            # « la plus basse » = par rapport a son jet min-max : Puissance 61 sur 61-80 est a 0 %, Vita 300
            # sur 351-400 est sous son min (negatif) : elle passe d'abord. C'est la plus rapide a remonter.
            def rempli(l):
                if avec_puits:
                    return l["val"] / l["max"]              # (comme sur les Psikopompe)
                return (l["val"] - l.get("min", 0)) / max(1, l["max"] - l.get("min", 0))
            # ligne sous son min naturel (Vita 347 sur 351-400) d'abord ; sinon, comme avant (Psikopompe),
            # les lignes lourdes par point d'abord, puis la plus basse dans son jet
            sous = [] if avec_puits else [k for k in leger if rempli(L[k[2]]) < 0]
            gros = [k for k in leger if lourdes_d_abord(k)] if avec_puits else []   # sans puits : la plus basse d'abord
            leger = sous or gros or leger
            # Over voulu deja commence (Vita 362/350) et pas de puits : on gere l'over. Les runes legeres d'abord
            # (Pa Force a 3 de poids tient dans l'over), puis les lourdes (Ré neutre a 6) ; pas une Ra Vita a 2 %
            # pour « proteger » l'over.
            vide = min(rempli(L[k[2]]) for k in leger)
            return joue(meilleur([k for k in leger if rempli(L[k[2]]) <= vide + .1]), "REMONTE")
        # c) il ne manque plus que des lignes lourdes (PM, PO tombes). Le gros puits (PA, PM, PO) ne se remet
        #    qu'une fois l'over fait (Vita a 440, +90) : l'over sert de tampon a la remise. Apres, s'il reste
        #    du reliquat, on peut tenter plus d'over (le bonus).
        # l'over est « fait » des que la prochaine grosse rune le ferait passer au-dela de 20 de poids
        # (Vita +80 = 16 de poids ; +50 de plus = 26) : on remet alors le gros puits, puis on tente plus haut
        def over_fait(x, l):
            g_ = tailles(x)[-1]
            # fait = l'objectif d'over atteint, ou presque (Vita +80 pour +90 : on remet le PM, puis on tente
            # plus haut avec le reliquat qui reste)
            # (avec un minimum accepte, Vita 440 / min 435 : fait des 435, pas avant ; 432 -> encore une Ra)
            m_ = conf.get("mins", {}).get(x)
            if m_:
                return l["val"] >= m_
            # ... ou des que l'over pese deja 15 de puits ou plus (Do % sorts 5/4 : 1 point = 15). Une ligne
            # lourde par point : le 5e % pose avec le puits, on remet tout de suite le PA, le 6e se tente apres
            # (vu le 14/10 : le puits brule sur le 6e, puis le PA remis sans puits a efface les 5 %).
            return l["val"] >= l["cible"] or l["val"] - l["max"] >= .8 * (l["cible"] - l["max"]) \
                or pds(x, l["val"] - l["max"]) >= 15
        # (seulement un over deja commence, au-dessus du max : sinon il n'y a rien a proteger, on remet le PM)
        # ... et seulement tant que le puits de sa chute paie la grosse rune de l'over (Ra Vita : 10).
        # Quand il ne reste plus ce reliquat, on remet la grosse rune tout de suite (pas de Ra Vita a 0 de puits).
        a_faire = [x for x, l in L.items() if 0 < l["max"] < l["cible"] and not over_fait(x, l)
                   and rel >= pds(x, qte(x, tailles(x)[-1]))]
        if a_faire and gerer_over and any(L[x]["cible"] > 0 for x in parasites):
            b_ = bruler()                   # Force 76/70 : d'abord ramener la Force (Pa Vita, Agi...), puis l'over
            if b_:
                r = sortie(b_, "GÈRE L'OVER", sans)
                r["texte"] = re.sub(r"   \| ATTENTION : fera retomber[^|]*", "", r["texte"]) + "   | " + ", ".join(
                    f"{L[x]['nom']} {L[x]['val']}/{L[x]['max']}" for x in parasites) + " à ramener au max avant l'over"
                return r
        if a_faire and any(x in alignes for x in a_faire):
            d_ = descente()                 # l'over d'abord realigne (Vita 380 -> 355), comme sur les Psikopompe
            if d_:
                d_["texte"] += "   | " + ", ".join(L[k_[2]]["nom"] for k_ in lourd) + " : à remettre une fois l'over fait"
                return d_
        if a_faire and not exo_pose:
            k = dans_reliquat()
            # (joue : un over parasite, Force 76/70, se gere avant la Ra Vita qui le mangerait : Force -> 66)
            if k:
                r = joue(k, "DANS LE RELIQUAT")
            else:
                co, _ = essais(a_faire, lambda l: l["cible"])
                r = joue(meilleur(co), "OVER") if co else None
            if r:
                r["texte"] += "   | " + ", ".join(L[k_[2]]["nom"] for k_ in lourd) + " : à remettre une fois l'over fait"
                return r
        if exo_puits:
            r = joue(meilleur(exo_puits), "EXO DANS LE PUITS")
            r["texte"] += "   | tenter le 1 % sorts avant de remettre la ligne lourde"
            return r
        return joue(meilleur(lourd), "REMETS")
    k = dans_reliquat(True)                  # jet complet : le reliquat part d'abord dans les over voulus
    if k:
        return sortie(k, "DANS LE RELIQUAT", sans)
    # jet au minimum : on tente l'exo / l'over tout de suite, sans remonter une ligne jetable avant
    # une ligne en attente de sa Ra mais deja a son minimum accepte (Puissance 71, min 68) : elle est finie,
    # on ne fait pas de « descente » pour elle, on passe a l'over / l'exo
    bloquees_bas = {x: v for x, v in bloquees.items()
                    if x in alignes or L[x]["val"] < L[x].get("bas", L[x]["cible"])}
    if bloquees_bas or attente:
        d_ = descente()
        if d_:
            return d_
    if sans:
        return {"texte": "A ACHETER : runes " + ", ".join(sans)}
    # 3) over / exo : le plus lourd d'abord
    vises = [s for s, l in L.items() if l["val"] < l["cible"] and s not in bloquees and s not in attente
             and not (0 < l["max"] >= l["cible"] and l["val"] >= l["bas"])]   # ligne du jet au minimum : finie
    # Le reliquat est epuise. Un over deja entame qui a atteint son minimum accepte est termine ; s'il est
    # reste en dessous, on bascule sur le plan B de l'item (un exo PM, PO...) au lieu de s'acharner.
    mins, plan_b = conf.get("mins", {}), conf.get("plan_b")
    entames = [s for s in vises if s in mins and L[s]["val"] > L[s]["max"] > 0]
    rates = [s for s in entames if L[s]["val"] < mins[s]]
    # (minimum atteint mais le puits paie encore la grosse rune et elle tient sous le plafond : Vita 437,
    #  12 de reliquat -> Ra Vita quand meme)
    paie_ra = lambda s: rel >= pds(s, qte(s, tailles(s)[-1])) \
        and L[s]["val"] + qte(s, tailles(s)[-1]) <= plafond(s, L[s]["max"])
    # (yoyo : minimum atteint, sans puits, mais d'autres lignes sont au-dessus de leur objectif - Sagesse 50
    #  pour 38, Fuite 35 pour 32. Leur excedent paie l'echec : on tente encore l'over (le 6e % en SC) tant
    #  qu'il couvre la rune. Il s'arrete tout seul quand Sagesse et Fuite sont a leur objectif.)
    def yoyo(s):
        if any(l_["max"] <= 0 and l_["val"] < l_["cible"] for l_ in L.values()):
            return False            # un exo (PO...) attend encore : l'over a son minimum lui sert de tampon
        exc_ = sum(pds(x, l_["val"] - l_["cible"]) for x, l_ in L.items()
                   if x != s and l_["max"] > 0 and 0 < l_["cible"] < l_["val"] and not l_["cible"] > l_["max"])
        t_ = next((t for t in tailles(s) if t in L[s]["dispo"]
                   and L[s]["val"] + qte(s, t) <= plafond(s, L[s]["max"])), None)
        return t_ is not None and exc_ + rel >= pds(s, qte(s, t_))
    vises = [s for s in vises if s not in entames or s in rates or paie_ra(s) or yoyo(s)]
    # (minimum atteint, le reste du puits ne paie plus de Ra : on l'epuise avec la plus grosse rune qu'il paie,
    #  Pa Vita a 3, Vita +5 a 1)
    for s in entames:
        if s in rates or paie_ra(s):
            continue
        g_ = next((t_ for t_ in reversed(tailles(s)) if t_ in L[s].get("dispo", ())
                   and rel >= pds(s, qte(s, t_)) and L[s]["val"] + qte(s, t_) <= plafond(s, L[s]["max"])), None)
        if g_:
            return {"stat": s, "taille": g_, "virtuel": False,
                    "texte": f"BONUS dans le reliquat : {nom_rune(s, g_)} +{qte(s, g_)}   | {L[s]['nom']} "
                             f"{L[s]['val']} (minimum {mins[s]} atteint), {rel:g} de reliquat paie la rune"}
    if rates and plan_b in POIDS and L.get(plan_b, {"val": 0})["val"] < 1:
        if plan_b not in L:
            L[plan_b] = {"nom": nom_code(plan_b), "min": 0, "max": 0, "val": 0, "cible": 1,
                         "dispo": ["base"], "virtuel": True}
        L[plan_b]["cible"] = max(1, L[plan_b]["cible"])
        cb, _ = essais([plan_b], lambda l: l["cible"])
        if cb:
            r = sortie(max(cb), "PLAN B", sans)
            r["texte"] += "   | " + ", ".join(f"{L[x]['nom']} restée à {L[x]['val']} (minimum {mins[x]})" for x in rates)
            return r
    if rates and plan_b in L and L[plan_b]["val"] >= 1:
        vises = [s for s in vises if s not in rates]          # plan B pose : on arrete l'over
    if not vises:
        if jet_leger_incomplet:
            return {"texte": "JET A REPRENDRE : 1 % sorts pose, sous le minimum : "
                    + ", ".join(L[s]["nom"] for s in jet_leger_incomplet), "stop": True}
        propre = not any(l["max"] <= 0 < l["val"] or l["val"] > l["max"] > 0 for l in L.values())
        jet_fini = all(l["val"] >= min(l["cible"], l["max"]) for s, l in L.items()
                       if l["max"] > 0 and l["cible"] > 0)
        if finition and propre and jet_fini:
            l = L[finition]
            bonus = []
            for t in tailles(finition):
                q = qte(finition, t)
                if t not in l["dispo"] or pds(finition, q) > rel or l["val"] + q > l["max"]:
                    continue
                (psc, psn, _), _n = probas(histo, finition, t, l)
                bonus.append(((psc + psn) * q, MULT[t], t))
            if bonus:
                t = max(bonus)[2]
                return {"stat": finition, "taille": t, "virtuel": False,
                        "texte": f"FINITION RELIQUAT : {nom_rune(finition, t)} +{qte(finition, t)}"
                                 f"   | jet principal atteint, bonus {l['val']}/{l['max']}"
                                 f"   | {rel:g} de reliquat, sans depasser le maximum naturel"}
        return {"texte": "OBJECTIF ATTEINT"
                + ("   | ni exo ni over sur l'item : tu peux le finir avec une rune de transcendance "
                   "(100 % de réussite, mais elle verrouille l'item)" if propre else "")
                + (f"   | {rel:g} de reliquat : il est perdu si tu équipes ou mets en vente l'item" if rel >= 1 else "")}
    # Double exo : jet propre, overs faits, il ne reste que le gros exo (PA, PM, PO) et le reliquat ne suffit pas
    # a le payer. Avant de le tenter, on met ce reliquat dans un petit exo a 1 de puits (Agi, Fo, Int, Cha +1 ou
    # Ini +10) : l'echec est paye par le reliquat. JUSTE s'il y a du reliquat. Un exo pose interdit ensuite tout
    # over : c'est pour ca qu'on attend que les overs soient faits.
    gros = [x for x in vises if L[x]["max"] <= 0 and POIDS.get(x, 0) >= LOURD and L[x]["val"] < L[x]["cible"]]
    petit_pose = any(l["max"] <= 0 < l["val"] and x not in conf.get("exos", {}) for x, l in L.items())
    # Over voulu sur l'item (Vita 390/350) : pas de petit exo (Ini +10 ratee = 10 vita en moins, l'over sort de
    # l'objectif). Le reliquat qui reste part dans l'over avec la plus grosse rune qu'il paie (Ra si 10, Pa a 3,
    # Vita +5 a 1), puis on tente le gros exo.
    ov_ = [x for x, l in L.items() if 0 < l["max"] < l["val"] and l["cible"] > l["max"]]
    if gros and set(vises) <= set(gros) and ov_ and rel >= 1:
        for x in ov_:
            g_ = next((t_ for t_ in reversed(tailles(x)) if t_ in L[x]["dispo"] and rel >= pds(x, qte(x, t_))
                       and L[x]["val"] + qte(x, t_) <= plafond(x, L[x]["max"])), None)
            if g_:
                return {"stat": x, "taille": g_, "virtuel": False,
                        "texte": f"DANS LE RELIQUAT {nom_rune(x, g_)} +{qte(x, g_)}   | {rel:g} de reliquat : on le "
                                 f"vide dans l'over de {L[x]['nom']}, puis {' / '.join(L[y]['nom'] for y in gros)}"}
    # Petit exo : seulement si la présélection en nomme un (« Petit exo » : Agi, Fo, Int, Cha ou Ini).
    choix = conf.get("petit_exo")
    if gros and set(vises) <= set(gros) and not parasites and not petit_pose and choix in PETITS_EXOS \
            and choix not in L and not ov_ \
            and 1 <= rel < min(pds(x, qte(x, "base")) for x in gros):
        return {"stat": choix, "taille": "base", "virtuel": True, "petit_exo": True,
                "texte": f"PETIT EXO dans le reliquat : {nom_rune(choix, 'base')} +{qte(choix, 'base')} avant le "
                         f"{' / '.join(L[x]['nom'] for x in gros)}   | {rel:g} de reliquat paie l'échec"
                         + ("" if choix in RUNES_APPRISES else
                            "   | rune pas encore apprise : bouton « Apprendre la rune » à côté de Petit exo")}
    # L'over (et l'exo) seulement sur un jet complet : tant qu'une ligne est sous son minimum, chaque rune
    # ratee pour la remonter pioche d'abord dans l'over (Vita 397 -> 336 en deux Ré neutre ratees).
    jet_incomplet = [x for x, l in L.items() if 0 < l["max"] and not (l["cible"] > l["max"])
                     and l["val"] < min(conf.get("mins", {}).get(x, l["cible"]), l["cible"], l["max"])
                     # (PM, PO, PA tombes : ils se remettent APRES l'over, il ne le bloquent pas)
                     and not (POIDS.get(x, 0) >= LOURD and l["max"] - l["val"] <= qte(x, tailles(x)[-1]))]
    if jet_incomplet and not avec_puits:
        vises = [x for x in vises if not (L[x]["cible"] > L[x]["max"] > 0)]
        if not vises:
            return {"texte": "ATTENDS L'OVER : " + ", ".join(f"{L[x]['nom']} {L[x]['val']}" for x in jet_incomplet)
                    + " sous le minimum et sans bonne rune — l'over de "
                    + ", ".join(L[x]["nom"] for x, l in L.items() if l["cible"] > l["max"] > 0)
                    + " se fera une fois le jet complet"}
    # l'over d'une ligne du jet passe avant les exos lourds (PO, PM, PA) : le PO toujours apres l'over
    # Une ligne sans rune jouable (Do poussee a 38 pour 40 : la Pa ferait 41, au-dessus du plafond) ne bloque
    # plus tout : on passe a la ligne suivante (l'over de vita, le PO...).
    c, sans, coincees, a_acheter = [], [], [], []
    for s in sorted(vises, key=lambda x: (L[x]["max"] > 0 and POIDS.get(x, 0) < LOURD, pds(x, qte(x, "base"))),
                    reverse=True):
        c, sans = essais([s], lambda l: l["cible"])
        if c:
            break
        (a_acheter if sans else coincees).append(L[s]["nom"])
    if not c:
        if a_acheter:
            return {"texte": "A ACHETER : runes " + ", ".join(a_acheter)}
        if jet_leger_incomplet:
            return {"texte": "JET A REPRENDRE : 1 % sorts pose, aucune remontee jouable sur : "
                    + ", ".join(L[s]["nom"] for s in jet_leger_incomplet), "stop": True}
        return {"texte": "OBJECTIF ATTEINT (aucune rune ne passe plus sur : " + ", ".join(
            f"{L[x]['nom']} {L[x]['val']}" for x in vises) + ")"
            + (f"   | {rel:g} de reliquat : il est perdu si tu équipes ou mets en vente l'item" if rel >= 1 else "")}
    coince_txt = ("   | coincée : " + ", ".join(coincees)) if coincees else ""
    # Over presque fini et plus de puits pour la grosse rune (Vita 432, objectif 440 / min 435, 5 de reliquat) :
    # la plus petite rune qui finit l'objectif (Vita +5, sinon Pa Vita), pas une Ra a 2 % sans puits
    if 0 < L[s]["max"] < L[s]["val"] and rel < pds(s, qte(s, tailles(s)[-1])):
        ecart = conf.get("mins", {}).get(s, L[s]["cible"]) - L[s]["val"]
        fin_ = [t for t in L[s]["dispo"] if t != tailles(s)[-1] and qte(s, t) >= ecart
                and L[s]["val"] + qte(s, t) <= plafond(s, L[s]["max"])]
        if ecart > 0 and fin_:
            t_ = min(fin_, key=lambda t: qte(s, t))
            (psc_, psn_, _), n_ = probas(histo, s, t_, L[s])
            c = [(0, MULT[t_], s, t_, psc_, psn_, n_, 0)]
    best = meilleur(c)
    # 3) pas assez de carburant : remonter d'abord les lignes sacrifiables
    sacrif = sum(pds(x, max(0, y["val"] - y["cible"])) for x, y in L.items() if x != s)
    if L[s]["max"] <= 0 and s not in ("pa", "pm", "po", "invo") \
            and not entame and rel + sacrif < pds(s, qte(s, best[3])):      # petits exos seulement
        f, _ = essais([x for x, y in L.items() if y["max"] > 0 and y["cible"] <= 0 and x not in intouchables
                       and y["val"] < y["max"] and x != s], lambda l: l["max"])
        f = [k for k in f if L[k[2]]["val"] + qte(k[2], k[3]) <= L[k[2]]["max"]]
        if f:
            return sortie(max(f), "CARBURANT", sans)
    r = joue(best, "EXO" if L[s]["max"] <= 0 else "OVER")     # (over non voulu, Vita 205/200 : gere d'abord)
    r["texte"] += coince_txt
    return r


# ---------------------------------------------------------------- lecture d'ecran
class Ocr:
    def __init__(self):
        self.mode, self.eng = None, None
        self.verrou = threading.RLock()    # la lecture tourne dans un fil, le guide dans un autre : un seul a la fois
        for mod in ("rapidocr_onnxruntime", "rapidocr"):
            try:
                self.eng = __import__(mod).RapidOCR()
                self.mode = "rapid"
                return
            except Exception:
                pass
        try:
            import pytesseract
            pytesseract.get_tesseract_version()
            self.eng, self.mode = pytesseract, "tess"
        except Exception:
            sys.exit("Aucun moteur de lecture : pip install rapidocr-onnxruntime")

    def ligne(self, bgr, chiffres=False):
        """Lit une seule ligne de texte clair sur fond sombre."""
        if chiffres:                      # recadre serre sur le nombre
            g = bgr.max(axis=2).astype(int)
            clair = np.argwhere(g > np.median(g) + 40)
            if len(clair) < 4:
                return ""
            (ya, xa), (yb, xb) = clair.min(axis=0), clair.max(axis=0)
            bgr = bgr[max(0, ya - 2):yb + 3, max(0, xa - 2):xb + 3]
        k = 48 / bgr.shape[0]
        img = cv2.resize(bgr, None, fx=k, fy=k, interpolation=cv2.INTER_CUBIC)
        img = cv2.copyMakeBorder(img, 8, 8, 8, 8, cv2.BORDER_REPLICATE)
        with self.verrou:
            return self._ligne(img, chiffres)

    def _ligne(self, img, chiffres):
        if self.mode == "tess":
            g = 255 - img.max(axis=2)
            if chiffres:
                txt = ""
                for psm in (8, 10, 7):
                    txt = txt or self.eng.image_to_string(
                        g, config=f"--psm {psm} -c tessedit_char_whitelist=0123456789").strip()
            else:
                txt = self.eng.image_to_string(g, config="--psm 7")
        else:
            txt = " ".join(self._textes(self.eng(img, use_det=False, use_cls=False, use_rec=True)))
        return re.sub(r"\D", "", txt) if chiffres else txt.strip()

    def tout(self, bgr):
        """Tous les textes d'une image : [(texte, x gauche, y centre)]. Lent : a appeler rarement."""
        out = []
        try:
            self.verrou.acquire()
            if self.mode == "tess":
                d = self.eng.image_to_data(255 - bgr.max(axis=2), config="--psm 11", output_type=self.eng.Output.DICT)
                for t, x, y, h in zip(d["text"], d["left"], d["top"], d["height"]):
                    if t.strip():
                        out.append((t.strip(), x, y + h / 2))
            else:
                res = self.eng(bgr)
                if hasattr(res, "txts"):
                    paires = zip(res.boxes if res.boxes is not None else [], res.txts or [])
                else:
                    paires = ((i[0], i[1]) for i in ((res[0] if isinstance(res, tuple) else res) or []))
                for boite, t in paires:
                    xs, ys = [p[0] for p in boite], [p[1] for p in boite]
                    out.append((str(t).strip(), min(xs), (min(ys) + max(ys)) / 2))
        except Exception as err:
            log(f"lecture complete impossible : {err}")
        finally:
            self.verrou.release()
        return out

    def _textes(self, res):
        """Garde le texte de chaque element lu, pas son score ni ses coordonnees."""
        if hasattr(res, "txts"):
            return [t for t in (res.txts or []) if t]
        if isinstance(res, tuple):
            res = res[0]
        out = []
        for item in res or []:
            if isinstance(item, str):
                out.append(item)
            elif isinstance(item, (list, tuple)):
                txt = next((e for e in item if isinstance(e, str)), None)
                if txt:
                    out.append(txt)
        return out


COLS = {"base": 0.810, "pa": 0.880, "ra": 0.947}   # centre des cases de runes / largeur de ligne


_COUL = [None]     # couleur de fond des lignes, trouvee automatiquement (depend du theme)


_GEOM = [[]]        # geometrie de reference du tableau en cours (toutes ses lignes)
_COUL_REF = [None]  # couleur de fond des lignes de ce tableau
_ABSENT = {}        # lignes sans texte lisible : nombre d'images de suite
_OCCULTES = set()   # lignes non detectees par leur couleur sur l'image en cours (survol, clic, infobulle)


def trouver_lignes(bgr):
    """Lignes du tableau.  Une fois le tableau vu, ses lignes gardent leur place : une ligne survolee ou
    cliquee change de fond et n'est plus detectee par sa couleur, mais elle est toujours la.  Elle n'est
    retiree que si sa place reste vide de texte 15 images de suite, ou si les autres lignes ont bouge."""
    _OCCULTES.clear()
    prec = _GEOM[0]

    def meme(a, b):
        # a = ligne vue sur cette image, b = ligne de reference ; a peut etre raccourcie par une infobulle
        return abs(a[0] - b[0]) <= 3 and abs(a[1] - b[1]) <= 3 and a[2] <= b[2] + 4

    if prec and _COUL_REF[0] is not None:
        vues = _lignes_de_couleur(bgr, _COUL_REF[0])
        if vues and len(vues) <= len(prec) and all(any(meme(r, q) for q in prec) for r in vues):
            garde = []
            for q in prec:
                if any(meme(r, q) for r in vues):
                    _ABSENT.pop(q, None)
                    garde.append(q)
                    continue
                x, y, w, h = q
                if encre(bgr[y + int(.12 * h):y + int(.88 * h), x + int(.245 * w):x + int(.63 * w)]) is not None:
                    _ABSENT.pop(q, None)
                else:
                    _ABSENT[q] = _ABSENT.get(q, 0) + 1
                if _ABSENT.get(q, 0) < 15:
                    garde.append(q)
                    _OCCULTES.add(q)
            _GEOM[0] = garde
            _COUL[0] = _COUL_REF[0]
            rows = list(garde)
        else:
            rows = None
    else:
        rows = None
    if rows is None:                         # premier passage, autre tableau, ou lignes deplacees
        rows = _completer(bgr, _trouver_lignes(bgr))
        _ABSENT.clear()
        _GEOM[0] = list(rows)
        _COUL_REF[0] = None if _COUL[0] is None or not rows else _COUL[0].copy()
    if _COUL[0] is not None:                 # ligne recouverte en partie : ses bords ne sont plus unis
        for x, y, w, h in rows:
            for yy in (y + 4, y + h - 5):
                bande = bgr[yy, x + int(.03 * w):x + int(.97 * w)].astype(int)
                if bande.size and (np.abs(bande - _COUL[0]).max(axis=1) <= 14).mean() < .9:
                    _OCCULTES.add((x, y, w, h))
    return rows


def _completer(bgr, rows):
    """Ajoute les lignes que leur couleur n'a pas revelees : la ligne selectionnee (cadre vert, fond plus
    clair) ou survolee au moment ou le tableau est (re)decouvert. Les lignes sont espacees regulierement :
    on teste chaque place libre de la grille, au-dessus, au milieu et en dessous."""
    if len(rows) < 2:
        return rows
    x, _, w, h = rows[0]
    pas = min(b[1] - a[1] for a, b in zip(rows, rows[1:]))
    if pas < h:
        return rows
    H, W = bgr.shape[:2]

    def boite(y):
        if y < 0 or y + h > H or x < 14 or x + w > W:
            return False
        dedans = np.median(bgr[y + 5:y + h - 5, x + 4:x + 11].reshape(-1, 3), axis=0)
        dehors = np.median(bgr[y + 5:y + h - 5, x - 13:x - 5].reshape(-1, 3), axis=0)
        if np.abs(dedans - dehors).max() < 10:
            return False                             # pas de rectangle ici (en-tete, vide)
        return encre(bgr[y + int(.12 * h):y + int(.88 * h), x + int(.245 * w):x + int(.63 * w)]) is not None

    ys = sorted(r[1] for r in rows)
    plus = []
    for a, b in zip(ys, ys[1:]):                     # trous au milieu
        n = int(round((b - a) / pas))
        plus += [int(round(a + (b - a) * i / n)) for i in range(1, n) if boite(int(round(a + (b - a) * i / n)))]
    for sens, depart in ((-1, ys[0]), (1, ys[-1])):  # au-dessus et en dessous
        y = depart + sens * pas
        while len(plus) < 6 and boite(int(round(y))):
            plus.append(int(round(y)))
            y += sens * pas
    return sorted(rows + [(x, y, w, h) for y in plus], key=lambda r: r[1])


def _trouver_lignes(bgr):
    """Rectangles (x, y, w, h) des lignes du tableau, quels que soient la resolution et le theme."""
    if _COUL[0] is not None:
        rows = _lignes_de_couleur(bgr, _COUL[0])
        if len(rows) >= 3:
            return rows
    q = (bgr[::3, ::3] >> 2).reshape(-1, 3).astype(np.int32)
    cles, nb = np.unique(q[:, 0] << 12 | q[:, 1] << 6 | q[:, 2], return_counts=True)
    meilleur = []
    for k in cles[np.argsort(-nb)[:14]]:
        coul = np.array([k >> 12, (k >> 6) & 63, k & 63]) * 4 + 2
        if coul.max() < 30 or coul.min() > 200:      # ni noir ni blanc
            continue
        rows = _lignes_de_couleur(bgr, coul)
        if len(rows) > len(meilleur):
            meilleur, _COUL[0] = rows, coul
    return meilleur if len(meilleur) >= 3 else []


def _lignes_de_couleur(bgr, coul):
    masque = cv2.inRange(bgr, np.clip(coul - 9, 0, 255).astype(np.uint8),
                         np.clip(coul + 9, 0, 255).astype(np.uint8))
    n, _, st, _ = cv2.connectedComponentsWithStats(masque, connectivity=4)
    cands = [tuple(int(v) for v in st[i][:4]) for i in range(1, n)
             if st[i][2] >= 200 and 8 <= st[i][2] / max(1, st[i][3]) <= 30
             and st[i][4] > 0.5 * st[i][2] * st[i][3]]
    if not cands:
        return []
    meilleur = []
    for x, _, w, _ in cands:      # groupe le plus nombreux de meme x et meme largeur
        g = [c for c in cands if abs(c[0] - x) <= 0.02 * w and abs(c[2] - w) <= 0.03 * w]
        if len(g) > len(meilleur):
            meilleur = g
    rows = sorted(meilleur, key=lambda c: c[1])
    # Une infobulle du jeu (survol d'une rune) recouvre le bout droit de plusieurs lignes : elles paraissent
    # plus courtes. Une ligne ne peut qu'etre raccourcie, jamais allongee : la vraie largeur est la plus
    # grande vue a ce meme x, et les lignes entieres rejoignent le groupe.
    if rows:
        x0, h0 = rows[0][0], rows[0][3]
        freres = [c for c in cands if abs(c[0] - x0) <= 3 and abs(c[3] - h0) <= 3 and c[2] >= rows[0][2]]
        large = max(c[2] for c in freres)
        if large > rows[0][2] + 4:
            ys = {}
            for c in rows + freres:
                ys.setdefault(c[1], (x0, c[1], large, h0))
            rows = sorted(ys.values(), key=lambda c: c[1])
    if len(rows) >= 2:            # bouche les trous (ligne masquee par une infobulle)
        pas = min(b[1] - a[1] for a, b in zip(rows, rows[1:]))
        plein = [rows[0]]
        for r in rows[1:]:
            k = round((r[1] - plein[-1][1]) / pas)
            for i in range(1, k):
                p = plein[-1]
                plein.append((p[0], int(p[1] + pas), p[2], p[3]))
            plein.append(r)
        rows = plein
    return rows


# ---- lecteur de chiffres maison : gabarits de la police du jeu (fm_chiffres.npz)
CW, CH = 32, 28


def _runs(on):
    idx, out = np.flatnonzero(on), []
    if len(idx):
        s = p = idx[0]
        for i in idx[1:]:
            if i != p + 1:
                out.append((int(s), int(p)))
                s = i
            p = i
        out.append((int(s), int(p)))
    return out


def encre(zone):
    """Carte d'encre 0..1 (texte sur fond uni), cadre de survol efface. None si zone vide."""
    z = zone.astype(np.float32)
    d = np.abs(z - np.median(z.reshape(-1, 3), axis=0)).max(axis=2)
    if d.size == 0 or d.max() < 50:
        return None
    e = np.clip(d / d.max(), 0, 1)
    fort = e > .5
    lig, col = fort.mean(axis=1) > .5, fort.mean(axis=0) > .6
    e[lig, :] = 0
    r = max(2, round(.11 * e.shape[0]))
    for c in np.flatnonzero(col):
        e[:, max(0, c - r):c + r + 1] = 0
    return e


def _canevas(g):
    k = CH / g.shape[0]
    g = cv2.resize(g, (max(1, min(CW, round(g.shape[1] * k))), CH), interpolation=cv2.INTER_LINEAR)
    c = np.zeros((CH, CW), np.float32)
    o = (CW - g.shape[1]) // 2
    c[:, o:o + g.shape[1]] = g
    return c


class Chiffres:
    def __init__(self):
        d = np.load(os.path.join(ICI, "fm_chiffres.npz"))
        self.lab = [str(x) for x in d["lab"]]
        g = d["gab"].reshape(len(self.lab), -1).astype(np.float32)
        g -= g.mean(axis=1, keepdims=True)
        self.gab = g / (np.linalg.norm(g, axis=1, keepdims=True) + 1e-6)
        self.douteux, self.marge = 0, 1.0

    def classer(self, g, dump=True):
        v = _canevas(g).ravel()
        v -= v.mean()
        sc = self.gab @ (v / (np.linalg.norm(v) + 1e-6))
        i = int(sc.argmax())
        autres = [x for j, x in enumerate(sc) if self.lab[j] != self.lab[i]]
        self.marge = float(sc[i] - max(autres)) if autres else 1.0     # ecart avec le 2e chiffre possible
        if dump and (sc[i] < .75 or sc[i] < .86 and self.marge < .02) and self.douteux < 150:          # garde une trace pour ameliorer les gabarits
            self.douteux += 1
            try:
                d = os.path.join(ICI, "fm_douteux")
                os.makedirs(d, exist_ok=True)
                cv2.imwrite(os.path.join(d, f"{self.lab[i].replace('%', 'p')}_{sc[i]:.2f}_{self.douteux}.png"),
                            (_canevas(g) * 255).astype(np.uint8))
            except OSError:
                pass
        return self.lab[i], float(sc[i])

    def nombre(self, e, glyphes, penche=0.0, dump=True, seuil=.6):
        """Texte ('374', '4%', '-8') d'un groupe de glyphes (x0, x1), ou None si incertain."""
        if not glyphes:
            return None
        lignes = np.flatnonzero((e[:, glyphes[0][0]:glyphes[-1][1] + 1] > .5).any(axis=1))
        y0, y1 = lignes[0], lignes[-1]
        txt = ""
        for a, b in glyphes:
            yy = np.flatnonzero((e[y0:y1 + 1, a:b + 1] > .5).any(axis=1))
            if len(yy) == 0:
                return None
            if np.ptp(yy) + 1 < .35 * (y1 - y0 + 1):
                if txt:
                    return None
                txt = "-"
                continue
            g = e[y0:y1 + 1, max(0, a - 3):b + 4] if penche else e[y0:y1 + 1, a:b + 1]
            if penche:                         # redresse l'italique
                hh = g.shape[0]
                g = cv2.warpAffine(g, np.float32([[1, penche, -penche * hh / 2], [0, 1, 0]]),
                                   (g.shape[1], hh))
                cc = np.flatnonzero((g > .4).any(axis=0))
                if len(cc) == 0:
                    return None
                g = g[:, cc[0]:cc[-1] + 1]
            ch, sc = self.classer(g, dump)
            if not penche and sc < .8 and g.shape[1] > .9 * g.shape[0]:
                # deux chiffres colles (« 33 » d'Initiative 333 lu comme un seul glyphe) : on coupe a la
                # colonne la plus vide du milieu et on lit chaque moitie
                wg = g.shape[1]
                m0, m1 = int(.3 * wg), int(.7 * wg)
                cut = m0 + int(np.argmin(g[:, m0:m1].sum(axis=0)))
                deux = []
                for part in (g[:, :cut], g[:, cut:]):
                    cc = np.flatnonzero((part > .4).any(axis=0))
                    if len(cc) == 0:
                        break
                    deux.append(self.classer(part[:, cc[0]:cc[-1] + 1], dump))
                if len(deux) == 2 and all(x[1] >= .8 and x[0].isdigit() for x in deux):
                    txt += deux[0][0] + deux[1][0]
                    continue
            if sc < seuil or not penche and sc < .86 and self.marge < .02:
                return None                    # 5 ou 8 ? (ligne survolee par la souris) : pas de valeur au hasard.
                                               # Pas pour le reliquat (italique) : ses chiffres sont toujours moins nets
            txt += ch
        return txt


class Noms:
    """Memoire des noms de stats deja lus, reconnus ensuite par leur forme (rapide)."""

    def __init__(self):
        self.noms, self.larg, self.vec = [], [], np.zeros((0, 16 * 96), np.float32)
        self.icone = np.zeros((0, 3), np.float32)
        try:
            d = np.load(F_NOMS)
            self.noms, self.larg = [str(x) for x in d["noms"]], [int(x) for x in d["larg"]]
            self.vec, self.icone = d["vec"].astype(np.float32), d["icone"].astype(np.float32)
            # purge les anciens « nom illisible » et les noms incomplets qui ne designent pas une seule stat
            # (« Résistance », « Resistan ce » : ils faisaient lire la ligne Eau comme une 2e ligne Feu)
            garde = [i for i, n in enumerate(self.noms) if n and code_stat(n, False)]
            if len(garde) < len(self.noms):
                self.noms, self.larg = [self.noms[i] for i in garde], [self.larg[i] for i in garde]
                self.vec, self.icone = self.vec[garde], self.icone[garde]
        except (OSError, KeyError, ValueError):
            pass
        self.vides = []          # lectures ratees recentes (largeur, forme, icone, heure) : jamais enregistrees

    @staticmethod
    def _vecteur(e, n0, n1):
        g = e[:, n0:n1 + 1]
        yy = np.flatnonzero((g > .5).any(axis=1))
        if len(yy) == 0:
            return None
        v = cv2.resize(g[yy[0]:yy[-1] + 1], (96, 16), interpolation=cv2.INTER_AREA).ravel()
        v = v - v.mean()
        return v / (np.linalg.norm(v) + 1e-6)

    def trouver(self, e, n0, n1, icone):
        """Meme forme de texte ET meme couleur d'icone (distingue Feu/Eau, PA/PM)."""
        v = self._vecteur(e, n0, n1)
        if v is None:
            return None
        L = n1 - n0 + 1
        # une lecture ratee n'est retenue que 4 secondes : apres, on relit le nom (infobulle partie, etc.)
        self.vides = [x for x in self.vides if time.time() - x[3] < 4]
        if any(abs(x[0] - L) <= 1 and np.abs(x[2] - icone).max() < 30 and float(x[1] @ v) >= .9 for x in self.vides):
            return ""
        if not self.noms:
            return None
        ok = (np.abs(np.array(self.larg) - L) <= 1) & (np.abs(self.icone - icone).max(axis=1) < 30)
        if not ok.any():
            return None
        sc = np.where(ok, self.vec @ v, -1)
        i = int(sc.argmax())
        return self.noms[i] if sc[i] >= .84 else None

    def ajouter(self, e, n0, n1, icone, nom):
        v = self._vecteur(e, n0, n1)
        if v is None:
            return
        if not nom:
            self.vides.append((n1 - n0 + 1, v.astype(np.float32), np.float32(icone), time.time()))
            return
        self.noms.append(nom)
        self.larg.append(n1 - n0 + 1)
        self.vec = np.vstack([self.vec, v[None].astype(np.float32)])
        self.icone = np.vstack([self.icone, np.float32(icone)[None]])
        try:
            np.savez_compressed(F_NOMS, noms=np.array(self.noms), larg=np.array(self.larg), vec=self.vec,
                                icone=self.icone)
        except OSError:
            pass


NOMS_VUS = Noms()


def lire_ligne(bgr, rect, ocr, cache, chiffres):
    x, y, w, h = rect
    ya, yb = y + int(.12 * h), y + int(.88 * h)

    def entier(f0, f1):
        e = encre(bgr[ya:yb, x + int(f0 * w):x + int(f1 * w)])
        if e is None:
            return 0
        rr = _runs((e > .5).any(axis=0))
        if len(rr) == 1 and np.ptp(np.flatnonzero((e[:, rr[0][0]:rr[0][1] + 1] > .5).any(axis=1))) <= .2 * e.shape[0]:
            return 0                                # un simple tiret : ligne d'exo, sans min ni max
        t = chiffres.nombre(e, rr)
        return int(t) if t and t.lstrip("-").isdigit() else None

    xa = x + int(.245 * w)
    zone = bgr[ya:yb, xa:x + int(.63 * w)]
    e = encre(zone)
    if e is None:
        return None
    runs = [(a, b) for a, b in _runs((e > .5).any(axis=0))
            if b > a or e[:, a].max() >= .75]          # un pixel isole et pale n'est pas un caractere
    if len(runs) < 2:
        return None
    # l'icone : tout ce qui commence dans sa zone (les chiffres demarrent plus a droite), plus les blocs
    # colles a elle ; une icone sombre se lit en plusieurs morceaux
    k = 0
    while k + 1 < len(runs) and (runs[k + 1][0] < .036 * w or runs[k + 1][0] - runs[k][1] < .1 * h):
        k += 1
    if k + 1 >= len(runs):
        return None
    i0, i1 = runs[0][0], runs[k][1]
    runs = runs[k:]
    pix = zone[:, i0:i1 + 1][e[:, i0:i1 + 1] > .5]
    icone = pix.mean(axis=0) if len(pix) else np.zeros(3)
    runs = runs[1:]
    val = [runs[0]]
    for a, b in runs[1:]:
        if a - val[-1][1] > .11 * h:
            break
        val.append((a, b))
    txt = chiffres.nombre(e, val)
    if not txt:
        return None
    pct = txt.endswith("%")
    txt = txt.rstrip("%")
    if not txt.lstrip("-").isdigit() or "%" in txt:
        return None
    # le nom est renormalise a part : la couleur de la valeur (blanc, vert, rouge) ou de l'icone
    # ne doit pas changer sa forme lue
    d0 = val[-1][1] + 1
    nom_e = e[:, d0:]
    if nom_e.size == 0 or nom_e.max() < .2:
        return None
    nom_e /= nom_e.max()
    reste = [(a + d0, b + d0) for a, b in _runs((nom_e > .5).any(axis=0))]
    if not reste:
        return None
    mots = [[reste[0]]]
    for a, b in reste[1:]:
        if a - mots[-1][-1][1] > .11 * h:
            mots.append([])
        mots[-1].append((a, b))
    if len(mots) >= 3 and len(mots[0]) == 1 and len(mots[1]) <= 3 \
            and (chiffres.nombre(e, mots[1], dump=False, seuil=.85) or "").isdigit():
        return None                                 # "7 a 16 dommages Neutre" : degats d'arme
    n0, n1 = reste[0][0], reste[-1][1]
    nom = NOMS_VUS.trouver(e, n0, n1, icone)
    if nom is None:
        # nom jamais vu : lecture lente une seule fois, du plus court au plus long
        nom = ""
        for g in (max(0, n0 - 4), max(0, val[0][0] - 4), None):
            img = zone[:, g:n1 + 5] if g is not None else bgr[ya:yb, x + int(.02 * w):xa + n1 + 5]
            nom = re.sub(r"^[^A-Za-z]+|[^A-Za-z\u00c0-\u00ff]+$", "", ocr.ligne(img))
            if code_stat(nom, False):
                break
        if re.match(r"^[a\u00e0]\s*\d", nom):            # "7 a 16 dommages Neutre" : ligne de degats d'arme
            nom = "(arme)"
        if not code_stat(nom, False) and nom != "(arme)":
            # une infobulle du jeu deborde sur le nom ("Agilite PRIX MOYEN...") : on reessaie avec le debut
            mots = nom.split()
            for k in range(len(mots) - 1, 0, -1):
                if len(norm(" ".join(mots[:k]))) >= 4 and code_stat(" ".join(mots[:k]), False):
                    nom = " ".join(mots[:k])
                    break
        if not code_stat(nom, False) or nom == "(arme)":
            log(f"ligne ignoree (pas une stat connue) : '{nom}'")
            nom = ""
        NOMS_VUS.ajouter(e, n0, n1, icone, nom)
    code = code_stat(nom, pct) if nom else None
    mini, maxi = entier(.02, .11), entier(.12, .22)
    # un exo est ecrit en bleu dans le jeu (les stats naturelles en vert) : signe plus sur que les tirets
    pix_nom = zone[:, n0:n1 + 1][e[:, n0:n1 + 1] > .5]
    c_nom = pix_nom.mean(axis=0) if len(pix_nom) else np.zeros(3)
    bleu = bool(c_nom[0] > c_nom[1] + 30 and c_nom[0] > c_nom[2] + 60)
    if bleu:
        mini = maxi = 0
    if not code:
        # nom illisible mais ligne sans min ni max : c'est un exo pose sur l'item. lire_ecran lui donnera
        # le code de l'exo demande dans l'objectif (ex. le 1er % dommages aux sorts).
        if (bleu or mini == 0 and maxi == 0) and int(txt) > 0:
            return "?", {"nom": "?", "min": 0, "max": 0, "val": int(txt), "dispo": [], "rect": rect}
        return None
    if maxi is None:
        return None
    if maxi > 0 and int(txt) > plafond(code, maxi):
        return None                                 # 6116 en Ré feu (max 7) : chiffres colles a autre chose, pas une valeur
    dispo = _dispo(bgr, rect, code)
    return code, {"nom": nom_code(code), "min": mini or 0, "max": maxi, "val": int(txt), "dispo": dispo,
                  "stock": _stocks(bgr, rect, dispo, chiffres), "rect": rect}


def _dispo(bgr, rect, code):
    x, y, w, h = rect
    dispo = []
    for t in tailles(code):
        f = COLS[t]
        cx, cy, r = int(x + f * w), y + h // 2, int(.25 * h)
        case = cv2.cvtColor(bgr[cy - r:cy + r, cx - r:cx + r], cv2.COLOR_BGR2GRAY)
        if case.size and case.std() > 14:
            dispo.append(t)
    return dispo


def _stocks(bgr, rect, dispo, chiffres):
    """Nombre de runes affiche dans chaque case (chiffres blancs en haut de la case) : {taille: n}."""
    x, y, w, h = rect
    out = {}
    for t in dispo:
        cx, r = int(x + COLS[t] * w), int(.52 * h)
        m = bgr[y + 1:y + int(.60 * h), max(0, cx - r):cx + r].min(axis=2) >= 200
        if m.sum() < 6:
            continue
        runs = [(a, b) for a, b in _runs(m.any(axis=0)) if m[:, a:b + 1].sum() >= 4]
        txt = chiffres.nombre(m.astype(np.float32), runs, dump=False, seuil=.5) if runs else None
        if txt and txt.isdigit():
            out[t] = int(txt)
    return out


# ---- stock de runes et liste d'achats (conseil seulement : c'est toi qui achetes)
F_STOCK = os.path.join(ICI, "fm_stock.json")
F_NOMS_HDV = os.path.join(ICI, "fm_noms_hdv.json")   # noms de runes de l'hotel de vente deja lus, reconnus par leur forme
F_FILE = os.path.join(ICI, "fm_file.json")        # file d'attente des prochains items (noms)
STOCK_ALERTE, STOCK_CIBLE = 20, 100          # par defaut : alerte sous 20 runes, racheter pour remonter a 100
_RUNES_VUES = set()                          # runes deja vues en stock (pour reperer une case qui se vide)


def nom_rune(s, t):
    return ("" if t == "base" else t.capitalize() + " ") + nom_code(s)


_ACHATS_PREC = []


def ravito_actif(regl):
    """Interrupteur « Conseils de ravitaillement » (onglet Stock de runes) : actif sauf s'il a ete coupe."""
    return (regl or {}).get("_ravito", {}).get("actif", True)


def lignes_stock(lignes, conf=None, stocks=None):
    """Vue stock des lignes naturelles et des exos demandes (stock inconnu hors tableau)."""
    out = dict(lignes or {})
    demandes = dict((conf or {}).get("exos", {}))
    petit = (conf or {}).get("petit_exo")
    if petit in PETITS_EXOS:
        demandes[petit] = 1
    for code, cible in demandes.items():
        if cible > 0 and code in POIDS and code not in out:
            out[code] = {"dispo": [], "stock": {}, "exo_stock": True}
            n = (stocks or {}).get(code)
            if isinstance(n, int) and not isinstance(n, bool) and n >= 0:
                out[code]["dispo"], out[code]["stock"] = ["base"], {"base": n}
    return out


def stocks_plan_suffisants(plan, etat, regl):
    """Annuler un depart obsolete seulement sur des stocks effectivement relus."""
    if not plan or not etat:
        return False
    for a in plan:
        cle=a.get("cle", "")
        if "/" not in cle:
            return False
        s,t=cle.split("/",1)
        r=(regl or {}).get(cle,{})
        if r.get("actif",True) is False or r.get("alerte",STOCK_ALERTE) <= 0:
            continue
        l=etat.get("lignes",{}).get(s,{})
        if not l or l.get("rate") or l.get("occulte"):
            return False
        n=l.get("stock",{}).get(t)
        if not isinstance(n,int) or isinstance(n,bool) or n < 0:
            return False
        if n < r.get("alerte",STOCK_ALERTE) and n < r.get("cible",STOCK_CIBLE):
            return False
    return True


RUNES_SAUTEES = {}      # rune -> (stock au moment du refus, heure) : pas de nouveau ravitaillement tant que rien ne change
SAUT_DUREE = 1800


def liste_achats(lignes, regl):
    out = []
    for x in _liste_achats_brut(lignes, regl):
        s = RUNES_SAUTEES.get(x["rune"])
        if s and s[0] == x["stock"] and time.time() - s[1] < SAUT_DUREE:
            continue
        RUNES_SAUTEES.pop(x["rune"], None)
        out.append(x)
    return out


def _liste_achats_brut(lignes, regl):
    """Runes de l'item en cours passees sous leur seuil d'alerte : [{rune, stock, acheter, lots, prix, budget}].
    regl : {"stat/taille": {"alerte": n, "cible": n, "prix": kamas par rune}} ; alerte 0 = rune non suivie."""
    out = []
    if not any(l.get("dispo") for l in lignes.values()):
        return out                                   # aucune case de rune visible : l'onglet Ressources n'est pas actif
    connues = [(s, t) for s, l in lignes.items() if s in POIDS for t in tailles(s) if f"{s}/{t}" in _RUNES_VUES]
    parties = [c for c in connues if c[1] not in lignes[c[0]].get("dispo", ())]
    if len(parties) >= 2 and 2 * len(parties) > len(connues):
        # Plus de la moitie des cases de runes ont disparu d'un coup : une fenetre cache le tableau (ou il se
        # redessine). Ce n'est pas un stock vide : on garde la derniere liste fiable.
        return [a for a in _ACHATS_PREC if regl.get(a.get("cle"), {}).get("actif", True) is not False]
    for s, l in lignes.items():
        if s not in POIDS or s == "?" or l.get("occulte") or l.get("rate"):
            continue                                 # ligne survolee, selectionnee ou non relue : chiffres peu fiables
        for t in tailles(s):
            cle = f"{s}/{t}"
            if t in l.get("dispo", ()):
                n = l.get("stock", {}).get(t)
                if n is None:
                    continue                         # nombre illisible sur cette image
                _RUNES_VUES.add(cle)
            elif l.get("exo_stock") and t == "base":
                continue  # stock inconnu : recherche inventaire avant tout parcours
            elif cle in _RUNES_VUES:
                n = 0                                # case observee sur l'item courant puis videe
            else:
                continue
            r = regl.get(cle, {})
            if r.get("actif", True) is False:
                continue
            alerte, cible = int(r.get("alerte", STOCK_ALERTE)), int(r.get("cible", STOCK_CIBLE))
            if alerte <= 0 or n >= alerte or cible <= n:
                continue
            q = -(-(cible - n) // 10) * 10           # jamais a l'unite : arrondi au lot de 10 superieur
            prix = r.get("prix")
            lots = [f"{k}×{t_}" for k, t_ in ((q // 1000, 1000), (q % 1000 // 100, 100), (q % 100 // 10, 10)) if k]
            out.append({"cle": cle, "rune": nom_rune(s, t), "stock": n, "acheter": q, "lots": " + ".join(lots),
                        "recherche": recherche_rune(s, t, regl),
                        "prix": prix, "budget": q * prix if prix else None,
                        "verifier_stock": True, "alerte": alerte, "cible": cible})
    _ACHATS_PREC[:] = sorted(out, key=lambda a: a["stock"])
    return list(_ACHATS_PREC)


PETITS_EXOS = ("agi", "fo", "int", "cha", "ini")   # 1 de puits chacun (Ini : +10)
RUNES_APPRISES = set()   # runes d'exo dont l'image est apprise (dossier fm_runes)
_EXOS_ATTENDUS = []     # exos demandes dans l'objectif de l'item en cours (pour nommer une ligne d'exo illisible)


def lire_reliquat(bgr, rows, chiffres):
    """Nombre apres 'reliquat :' au-dessus du tableau (italique). None si illisible."""
    x, y, w, _ = rows[0]
    pas = min(b[1] - a[1] for a, b in zip(rows, rows[1:])) if len(rows) > 1 else rows[0][3] * 1.16
    y0, y1 = max(0, int(y - 3.0 * pas)), max(1, int(y - 1.9 * pas))
    v = _reliquat_zone(bgr, x, w, y0, y1, chiffres)
    if v is not None:
        _REL_ZONE[0] = (x, w, y0, y1)
    elif _REL_ZONE[0] and abs(_REL_ZONE[0][0] - x) <= 3 and abs(_REL_ZONE[0][1] - w) <= 4:
        v = _reliquat_zone(bgr, x, w, _REL_ZONE[0][2], _REL_ZONE[0][3], chiffres)   # derniere zone ou il a ete lu
    return v


_REL_ZONE = [None]


def _reliquat_zone(bgr, x, w, y0, y1, chiffres):
    e = encre(bgr[y0:y1, x:x + int(.27 * w)])
    if e is None:
        return None
    m = e > .5
    runs = _runs(m.any(axis=0))
    if not runs:
        return None
    H = max(np.ptp(np.flatnonzero(m[:, a:b + 1].any(axis=1))) + 1 for a, b in runs)
    garde = [runs[0]]
    for r in runs[1:]:                              # s'arrete au premier grand vide
        if r[0] - garde[-1][1] > 2.5 * H:
            break
        garde.append(r)
    deux = [i for i, (a, b) in enumerate(garde)     # le deux-points : deux petits blocs superposes
            if b - a + 1 <= .45 * H and len(_runs(m[:, a:b + 1].any(axis=1))) == 2]
    if not deux or deux[-1] + 1 >= len(garde):
        return None
    xa, xb = garde[deux[-1] + 1][0], garde[-1][1]
    sous = (m[:, xa:xb + 1] * 255).astype(np.uint8)
    n, _, st, _ = cv2.connectedComponentsWithStats(sous, connectivity=8)
    comps = sorted((tuple(int(v) for v in st[i][:4]) for i in range(1, n)))    # le point decimal peut ne faire qu'un pixel
    txt = ""
    for cx, cy, cw, ch_ in comps:
        if ch_ < .45 * H:
            lig = np.flatnonzero(m.any(axis=1))
            pos = (cy + ch_ / 2 - lig[0]) / max(1, lig[-1] - lig[0])     # 0 = haut du texte, 1 = bas
            if pos > .7:
                txt += "." if txt and "." not in txt else ""
            elif .3 < pos < .7 and cw >= 2:
                txt += "-" if not txt else ""
            continue
        # deux chiffres italiques qui se touchent (« 44 » de 44.8) forment un seul bloc : on le coupe en
        # autant de chiffres que sa largeur en contient (un chiffre fait environ 0,55 x la hauteur du texte)
        k_ = max(1, round(cw / (.55 * H)))
        bornes = [round(cw * i / k_) for i in range(k_ + 1)]
        for a_, b_ in zip(bornes, bornes[1:]):
            sub = np.zeros_like(e)
            sub[:, xa + cx + a_:xa + cx + b_] = e[:, xa + cx + a_:xa + cx + b_]
            sub[:max(0, cy - 1)] = 0
            sub[cy + ch_ + 1:] = 0
            sub = sub[:, xa + cx + a_:xa + cx + b_]
            t = chiffres.nombre(sub, [(0, b_ - a_ - 1)], penche=.2)
            if not t or not t.isdigit():
                return None
            txt += t
    try:
        return float(txt)
    except ValueError:
        return None


def trouver_popup(bgr):
    """Bouton OK vert d'une fenetre "Attention !" du jeu, ou None."""
    m = cv2.inRange(bgr, np.array([0, 145, 115], np.uint8), np.array([45, 205, 180], np.uint8))
    n, _, st, _ = cv2.connectedComponentsWithStats(m, connectivity=8)
    for i in range(1, n):
        x, y, w, h, aire = (int(v) for v in st[i])
        if w >= 90 and 4 <= w / max(1, h) <= 9 and aire > .75 * w * h:
            return x, y, x + w, y + h
    return None


def trouver_rune(bgr, gab, indice):
    """Position (x, y) du gabarit d'une rune dans l'inventaire affiche, ou None."""
    if gab is None or float(gab.std()) < 25:
        return None                     # gabarit vide (case vide apprise par erreur) : il colle a toutes les cases vides
    gh, gw = gab.shape[:2]
    if indice:
        x0, y0 = max(0, indice[0] - 8), max(0, indice[1] - 8)
        zone = bgr[y0:y0 + gh + 16, x0:x0 + gw + 16]
        if zone.shape[0] >= gh and zone.shape[1] >= gw:
            r = cv2.matchTemplate(zone, gab, cv2.TM_CCOEFF_NORMED)
            _, mx, _, loc = cv2.minMaxLoc(r)
            if mx >= .85:
                return x0 + loc[0], y0 + loc[1]
    r = cv2.matchTemplate(bgr, gab, cv2.TM_CCOEFF_NORMED)
    _, mx, _, loc = cv2.minMaxLoc(r)
    if mx >= .85:
        return int(loc[0]), int(loc[1])
    # La rune a change de case : le bas du gabarit contient le bord de la case d'origine (cadre blanc de la
    # case selectionnee). On reessaie avec le haut du gabarit seulement, plus strictement.
    r = cv2.matchTemplate(bgr, gab[:int(.75 * gh)], cv2.TM_CCOEFF_NORMED)
    _, mx, _, loc = cv2.minMaxLoc(r)
    return (int(loc[0]), int(loc[1])) if mx >= .92 else None


def lire_ecran(bgr, ocr, cache, chiffres):
    rows = trouver_lignes(bgr)
    if not rows:
        return None
    if len(cache) > 4000:
        cache.clear()
    lignes = {}
    inconnues = []
    for r in rows:
        res = lire_ligne(bgr, r, ocr, cache, chiffres)
        if res:
            res[1]["occulte"] = r in _OCCULTES
            if res[0] == "?":
                inconnues.append(res[1])
            else:
                lignes[res[0]] = res[1]
    libres = [c for c in _EXOS_ATTENDUS if c not in lignes]
    if len(inconnues) == 1 and len(libres) == 1:
        d_ = _dispo(bgr, inconnues[0]["rect"], libres[0])
        lignes[libres[0]] = dict(inconnues[0], nom=nom_code(libres[0]), dispo=d_,
                                 stock=_stocks(bgr, inconnues[0]["rect"], d_, chiffres))
    if not lignes:
        return None
    return {"lignes": lignes, "reliquat": lire_reliquat(bgr, rows, chiffres), "rows": rows}


def case_rune(etat, reco):
    """Rectangle ecran de la case a cliquer, ou None (exo a glisser a la main)."""
    l = etat["lignes"].get(reco.get("stat"))
    if not l or reco.get("virtuel") or not l.get("rect") or reco["taille"] not in l["dispo"]:
        return None
    x, y, w, h = l["rect"]
    cx, cy, r = int(x + COLS[reco["taille"]] * w), y + h // 2, int(.42 * h)
    return cx - r, cy - r, cx + r, cy + r


# ---------------------------------------------------------------- fichiers
def charger_txt(chemin):
    try:
        with open(chemin) as f:
            return f.read()
    except OSError:
        return ""


DUREE_MAX = 3600            # au-dela d'une heure, une « duree » est forcement une erreur de mesure


class Bilan:
    """Ce que l'outil constate tout seul sur les points pas encore valides en jeu : ecrit dans fm_bilan.json
    (donnees) et fm_bilan.txt (lisible). Rien n'est envoye nulle part : les fichiers restent dans le dossier."""

    def __init__(self):
        self.f, self.t, self.sale = os.path.join(ICI, "fm_bilan"), 0.0, False
        self.d = charger_json_brut(self.f + ".json") or {}
        self.d.setdefault("depuis", time.strftime("%Y-%m-%d %H:%M"))
        du = self.d.get("durees", {})
        for k in [k for k, e in du.items() if not 0 <= e.get("max", 0) <= DUREE_MAX]:
            du.pop(k)                                # mesure faussee par l'ancien bug (heure systeme) : on la refait
            self.sale = True
        self.t_zero = 0.0
        self.remise_a_zero()

    def remise_a_zero(self):
        """Si le fichier fm_bilan_zero.txt existe, les compteurs repartent de zero (tes avis sont gardes)."""
        drapeau = self.f + "_zero.txt"
        try:
            if os.path.exists(drapeau) and os.path.getsize(drapeau) > 0:
                self.d = {"depuis": time.strftime("%Y-%m-%d %H:%M"), "avis": self.d.get("avis", {}),
                          "systeme": {k: v for k, v in self.d.get("systeme", {}).items() if k != "lectures_hdv_evitees"}}
                self.sale = True
                try:
                    os.remove(drapeau)
                except OSError:                      # impossible a effacer : on le vide, et on l'ignore tant qu'il est vide
                    open(drapeau, "w").close()
        except OSError:
            pass

    def note(self, section, cle, **champs):
        """Compteur +1 sur section/cle, et derniere valeur de chaque champ donne."""
        e = self.d.setdefault(section, {}).setdefault(str(cle), {"n": 0})
        e["n"] += 1
        e["vu"] = time.strftime("%m-%d %H:%M:%S")
        for k, v in champs.items():
            if isinstance(v, bool):
                e[k] = e.get(k, 0) + int(v)            # un booleen se compte (nombre de fois vrai)
            else:
                e[k] = v
        self.sale = True

    def duree(self, quoi, sec):
        if not 0 <= sec <= DUREE_MAX:                # durée impossible (horloge remise à zéro ailleurs) : ignorée
            self.note("erreurs", f"duree ignoree pour {quoi} : {sec:.0f} s")
            return
        e = self.d.setdefault("durees", {}).setdefault(quoi, {"n": 0, "total": 0.0, "max": 0.0})
        e["n"], e["total"], e["max"] = e["n"] + 1, round(e["total"] + sec, 3), round(max(e["max"], sec), 3)
        self.sale = True

    def pose(self, section, cle, valeur):
        self.d.setdefault(section, {})[cle] = valeur
        self.sale = True

    def limites(self):
        """Etat de chaque limite connue, d'apres ce que l'outil a constate : [{n, titre, statut, preuve, test}].
        statut : OK, PROBLÈME, À CONFIRMER (l'outil a vu passer le cas, a toi de dire si c'etait juste),
        NON TESTÉ, PAS CODÉ. Ton avis (boutons de l'onglet Bilan) passe avant le constat automatique."""
        d = self.d
        par, et, rp, fi, ac = d.get("parcours", {}), d.get("etapes", {}), d.get("reperes", {}), d.get("fiches", {}), d.get("achats", {})
        du, pg, sy = d.get("durees", {}), d.get("page", {}), d.get("systeme", {})
        n_ok, n_ko = par.get("OK", {}).get("n", 0), par.get("à vérifier", {}).get("n", 0)
        L = []

        def lim(n, titre, statut, preuve, test):
            avis = d.get("avis", {}).get(str(n))
            L.append({"n": n, "titre": titre, "statut": {"regle": "OK", "probleme": "PROBLÈME"}.get(avis, statut),
                      "auto": statut, "avis": avis, "preuve": preuve, "test": test})

        lim(1, "Ravitaillement complet, fait à la main en suivant les cadres",
            "OK" if n_ok and not n_ko else "PROBLÈME" if n_ko else "À CONFIRMER" if et else "NON TESTÉ",
            f"{n_ok} terminé(s) OK, {n_ko} à vérifier ; étapes vues : {', '.join(sorted(et)) or 'aucune'} sur 7",
            "Laisse une rune passer sous son seuil et suis les 7 étapes sans le mode automatique. Détail dans fm_ravitaillements.txt.")
        at = {k: r for k, r in rp.items() if k in ("cordomager", "multi", "costumager", "joaillomager")}
        lim(2, "Cadre sur le bon atelier au retour",
            "À CONFIRMER" if any(r.get("trouve") for r in at.values()) else "NON TESTÉ",
            ", ".join(f"{k} trouvé {r.get('trouve', 0)}/{r['n']} à {r.get('point')}" for k, r in at.items()) or "aucun atelier cherché",
            "À l'étape 6/7, regarde si le cadre vert est sur l'atelier dont le nom est dans le texte, puis clique Réglé ou Problème ici.")
        lus, reconnus = len(fi), sum(1 for f in fi.values() if f.get("dans_liste"))
        lim(3, "Texte de recherche = nom exact de la rune à l'hôtel de vente",
            "NON TESTÉ" if not reconnus else "OK" if not par.get("introuvable") else "PROBLÈME",
            f"{lus} fiche(s) lue(s), dont {reconnus} reconnue(s) comme rune à acheter : "
            + (", ".join(k for k, f in fi.items() if f.get("dans_liste")) or "aucune")
            + (f" ; introuvable après 2 tris : {par['introuvable'].get('detail')}" if par.get("introuvable") else ""),
            "Ouvre la fiche de chaque rune à acheter. Si l'outil dit « pas dans ta liste », corrige « Texte à taper » dans Stock de runes.")
        regl = charger_json_brut(self.f.replace("fm_bilan", "fm_stock") + ".json") or {}
        sans = [k for k, v in regl.items() if not k.startswith("_") and not v.get("prix")]
        lim(4, "Prix maximum par rune",
            "OK", f"{len(sans)} rune(s) sans prix max (plafond = prix moyen + {regl.get('_marge', {}).get('pct', 20)} %) : "
            + (", ".join(sans[:8]) or "aucune"), "Rien à tester : c'est un choix. Mets un prix dans Stock de runes si tu veux un plafond fixe.")
        lim(5, "Repères hors du Port de givre", "NON TESTÉ", "images de référence : Port de givre seulement",
            "Dans une autre ville, recale chaque repère avec l'onglet Repères (bouton Calibrer).")
        gros = {k: a for k, a in ac.items() if re.search(r"x(\d+)$", k) and int(re.search(r"x(\d+)$", k).group(1)) >= 10}
        lim(6, "Fenêtre « Acheter » lue pour un lot de 10, 100 ou 1000",
            "NON TESTÉ" if not gros else "OK" if all(a.get("lu") and a.get("sens") in ("prix du lot entier", "prix par rune", "unitaire + total cohérents")
                                                     for a in gros.values()) else "PROBLÈME",
            " ; ".join(f"{k} : prix affiché {a.get('prix')}, lot {a.get('prix_lot')} → {a.get('sens')}" for k, a in gros.items())
            or "seulement des lots à l'unité vus" if ac else "aucune fenêtre d'achat vue",
            "Clique ACHETER sur un lot de 10 ou 100 et laisse la fenêtre ouverte 6 secondes avant de confirmer.")
        lim(7, "Rune d'un exo pas encore posé suivie dans le stock", "PAS CODÉ", "", "Rien à tester tant que ce n'est pas codé.")
        fd = du.get("lecture rapide hdv") or du.get("lecture fiche hdv")      # la lecture rapide, quand elle sert
        moy = fd["total"] / max(1, fd["n"]) if fd else None
        lim(8, "Vitesse de lecture de l'hôtel de vente",
            "NON TESTÉ" if moy is None else "OK" if moy <= 1.5 else "PROBLÈME",
            "" if moy is None else f"{fd['n']} lectures, moyenne {moy:.1f} s, pire {fd['max']:.1f} s (visé : 1,5 s) ; "
                                     f"{sy.get('lectures_hdv_evitees', 0)} relectures évitées (écran inchangé)",
            "Se mesure tout seul dès que l'hôtel de vente est ouvert pendant un ravitaillement.")
        lim(9, "Comparaison d'image (OpenCV)", "OK" if sy.get("detecteur") == "SIFT" else "NON TESTÉ" if not sy.get("detecteur") else "À CONFIRMER",
            f"OpenCV {sy.get('opencv', '?')}, détecteur {sy.get('detecteur', 'pas encore utilisé')}", "Se mesure tout seul.")
        lim(10, "Lignes en malus (demi-poids)", "NON TESTÉ", "pas mesurable par l'outil",
            "Sur un item avec une ligne négative, regarde si le conseil « MALUS » est sensé, puis clique Réglé ou Problème ici.")
        lim(11, "Compteur du 2e % : échecs sans perte", "PAS CODÉ", "", "Rien à tester tant que ce n'est pas codé.")
        dec = {k: r for k, r in rp.items() if k in ("sortie", "hdv", "porte")}
        taux = [r.get("trouve", 0) / max(1, r["n"]) for r in dec.values()]
        lim(12, "Repères du décor trouvés (sortie, hôtel de vente, porte)",
            "NON TESTÉ" if not dec else "OK" if min(taux) >= .5 else "PROBLÈME",
            ", ".join(f"{k} {r.get('trouve', 0)}/{r['n']}" for k, r in dec.items())
            + (" — attention : compte aussi les moments où une fenêtre couvrait le jeu" if dec else ""),
            "Fais un ravitaillement sans rien par-dessus le jeu (page de réglages sur le côté), après « Remettre à zéro ».")
        tel = pg.get("commande telephone", {}).get("n", 0) + pg.get("decision telephone", {}).get("n", 0)
        lim(13, "Pages web : réglages sur le PC et sur le téléphone",
            "PROBLÈME" if pg.get("erreur") else "OK" if pg.get("commande") and tel else "À CONFIRMER" if pg.get("ouverte") else "NON TESTÉ",
            f"ouverte {pg.get('ouverte', {}).get('n', 0)} fois, {pg.get('commande', {}).get('n', 0)} commande(s) reçue(s) dont "
            f"{tel} du téléphone, {pg.get('erreur', {}).get('n', 0)} erreur(s)",
            "Enregistre un objectif depuis le PC, puis ajoute un item à la file depuis ton téléphone.")
        lo, lk = par.get("liste OK", {}).get("n", 0), par.get("liste à vérifier", {}).get("n", 0)
        lim(14, "Liste de plusieurs runes achetée de bout en bout, à la main",
            "OK" if lo else "PROBLÈME" if lk else "NON TESTÉ",
            f"{lo} liste(s) OK, {lk} à vérifier" + (f" ; dernière : {par.get('liste OK', par.get('liste à vérifier', {})).get('detail')}"
                                                    if lo or lk else ""),
            "Laisse 2 ou 3 runes passer sous leur seuil et fais tout le ravitaillement à la main.")
        hv = d.get("hdv", {})
        rej, cpl = hv.get("nom rejeté (largeur incohérente)", {}), hv.get("nom complété par la liste", {})
        lim(15, "Noms de runes lus en entier à l'hôtel de vente (le moteur saute parfois un mot)",
            "PROBLÈME" if rej.get("n", 0) > cpl.get("n", 0) + 3 else "À CONFIRMER" if rej or cpl else "NON TESTÉ",
            f"{rej.get('n', 0)} nom(s) rejeté(s), {cpl.get('n', 0)} complété(s) par la liste"
            + (f" ; dernier : {cpl.get('detail') or rej.get('detail')}" if rej or cpl else ""),
            "Cherche une rune au nom long (ex. « rune pa prospe ») : le cadre doit aller sur la bonne ligne.")
        lim(16, "Annuler un ravitaillement / arrêt tout seul s'il n'avance plus", "PAS CODÉ", "",
            "Rien à tester tant que ce n'est pas codé.")
        return L

    def texte(self):
        d, o = self.d, []
        o.append("ÉTAT DES LIMITES")
        for x in self.limites():
            o.append(f"  {x['n']:>2}. [{x['statut']}] {x['titre']}" + (f" (ton avis ; constat de l'outil : {x['auto']})" if x["avis"] else "")
                     + (f" — {x['preuve']}" if x["preuve"] else ""))
        o.append("")

        def verdict(ok, vu=True):
            return "PAS ENCORE VU" if not vu else "OK" if ok else "PROBLEME"

        sy = d.get("systeme", {})
        o.append(f"BILAN DE L'OUTIL — depuis {d.get('depuis')} — écrit {time.strftime('%Y-%m-%d %H:%M:%S')}")
        o.append("Système : " + ", ".join(f"{k} = {v}" for k, v in sy.items()))
        et = d.get("etapes", {})
        o.append("")
        o.append(f"1. RAVITAILLEMENT EN JEU : {verdict(d.get('parcours', {}).get('termine', {}).get('n', 0) > 0, bool(et))}"
                 f" — parcours terminés : {d.get('parcours', {}).get('termine', {}).get('n', 0)}")
        for n in sorted(et):
            e = et[n]
            o.append(f"   étape {n}/7 : vue {e['n']} fois, repère affiché {e.get('cadre', 0)} fois"
                     f"{', repère manquant ' + str(e.get('sans_cadre', 0)) + ' fois' if e.get('sans_cadre') else ''}")
        o.append("   (OK = les étapes se sont enchaînées jusqu'au bout ; si un cadre était au mauvais endroit, ça se voit "
                 "dans les images de fm_parcours, pas ici)")
        rp = d.get("reperes", {})
        o.append("")
        o.append("2 et 5. REPÈRES (comparaison d'image) : " + verdict(all(r.get("trouve", 0) > 0 for r in rp.values()), bool(rp)))
        for k, r in sorted(rp.items()):
            o.append(f"   {k:<13} cherché {r['n']} fois, trouvé {r.get('trouve', 0)} fois"
                     f"{' — ' + verdict(False) if not r.get('trouve') else ''} | dernier point : {r.get('point')}"
                     f" | recalé à la main : {'oui' if r.get('cal') else 'non'}"
                     + ("" if k in REPERES_DECOR else " | interface : « trouvé » non concluant (position par défaut si non reconnu)"))
        fi = d.get("fiches", {})
        o.append("")
        o.append("3. TEXTES DE RECHERCHE (nom lu sur la fiche = texte de ta liste ?) : "
                 + verdict(all(f.get("dans_liste", 0) > 0 for f in fi.values()), bool(fi)))
        for k, f in sorted(fi.items()):
            o.append(f"   « {k} » lue {f['n']} fois, reconnue dans la liste {f.get('dans_liste', 0)} fois | prix moyen "
                     f"{f.get('moyen')} | lots {f.get('lots')} | en inventaire {f.get('qte')} | liste : {f.get('liste')}")
        ac = d.get("achats", {})
        o.append("")
        o.append("6. FENÊTRE « ACHETER » : " + verdict(all(a.get("lu", 0) > 0 for a in ac.values()), bool(ac)))
        for k, a in sorted(ac.items()):
            o.append(f"   {k} : vue {a['n']} fois, lue en entier {a.get('lu', 0)} fois | prix affiché {a.get('prix')} | "
                     f"prix du lot sur la fiche {a.get('prix_lot')} → {a.get('sens')} | conseil : {a.get('conseil')}")
        du = d.get("durees", {})
        o.append("")
        o.append("8. VITESSE : lectures par seconde " + str(sy.get("lectures_s", "?")))
        for k, e in sorted(du.items()):
            o.append(f"   {k:<22} {e['n']} fois, moyenne {e['total'] / max(1, e['n']):.2f} s, pire {e['max']:.2f} s"
                     f"{' — LENT' if e['total'] / max(1, e['n']) > 1 else ''}")
        o.append("")
        o.append(f"9. OPENCV : {sy.get('opencv', '?')}, détecteur {sy.get('detecteur', 'pas encore utilisé')}")
        pg = d.get("page", {})
        o.append("")
        o.append("12. PAGE DE RÉGLAGES : " + verdict(not pg.get("erreur"), bool(pg.get("ouverte")))
                 + f" — ouverture : {sy.get('ouverture_page', '?')}")
        for k, e in sorted(pg.items()):
            o.append(f"   {k:<14} {e['n']} fois, dernière {e.get('vu')}{' | ' + str(e.get('detail')) if e.get('detail') else ''}")
        er = d.get("erreurs", {})
        o.append("")
        o.append(f"ERREURS : {sum(e['n'] for e in er.values())}")
        for k, e in sorted(er.items(), key=lambda kv: -kv[1]["n"]):
            o.append(f"   {e['n']} × {k} (dernière {e.get('vu')})")
        o.append("")
        o.append("Pas mesurable par l'outil : 4 (seuils, c'est ton choix), 7 (rune d'exo pas posé), 10 (malus), "
                 "11 (échecs sans perte).")
        return "\n".join(o)

    def ecrire(self, force=False):
        if time.time() - self.t_zero > 5:
            self.t_zero = time.time()
            self.remise_a_zero()
        if not self.sale or not force and time.time() - self.t < 10:
            return
        self.t, self.sale = time.time(), False
        try:
            with open(self.f + ".json", "w", encoding="utf-8") as f:
                json.dump(self.d, f, indent=1, ensure_ascii=False, default=str)
            with open(self.f + ".txt", "w", encoding="utf-8") as f:
                f.write(self.texte())
        except Exception as err:
            log(f"bilan non ecrit : {err}")


def charger_json_brut(chemin):
    try:
        with open(chemin, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def charger_json(chemin, defaut):
    try:
        with open(chemin, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return defaut


def noter_passe(avant, apres, reco, histo, item=""):
    """Deduit la rune passee et son resultat en comparant deux lectures stables, et l'apprend."""
    A, B = avant["lignes"], apres["lignes"]
    if set(A) != set(B):
        # une ligne a change de nom entre les deux lectures : lecture douteuse... sauf une ligne d'exo (max 0)
        # qui apparait (exo passe) ou disparait (exo perdu), ou une ligne pas relue d'un cote seulement
        # (Initiative 333 mal lue juste apres un PA rate) : on compare les lignes vues des deux cotes
        diff_ = set(A) ^ set(B)
        if any(A.get(x, B.get(x))["max"] != 0 for x in diff_) and len(diff_) > 1:
            return
        A = {x: y for x, y in A.items() if x in B or y["max"] == 0}
        B = {x: y for x, y in B.items() if x in A or y["max"] == 0}
    gains = [s for s in B if s in A and B[s]["val"] > A[s]["val"]]
    gains += [s for s in B if s not in A and B[s]["max"] == 0 and B[s]["val"] > 0]      # exo passe
    pertes = [s for s in A if B.get(s, {"val": 0})["val"] < A[s]["val"]]
    if len(gains) > 1:
        return
    if not gains and not pertes:
        # echec paye en entier par le reliquat : aucune ligne ne bouge, seul le reliquat baisse du poids
        # de la rune (ex. une tentative de % dommages aux sorts dans 37 de reliquat : 37.4 -> 22.4)
        s_, t_ = reco.get("stat"), reco.get("taille")
        if not s_ or avant["reliquat"] is None or apres["reliquat"] is None:
            return
        p_ = pds(s_, qte(s_, t_))
        if not (.5 * p_ <= avant["reliquat"] - apres["reliquat"] <= p_ + .5):
            return
    if gains:
        s = gains[0]
        d = B[s]["val"] - A.get(s, {"val": 0})["val"]
        t = min(MULT, key=lambda k: abs(qte(s, k) - d))
    else:
        s, t = reco.get("stat"), reco.get("taille")
        if not s:
            return
    l = A.get(s, {"max": 0, "val": 0})
    ctx = contexte(s, t, l)
    r0, r1 = avant["reliquat"] or 0, apres["reliquat"] or 0
    i = 2 if not gains else (0 if not pertes and r1 >= r0 else 1)
    histo.setdefault(ctx, [0, 0, 0])[i] += 1
    histo.setdefault(s + "|" + ctx, [0, 0, 0])[i] += 1
    try:
        with open(F_HISTO, "w", encoding="utf-8") as f:
            json.dump(histo, f)
        neuf = not os.path.exists(F_PASSES)
        with open(F_PASSES, "a", encoding="utf-8") as f:
            if neuf:
                f.write("heure;item;stat;taille;situation;avant;max;resultat;pertes;reliquat_avant;"
                        "reliquat_apres;conseil\n")
            perdu = " ".join(f"{x}{B.get(x, {'val': 0})['val'] - A[x]['val']}" for x in pertes)
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')};{item};{s};{t};{ctx};{l['val']};{l['max']};"
                    f"{('SC', 'SN', 'EC')[i]};{perdu};{r0:g};{r1:g};"
                    f"{reco.get('taille', '')} {reco.get('stat', '')}\n")
        # etat complet avant / apres chaque passe : pour comparer ta facon de FM aux conseils de l'outil
        with open(os.path.join(ICI, "fm_passes_detail.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps({"t": time.strftime("%Y-%m-%d %H:%M:%S"), "item": item, "rune": f"{t} {s}",
                                "res": ("SC", "SN", "EC")[i], "rel": [r0, r1],
                                "avant": {x: y["val"] for x, y in A.items()},
                                "apres": {x: y["val"] for x, y in B.items()},
                                "conseil": f"{reco.get('taille', '')} {reco.get('stat', '')}".strip(),
                                "texte": str(reco.get("texte", ""))[:160]}, ensure_ascii=False) + "\n")
    except OSError:
        pass
    log(f"  passe : {t} {s} ({ctx}) -> {('SC', 'SN', 'EC')[i]}")
    return s, t, i


def log(msg):
    print(msg)
    try:
        with open(os.path.join(ICI, "fm_log.txt"), "a", encoding="utf-8") as f:
            f.write(time.strftime("%H:%M:%S ") + msg + "\n")
    except OSError:
        pass


def resume(etat):
    return (tuple(sorted((s, l["val"]) for s, l in etat["lignes"].items())), etat["reliquat"])


# ---------------------------------------------------------------- modes
def mode_image(chemin, ocr, histo):
    bgr = cv2.imread(chemin)
    if bgr is None:
        sys.exit(f"image illisible : {chemin}")
    t = time.time()
    etat = lire_ecran(bgr, ocr, {}, Chiffres())
    if not etat:
        sys.exit("tableau de forgemagie non trouve dans l'image")
    print(f"lecture en {time.time() - t:.2f}s ({ocr.mode}), {len(etat['rows'])} lignes vues")
    for s, l in etat["lignes"].items():
        print(f"  {s:<12}{l['min']:>4}{l['max']:>5}{l['val']:>5}  {'/'.join(l['dispo']):<11} {l['nom']}")
    print("  reliquat :", etat["reliquat"])
    connu = trouver_item(charger_items(), signature(etat["lignes"]))
    print("  item :", connu["nom"] if connu else "inconnu (objectif = max partout)")
    reco = recommander_live(etat, connu or {}, histo)
    print(">>", reco["texte"])
    for x, y, w, h in etat["rows"]:
        cv2.rectangle(bgr, (x, y), (x + w, y + h), (0, 255, 255), 1)
    c = case_rune(etat, reco)
    if c:
        cv2.rectangle(bgr, c[:2], c[2:], (0, 255, 0), 3)
    sortie = os.path.splitext(chemin)[0] + "_debug.png"
    cv2.imwrite(sortie, bgr)
    print("image annotee :", sortie)


# ---------------------------------------------------------------- items et objectifs
def signature(lignes):
    return {(s, l["min"], l["max"]) for s, l in lignes.items() if not l.get("hors")}


def proche(a, b):
    """Part des lignes communes entre deux signatures (0..1)."""
    a, b = set(map(tuple, a)), set(map(tuple, b))
    return len(a & b) / max(1, min(len(a), len(b)))


def charger_items():
    return charger_json(F_ITEMS, {"items": []}).get("items", [])


def trouver_item(items, sig):
    notes = [(proche(it["sig"], sig), i) for i, it in enumerate(items)]
    return items[max(notes)[1]] if notes and max(notes)[0] >= .7 else None


def lire_nom_item(bgr, rows, ocr):
    """Nom de l'item affiche a gauche du tableau (present quand il y a un historique)."""
    try:
        x, y, w, h = rows[0]
        zone = bgr[max(0, int(y - 1.0 * h)):int(y - .3 * h), max(0, int(x - .365 * w)):int(x - .10 * w)]
        if zone.size == 0 or encre(zone) is None:
            return ""
        nom = re.sub(r"[^A-Za-zÀ-ÿ' -]", "", ocr.ligne(zone)).strip(" -'")
        return nom.title() if len(nom) >= 4 else ""
    except Exception:
        return ""


def nom_code(s):
    """Libelle lisible d'un code de stat."""
    if s in NOM_PROPRE:
        return NOM_PROPRE[s]
    fixes = {"pa": "PA", "pm": "PM", "do": "Dommages", "soin": "Soins", "tacle": "Tacle", "fuite": "Fuite",
             "pods": "Pods", "renvoi": "Renvoi dommages", "do_cri": "Do critiques", "do_pou": "Do poussée",
             "do_pieges": "Do pièges", "pui_pieges": "Puissance pièges", "re_cri": "Ré critiques",
             "re_pou": "Ré poussée", "esq_pa": "Esquive PA", "esq_pm": "Esquive PM",
             "do_per_ar": "Do % armes", "do_per_di": "Do % distance", "do_per_me": "Do % mêlée",
             "re_per_me": "Ré % mêlée", "re_per_di": "Ré % distance"}
    if s in fixes:
        return fixes[s]
    for pre, lib in (("re_per_", "Ré % "), ("re_", "Ré "), ("do_", "Do ")):
        if s.startswith(pre):
            return lib + s[len(pre):]
    return s


def Bouton(parent, **kw):
    """Bouton plat aux couleurs de l'outil."""
    base = dict(bg="#3a3d55", fg="#ecebf5", activebackground="#4d5174", activeforeground="#ffffff", relief="flat",
                bd=0, padx=10, pady=4, cursor="hand2", font=("Segoe UI", 9))
    base.update(kw)
    return tk.Button(parent, **base)


def Champ(parent, **kw):
    """Case de saisie sombre, bordure verte quand elle est active."""
    base = dict(bg="#14151d", fg="#ecebf5", insertbackground="#ecebf5", relief="flat", bd=0, highlightthickness=1,
                highlightbackground="#3a3d55", highlightcolor="#35c46a", font=("Segoe UI", 10),
                disabledbackground="#14151d")
    base.update(kw)
    return tk.Entry(parent, **base)


def habiller(w, fond):
    """Theme sombre commun aux listes deroulantes et aux tableaux."""
    try:
        w.configure(bg=fond)
        st = ttk.Style(w)
        st.theme_use("clam")
        st.configure("TCombobox", fieldbackground="#14151d", background="#3a3d55", foreground="#ecebf5",
                     arrowcolor="#ecebf5", bordercolor="#3a3d55", lightcolor="#3a3d55", darkcolor="#3a3d55")
        st.map("TCombobox", fieldbackground=[("readonly", "#14151d")], foreground=[("readonly", "#ecebf5")],
               selectbackground=[("readonly", "#14151d")], selectforeground=[("readonly", "#ecebf5")])
        st.configure("Treeview", background="#262838", fieldbackground="#262838", foreground="#ecebf5",
                     rowheight=24, borderwidth=0)
        st.configure("Treeview.Heading", background="#3a3d55", foreground="#ecebf5", relief="flat")
        st.map("Treeview", background=[("selected", "#4d5174")])
        for cle, v in (("background", "#14151d"), ("foreground", "#ecebf5"), ("selectBackground", "#4d5174")):
            w.option_add("*TCombobox*Listbox." + cle, v)
    except Exception as err:
        log(f"theme sombre non applique : {err}")


BILAN = Bilan()
INTERFACE_WEB = [True]     # reglages dans une page web locale ; --tk pour revenir aux anciennes fenetres


class Panneau:
    """Fenetre de reglage : objectif ligne par ligne, plages Pa/Ra, exos, sauvegarde par item."""
    FOND, CARTE, TXT, GRIS, VERT, ROUGE = "#1b1c27", "#262838", "#ecebf5", "#8d8fa6", "#35c46a", "#ff6b6b"

    def __init__(self, root, cacher):
        self.items, self.conf, self.sig = charger_items(), None, set()
        self.lignes, self.rangs, self.n_rang = {}, {}, 0
        # FM_CLICK_PATCH:MODE_INIT
        self.mode = tk.StringVar(value="automatique")
        self.apprendre = None            # (code, heure limite, position notee, pret) pendant l'apprentissage
        F = self.FOND
        self.win = w = tk.Toplevel(root)
        if INTERFACE_WEB[0]:
            w.withdraw()                     # ancienne fenetre : jamais montree, la page web la remplace
            w.attributes("-alpha", 0.0)
        w.title("FM - objectif de l'item")
        habiller(w, F)
        w.attributes("-topmost", True)
        w.geometry("+8+110")
        w.protocol("WM_DELETE_WINDOW", w.iconify)
        self.etat = tk.Label(w, text="En attente d'un item dans l'atelier...", bg=F, fg=self.TXT,
                             font=("Segoe UI", 11, "bold"), anchor="w")
        self.etat.pack(fill="x", padx=10, pady=(8, 4))
        haut = tk.Frame(w, bg=F)
        haut.pack(fill="x", padx=10)
        tk.Label(haut, text="Item", bg=F, fg=self.GRIS).pack(side="left")
        self.nom = Champ(haut, width=28)
        self.nom.pack(side="left", padx=(4, 14))
        tk.Label(haut, text="Présélection", bg=F, fg=self.GRIS).pack(side="left")
        self.choix = ttk.Combobox(haut, state="readonly", width=26, values=[it["nom"] for it in self.items])
        self.choix.pack(side="left", padx=4)
        self.choix.bind("<<ComboboxSelected>>", self._choisi)
        # FM_CLICK_PATCH:MODE_UI
        mode = tk.Frame(w, bg=F)
        mode.pack(fill="x", padx=10, pady=(6, 0))
        tk.Label(mode, text="Mode de clics", bg=F, fg=self.GRIS).pack(side="left")
        for valeur, libelle in (("automatique", "Automatique"), ("manuel", "Manuel")):
            tk.Radiobutton(mode, text=libelle, variable=self.mode, value=valeur,
                           command=self._mode_change, bg=F, fg=self.TXT, selectcolor=self.CARTE,
                           activebackground=F, activeforeground=self.TXT).pack(side="left", padx=5)
        # FM_CLICK_PATCH:MODE_HELP
        tk.Label(w, text="Automatique clique la rune recommandée. Bouger la souris ou appuyer sur Echap "
                 "passe en Manuel ; choisis Automatique pour reprendre.",
                 bg=F, fg=self.GRIS, anchor="w", justify="left", wraplength=600).pack(fill="x", padx=10)
        self.grille = tk.Frame(w, bg=self.CARTE)
        self.grille.pack(fill="x", padx=10, pady=8)
        exo = tk.Frame(w, bg=F)
        exo.pack(fill="x", padx=10)
        tk.Label(exo, text="Ajouter un exo", bg=F, fg=self.GRIS).pack(side="left")
        self.codes_exo = sorted(POIDS, key=lambda c: -POIDS[c])
        self.exo_stat = ttk.Combobox(exo, state="readonly", width=24,
                                     values=[f"{nom_code(c)}  (puits {POIDS[c]:g})" for c in self.codes_exo])
        self.exo_stat.pack(side="left", padx=4)
        tk.Label(exo, text="x", bg=F, fg=self.GRIS).pack(side="left")
        self.exo_qte = tk.Spinbox(exo, from_=1, to=20, width=3, bg="#14151d", fg="#ecebf5", buttonbackground="#3a3d55",
                                  relief="flat", insertbackground="#ecebf5")
        self.exo_qte.pack(side="left", padx=4)
        Bouton(exo, text="+ Ajouter", command=self.ajouter_exo).pack(side="left", padx=4)
        tk.Label(exo, text="Plan B", bg=F, fg=self.GRIS).pack(side="left", padx=(16, 0))
        self.plan_b = ttk.Combobox(exo, state="readonly", width=18,
                                   values=["(aucun)"] + [nom_code(c) for c in self.codes_exo])
        self.plan_b.current(0)
        self.plan_b.pack(side="left", padx=4)
        tk.Label(exo, text="Petit exo", bg=F, fg=self.GRIS).pack(side="left", padx=(16, 0))
        self.petit_exo = ttk.Combobox(exo, state="readonly", width=12,
                                      values=["(aucun)"] + [nom_code(c) for c in PETITS_EXOS])
        self.petit_exo.current(0)
        self.petit_exo.pack(side="left", padx=4)
        finition = tk.Frame(w, bg=F)
        finition.pack(fill="x", padx=10, pady=4)
        tk.Label(finition, text="Ligne bonus apres le jet atteint (reliquat restant)", bg=F, fg=self.GRIS).pack(side="left")
        self.finition = ttk.Combobox(finition, state="readonly", width=24,
                                    values=["(aucune)"] + [nom_code(c) for c in self.codes_exo])
        self.finition.current(0)
        self.finition.pack(side="left", padx=4)
        Bouton(exo, text="Apprendre la rune", command=self._apprendre_petit).pack(side="left", padx=4)
        tk.Label(w, bg=F, fg=self.GRIS, justify="left", anchor="w", font=("Segoe UI", 8),
                 text="Objectif sous le max ou « jetable » = ligne dont on se fout : remontée seulement comme "
                      "carburant d'un exo   |   au-dessus du max = over (plafond : puits 101)\n"
                      "Min accepté : over considéré réussi à partir de cette valeur quand le reliquat est vide ; "
                      "en dessous, on passe au Plan B (exo de rechange)\n"
                      "Normale / Pa / Ra de...à : utiliser cette rune seulement quand la valeur actuelle est dans "
                      "la plage (tout vide = choix automatique ; hors plages = taille adaptée au palier)").pack(fill="x", padx=10, pady=(6, 0))
        bas = tk.Frame(w, bg=F)
        bas.pack(fill="x", padx=10, pady=8)
        Bouton(bas, text="Tout au max", command=lambda: self.remplir("max")).pack(side="left")
        Bouton(bas, text="Tout au min", command=lambda: self.remplir("min")).pack(side="left", padx=4)
        Bouton(bas, text="Proposer Pa / Ra", command=self.proposer).pack(side="left", padx=4)
        Bouton(bas, text="Laisser l'algo choisir", command=self.vider_plages).pack(side="left", padx=4)
        Bouton(bas, text="Statistiques", command=self.statistiques).pack(side="left", padx=4)
        Bouton(bas, text="Stock de runes", command=self.fenetre_stock).pack(side="left", padx=4)
        Bouton(bas, text="Repères", command=self.fenetre_reperes).pack(side="left", padx=4)
        Bouton(bas, text="  ENREGISTRER  ", command=self.enregistrer, bg="#2e9e4f", fg="white", activebackground="#35c46a", padx=16, pady=6,
                  font=("Segoe UI", 10, "bold")).pack(side="right")
        w.update()
        cacher(w)
        self.cmds, self.rev, self.t_web, self.calib, self.msg_calib = queue.Queue(), 0, 0.0, None, ("", True)
        self.msg_stock = ("", True)
        from fm_file_atelier import JournalFile
        self.journal_file = JournalFile(os.path.join(ICI,'fm_file_suivi.json'))
        try:
            if not self.journal_file.chemin.exists():
                anciens = charger_json(F_FILE, [])
                if anciens:
                    self.journal_file.planifier(anciens,self.items)
            self.file = [t['profil']['nom'] for t in self.journal_file.attentes]
        except Exception as err:
            self.file = []
            self.journal_file.erreur = str(err)
            log('File bloquee : '+str(err))
        if INTERFACE_WEB[0]:
            w.withdraw()                 # les reglages se font dans la page web ; cette fenetre reste en secours

    @property
    def prochain(self):
        """Premier item de la file d'attente (choisie sur le telephone ou la page), ou None."""
        return self.file[0] if getattr(self, "file", None) else None

    def _sauver_file(self):
        try:
            self.journal_file.planifier(self.file,self.items)
            from fm_fichiers import ecrire_texte
            ecrire_texte(F_FILE,json.dumps(self.file,ensure_ascii=False))
        except Exception as err:
            self.journal_file.erreur = str(err)
            log(f"file d'items non sauvegardee : {err}")

    # ---- page web de reglages : la page envoie des commandes, executees ici (fil des fenetres)
    def _poser(self, form):
        """Recopie dans les cases ce qui est saisi dans la page."""
        if not form:
            return
        self._met(self.nom, form.get("nom", ""))
        if "nom_jeu" in form:
            self.nom_jeu = str(form.get("nom_jeu") or "").strip()
        if "metier_depart" in form:
            from fm_demarrage import METIERS as metiers_depart
            self.metier_depart = form.get("metier_depart") if form.get("metier_depart") in metiers_depart else ''
        pb = form.get("plan_b")
        self.plan_b.current(self.codes_exo.index(pb) + 1 if pb in self.codes_exo else 0)
        pe = form.get("petit_exo")
        self.petit_exo.current(PETITS_EXOS.index(pe) + 1 if pe in PETITS_EXOS else 0)
        if "finition" in form:
            fi = form.get("finition")
            self.finition.current(self.codes_exo.index(fi) + 1 if fi in self.codes_exo else 0)
        for s, d in (form.get("rangs") or {}).items():
            r = self.rangs.get(s)
            if not r:
                continue
            self._met(r["obj"], d.get("obj", ""))
            if r["tol"] is not None:
                self._met(r["tol"], d.get("tol", ""))
            if r["rem"] is not None:
                self._met(r["rem"], d.get("rem", ""))
            for t, (de, a) in r["plages"].items():
                v = (d.get("plages") or {}).get(t) or ["", ""]
                self._met(de, v[0])
                self._met(a, v[1])

    def _executer(self, c):
        quoi = c.get("cmd")
        self._poser(c.get("form"))
        if quoi == "enregistrer":
            self.enregistrer()
        elif quoi == "proposer":
            self.proposer()
            self.etat.config(text="Plages Pa / Ra proposées : vérifie puis Enregistrer", fg=self.ROUGE)
        elif quoi == "remplir" and c.get("cle") in ("min", "max"):
            self.remplir(c["cle"])
        elif quoi == "vider":
            self.vider_plages()
        elif quoi == "ajouter_exo" and c.get("code") in POIDS and str(c.get("qte", "")).isdigit():
            self.ajouter_exo(c["code"], int(c["qte"]))
        elif quoi == "retirer_exo":
            if self.rangs.get(c.get("code"), {}).get("exo"):
                self.retirer_exo(c["code"])
        elif quoi == "apprendre" and c.get("code") in POIDS:
            self.demander_rune(c["code"])
        elif quoi == "preselection":
            it = next((i for i in self.items if i["nom"] == c.get("nom")), None)
            if it:
                self.charger_preselection(it)
        elif quoi == "avis_limite" and str(c.get("n", "")).isdigit():
            if c.get("avis") in ("regle", "probleme"):
                BILAN.d.setdefault("avis", {})[str(c["n"])] = c["avis"]
            else:
                BILAN.d.get("avis", {}).pop(str(c["n"]), None)
            BILAN.sale = True
            BILAN.ecrire(force=True)
        elif quoi == "bilan_zero":
            BILAN.d = {"depuis": time.strftime("%Y-%m-%d %H:%M"), "avis": BILAN.d.get("avis", {}),
                       "systeme": BILAN.d.get("systeme", {})}
            BILAN.sale = True
            BILAN.ecrire(force=True)
        elif quoi == "file":
            connus = {it["nom"] for it in self.items}
            self.file = [n for n in (c.get("noms") or []) if n in connus][:30]
            self._sauver_file()
        elif quoi == "mode" and c.get("mode") in ("automatique", "manuel"):
            self.mode.set(c["mode"])
            self._mode_change()
            log(f"Mode {c['mode']} choisi depuis la page.")
        elif quoi == "stock":
            self.msg_stock = self.sauver_stock(c.get("rows") or {}, c.get("marge"))
        elif quoi == "ravito":
            self.msg_stock = self.basculer_ravito(bool(c.get("actif")))
        elif quoi == "calibrer" and c.get("k") in LIEUX_DEFAUT:
            self.calib = (c["k"], time.time() + 4)
            self.msg_calib = (f"Place ta souris sur : {LIEUX_DEFAUT[c['k']][2]} (4 secondes)...", False)
        self.rev += 1

    def web_tick(self):
        """Appele a chaque tour de la boucle principale : execute les commandes de la page et publie l'etat."""
        while True:
            try:
                c = self.cmds.get_nowait()
            except queue.Empty:
                break
            try:
                self._executer(c)
            except Exception as err:
                log(f"commande de la page refusee ({c.get('cmd')}) : {type(err).__name__} {err}")
                BILAN.note("page", "erreur", detail=f"{c.get('cmd')} : {type(err).__name__} {err}")
        if self.calib and time.time() >= self.calib[1]:
            k, self.calib = self.calib[0], None
            self.msg_calib = self.calibrer_point(k)
        SUIVI.liste_items, SUIVI.file = [it["nom"] for it in self.items], list(self.file)
        try:
            active = self.journal_file.active
            SUIVI.file_suivi = {'en_cours':active['profil']['nom'] if active else None,
                                'termines':sum(t['etat']=='termine' for t in self.journal_file.d['taches']),
                                'suspendus':sum(t['etat']=='suspendu' for t in self.journal_file.d['taches']),
                                'erreur':None}
        except Exception as err:
            SUIVI.file_suivi = {'en_cours':None,'termines':None,'erreur':str(err)}
        if time.time() - self.t_web < .25:
            return
        self.t_web = time.time()
        rangs = []
        for s, r in self.rangs.items():
            rangs.append({"s": s, "nom": nom_code(s) if r["exo"] else self.lignes.get(s, {}).get("nom", nom_code(s)),
                          "min": r["min"], "max": r["max"], "exo": r["exo"], "val": str(r["actuel"].cget("text")),
                          "obj": r["obj"].get(), "tol": r["tol"].get() if r["tol"] is not None else "",
                          "rem": r["rem"].get() if r["rem"] is not None else "",
                          "plages": {t: [de.get(), a.get()] for t, (de, a) in r["plages"].items()}})
        regl = getattr(self, "stock_regl", None)
        if regl is None:
            regl = self.stock_regl = charger_json(F_STOCK, {})
        stock = []
        for s, l in lignes_stock(self.lignes, self.conf, getattr(self, "stock_exos", {})).items():
            if s not in POIDS:
                continue
            for i, t in enumerate(tailles(s)):
                cle = f"{s}/{t}"
                n = l.get("stock", {}).get(t, "? (exo)" if l.get("exo_stock") else (0 if t not in l.get("dispo", ()) else "?"))
                if n is None:
                    n = "?"
                x = regl.get(cle, {})
                stock.append({"cle": cle, "nom": nom_rune(s, t), "n": n if l.get("stock") else ("? (exo)" if l.get("exo_stock") else n), "debut": i == 0,
                              "actif": x.get("actif", True),
                              "alerte": x.get("alerte", STOCK_ALERTE), "cible": x.get("cible", STOCK_CIBLE),
                              "prix": x.get("prix", ""), "rech": recherche_rune(s, t, regl)})
        i_pb = self.plan_b.current()
        lieux = Guide.lieux()
        SUIVI.reglages = {
            "rev": self.rev, "etat": str(self.etat.cget("text")), "ok": str(self.etat.cget("fg")) != self.ROUGE,
            "nom": self.nom.get(), "nom_jeu": getattr(self, "nom_jeu", "") or "", "items": [it["nom"] for it in self.items],
            "metier_depart": getattr(self, "metier_depart", ""),
            "plan_b": self.codes_exo[i_pb - 1] if isinstance(i_pb, int) and i_pb > 0 else None,
            "petit_exo": self._petit_exo(),
            "finition": self._finition(),
            "petits": [{"c": c, "nom": nom_code(c)} for c in PETITS_EXOS],
            "codes": [{"c": c, "nom": nom_code(c), "puits": f"{POIDS[c]:g}"} for c in self.codes_exo],
            "rangs": rangs, "conseil": SUIVI.texte, "stop": SUIVI.stop,
            "stock": {"rows": stock, "marge": regl.get("_marge", {}).get("pct", MARGE_PRIX), "ravito": ravito_actif(regl),
                      "msg": self.msg_stock[0], "ok": self.msg_stock[1]},
            "lieux": [{"k": k, "nom": v[2], "x": lieux[k][0], "y": lieux[k][1]} for k, v in LIEUX_DEFAUT.items()],
            "calib": self.msg_calib[0], "calib_ok": self.msg_calib[1], "mode": self.mode.get()}

    def sauver_stock(self, rows, marge):
        """Enregistre les reglages du stock saisis dans la page. Retourne (message, reussi)."""
        regl = dict(getattr(self, "stock_regl", None) or charger_json(F_STOCK, {}))
        for cle, v in rows.items():
            if "/" not in cle or cle.split("/")[0] not in POIDS:
                continue
            va, vc = str(v.get("alerte", "")).strip(), str(v.get("cible", "")).strip()
            vp = str(v.get("prix", "")).strip().replace(" ", "")
            if not (va.isdigit() and vc.isdigit()) or vp and not vp.isdigit():
                return f"À corriger : {nom_rune(*cle.split('/'))} (nombres entiers seulement)", False
            regl[cle] = {"alerte": int(va), "cible": int(vc),
                         "actif": v.get("actif", regl.get(cle, {}).get("actif", True)) is not False}
            if vp:
                regl[cle]["prix"] = int(vp)
            s_, t_ = cle.split("/")
            rech = str(v.get("rech", "")).strip()
            if rech and rech != recherche_rune(s_, t_):
                regl[cle]["recherche"] = rech
        if str(marge or "").strip().isdigit():
            regl["_marge"] = {"pct": int(str(marge).strip())}
        try:
            with open(F_STOCK, "w", encoding="utf-8") as f:
                json.dump(regl, f, indent=1)
        except OSError as err:
            log(f"sauvegarde du stock impossible : {err}")
            return f"Sauvegarde impossible : {err}", False
        self.stock_regl = regl
        return "Stock enregistré à " + time.strftime("%H:%M:%S"), True

    def basculer_ravito(self, actif):
        """Coupe ou remet les conseils de ravitaillement. Coupe : un ravitaillement en cours est abandonne."""
        regl = dict(getattr(self, "stock_regl", None) or charger_json(F_STOCK, {}))
        regl["_ravito"] = {"actif": actif}
        try:
            with open(F_STOCK, "w", encoding="utf-8") as f:
                json.dump(regl, f, indent=1)
        except OSError as err:
            return f"Sauvegarde impossible : {err}", False
        self.stock_regl = regl
        if not actif and GUIDE.phase is not None:
            GUIDE.phase, GUIDE.liste = None, []
            log("ravitaillement abandonne (conseils de ravitaillement coupes)")
            BILAN.note("parcours", "abandonne")
        log("conseils de ravitaillement " + ("actives" if actif else "coupes"))
        return ("Conseils de ravitaillement activés" if actif else "Conseils de ravitaillement coupés : la FM continue sans "
                "s'arrêter pour acheter") + " (" + time.strftime("%H:%M:%S") + ")", True

    def calibrer_point(self, k):
        """Note la position de la souris comme repere k (lecture seule de la position). Retourne (message, reussi)."""
        try:
            import ctypes
            from ctypes import wintypes
            p_ = wintypes.POINT()
            ctypes.windll.user32.GetCursorPos(ctypes.byref(p_))
            gx, gy, W, H = getattr(self, "ecran", (0, 0, 1920, 1080))
            d = charger_json(F_LIEUX, {})
            d[k] = [round((p_.x - gx) / W, 4), round((p_.y - gy) / H, 4)]
            if not (0 <= d[k][0] <= 1 and 0 <= d[k][1] <= 1):
                return "La souris n'était pas sur l'écran du jeu : repère inchangé", False
            with open(F_LIEUX, "w", encoding="utf-8") as f:
                json.dump(d, f, indent=1)
            img = getattr(self, "image", None)           # image de reference autour du point, pour le retrouver
            if img is not None:
                cx, cy = p_.x - gx, p_.y - gy
                t_ = (REPERE_DECOR if k in REPERES_DECOR else REPERE_TAILLE) // 2
                bout = img[max(0, cy - t_):cy + t_, max(0, cx - t_):cx + t_]
                if bout.shape[0] == 2 * t_ and bout.shape[1] == 2 * t_:
                    os.makedirs(D_REPERES, exist_ok=True)
                    cv2.imwrite(os.path.join(D_REPERES, k + ".png"), bout)
            GUIDE.gabarits.pop(k, None)
            GUIDE.refs.pop(k, None)
            GUIDE.cache.pop(k, None)
            return f"Repère enregistré : {LIEUX_DEFAUT[k][2]}", True
        except Exception as err:
            return f"Calibrage impossible ici : {err}", False

    # ---- construction du tableau
    @staticmethod
    def _met(e, v):
        e.delete(0, "end")
        e.insert(0, "" if v is None else str(v))

    def _entetes(self):
        for c, t in enumerate(("Caractéristique", "Min", "Max", "Actuel", "Objectif", "Min accepté", "Remonter à", "",
                               "Normale de", "à", "Pa de", "à", "Ra de", "à", "")):
            tk.Label(self.grille, text=t, bg=self.CARTE, fg=self.GRIS,
                     font=("Segoe UI", 8, "bold")).grid(row=0, column=c, padx=4, pady=(4, 2), sticky="w")

    def _rang(self, s, nom, mini, maxi, val, exo=False):
        g, r = self.grille, self.n_rang + 1
        self.n_rang = r
        fond = "#2f3146" if r % 2 else self.CARTE
        w = []

        def lab(c, txt, fg=self.TXT, gras=False):
            x = tk.Label(g, text=txt, bg=fond, fg=fg, anchor="w",
                         font=("Segoe UI", 10, "bold" if gras else "normal"))
            x.grid(row=r, column=c, padx=4, pady=1, sticky="we")
            w.append(x)
            return x

        lab(0, ("EXO  " if exo else "") + nom, fg="#ffd166" if exo else self.TXT, gras=True)
        lab(1, "-" if exo else str(mini), fg=self.GRIS)
        lab(2, "-" if exo else str(maxi), fg=self.GRIS)
        actuel = lab(3, str(val), fg=self.VERT, gras=True)
        obj = Champ(g, width=6, justify="center")
        obj.grid(row=r, column=4, padx=4)
        w.append(obj)
        tol = None
        if not exo:
            tol = Champ(g, width=6, justify="center")
            tol.grid(row=r, column=5, padx=4)
            w.append(tol)
        rem = None
        if not exo:
            rem = Champ(g, width=6, justify="center")
            rem.grid(row=r, column=6, padx=4)
            w.append(rem)
        raccourcis = tk.Frame(g, bg=fond)
        raccourcis.grid(row=r, column=7, padx=2)
        w.append(raccourcis)
        if not exo:
            for txt, v in (("min", mini), ("max", maxi), ("jetable", 0)):
                Bouton(raccourcis, text=txt, font=("Segoe UI", 7), padx=2, pady=0,
                          command=lambda v=v: self._met(obj, v)).pack(side="left")
        plages = {}
        for t, c in (("base", 8), ("pa", 10), ("ra", 12)):
            if t in tailles(s):
                de, a = Champ(g, width=4, justify="center"), Champ(g, width=4, justify="center")
                de.grid(row=r, column=c, padx=2)
                a.grid(row=r, column=c + 1, padx=2)
                w += [de, a]
                plages[t] = (de, a)
            else:
                lab(c, "-", fg=self.GRIS)
                lab(c + 1, "", fg=self.GRIS)
        if exo:
            x = Bouton(g, text="x", font=("Segoe UI", 7), padx=3, pady=0, fg=self.ROUGE,
                          command=lambda: self.retirer_exo(s))
            x.grid(row=r, column=14, padx=4)
            w.append(x)
            x = Bouton(g, text="Apprendre la rune", font=("Segoe UI", 7), padx=3, pady=0,
                          command=lambda: self.demander_rune(s))
            x.grid(row=r, column=15, padx=4)
            w.append(x)
        self.rangs[s] = {"obj": obj, "tol": tol, "rem": rem, "plages": plages, "exo": exo, "widgets": w, "actuel": actuel,
                         "min": mini, "max": maxi}
        return obj

    def nouvel_item(self, lignes, sig, nom_lu):
        self.finition.current(0)
        """Appele quand un autre item est pose dans l'atelier."""
        self.lignes = {s: dict(l) for s, l in lignes.items() if l["max"] > 0}
        self.sig = set(sig)
        for c in self.grille.winfo_children():
            c.destroy()
        self.rangs, self.n_rang = {}, 0
        self._entetes()
        for s, l in self.lignes.items():
            self._met(self._rang(s, l["nom"], l["min"], l["max"], l["val"]), l["max"])
        self.proposer()
        connu = trouver_item(self.items, sig)
        from fm_demarrage import profil_correspond
        depart = getattr(self,"profil_file",None) or getattr(self,"profil_demarrage",None)
        depart = depart if depart and profil_correspond(depart,lignes) else None
        self.nom_jeu = (nom_lu or "").strip()
        if nom_lu:                                   # le nom lu dans le jeu departage les presélections proches
            meme_nom = [it for it in self.items if it.get("nom_jeu") and norm(it["nom_jeu"]) == norm(nom_lu)
                        and proche(it["sig"], sig) >= .5]
            if meme_nom and connu not in meme_nom:
                connu = max(meme_nom, key=lambda it: proche(it["sig"], sig))
        if depart:
            connu = depart
        file = [] if depart else (getattr(self, "file", None) or [])
        if file:                                       # le premier item de la file qui ressemble a celui pose
            voulu = next((it for n in file[:1] for it in self.items
                          if it["nom"] == n and proche(it["sig"], sig) >= .5), None)
            if voulu is not None:
                connu = voulu
                SUIVI.evenement("file ok", f"Item posé : {voulu['nom']}, objectif chargé"
                                + (f" — ensuite : {self.file[0]}" if self.file else " — file terminée"), 5)
            else:
                SUIVI.evenement("file non", "L'item posé ne ressemble à aucun item de ta file : "
                                + (f"objectif de {connu['nom']} chargé" if connu else "objectif à régler"), 5)
        self._met(self.nom, nom_lu)
        if connu:
            mode_depart = self.mode.get() if depart and hasattr(self,"mode") else None
            self.appliquer(connu)
            self.conf = self._conf(connu)
            if mode_depart == "automatique":
                self.mode.set("automatique")
                self._mode_change()
            self.profil_demarrage = None
            self.etat.config(text=f"Objectif chargé : {connu['nom']}", fg=self.VERT)
        else:
            self.mode.set("manuel")
            self.conf = None
            self.etat.config(text="NOUVEL ITEM : règle l'objectif puis ENREGISTRER", fg=self.ROUGE)
            if not INTERFACE_WEB[0]:
                self.win.deiconify()
        self.rev = getattr(self, "rev", 0) + 1
        return connu

    def maj(self, lignes):
        """Rafraichit la colonne Actuel."""
        self.lignes = lignes
        for s, r in self.rangs.items():
            v = str(lignes[s]["val"]) if s in lignes else ("0" if r["exo"] else "?")
            if r["actuel"].cget("text") != v:
                r["actuel"].config(text=v)

    # ---- exos
    def ajouter_exo(self, code=None, qte=None):
        if code is None:
            i = self.exo_stat.current()
            if i < 0:
                self.etat.config(text="Choisis d'abord la stat de l'exo", fg=self.ROUGE)
                return
            code = self.codes_exo[i]
            qte = self.exo_qte.get()
        if code in self.rangs:
            self.etat.config(text=f"{nom_code(code)} est déjà dans le tableau : change son objectif", fg=self.ROUGE)
            return
        self._met(self._rang(code, nom_code(code), 0, 0, 0, exo=True), qte)

    def demander_rune(self, code):
        """Apprend a quoi ressemble la rune d'un exo : l'utilisateur la montre avec sa souris."""
        self.apprendre = (code, time.time() + 4, None, False)

    def retirer_exo(self, code):
        for x in self.rangs.pop(code, {"widgets": []})["widgets"]:
            x.destroy()

    # ---- remplissage / lecture
    def remplir(self, cle):
        for s, r in self.rangs.items():
            if not r["exo"]:
                self._met(r["obj"], r[cle])
        self.proposer()

    def vider_plages(self):
        """Efface toutes les plages Pa / Ra : l'algo choisit la rune d'apres les passes observees."""
        for r in self.rangs.values():
            for de, a in r["plages"].values():
                self._met(de, None)
                self._met(a, None)
        self.etat.config(text="Plages vidées : l'algo choisira les runes. ENREGISTRER pour valider", fg=self.ROUGE)

    def proposer(self):
        """Propose les plages Pa / Ra de chaque ligne d'apres son objectif (modifiables ensuite).
        La Ra passe mieux que la Pa sur une ligne deja haute : Pa pour monter, Ra pour le dernier saut
        (de objectif-10 a objectif-5, elle atterrit entre l'objectif et +5), rune normale sinon.
        Fo/Int/Cha/Agi : au-dela de 60 seules les Ra passent, donc Ra de 60 jusqu'a l'objectif."""
        for s, r in self.rangs.items():
            v = r["obj"].get().strip()
            if r["exo"] or not v.isdigit():
                continue
            obj = int(v)
            for t, (de, a) in r["plages"].items():
                self._met(de, None)
                self._met(a, None)
            fin_pa = obj - qte(s, "pa")
            haut = plafond(s, r["max"])               # la Ra reste permise jusqu'au plafond de la ligne
            # ligne qui reste sous le palier des Pa (Do poussee : la Pa passe bien jusqu'a ~50, objectif 40) :
            # pas de Ra, la Pa monte jusqu'au bout (sinon « la laisser redescendre a 30 pour la Ra »)
            sans_ra = s not in ("pui", "sa") and obj <= r["max"] and obj <= palier(s, "pa")
            if "ra" in r["plages"] and not sans_ra:
                q = qte(s, "ra")
                debut = obj - q                       # par defaut : le dernier saut vers l'objectif
                # la Ra reste permise jusqu'au plafond quand la ligne vise haut (over voulu, ligne
                # au-dela de 60) ; sinon elle s'arrete assez tot pour atterrir pres de l'objectif
                fin = haut if obj > r["max"] else obj - q // 2
                if s not in ("pui", "sa") and obj > palier(s, "pa"):
                    debut, fin = min(debut, palier(s, "pa")), haut   # au-dela du palier des Pa (60, 300 vita)
                # Ra des la moitie du max : tes passes (oct. 2026) donnent, par rune, Ra Sagesse +17.8 de
                # poids net contre +5.6 en Pa, Ra Puissance +7.8 contre +3.1, Ra Vita +6.4 contre +0.4.
                # Un succes avec la grosse rune remonte le jet d'un coup.
                debut = min(debut, -(-r["max"] // 2))
                if s == "sa":
                    debut = 0                          # Ra Sagesse le plus tot possible : un succes remet la ligne d'un coup
                fin = min(fin, haut - q)               # une Ra plus haut depasserait le plafond : refusee
                if obj <= r["max"]:
                    fin = min(fin, r["max"] - q)       # pas d'over voulu : une Ra qui franchit le max (Vita 362 -> 412)
                                                       # passe tres mal ; la derniere Ra part de max - 50 au plus
                if debut >= 0 and debut + q <= haut:
                    self._met(r["plages"]["ra"][0], debut)
                    self._met(r["plages"]["ra"][1], fin)
                    if obj > r["max"] or s in CARAC:  # over voulu, ou Fo/Int/Cha/Agi (au-dela de 60, Ra seulement)
                        fin_pa = min(fin_pa, debut - 1)
                    fin_pa = min(fin_pa, palier(s, "pa") - 1)   # jamais de Pa a partir de son palier (Puissance 60 et plus)
                    # sinon la Pa reste permise par-dessus : la Ra passe en premier dans sa plage, la Pa
                    # finit la ligne quand la Ra depasserait (Sagesse 31-32 pour 35)
            if s == "do_cri" and obj - qte(s, "pa") >= 0:
                # Do critiques : runes normales tout du long, la Pa seulement quand elle finit pile (9 -> 12)
                self._met(r["plages"]["base"][0], 0)
                self._met(r["plages"]["base"][1], obj - 1)
                self._met(r["plages"]["pa"][0], obj - qte(s, "pa"))
                self._met(r["plages"]["pa"][1], obj - qte(s, "pa"))
                continue
            if s.startswith("do_") and s[3:] in ELEMS:        # dommages elementaires : Pa pour le dernier saut
                if obj - qte(s, "pa") >= 1:
                    self._met(r["plages"]["base"][0], 0)       # runes normales jusqu'a 16 pour viser 20
                    self._met(r["plages"]["base"][1], obj - qte(s, "pa") - 1)
                if obj - qte(s, "pa") >= 0:
                    self._met(r["plages"]["pa"][0], obj - qte(s, "pa"))      # 17 pour viser 20
                    self._met(r["plages"]["pa"][1], obj - qte(s, "pa"))
                continue
            if "pa" in r["plages"]:
                d_pa = 15 if s == "pui" else 0
                if fin_pa >= d_pa:
                    self._met(r["plages"]["pa"][0], d_pa)
                    self._met(r["plages"]["pa"][1], fin_pa)
                    if d_pa > 0:
                        self._met(r["plages"]["base"][0], 0)
                        self._met(r["plages"]["base"][1], d_pa - 1)

    @staticmethod
    def _conf(it):
        # FM_CLICK_PATCH:MODE_CONFIG
        conf = Panneau._conf_base(it)
        mode = it.get("mode", "automatique")
        conf["mode"] = mode if mode in ("automatique", "manuel") else "automatique"
        return conf

    def _mode_change(self):
        if self.conf is not None:
            self.conf["mode"] = self.mode.get()

    @staticmethod
    def _conf_base(it):
        return {"cibles": dict(it.get("cibles", {})), "exos": dict(it.get("exos", {})),
                "regles": dict(it.get("regles", {})), "mins": dict(it.get("mins", {})),
                "remonte": dict(it.get("remonte", {})), "plan_b": it.get("plan_b"), "petit_exo": it.get("petit_exo"),
                "finition": it.get("finition")}

    def _apprendre_petit(self):
        """Montre la rune du petit exo (souris dessus dans l'inventaire, 4 secondes) pour qu'on la retrouve."""
        c = self._petit_exo()
        if not c:
            self.etat.config(text="Choisis d'abord la rune du petit exo", fg=self.ROUGE)
            return
        self.demander_rune(c)
        self.etat.config(text=f"Place ta souris sur la rune {nom_rune(c, 'base')} dans l'inventaire (4 secondes)",
                         fg=self.ROUGE)

    def _petit_exo(self):
        i = self.petit_exo.current()
        return PETITS_EXOS[i - 1] if isinstance(i, int) and i > 0 else None

    def _finition(self):
        i = self.finition.current()
        return self.codes_exo[i - 1] if isinstance(i, int) and i > 0 else None

    def _choisi(self, _evt=None):
        i = self.choix.current()
        if 0 <= i < len(self.items):
            self.charger_preselection(self.items[i])

    def charger_preselection(self, it):
        """Hors atelier, afficher le profil sauvegarde sans inventer un jet actuel."""
        hors_atelier = not getattr(self,"tableau_visible",False)
        if hors_atelier:
            for w in self.grille.winfo_children():
                w.destroy()
            self.lignes,self.rangs,self.n_rang = {},{},0
            self.sig = {tuple(s) for s in it.get("sig",[]) if len(s)==3}
            self._entetes()
            for s,mini,maxi in it.get("sig",[]):
                if maxi <= 0 or s not in POIDS:
                    continue
                self.lignes[s] = {"nom":nom_code(s),"min":mini,"max":maxi,"val":"?",
                                  "dispo":[],"stock":{t:None for t in tailles(s)},"profil_seulement":True}
                self._rang(s,nom_code(s),mini,maxi,"?")
        self.appliquer(it)   # objectifs, minima et plages sauvegardes, sans les recalculer
        if hors_atelier:
            for r in self.rangs.values():
                if r["exo"]:
                    r["actuel"].config(text="?")
            self.conf = self._conf(it)
            if hasattr(self,"_mode_change"):
                self._mode_change()
            self.etat.config(text=f"Objet prévu au prochain F1 : {it['nom']} — profil chargé",fg=self.VERT)
        else:
            self.etat.config(text="Présélection appliquée : vérifie puis Enregistrer",fg=self.ROUGE)

    def appliquer(self, it):
        self._met(self.nom, it["nom"])
        # FM_CLICK_PATCH:MODE_APPLY
        self.mode.set("manuel")
        self.metier_depart = it.get("metier_depart", "")
        fi = it.get("finition")
        self.finition.current(self.codes_exo.index(fi) + 1 if fi in self.codes_exo else 0)
        self.nom_jeu = it.get("nom_jeu", "")
        pb = it.get("plan_b")
        self.plan_b.current(self.codes_exo.index(pb) + 1 if pb in self.codes_exo else 0)
        pe = it.get("petit_exo")
        self.petit_exo.current(PETITS_EXOS.index(pe) + 1 if pe in PETITS_EXOS else 0)
        for s in [s for s, r in self.rangs.items() if r["exo"]]:
            self.retirer_exo(s)
        for s, q in it.get("exos", {}).items():
            if s in POIDS and s not in self.rangs:
                self.ajouter_exo(s, q)
        for s, r in self.rangs.items():
            if not r["exo"]:
                self._met(r["obj"], it.get("cibles", {}).get(s, r["max"]))
                self._met(r["tol"], it.get("mins", {}).get(s))
                self._met(r["rem"], it.get("remonte", {}).get(s))
            regle = it.get("regles", {}).get(s, {})
            for t, (de, a) in r["plages"].items():
                self._met(de, regle.get(t, [None, None])[0])
                self._met(a, regle.get(t, [None, None])[1])

    def enregistrer(self):
        cibles, exos, regles, mins, remonte, rate = {}, {}, {}, {}, {}, []
        for s, r in self.rangs.items():
            v = r["obj"].get().strip()
            if not v.lstrip("-").isdigit():
                rate.append(nom_code(s))
                continue
            if r["exo"]:
                exos[s] = min(int(v), plafond(s))
            else:
                cibles[s] = min(int(v), plafond(s, r["max"]))
                m = r["tol"].get().strip()
                if m.isdigit() and int(m) <= cibles[s]:
                    mins[s] = int(m)
                elif m:
                    rate.append(f"min accepté {nom_code(s)}")
                m = r["rem"].get().strip()
                if m.isdigit() and (mins.get(s, 0) <= int(m) <= cibles[s]
                                    or cibles[s] <= 0 and int(m) <= r["max"]):     # jetable : 0 = jamais, ou une valeur
                    remonte[s] = int(m)
                elif m:
                    rate.append(f"« remonter à » {nom_code(s)} (entre le min accepté et l'objectif)")
            for t, (de, a) in r["plages"].items():
                d, f = de.get().strip(), a.get().strip()
                if not d and not f:
                    continue
                if d.lstrip("-").isdigit() and f.lstrip("-").isdigit() and int(d) <= int(f):
                    regles.setdefault(s, {})[t] = [int(d), int(f)]
                else:
                    rate.append(f"plage {'Normale' if t == 'base' else t.capitalize()} {nom_code(s)}")
        hors = sum(pds(s, n) for s, n in exos.items()) \
            + sum(pds(s, c - self.rangs[s]["max"]) for s, c in cibles.items() if c > self.rangs[s]["max"] > 0)
        if hors > PLAFOND and not rate:
            rate.append(f"exos + over demandés = {hors:g} de densité, le jeu en accepte {PLAFOND} au total")
        if rate:
            self.etat.config(text="A corriger : " + ", ".join(rate), fg=self.ROUGE)
            return
        self.items = charger_items()                 # relu du disque : ne jamais ecraser une presélection ajoutee ailleurs
        nom = self.nom.get().strip() or f"Item {len(self.items) + 1}"
        autre = next((it for it in self.items if it["nom"] == nom and it.get("sig") and self.sig
                      and proche(it["sig"], self.sig) < .5), None)
        if autre:
            # Ce nom appartient a la presélection d'un AUTRE item (lignes differentes) : on ne l'ecrase pas.
            self.etat.config(text=f"« {nom} » est déjà la présélection d'un autre item"
                             + (f" ({autre['nom_jeu']})" if autre.get("nom_jeu") else "")
                             + " : change le nom de la présélection avant d'enregistrer", fg=self.ROUGE)
            return
        i_pb = self.plan_b.current()
        nom_jeu = (getattr(self, "nom_jeu", "") or "").strip()
        sig_ = sorted(self.sig)
        # Une ligne de la presélection pas lue a l'ecran au moment d'enregistrer (tableau defile : Do % sorts
        # en bas) : on la garde, avec son objectif, son minimum et ses plages, au lieu de l'effacer.
        ancien = next((it for it in self.items if it["nom"] == nom), None)
        if ancien:
            vus = {x[0] for x in sig_}
            for x in ancien.get("sig", []):
                if x[0] not in vus and x[0] not in exos:
                    sig_.append(x)
                    for cle, dest in (("cibles", cibles), ("mins", mins), ("remonte", remonte), ("regles", regles)):
                        if x[0] in ancien.get(cle, {}):
                            dest[x[0]] = ancien[cle][x[0]]
            sig_.sort()
        fiche = {"nom": nom, "nom_jeu": nom_jeu, "metier_depart": getattr(self,"metier_depart", ""), "sig": sig_, "cibles": cibles, "exos": exos, "regles": regles,
                 "mins": mins, "remonte": remonte, "plan_b": self.codes_exo[i_pb - 1] if i_pb > 0 else None,
                 "petit_exo": self._petit_exo(), "finition": self._finition()}
        try:                                         # copie de securite avant chaque ecriture
            import shutil
            if os.path.exists(F_ITEMS):
                shutil.copyfile(F_ITEMS, F_ITEMS.replace(".json", "_copie.json"))
        except OSError:
            pass
        # on remplace seulement la presélection du meme nom ; les autres presélections du meme item restent
        # FM_CLICK_PATCH:MODE_SAVE
        fiche["mode"] = self.mode.get()
        self.items = [it for it in self.items if it["nom"] != nom]
        self.items.append(fiche)
        try:
            with open(F_ITEMS, "w", encoding="utf-8") as f:
                json.dump({"items": self.items}, f, indent=1, ensure_ascii=False)
        except OSError as err:
            log(f"sauvegarde impossible : {err}")
            self.etat.config(text=f"Sauvegarde impossible : {err}",fg=self.ROUGE)
            return
        self.conf = self._conf(fiche)
        # Geste explicite de l'utilisateur : autoriser la verification du profil
        # ET de l'objet actuel au prochain F1, sans effacer le journal de file.
        from copy import deepcopy
        self.reconciliation_file={'id':time.monotonic_ns(),'profil':deepcopy(fiche)}
        self.choix.config(values=[it["nom"] for it in self.items])
        self.etat.config(text=f"Objectif enregistré : {nom}", fg=self.VERT)
        log(f"objectif enregistre pour {nom} : {cibles} exos {exos} regles {regles} mins {mins} remonte {remonte} "
            f"plan B {fiche['plan_b']} petit exo {fiche['petit_exo']} finition {fiche['finition']}")

    # ---- reperes du guide de ravitaillement : ou sont la porte, l'hotel de vente, les ateliers...
    def fenetre_reperes(self):
        w = tk.Toplevel(self.win)
        w.title("FM - repères du ravitaillement")
        w.configure(bg=self.FOND)
        w.attributes("-topmost", True)
        g = tk.Frame(w, bg=self.CARTE)
        g.pack(fill="both", expand=True, padx=8, pady=8)
        info = tk.Label(w, text="Pour recaler un repère : clique « Calibrer », puis place ta souris dessus dans "
                                "le jeu et ne bouge plus pendant 4 secondes.", fg=self.GRIS, bg=self.FOND)
        info.pack(pady=(0, 6))
        etiq = {}

        def montrer():
            lieux = Guide.lieux()
            for k, lab in etiq.items():
                lab.config(text=f"{lieux[k][0]:.3f} ; {lieux[k][1]:.3f}")

        def calibrer(k):
            info.config(text=f"Place ta souris sur : {LIEUX_DEFAUT[k][2]} (4 secondes)...", fg=self.ROUGE)

            def prendre():
                msg, ok = self.calibrer_point(k)
                info.config(text=msg, fg=self.VERT if ok else self.ROUGE)
                montrer()

            w.after(4000, prendre)

        for r, (k, v) in enumerate(LIEUX_DEFAUT.items()):
            tk.Label(g, text=v[2], bg=self.CARTE, fg=self.TXT, anchor="w").grid(row=r, column=0, padx=6, sticky="we")
            etiq[k] = tk.Label(g, text="", bg=self.CARTE, fg=self.GRIS)
            etiq[k].grid(row=r, column=1, padx=6)
            Bouton(g, text="Calibrer", font=("Segoe UI", 8), command=lambda k=k: calibrer(k)).grid(
                row=r, column=2, padx=6, pady=1)
        montrer()

    # ---- stock de runes : seuils d'alerte, quantite a racheter, prix maximum
    def fenetre_stock(self):
        regl = charger_json(F_STOCK, {})
        lignes = lignes_stock(getattr(self, "lignes", None), self.conf, getattr(self, "stock_exos", {}))
        w = tk.Toplevel(self.win)
        w.title("FM - stock de runes")
        w.configure(bg=self.FOND)
        w.attributes("-topmost", True)
        g = tk.Frame(w, bg=self.CARTE)
        g.pack(fill="both", expand=True, padx=8, pady=8)
        for c, t in enumerate(("Rune", "En stock", "Alerte sous", "Remonter à", "Prix max / rune",
                               "Texte à taper à l'hôtel de vente")):
            tk.Label(g, text=t, bg=self.CARTE, fg=self.GRIS, font=("Segoe UI", 8, "bold")).grid(
                row=0, column=c, padx=6, pady=(4, 2), sticky="w")
        champs, actifs, r = {}, {}, 0
        for s, l in lignes.items():
            if s not in POIDS:
                continue
            for t in tailles(s):
                cle, r = f"{s}/{t}", r + 1
                n = l.get("stock", {}).get(t, 0 if t not in l.get("dispo", ()) else "?")
                actif = tk.BooleanVar(value=regl.get(cle, {}).get("actif", True))
                tk.Checkbutton(g, text=nom_rune(s, t), variable=actif, bg=self.CARTE,
                               fg=self.TXT, selectcolor=self.CARTE, anchor="w",
                               font=("Segoe UI", 10, "bold")).grid(row=r, column=0, padx=6, sticky="we")
                tk.Label(g, text=str(n), bg=self.CARTE, fg=self.VERT).grid(row=r, column=1, padx=6)
                e3 = []
                for c, (k, d) in enumerate((("alerte", STOCK_ALERTE), ("cible", STOCK_CIBLE), ("prix", "")), 2):
                    e = Champ(g, width=8, justify="center")
                    e.grid(row=r, column=c, padx=6, pady=1)
                    self._met(e, regl.get(cle, {}).get(k, d))
                    e3.append(e)
                e = Champ(g, width=22)
                e.grid(row=r, column=5, padx=6, pady=1)
                self._met(e, recherche_rune(s, t, regl))
                e3.append(e)
                actifs[cle] = actif
                champs[cle] = e3
        bm = tk.Frame(w, bg=self.CARTE)
        bm.pack(pady=(0, 6), ipadx=6, ipady=4)
        tk.Label(bm, text="Sans prix max : accepter jusqu'au prix moyen de l'hôtel de vente +", bg=self.CARTE,
                 fg=self.TXT).pack(side="left", padx=4)
        e_marge = Champ(bm, width=5, justify="center")
        e_marge.pack(side="left")
        self._met(e_marge, regl.get("_marge", {}).get("pct", MARGE_PRIX))
        tk.Label(bm, text="%", bg=self.CARTE, fg=self.TXT).pack(side="left", padx=4)
        info = tk.Label(w, text="Décoche Réapprovisionner pour exclure une rune. Stock exo inconnu : vérifié à l'HDV avant achat.",
                        bg=self.FOND, fg=self.GRIS)
        info.pack(pady=(0, 4))

        def enregistrer():
            for cle, (a, c, p_, rech) in champs.items():
                va, vc, vp = a.get().strip(), c.get().strip(), p_.get().strip().replace(" ", "")
                if not (va.isdigit() and vc.isdigit()) or vp and not vp.isdigit():
                    info.config(text=f"A corriger : {cle} (nombres entiers seulement)", fg=self.ROUGE)
                    return
                regl[cle] = {"alerte": int(va), "cible": int(vc), "actif": actifs[cle].get()}
                if vp:
                    regl[cle]["prix"] = int(vp)
                s_, t_ = cle.split("/")
                if rech.get().strip() and rech.get().strip() != recherche_rune(s_, t_):
                    regl[cle]["recherche"] = rech.get().strip()
            if e_marge.get().strip().isdigit():
                regl["_marge"] = {"pct": int(e_marge.get().strip())}
            try:
                with open(F_STOCK, "w", encoding="utf-8") as f:
                    json.dump(regl, f, indent=1)
            except OSError as err:
                log(f"sauvegarde du stock impossible : {err}")
            self.stock_regl = regl
            info.config(text="Stock enregistré.", fg=self.VERT)

        Bouton(w, text="ENREGISTRER", command=enregistrer).pack(pady=(0, 8))

    # ---- statistiques des passes observees
    @staticmethod
    def stats_passes():
        """Tes passes par rune et par situation : [(taille, stat, situation), [SC, SN, EC]]."""
        stats = {}
        try:
            with open(F_PASSES, encoding="utf-8") as f:
                for ligne in list(f)[1:]:
                    c = ligne.rstrip("\n").split(";")
                    if len(c) >= 8:
                        try:
                            sit = libelle_contexte(contexte(c[2], c[3], {"val": int(c[5]), "max": int(c[6])}))
                        except (ValueError, KeyError, IndexError):
                            sit = c[4]
                        k = (c[3], c[2], sit)
                        n = stats.setdefault(k, [0, 0, 0])
                        n[("SC", "SN", "EC").index(c[7]) if c[7] in ("SC", "SN", "EC") else 2] += 1
        except OSError:
            pass
        return stats

    def statistiques(self):
        stats = self.stats_passes()
        w = tk.Toplevel(self.win)
        w.title("FM - statistiques de tes passes")
        w.configure(bg=self.FOND)
        w.attributes("-topmost", True)
        cols = ("Rune", "Situation", "Passées", "SC", "SN", "Échecs", "Réussite")
        t = ttk.Treeview(w, columns=cols, show="headings", height=min(22, max(4, len(stats))))
        for c in cols:
            t.heading(c, text=c)
            t.column(c, width=150 if c == "Rune" else 80, anchor="w" if c == "Rune" else "center")
        for (taille, s, ctx), (sc, sn, ec) in sorted(stats.items(), key=lambda kv: -sum(kv[1])):
            n = sc + sn + ec
            rune = ("" if taille == "base" else taille.capitalize() + " ") + nom_code(s)
            t.insert("", "end", values=(rune, ctx, n, sc, sn, ec, f"{(sc + sn) / n:.0%}"))
        t.column("Situation", width=190)
        t.pack(fill="both", expand=True, padx=8, pady=8)
        if not stats:
            tk.Label(w, text="Aucune passe enregistrée pour l'instant.", bg=self.FOND, fg=self.GRIS).pack(pady=(0, 8))


# ---------------------------------------------------------------------------------------------------
# Suivi sur le telephone : une petite page web servie par ce PC sur le reseau local (meme Wi-Fi).
# Lecture seule : le conseil en cours, les evenements (exo passe, rune a acheter, arret), le compteur de
# tentatives d'exo et une image de la fenetre de forgemagie. Notifications poussees en option avec ntfy :
# mettre un nom de sujet (au hasard, long) dans fm_ntfy.txt et s'y abonner dans l'application ntfy.
PORT_SUIVI = 8765
F_NTFY = os.path.join(ICI, "fm_ntfy.txt")
F_TEL = os.path.join(ICI, "fm_telephone.txt")


def objectifs_rares(conf, lignes):
    """[(stat, valeur visee, valeur de depart)] : les exos demandes (depart 0) et les over voulus sur une
    ligne a rune unique (depart = le max de la ligne ; ex. dommages aux sorts 4 -> 6)."""
    out = [(s, int(n), 0) for s, n in sorted(((conf or {}).get("exos") or {}).items()) if n > 0 and s in POIDS]
    for s, c in sorted(((conf or {}).get("cibles") or {}).items()):
        mx = (lignes or {}).get(s, {}).get("max", 0)
        if mx > 0 and c > mx and len(tailles(s)) == 1 and not any(s == o[0] for o in out):
            out.append((s, int(c), int(mx)))
    return out


def compteur_exos(item):
    """{(stat, valeur avant): [essais, reussis, essais depuis la derniere reussite]} pour cet item,
    d'apres fm_passes.csv. (do_per_so, 0) = 1er % dommages aux sorts, (do_per_so, 1) = le 2e."""
    out = {}
    try:
        with open(F_PASSES, encoding="utf-8") as f:
            for li in f:
                c = li.rstrip("\n").split(";")
                if len(c) < 8 or c[1] != item or c[2] not in POIDS:
                    continue
                if c[6] != "0" and not float(c[5] or 0) >= float(c[6] or 0) > 0:
                    continue                         # ni un exo, ni une rune posee sur une ligne deja a son max
                k = out.setdefault((c[2], int(float(c[5] or 0))), [0, 0, 0])
                k[0] += 1
                if c[7] in ("SC", "SN"):
                    k[1] += 1
                    k[2] = 0
                else:
                    k[2] += 1
    except (OSError, ValueError):
        pass
    return out


class Suivi:
    PAGE = """<!doctype html><html lang=fr><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><title>FM</title>
<style>body{margin:0;background:#14161c;color:#e8e8ea;font:15px system-ui,sans-serif}
#c{padding:10px 14px 2px;font-weight:700;font-size:17px;color:#3ddc84;line-height:1.25;height:2.5em;overflow:hidden;
display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical}
#cd{padding:0 14px 8px;color:#9aa0ad;font-size:12px;line-height:1.3;height:2.6em;overflow:hidden;
display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;border-bottom:1px solid #2a2d36}
#c.stop{color:#ff5a4f}#m{padding:6px 14px;color:#9aa0ad;font-size:13px}
img{width:100%;display:block}h2{font-size:13px;margin:14px 14px 4px;color:#9aa0ad;text-transform:uppercase}
table{border-collapse:collapse;margin:0 14px}td,th{padding:3px 12px 3px 0;text-align:left;font-size:14px}
#q{display:none;margin:8px 14px;padding:12px;border:1px solid #ffd166;border-radius:8px;background:#221d10}
#s{display:none;margin:8px 14px;padding:12px;border:1px solid #3ddc84;border-radius:8px;background:#102218}#s b{color:#3ddc84}#s button{display:block;width:100%;margin:8px 0 0;padding:12px;font-size:15px;text-align:left}#s button.non{background:#2a2d36}#q b{color:#ffd166}#q button{display:block;width:100%;margin:8px 0 0;padding:12px;font-size:15px;text-align:left}
#q button.non{background:#3a2326}
.lien{display:block;margin:10px 14px;padding:12px;background:#1f9d57;color:#fff;border-radius:6px;text-align:center;
font-weight:700;text-decoration:none}
#f div{display:flex;align-items:center;gap:6px;padding:8px 0;border-bottom:1px solid #22252d}
#f span{flex:1}#f i{font-style:normal;color:#9aa0ad;width:22px}#f div:first-child span{color:#3ddc84;font-weight:700}
#f button{margin:0;padding:8px 13px;font-size:16px}
#e div{padding:5px 14px;border-bottom:1px solid #22252d}#e b{color:#ffd166}#e span{color:#9aa0ad;margin-right:8px}
button{margin:8px 14px;padding:8px 12px;background:#2a2d36;color:#e8e8ea;border:0;border-radius:6px}</style>
<div id=c>connexion...</div><div id=cd></div><div id=m></div><div id=q></div><div id=s></div><img id=i alt="">
<a id=rg class=lien>Régler l’item posé dans l’atelier</a>
<h2>File d’items à faire</h2><div style="padding:0 14px"><div id=f></div>
<select id=n style="width:100%;padding:12px;font-size:16px;background:#2a2d36;color:#e8e8ea;border:0;border-radius:6px"></select>
<div id=np style="color:#9aa0ad;font-size:13px;padding:6px 0"></div></div>
<button id=b>Activer le son et la vibration</button>
<h2>Tentatives d'exo</h2><div id=p style="padding:0 14px 6px;font-size:22px;font-weight:700"></div><table id=x></table><h2>À acheter</h2><table id=a></table><h2>Événements</h2><div id=e></div>
<script>
let vu=-1,ac=null,vi=-1,occ=false;const K=location.pathname.split('/')[1];
document.getElementById('b').onclick=()=>{ac=new (window.AudioContext||window.webkitAudioContext)();bip();
 document.getElementById('b').style.display='none'};
function bip(){if(navigator.vibrate)navigator.vibrate([200,100,200]);if(!ac)return;
 const o=ac.createOscillator(),g=ac.createGain();o.connect(g);g.connect(ac.destination);o.frequency.value=880;
 g.gain.value=.2;o.start();o.stop(ac.currentTime+.35)}
let nv='',F=[];const N=()=>document.getElementById('n');
function envoi(){nv='';fetch('/'+K+'/cmd',{method:'POST',body:JSON.stringify({cmd:'file',noms:F})});dessine(null)}
function dessine(d){if(d){const cle=JSON.stringify([d.items,d.file,d.file_suivi]);if(cle==nv||document.activeElement===N())return;nv=cle;F=d.file.slice();
  N().innerHTML='<option value="">+ Ajouter un item à la file…</option>'+d.items.map(x=>'<option>'+esc(x)+'</option>').join('')}
 document.getElementById('f').innerHTML=F.map((x,i)=>'<div><i>'+(i+1)+'.</i><span>'+esc(x)+'</span>'+(i?'<button data-u="'+i+'">↑</button>':'')+'<button data-x="'+i+'">✕</button></div>').join('');
 document.querySelectorAll('#f [data-u]').forEach(b=>b.onclick=()=>{const i=+b.dataset.u;[F[i-1],F[i]]=[F[i],F[i-1]];envoi()});
 document.querySelectorAll('#f [data-x]').forEach(b=>b.onclick=()=>{F.splice(+b.dataset.x,1);envoi()});
 const suivi=d&&d.file_suivi;document.getElementById('np').textContent=(suivi?(suivi.erreur?'File bloquée : '+suivi.erreur:(suivi.en_cours?'En cours : '+suivi.en_cours+'. ':'')+suivi.termines+' tâche(s) terminée(s). '):'')+(F.length?'Tâches en attente (doublons permis). Chaque réussite est sauvegardée avant de passer à la suivante.':'Aucune tâche en attente.')}
document.addEventListener('DOMContentLoaded',()=>{document.getElementById('rg').href='/'+K+'/reglages';
 N().onchange=()=>{if(N().value){F.push(N().value);envoi()}N().value='';N().blur()}});
let qv='';function dec(lot){fetch('/'+K+'/decision',{method:'POST',body:JSON.stringify({nom:qn,lot:lot})});
 document.getElementById('q').style.display='none';qv=''}let qn='';
function question(q){const e=document.getElementById('q');if(!q){e.style.display='none';qv='';return}
 const cle=JSON.stringify([q.nom,q.lots,q.max]);if(cle==qv)return;qv=cle;qn=q.nom;e.style.display='block';
 e.innerHTML='<b>HORS DE PRIX : '+esc(q.nom)+'</b><br>Il manque '+q.manque+' runes. Prix moyen '+q.moyen+' k, ton max '+q.max+' k la rune.'+
  Object.keys(q.lots).sort((a,b)=>b-a).map(n=>'<button data-l="'+n+'">Accepter le lot de '+n+' à '+q.lots[n]+' k la rune ('+Math.round(q.lots[n]/q.moyen*100)+' % du prix moyen)</button>').join('')+
  '<button class=non data-l="">Refuser : ne pas acheter cette rune</button>';
 e.querySelectorAll('button').forEach(b=>b.onclick=()=>dec(b.dataset.l===''?null:+b.dataset.l))}

function suite(s,v){const e=document.getElementById('s');if(!s){if(v){e.style.display='block';
 e.innerHTML='<b>Prochain item : '+esc(v)+'</b><br>Place-le dans la fenêtre : ses objectifs seront appliqués tout seuls.'}else e.style.display='none';sv='';return}
 const cle=JSON.stringify(s);if(cle==sv)return;sv=cle;e.style.display='block';
 e.innerHTML='<b>'+esc(s.motif)+(s.item?' : '+esc(s.item):'')+'</b><br>Quel item charger ensuite ?'+
  s.items.map((n,i)=>'<button data-i="'+i+'">'+esc(n)+'</button>').join('')+'<button class=non data-i="-1">Plus tard</button>';
 e.querySelectorAll('button').forEach(b=>b.onclick=()=>{const i=+b.dataset.i;
  fetch('/'+K+'/suivant',{method:'POST',body:JSON.stringify({nom:i<0?null:s.items[i]})});e.style.display='none'})}
let sv='';
function esc(t){return String(t).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]))}
async function maj(){if(occ)return;occ=true;try{const r=await fetch('/'+K+'/etat');const d=await r.json();
 const c=document.getElementById('c'),pp=String(d.texte).split('|').map(x=>x.trim()).filter(x=>x);c.textContent=pp[0];c.className=d.stop?'stop':'';
 document.getElementById('cd').textContent=pp.slice(1).join(' · ');
 document.getElementById('m').textContent=d.item+'  |  lu il y a '+d.age+' s';
 document.getElementById('p').textContent=d.exos.length?d.exos[0][1]+' tentative'+(d.exos[0][1]>1?'s':'')+' — '+d.exos[0][0]:'aucun exo demandé';
 document.getElementById('x').innerHTML='<tr><th>Exo visé<th>Tentatives<th>Passés<th>Depuis le dernier<th>Marche précédente passée</tr>'+
  d.exos.map(x=>'<tr><td>'+esc(x[0])+'<td>'+x[1]+'<td>'+x[2]+'<td>'+x[3]+'<td>'+(x[4]===null?'':x[4]+' fois')+'</tr>').join('');
 document.getElementById('a').innerHTML=d.achats.length?'<tr><th>Rune<th>Stock<th>Acheter<th>Lots<th>Budget max</tr>'+
  d.achats.map(x=>'<tr><td>'+esc(x.rune)+'<td>'+x.stock+'<td>'+x.acheter+'<td>'+x.lots+'<td>'+(x.budget?x.budget.toLocaleString('fr-CA')+' k':'')+'</tr>').join(''):'<tr><td>rien, le stock est bon</tr>';
 document.getElementById('e').innerHTML=d.evenements.map(x=>'<div><span>'+x[0]+'</span><b>'+esc(x[1])+'</b></div>').join('');
 question(d.demande);suite(d.suite,d.suivant);dessine(d);if(vu>=0&&d.n>vu)bip();vu=d.n;if(d.img!=vi){vi=d.img;document.getElementById('i').src='/'+K+'/ecran.jpg?'+vi;}
 }catch(e){document.getElementById('c').textContent='PC injoignable';}occ=false;}
setInterval(maj,300);maj();
</script>"""

    PAGE_R = r"""<!doctype html><html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Forgemagie</title>
<style>
:root{--fond:#0f1117;--carte:#171a23;--carte2:#1d212c;--bord:#2a2f3d;--txt:#e9ebf1;--gris:#8b92a5;--vert:#3ddc84;
--vert2:#1f9d57;--rouge:#ff6b6b;--or:#ffd166;--bleu:#6ea8fe}
*{box-sizing:border-box}html,body{margin:0;background:var(--fond);color:var(--txt);
font:14px/1.45 "Segoe UI",system-ui,-apple-system,sans-serif}
header{position:sticky;top:0;z-index:5;background:rgba(15,17,23,.92);backdrop-filter:blur(8px);
border-bottom:1px solid var(--bord);padding:14px 24px 0}
.haut{display:flex;gap:16px;align-items:center;flex-wrap:wrap}
h1{font-size:15px;margin:0;letter-spacing:.08em;text-transform:uppercase;color:var(--gris);font-weight:600}
#conseil{flex:1;min-width:260px;font-weight:600;color:var(--vert);font-size:15px;white-space:pre-line}
#conseil.stop{color:var(--rouge)}
.pastille{font-size:12px;padding:3px 10px;border-radius:99px;background:var(--carte2);color:var(--gris);border:1px solid var(--bord)}
.pastille.ok{color:var(--vert);border-color:#1f5a3a}.pastille.ko{color:var(--rouge);border-color:#6b2b2b}
nav{display:flex;gap:4px;margin-top:12px}
nav button{background:none;border:0;color:var(--gris);padding:9px 14px;font:inherit;font-weight:600;cursor:pointer;
border-bottom:2px solid transparent}
nav button:hover{color:var(--txt)}nav button.actif{color:var(--txt);border-bottom-color:var(--vert)}
main{padding:20px 24px 110px;max-width:1280px;margin:0 auto}
.carte{background:var(--carte);border:1px solid var(--bord);border-radius:12px;padding:16px 18px;margin-bottom:16px}
.ligne{display:flex;gap:14px;align-items:end;flex-wrap:wrap}
label.c{display:flex;flex-direction:column;gap:5px;font-size:12px;color:var(--gris)}
input,select{background:#0c0e13;color:var(--txt);border:1px solid var(--bord);border-radius:8px;padding:7px 10px;
font:inherit;outline:none;transition:border-color .12s,box-shadow .12s}
input:focus,select:focus{border-color:var(--vert);box-shadow:0 0 0 3px rgba(61,220,132,.15)}
input.n{width:68px;text-align:center;font-variant-numeric:tabular-nums}input.p{width:52px;text-align:center;padding:6px 4px}
input.err{border-color:var(--rouge)}
button.b{background:var(--carte2);color:var(--txt);border:1px solid var(--bord);border-radius:8px;padding:8px 14px;
font:inherit;font-weight:600;cursor:pointer;transition:background .12s,border-color .12s}
button.b:hover{background:#262b39;border-color:#3a4155}
button.b.principal{background:var(--vert2);border-color:var(--vert2);color:#fff;padding:10px 26px}
button.b.principal:hover{background:#25b565}
button.b.petit{padding:4px 10px;font-size:12px;font-weight:500}
button.b.danger{color:var(--rouge)}
table{width:100%;border-collapse:collapse}
th{font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:var(--gris);font-weight:600;text-align:left;
padding:6px 8px 10px;white-space:nowrap}
th[title]{cursor:help;text-decoration:underline dotted #4a5165;text-underline-offset:4px}
td{padding:6px 8px;border-top:1px solid #20242f;vertical-align:middle}
tr:hover td{background:rgba(255,255,255,.02)}
td.num,th.num{text-align:center;font-variant-numeric:tabular-nums}
td.nom{font-weight:600;white-space:nowrap}td.gris{color:var(--gris)}
td.val{color:var(--vert);font-weight:700;font-size:15px}
.etq{display:inline-block;font-size:10px;font-weight:700;letter-spacing:.05em;text-transform:uppercase;padding:2px 7px;
border-radius:99px;margin-left:8px;vertical-align:1px}
.etq.exo{background:rgba(110,168,254,.15);color:var(--bleu)}.etq.over{background:rgba(255,209,102,.15);color:var(--or)}
.etq.jet{background:rgba(139,146,165,.18);color:var(--gris)}
tr.jet td.nom{color:var(--gris)}
.puces{display:inline-flex;gap:4px;margin-left:8px}
.puces button{background:none;border:1px solid var(--bord);color:var(--gris);border-radius:99px;font-size:11px;
padding:2px 8px;cursor:pointer}.puces button:hover{color:var(--txt);border-color:var(--gris)}
.av{display:none}body.avance .av{display:table-cell}
.barre{position:fixed;left:0;right:0;bottom:0;background:rgba(15,17,23,.95);backdrop-filter:blur(8px);
border-top:1px solid var(--bord);padding:12px 24px;display:flex;gap:10px;align-items:center;flex-wrap:wrap;z-index:5}
.barre .msg{flex:1;min-width:200px;font-weight:600}.ok{color:var(--vert)}.ko{color:var(--rouge)}
.aide{color:var(--gris);font-size:12.5px;margin:10px 2px 0}
.sep{border-top:1px solid var(--bord) !important}
section{display:none}section.actif{display:block}
.sw{display:flex;align-items:center;gap:8px;color:var(--gris);font-size:13px;cursor:pointer;user-select:none}
.sw input{accent-color:var(--vert);width:16px;height:16px}
.vide{color:var(--gris);padding:30px;text-align:center}
@media(max-width:760px){header{padding:10px 12px 0}main{padding:12px 12px 170px}nav{overflow-x:auto}nav button{white-space:nowrap;padding:9px 10px}
.carte{padding:12px}table,tbody,td{display:block}tr{display:grid;grid-template-columns:repeat(3,1fr);gap:8px 10px;
background:var(--carte2);border:1px solid var(--bord);border-radius:10px;padding:12px;margin:8px 0}
tr:first-child{display:none}td{border:0;padding:0;text-align:left!important}td.nom,td.obj,td.large{grid-column:1/-1}td.nom{font-size:16px}
td[data-l]::before{content:attr(data-l);display:block;font-size:10px;text-transform:uppercase;letter-spacing:.05em;color:var(--gris);margin-bottom:3px}
td:empty{display:none}.av{display:none!important}body.avance td.av{display:block!important}
input.n,input.p,td input{width:100%!important;padding:10px 6px;font-size:16px}.puces{display:flex;margin:8px 0 0;gap:8px}
.puces button{flex:1;padding:8px;font-size:13px}.ligne label.c,.ligne select,.ligne input:not([type=checkbox]){width:100%!important}
.barre{padding:8px 10px;gap:6px}.barre .msg{flex-basis:100%;min-width:0}.barre button.b{flex:1;padding:9px 4px;font-size:12px}
.barre button.principal{flex-basis:100%;padding:13px;font-size:15px}select,input{font-size:16px}}
</style></head><body>
<header><div class="haut"><h1>Forgemagie</h1><div id="conseil">Connexion…</div>
<a id="suivi" class="pastille" style="text-decoration:none">← Suivi</a><button id="modeclic" class="pastille" style="cursor:pointer;font:inherit;font-size:12px" title="Automatique : clique la rune et gère le ravitaillement. Souris bougée ou Échap : repasse en manuel.">Mode : …</button>
<span class="pastille">F1 dans Dofus : Automatique · Échap : Manuel</span>
<span id="lien" class="pastille">hors ligne</span></div>
<nav><button data-t="obj" class="actif">Objectif de l'item</button><button data-t="stock">Stock de runes</button>
<button data-t="rep">Repères</button><button data-t="stats">Statistiques</button><button data-t="bilan">Bilan</button></nav></header>
<main>
<section id="obj" class="actif">
 <div class="carte"><div class="ligne">
  <label class="c">Nom de la présélection<input id="nom" style="width:240px"></label>
  <label class="c" title="Le nom exact de l'item dans le jeu. Rempli tout seul quand l'outil arrive à le lire ; corrige-le au besoin.">Nom de l’item dans le jeu<input id="nomjeu" style="width:240px"></label>
  <label class="c">Présélection<select id="presel" style="width:240px"></select></label>
  <label class="c" title="Au premier F1, rejoint l'atelier -83,-40 et charge l'objet de cette preselection.">Atelier de départ<select id="metierdepart"><option value="">Automatique selon le nom</option><option value="joaillomager">Joaillomager</option><option value="cordomager">Cordomager</option><option value="costumager">Costumager</option><option value="forgemager">Forgemager</option><option value="sculptemager">Sculptemager</option><option value="facomager">Facomager</option></select></label>
  <label class="c" title="Les objectifs et le carburant restent inchanges. Une fois tout le jet atteint, monter cette ligne au max naturel avec le reliquat restant, sans exo ni over.">Ligne bonus — reliquat<select id="finition" style="width:200px"></select></label>
  <label class="c">Plan B (exo de rechange)<select id="planb" style="width:200px"></select></label>
  <label class="c" title="Rune à 1 de puits tentée dans le reliquat avant le gros exo (PA, PM, PO). Aucun = jamais.">Petit exo<select id="petitexo" style="width:140px"></select></label>
  <button class="b petit" id="appetit" title="Choisis la rune, puis montre-la avec ta souris dans l'inventaire (4 s)">Apprendre la rune</button>
  <span style="flex:1"></span>
  <label class="sw"><input type="checkbox" id="avance">Réglages avancés (plages Normale / Pa / Ra)</label>
 </div></div>
 <div class="carte" style="padding:8px 10px 12px;overflow-x:auto"><table id="tobj"></table>
  <div id="videobj" class="vide">En attente d'un item dans l'atelier…</div></div>
 <div class="carte"><div class="ligne">
  <label class="c">Ajouter un exo<select id="exostat" style="width:260px"></select></label>
  <label class="c">Quantité<input id="exoqte" class="n" value="1"></label>
  <button class="b" id="exoadd">+ Ajouter</button>
 </div>
 <p class="aide">Objectif à 0 = ligne « jetable » : elle sert de carburant et n'est remontée que quand elle est très basse.
 Objectif au-dessus du max = over. Survole un en-tête de colonne pour son explication.</p></div>
</section>
<section id="stock">
 <div class="carte" style="padding:8px 10px 12px;overflow-x:auto"><table id="tstock"></table>
  <div id="videstock" class="vide">Pose un item dans l'atelier pour voir ses runes.</div></div>
 <div class="carte"><div class="ligne"><label class="c">Sans prix max : accepter jusqu'au prix moyen de l'hôtel de vente +
  <span><input id="marge" class="n"> %</span></label>
  <label class="sw" title="Coupé : plus de « stock bas », plus de guide d'achat. Un ravitaillement en cours est abandonné."><input type="checkbox" id="ravito">Conseils de ravitaillement</label><span style="flex:1"></span>
  <span id="msgstock" style="font-weight:600"></span><button class="b principal" id="savestock">Enregistrer le stock</button></div>
  <p class="aide">« Alerte sous » à 0 = rune non suivie. Les achats se font toujours par lots de 10, 100 ou 1000.</p></div>
</section>
<section id="rep">
 <div class="carte" style="padding:8px 10px 12px"><table id="trep"></table></div>
 <div class="carte"><span id="msgrep" style="font-weight:600">Pour recaler un repère : clique « Calibrer », puis place ta souris dessus
 dans le jeu et ne bouge plus pendant 4 secondes.</span></div>
</section>
<section id="stats"><div class="carte" style="padding:8px 10px 12px;overflow-x:auto"><table id="tstats"></table>
 <div id="videstats" class="vide">Aucune passe enregistrée pour l'instant.</div></div></section>
<section id="bilan"><div class="carte" style="padding:8px 10px 12px;overflow-x:auto"><table id="tlim"></table></div>
<div class="carte"><div class="ligne"><span id="depuis" class="aide" style="margin:0;flex:1"></span>
<button class="b" id="zero" title="Efface les compteurs pour repartir d'un test propre. Tes avis Réglé / Problème sont gardés.">Remettre les compteurs à zéro</button></div>
<p class="aide">OK et PROBLÈME viennent de ce que l'outil a constaté. À CONFIRMER : il a vu passer le cas, à toi de dire si c'était juste. Ton avis passe avant le constat.</p></div>
<div class="carte"><pre id="pbilan" style="margin:0;white-space:pre-wrap;font:13px/1.55 Consolas,monospace"></pre></div></section>
</main>
<div class="barre" id="barre"><span class="msg" id="msg"></span>
 <button class="b" data-c="remplir" data-a="max">Tout au max</button>
 <button class="b" data-c="remplir" data-a="min">Tout au min</button>
 <button class="b" data-c="proposer" title="Remplit les plages Pa / Ra d'après l'objectif">Proposer Pa / Ra</button>
 <button class="b" data-c="vider" title="Efface les plages : l'algo choisit la rune d'après tes passes">Laisser l'algo choisir</button>
 <button class="b principal" data-c="enregistrer">Enregistrer</button></div>
<script>
const K=location.pathname.split('/')[1],$=i=>document.getElementById(i);
let rev=-1,D=null,occ=false,stockVu='';$('suivi').href='/'+K;
function etiq(t,L){t.querySelectorAll('tr').forEach(tr=>{let i=0;[...tr.children].forEach(td=>{if(L[i])td.dataset.l=L[i];i+=td.colSpan||1})})}
const esc=t=>String(t??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const TT={base:'Normale',pa:'Pa',ra:'Ra'};
document.querySelectorAll('nav button').forEach(b=>b.onclick=()=>{
 document.querySelectorAll('nav button').forEach(x=>x.classList.toggle('actif',x===b));
 document.querySelectorAll('section').forEach(s=>s.classList.toggle('actif',s.id===b.dataset.t));
 $('barre').style.display=b.dataset.t==='obj'?'flex':'none';if(b.dataset.t==='stats')stats();
 if(b.dataset.t==='bilan')bilan();});
$('avance').onchange=e=>{document.body.classList.toggle('avance',e.target.checked);
 try{localStorage.setItem('fm_av',e.target.checked?'1':'')}catch(_){}};
try{if(localStorage.getItem('fm_av')){$('avance').checked=true;document.body.classList.add('avance')}}catch(_){}
function etiquettes(tr){const o=parseInt(tr.querySelector('[data-f=obj]').value),mx=+tr.dataset.max,exo=tr.dataset.exo==='1';
 tr.classList.toggle('jet',!exo&&o===0);
 tr.querySelector('.tags').innerHTML=exo?'<span class="etq exo">exo</span>':o===0?'<span class="etq jet">carburant</span>':
  o>mx?'<span class="etq over">over +'+(o-mx)+'</span>':'';}
function rendre(d){
 $('nom').value=d.nom;$('nomjeu').value=d.nom_jeu||'';
 $('metierdepart').value=d.metier_depart||'';
 $('presel').innerHTML='<option value="">— choisir —</option>'+d.items.map(n=>'<option>'+esc(n)+'</option>').join('');
 $('presel').value=d.items.includes(d.nom)?d.nom:'';
 $('planb').innerHTML='<option value="">(aucun)</option>'+d.codes.map(c=>'<option value="'+c.c+'"'+(c.c===d.plan_b?' selected':'')+'>'+esc(c.nom)+'</option>').join('');
 $('petitexo').innerHTML='<option value="">(aucun)</option>'+(d.petits||[]).map(c=>'<option value="'+c.c+'"'+(c.c===d.petit_exo?' selected':'')+'>'+esc(c.nom)+'</option>').join('');
 $('finition').innerHTML='<option value="">(aucune)</option>'+d.rangs.filter(c=>!c.exo&&c.max>0).map(c=>'<option value="'+c.s+'"'+(c.s===d.finition?' selected':'')+'>'+esc(c.nom)+'</option>').join('');
 $('exostat').innerHTML=d.codes.map(c=>'<option value="'+c.c+'">'+esc(c.nom)+'  (puits '+c.puits+')</option>').join('');
 $('videobj').style.display=d.rangs.length?'none':'block';
 let h='';if(d.rangs.length){h='<tr><th>Caractéristique<th class=num>Min<th class=num>Max<th class=num>Actuel'+
  '<th title="Valeur visée. 0 = jetable (carburant). Au-dessus du max = over.">Objectif'+
  '<th class=num title="À partir de cette valeur, on peut tenter les exos. En dessous, on remonte la ligne.">Min accepté'+
  '<th class=num title="Quand la ligne passe sous le min accepté, on la remonte jusqu\'ici. Ligne jetable : vide = automatique, 0 = ne jamais y toucher.">Remonter à';
  for(const t of ['base','pa','ra'])h+='<th class="num av" colspan=2 title="Utiliser la rune '+TT[t]+' seulement quand la valeur actuelle est dans cette plage. Vide = choix automatique.">'+TT[t]+' de … à';
  h+='<th></tr>';
  for(const r of d.rangs){h+='<tr data-s="'+r.s+'" data-max="'+r.max+'" data-min="'+r.min+'" data-exo="'+(r.exo?1:0)+'">'+
   '<td class=nom>'+esc(r.nom)+'<span class=tags></span><td class="num gris">'+(r.exo?'–':r.min)+'<td class="num gris">'+(r.exo?'–':r.max)+
   '<td class="num val" id="v_'+r.s+'">'+esc(r.val)+
   '<td class=obj style="white-space:nowrap"><input class=n data-f=obj value="'+esc(r.obj)+'">'+(r.exo?'':'<span class=puces><button data-v="'+r.min+'">min</button><button data-v="'+r.max+'">max</button><button data-v="0">jetable</button></span>')+
   '<td class=num>'+(r.exo?'':'<input class=n data-f=tol value="'+esc(r.tol)+'">')+
   '<td class=num>'+(r.exo?'':'<input class=n data-f=rem value="'+esc(r.rem)+'">');
   for(const t of ['base','pa','ra']){const p=r.plages[t];h+=p?'<td class="num av"><input class=p data-p="'+t+'" data-i=0 value="'+esc(p[0])+'"><td class="num av"><input class=p data-p="'+t+'" data-i=1 value="'+esc(p[1])+'">':'<td class="num av gris" colspan=2>–';}
   h+='<td style="white-space:nowrap;text-align:right">'+(r.exo?'<button class="b petit" data-ap="'+r.s+'" title="Montre la rune avec ta souris dans l\'inventaire">Apprendre la rune</button> <button class="b petit danger" data-rm="'+r.s+'">Retirer</button>':'')+'</tr>';}}
 $('tobj').innerHTML=h;etiq($('tobj'),['','Min','Max','Actuel','Objectif','Min accepté','Remonter à','Normale de','à','Pa de','à','Ra de','à','']);
 $('tobj').querySelectorAll('tr[data-s]').forEach(tr=>{etiquettes(tr);
  tr.querySelector('[data-f=obj]').oninput=()=>etiquettes(tr);
  tr.querySelectorAll('.puces button').forEach(b=>b.onclick=()=>{tr.querySelector('[data-f=obj]').value=b.dataset.v;etiquettes(tr)});});
 $('tobj').querySelectorAll('[data-ap]').forEach(b=>b.onclick=()=>cmd('apprendre',{code:b.dataset.ap}));
 $('tobj').querySelectorAll('[data-rm]').forEach(b=>b.onclick=()=>cmd('retirer_exo',{code:b.dataset.rm}));
 $('trep').innerHTML='<tr><th>Repère<th class=num>Position (fraction de l\'écran)<th></tr>'+d.lieux.map(l=>'<tr><td class=nom>'+esc(l.nom)+
  '<td class="num gris" id="l_'+l.k+'">'+l.x.toFixed(3)+' ; '+l.y.toFixed(3)+'<td style="text-align:right"><button class="b petit" data-cal="'+l.k+'">Calibrer</button></tr>').join('');
 $('trep').querySelectorAll('[data-cal]').forEach(b=>b.onclick=()=>cmd('calibrer',{k:b.dataset.cal},false));
}
function rendreStock(d){const cle=JSON.stringify(d.stock.rows.map(r=>[r.cle,r.alerte,r.cible,r.prix,r.rech,r.actif]))+d.stock.marge;
 if(cle===stockVu){d.stock.rows.forEach(r=>{const e=document.getElementById('n_'+r.cle);if(e)e.textContent=r.n});return}
 if(document.activeElement&&$('stock').contains(document.activeElement)&&stockVu)return;
 stockVu=cle;$('videstock').style.display=d.stock.rows.length?'none':'block';$('marge').value=d.stock.marge;
 $('tstock').innerHTML=d.stock.rows.length?'<tr><th>Rune<th class=num>En stock<th class=num title="Sous ce nombre, l’outil lance le ravitaillement. 0 = rune non suivie.">Alerte sous'+
  '<th class=num title="Quantité visée après achat.">Remonter à<th class=num title="Prix maximum par rune. Vide = prix moyen de l\'hôtel de vente + le % ci-dessous.">Prix max / rune'+
  '<th title="Doit être exactement le nom affiché sur la fiche de la rune à l\'hôtel de vente.">Texte à taper à l\'hôtel de vente</tr>'+
  d.stock.rows.map(r=>'<tr data-cle="'+r.cle+'"'+(r.debut?' class=g':'')+'><td class=nom'+(r.debut?' style="border-top-color:var(--bord)"':'')+'>'+'<label><input type=checkbox data-f=actif '+(r.actif!==false?'checked':'')+'> '+esc(r.nom)+'</label>'+
  '<td class="num val" id="n_'+r.cle+'">'+esc(r.n)+'<td class=num><input class=n data-f=alerte value="'+esc(r.alerte)+'"><td class=num><input class=n data-f=cible value="'+esc(r.cible)+'">'+
  '<td class=num><input class=n data-f=prix value="'+esc(r.prix)+'"><td class=large><input data-f=rech style="width:220px" value="'+esc(r.rech)+'"></tr>').join(''):'';etiqStock()}
function etiqStock(){etiq($('tstock'),['','En stock','Alerte sous','Remonter à','Prix max / rune','Texte à taper à l’hôtel de vente'])}
const COUL={'OK':'var(--vert)','PROBLÈME':'var(--rouge)','À CONFIRMER':'var(--or)','NON TESTÉ':'var(--gris)','PAS CODÉ':'var(--gris)'};
async function bilan(){try{const d=await(await fetch('/'+K+'/limites.json')).json();$('depuis').textContent='Compteurs depuis le '+d.depuis;
 $('tlim').innerHTML='<tr><th>Limite<th>État<th>Ce que l’outil a constaté<th>Comment tester<th></tr>'+d.limites.map(x=>'<tr><td class=nom style="white-space:normal">'+x.n+'. '+esc(x.titre)+
  '<td data-l="État"><span class=etq style="margin:0;color:'+COUL[x.statut]+';border:1px solid '+COUL[x.statut]+'">'+x.statut+'</span>'+(x.avis?'<div class=aide style="margin:4px 0 0">ton avis (outil : '+x.auto+')</div>':'')+
  '<td class="gris large" data-l="Constat">'+esc(x.preuve||'–')+'<td class="gris large" data-l="Comment tester">'+esc(x.test)+
  '<td class=large style="white-space:nowrap;text-align:right"><button class="b petit" data-n="'+x.n+'" data-a="regle">Réglé</button> <button class="b petit danger" data-n="'+x.n+'" data-a="probleme">Problème</button>'+(x.avis?' <button class="b petit" data-n="'+x.n+'" data-a="">Effacer mon avis</button>':'')+'</tr>').join('');
 $('tlim').querySelectorAll('[data-n]').forEach(b=>b.onclick=async()=>{await cmd('avis_limite',{n:b.dataset.n,avis:b.dataset.a},false);setTimeout(bilan,500)});
 $('pbilan').textContent=await(await fetch('/'+K+'/bilan.txt')).text()}catch(e){}}
$('zero').onclick=async()=>{await cmd('bilan_zero',{},false);setTimeout(bilan,500)};
function form(){const f={nom:$('nom').value,nom_jeu:$('nomjeu').value,metier_depart:$('metierdepart').value,plan_b:$('planb').value||null,petit_exo:$('petitexo').value||null,finition:$('finition').value||null,rangs:{}};
 $('tobj').querySelectorAll('tr[data-s]').forEach(tr=>{const r={obj:tr.querySelector('[data-f=obj]').value,plages:{}};
  const t=tr.querySelector('[data-f=tol]'),m=tr.querySelector('[data-f=rem]');if(t)r.tol=t.value;if(m)r.rem=m.value;
  tr.querySelectorAll('[data-p]').forEach(i=>{(r.plages[i.dataset.p]=r.plages[i.dataset.p]||['',''])[+i.dataset.i]=i.value});
  f.rangs[tr.dataset.s]=r});return f}
async function cmd(c,extra,avecForm=true){const corps=Object.assign({cmd:c},extra||{});if(avecForm)corps.form=form();
 try{const r=await fetch('/'+K+'/cmd',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(corps)});
  if(!r.ok)$('msg').textContent='Refusé par l’outil (appareil hors du réseau local ?).';}catch(e){$('msg').textContent='PC injoignable'}}
document.querySelectorAll('#barre [data-c]').forEach(b=>b.onclick=()=>cmd(b.dataset.c,b.dataset.a?{cle:b.dataset.a}:{}));
$('exoadd').onclick=()=>cmd('ajouter_exo',{code:$('exostat').value,qte:$('exoqte').value});
$('appetit').onclick=()=>{const c=$('petitexo').value;if(c)cmd('apprendre',{code:c})};
$('presel').onchange=e=>{if(e.target.value)cmd('preselection',{nom:e.target.value},false)};
$('ravito').onchange=e=>cmd('ravito',{actif:e.target.checked},false);
$('savestock').onclick=()=>{const rows={};$('tstock').querySelectorAll('tr[data-cle]').forEach(tr=>{const o={};
 tr.querySelectorAll('[data-f]').forEach(i=>o[i.dataset.f]=i.type==='checkbox'?i.checked:i.value);rows[tr.dataset.cle]=o});stockVu='';
 cmd('stock',{rows:rows,marge:$('marge').value},false)};
async function stats(){try{const r=await(await fetch('/'+K+'/stats.json')).json();$('videstats').style.display=r.length?'none':'block';
 $('tstats').innerHTML=r.length?'<tr><th>Rune<th>Situation<th class=num>Passées<th class=num>SC<th class=num>SN<th class=num>Échecs<th class=num>Réussite</tr>'+
  r.map(x=>'<tr><td class=nom>'+esc(x[0])+'<td class=gris>'+esc(x[1])+'<td class=num>'+x[2]+'<td class=num>'+x[3]+'<td class=num>'+x[4]+'<td class=num>'+x[5]+'<td class="num val">'+x[6]+'</tr>').join(''):'';}catch(e){}}
async function maj(){if(occ)return;occ=true;try{const d=await(await fetch('/'+K+'/reglages.json')).json();D=d;
 (()=>{const b=$('modeclic'),a=d.mode==='automatique';b.textContent='Mode : '+(a?'AUTOMATIQUE':'MANUEL');
  b.className='pastille '+(a?'ok':'ko');b.dataset.m=d.mode})();
 $('lien').textContent='en ligne';$('lien').className='pastille ok';
 $('conseil').textContent=d.conseil;$('conseil').className=d.stop?'stop':'';
 $('msg').textContent=d.etat;$('msg').className='msg '+(d.ok?'ok':'ko');
 if(document.activeElement!==$('ravito'))$('ravito').checked=d.stock.ravito!==false;
 $('msgstock').textContent=d.stock.msg;$('msgstock').className=d.stock.ok?'ok':'ko';
 if(d.calib){$('msgrep').textContent=d.calib;$('msgrep').className=d.calib_ok?'ok':'ko'}
 if(d.rev!==rev){rev=d.rev;rendre(d)}else{d.rangs.forEach(r=>{const e=document.getElementById('v_'+r.s);if(e)e.textContent=r.val});
  d.lieux.forEach(l=>{const e=document.getElementById('l_'+l.k);if(e)e.textContent=l.x.toFixed(3)+' ; '+l.y.toFixed(3)})}
 rendreStock(d);
 }catch(e){$('lien').textContent='hors ligne';$('lien').className='pastille ko'}occ=false}
$('modeclic').onclick=e=>cmd('mode',{mode:e.target.dataset.m==='automatique'?'manuel':'automatique'},false);
setInterval(maj,400);maj();
</script></body></html>
"""

    def __init__(self):
        self.reglages, self.cmds, self.ouvrir = None, None, False
        self.texte, self.stop, self.item, self.t = "en attente de la fenêtre de forgemagie", False, "", 0.0
        self.t_exo, self.vu_img, self.n_img, self.achats = 0.0, None, 0, []
        self.jpeg, self.t_img, self.evs, self.n, self.vus, self.exos = b"", 0.0, [], 0, {}, []
        self.cle = hashlib.sha1(os.urandom(16)).hexdigest()[:6]
        try:
            self.cle = open(F_TEL, encoding="utf-8").read().strip().rsplit("/", 1)[-1][:12] or self.cle
        except OSError:
            pass
        self.sujet = (charger_txt(F_NTFY) or "").strip()

    def demarrer(self):
        import socket
        import threading
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        suivi = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                chemin = self.path.split("?")[0].strip("/").split("/")
                if chemin[0] != suivi.cle:
                    self.send_error(404)
                    return
                quoi = chemin[1] if len(chemin) > 1 else ""
                if quoi == "etat":
                    corps, typ = json.dumps(suivi.etat()).encode(), "application/json"
                elif quoi == "ecran.jpg":
                    corps, typ = suivi.jpeg, "image/jpeg"
                elif quoi == "reglages":
                    corps, typ = suivi.PAGE_R.encode(), "text/html; charset=utf-8"
                elif quoi == "reglages.json":
                    if suivi.reglages is None:
                        self.send_error(503)
                        return
                    corps, typ = json.dumps(suivi.reglages).encode(), "application/json"
                    if time.time() - getattr(suivi, "t_page", 0) > 30:
                        suivi.t_page = time.time()
                        BILAN.note("page", "ouverte", detail=self.client_address[0])
                elif quoi == "limites.json":
                    corps, typ = json.dumps({"depuis": BILAN.d.get("depuis"), "limites": BILAN.limites()}).encode(), "application/json"
                elif quoi == "bilan.txt":
                    corps, typ = BILAN.texte().encode(), "text/plain; charset=utf-8"
                elif quoi == "stats.json":
                    lignes = []
                    for (taille, s_, ctx), (sc, sn, ec) in sorted(Panneau.stats_passes().items(),
                                                                  key=lambda kv: -sum(kv[1])):
                        n = sc + sn + ec
                        lignes.append([nom_rune(s_, taille) if s_ in POIDS else s_, ctx, n, sc, sn, ec,
                                       f"{(sc + sn) / n:.0%}"])
                    corps, typ = json.dumps(lignes).encode(), "application/json"
                else:
                    corps, typ = suivi.PAGE.encode(), "text/html; charset=utf-8"
                self.send_response(200)
                self.send_header("Content-Type", typ)
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(corps)))
                self.end_headers()
                self.wfile.write(corps)

            def do_POST(self):
                chemin = self.path.split("?")[0].strip("/").split("/")
                # Accepte : ce PC, ou un appareil du meme reseau local qui connait le lien secret ; et seulement
                # depuis une page servie par l'outil lui-meme (pas depuis un autre site ouvert dans le navigateur).
                ip = self.client_address[0].replace("::ffff:", "")
                local = ip in ("127.0.0.1", "::1") or ip.startswith(("10.", "192.168.", "169.254.")) \
                    or re.match(r"172\.(1[6-9]|2\d|3[01])\.", ip) is not None
                orig = self.headers.get("Origin")
                if not local or orig and orig.split("//")[-1] != self.headers.get("Host"):
                    self.send_error(403)
                    return
                if chemin[0] == suivi.cle and chemin[1:] == ["suivant"]:
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
                if chemin[0] == suivi.cle and chemin[1:] == ["decision"]:
                    # Seule chose modifiable depuis le telephone : accepter, pour UNE rune, UN des prix affiches.
                    try:
                        c = json.loads(self.rfile.read(min(int(self.headers.get("Content-Length", 0)), 2000)))
                        q = GUIDE.demande
                        assert q and c.get("nom") == q["nom"]
                        if c.get("lot") is None:
                            GUIDE.derog.pop(norm(q["nom"]), None)
                            suivi.evenement("refus " + q["nom"], f"Prix refusé pour {q['nom']} : pas d'achat", 5)
                        else:
                            u = q["lots"][int(c["lot"])] if int(c["lot"]) in q["lots"] else q["lots"][str(c["lot"])]
                            GUIDE.derog[norm(q["nom"])] = u * 1.005      # ce prix-la, pas plus : le lot suivant
                            suivi.evenement("accepte " + q["nom"],       # plus cher redeclenche la question
                                            f"Prix accepté pour {q['nom']} : {u} k la rune au maximum", 5)
                        GUIDE.demande, GUIDE.t_fiche = None, 0.0
                        BILAN.note("page", "decision telephone", detail=str(c))
                    except Exception:
                        self.send_error(400)
                        return
                    self.send_response(204)
                    self.end_headers()
                    return
                if chemin[0] != suivi.cle or chemin[1:] != ["cmd"] or suivi.cmds is None:
                    self.send_error(403)
                    return
                try:
                    c = json.loads(self.rfile.read(min(int(self.headers.get("Content-Length", 0)), 200000)))
                    assert isinstance(c, dict)
                    suivi.cmds.put(c)
                    BILAN.note("page", "commande", detail=f"{c.get('cmd')} depuis {ip}")
                    if ip not in ("127.0.0.1", "::1"):
                        BILAN.note("page", "commande telephone", detail=str(c.get("cmd")))
                except Exception:
                    self.send_error(400)
                    return
                self.send_response(204)
                self.end_headers()

        def servir():
            # l'instance precedente tient encore le port quelques instants avant de se fermer : on reessaie
            for essai in range(40):
                try:
                    srv = ThreadingHTTPServer(("0.0.0.0", PORT_SUIVI), H)
                    break
                except OSError as e:
                    if essai == 39:
                        log(f"suivi telephone indisponible (port {PORT_SUIVI}) : {e}")
                        return
                    time.sleep(.4)
            if suivi.ouvrir:
                suivi.ouvrir_reglages()
            srv.serve_forever()

        threading.Thread(target=servir, daemon=True).start()
        try:
            so = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            so.connect(("10.255.255.255", 1))        # aucune donnee envoyee : sert a connaitre l'adresse locale
            ip = so.getsockname()[0]
            so.close()
        except OSError:
            ip = "ADRESSE-DU-PC"
        url = f"http://{ip}:{PORT_SUIVI}/{self.cle}"
        try:
            with open(F_TEL, "w", encoding="utf-8") as f:
                f.write(url + "\n")
        except OSError:
            pass
        log(f"suivi sur le telephone (meme Wi-Fi) : {url}")

    def ouvrir_reglages(self):
        """Ouvre la page de reglages dans une fenetre a part (Edge ou Chrome en mode application, sinon le
        navigateur par defaut)."""
        url = f"http://127.0.0.1:{PORT_SUIVI}/{self.cle}/reglages"
        log(f"reglages : {url}")
        try:
            if sys.platform == "win32":
                import subprocess
                for nav in ("msedge", "chrome"):
                    if subprocess.call(f'start "" {nav} --app={url} --window-size=1180,860', shell=True,
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0:
                        BILAN.pose("systeme", "ouverture_page", f"fenêtre {nav} lancée")
                        return
            BILAN.pose("systeme", "ouverture_page", "navigateur par défaut")
            import webbrowser
            webbrowser.open(url)
        except Exception as err:
            log(f"ouverture de la page de reglages impossible : {err}")
            BILAN.pose("systeme", "ouverture_page", f"échec : {err}")

    def etat(self):
        q = GUIDE.demande
        if q and time.time() - q["t"] > 15:
            q = GUIDE.demande = None               # la fiche n'est plus a l'ecran
        return {"demande": q, "items": getattr(self, "liste_items", []), "file": getattr(self, "file", []),
                "file_suivi": getattr(self,"file_suivi",{}),
                "texte": self.texte, "stop": self.stop, "item": (f"{self.nom_reel} — objectif : {self.item}" if getattr(self, "nom_reel", "") and self.item and self.nom_reel.lower() != self.item.lower() else (getattr(self, "nom_reel", "") or self.item)), "age": int(time.time() - self.t),
                "exos": self.exos, "evenements": self.evs[:40], "n": self.n, "img": self.n_img,
                "achats": self.achats, "suite": getattr(self, "suite", None),
                "suivant": getattr(self, "suivant", None)}

    def evenement(self, cle, msg, delai=60):
        """Ajoute un evenement (et une notification) ; le meme n'est pas repete avant `delai` secondes."""
        if time.time() - self.vus.get(cle, 0) < delai:
            return
        self.vus[cle] = time.time()
        self.evs.insert(0, [time.strftime("%H:%M:%S"), msg])
        del self.evs[80:]
        self.n += 1
        log("evenement : " + msg)
        if self.sujet:
            import threading
            threading.Thread(target=self._pousser, args=(msg,), daemon=True).start()

    def _pousser(self, msg):
        try:
            import urllib.request
            urllib.request.urlopen(urllib.request.Request(
                "https://ntfy.sh/" + self.sujet, data=msg.encode("utf-8"), headers={"Title": "Forgemagie"}), timeout=8)
        except Exception:
            pass

    def maj_exos(self, item, vises=None):
        """Une ligne par exo ou over demande : les tentatives du dernier point vise seulement (pour « 2 % do
        sorts », celles faites avec le 1er % deja pose ; pour un over 4 -> 6, celles faites a 5)."""
        c = compteur_exos(item)
        self.exos = []
        for s_, n_, d_ in vises or []:
            t = c.get((s_, n_ - 1), [0, 0, 0])
            nom = (f"{n_}e % " if n_ > 1 else "") + nom_code(s_) if d_ == 0 else f"{nom_code(s_)} {n_ - 1} → {n_}"
            self.exos.append([nom, t[0], t[1], t[2], c.get((s_, d_), [0, 0, 0])[1] if n_ - d_ > 1 else None])

    def maj(self, bgr, etat, txt, reco, cadre, item):
        self.texte, self.stop, self.item, self.t = txt, bool(reco.get("stop")), item, time.time()
        if getattr(self, "suivant", None) and self.suivant == item:
            self.suivant = None
        m = re.search(r"A ACHETER : ([^|]+)", txt)
        if m:
            self.evenement("achat " + m.group(1).strip(), "Rune manquante : " + m.group(1).strip(), 300)
        if txt.startswith("STOP"):
            self.evenement("stop", txt.split("|")[0].strip(), 120)
        if txt.startswith("ATTENDS"):
            self.evenement("attends", txt.split("|")[0].strip(), 120)
        if txt.startswith("OBJECTIF ATTEINT"):
            self.evenement("fini", "Objectif atteint sur " + (item or "l'item"), 600)
        # image : a chaque changement lu sur l'ecran (donc a chaque rune), sinon une fois par seconde
        cle = (resume(etat), txt)
        if not etat.get("rows") or time.time() - self.t_img < (.15 if cle != self.vu_img else 1):
            return
        self.t_img, self.vu_img = time.time(), cle
        x, y, w, h = etat["rows"][0]
        bas = etat["rows"][-1][1] + etat["rows"][-1][3]
        x0, y0 = max(0, x - 12), max(0, y - int(3.4 * h))
        img = bgr[y0:min(bgr.shape[0], bas + h), x0:min(bgr.shape[1], x + int(1.8 * w))].copy()
        if cadre:
            cv2.rectangle(img, (int(cadre[0]) - x0, int(cadre[1]) - y0), (int(cadre[2]) - x0, int(cadre[3]) - y0),
                          (48, 59, 255) if reco.get("stop") else (102, 255, 0), 3)
        k = min(1.0, 900 / img.shape[1])
        if k < 1:
            img = cv2.resize(img, None, fx=k, fy=k, interpolation=cv2.INTER_AREA)
        ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 60])
        if ok:
            self.jpeg = buf.tobytes()
            self.n_img += 1



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


SUIVI = Suivi()


# ---------------------------------------------------------------------------------------------------
# Guide de ravitaillement : quand une rune passe sous son seuil, l'outil indique pas a pas ou aller et quoi
# acheter (fermer la forgemagie, sortir, hotel de vente, liste d'achats, rentrer, bon atelier, remettre
# l'item). Il montre et il explique ; c'est toi qui te deplaces, qui tapes et qui achetes.
F_LIEUX = os.path.join(ICI, "fm_lieux.json")
D_REPERES = os.path.join(ICI, "fm_reperes")   # une petite image de reference par repere (comparaison d'image)
REPERE_TAILLE, REPERE_MARGE, REPERE_SEUIL = 120, 110, .6    # interface : cote de l'image, zone de recherche, ressemblance
REPERE_DECOR, REPERE_POINTS = 220, 12                       # decor : cote de l'image de reference, appariements minimum
D_PARCOURS = os.path.join(ICI, "fm_parcours")
PARCOURS_PAUSE, PARCOURS_MAX = 5, 300     # une capture au moins toutes les 5 s pendant le parcours, 300 gardees
MARGE_PRIX, FICHE_PAUSE = 20, .3      # % tolere au-dessus du prix moyen sans prix max ; secondes entre deux coups d'oeil
FICHE_RELIRE = 8                      # relecture complete forcee au moins toutes les 8 s, meme si rien ne semble bouger
REPERES_DECOR = {"sortie", "hdv", "porte", "cordomager", "multi", "costumager", "joaillomager"}
# Reperes en fraction de l'ecran (x, y), releves sur tes captures du Port de givre en 1920x1080.
# Chacun se recale avec le bouton « Repères » de la fenetre d'objectifs.
LIEUX_DEFAUT = {
    "fermer": (1585 / 1917, 178 / 1078, "Croix qui ferme la forgemagie"),
    "sortie": (1175 / 1917, 692 / 1078, "Case de sortie de l'atelier"),
    "hdv": (781 / 1917, 450 / 1078, "Hôtel de vente (dehors)"),
    "recherche": (712 / 1917, 262 / 1078, "Barre de recherche de l'hôtel de vente"),
    "porte": (1055 / 1917, 415 / 1078, "Porte de l'atelier (dehors)"),
    "cordomager": (790 / 1917, 445 / 1078, "Atelier Cordomager"),
    "multi": (706 / 1917, 498 / 1078, "Atelier Sculptemager / Forgemager / Façomager"),
    "costumager": (1089 / 1917, 444 / 1078, "Atelier Costumager"),
    "joaillomager": (1182 / 1917, 474 / 1078, "Atelier Joaillomager"),
    "equipement": (1222 / 1917, 268 / 1078, "Onglet Équipement de l'inventaire"),
    "ressources": (1222 / 1917, 353 / 1078, "Onglet Ressources de l'inventaire"),
}
METIERS = {"cordomager": "cordomager", "joaillomager": "joaillomager", "costumager": "costumager",
           "sculptemager": "multi", "forgemager": "multi", "facomager": "multi"}
# Texte a taper dans la recherche de l'hotel de vente (modifiable dans « Stock de runes »)
_RECH = {"vi": "vi", "ini": "ini", "pods": "pod", "fo": "fo", "int": "ine", "cha": "cha", "agi": "age", "sa": "sa",
         "pp": "prospe", "pui": "pui", "cri": "cri", "soin": "so", "do": "do", "invo": "invo", "po": "po",
         "pm": "ga pme", "pa": "ga pa", "tacle": "tac", "fuite": "fui", "ret_pa": "ret pa", "ret_pm": "ret pme",
         "esq_pa": "ré pa", "esq_pm": "ré pme", "do_cri": "do cri", "do_pou": "do pou", "re_cri": "ré cri",
         "re_pou": "ré pou", "do_per_so": "do per so", "do_per_ar": "do per ar", "do_per_di": "do per di",
         "do_per_me": "do per mé", "re_per_me": "ré per mé", "re_per_di": "ré per di", "renvoi": "do ren",
         "do_pieges": "do pi", "pui_pieges": "pi per"}


def recherche_rune(s, t, regl=None):
    """Texte a taper pour trouver cette rune a l'hotel de vente."""
    perso = ((regl or {}).get(f"{s}/{t}") or {}).get("recherche")
    if perso:
        return perso
    try:
        import dofusdb
        exact = dofusdb.charger().get(f"{s}/{t}")
        if exact:
            return exact.lower()
    except Exception:
        pass
    base = _RECH.get(s)
    if base is None:
        for pre, lib in (("re_per_", "ré per "), ("re_", "ré "), ("do_", "do ")):
            if s.startswith(pre):
                base = lib + s[len(pre):]
                break
    return "rune " + ("" if t == "base" else t + " ") + (base or s)


class Guide:
    def __init__(self):
        self.phase, self.metier, self.vu_hdv = None, "", False
        self.t_ocr, self.hdv, self.t_metier, self.liste = 0.0, False, 0.0, []
        self.t_fiche, self.fiche, self.t_vu_fiche, self.t_vu_hdv, self.regl = 0.0, None, 0.0, 0.0, None
        self.noms_hdv, self.liste_incomplete = None, False
        self.derog, self.demande = {}, None    # prix acceptes a la main pour une rune ; question en attente
        self.alertes = []
        self.gabarits, self.cache = {}, {}
        self.det, self.norme, self.refs, self.vue = None, None, {}, (None, None)

    @staticmethod
    def lieux():
        d = {k: v[:2] for k, v in LIEUX_DEFAUT.items()}
        for k, v in charger_json(F_LIEUX, {}).items():
            if k in d and isinstance(v, list) and len(v) == 2:
                d[k] = tuple(v)
        return d

    def _attendu(self, bgr, nom):
        fx, fy = self.lieux()[nom]
        return int(fx * bgr.shape[1]), int(fy * bgr.shape[0])

    def _dans_le_decor(self, bgr, nom):
        """Repere du decor (porte, hotel de vente, sortie, ateliers) retrouve par comparaison d'image, meme si
        le zoom ou le cadrage de la carte a change et si des personnages passent devant : on apparie des
        points caracteristiques entre l'image de reference et l'ecran. None si le repere n'est pas a l'ecran."""
        vu = self.cache.get(nom)
        if vu and time.time() - vu[0] < 1.5:
            return vu[1]
        pt = None
        try:
            if self.det is None:
                try:
                    self.det, self.norme = cv2.SIFT_create(), cv2.NORM_L2
                except AttributeError:
                    self.det, self.norme = cv2.ORB_create(nfeatures=4000), cv2.NORM_HAMMING
            if nom not in self.refs:
                g = cv2.imread(os.path.join(D_REPERES, nom + ".png"))
                self.refs[nom] = None if g is None else \
                    (self.det.detectAndCompute(cv2.cvtColor(g, cv2.COLOR_BGR2GRAY), None), g.shape[:2])
            ref = self.refs[nom]
            if ref is not None and ref[0][1] is not None:
                (k1, d1), (gh, gw) = ref
                if self.vue[0] is not bgr:                    # points de l'ecran : calcules une fois par image
                    self.vue = (bgr, self.det.detectAndCompute(cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY), None))
                k2, d2 = self.vue[1]
                if d2 is not None and len(k2) >= 8:
                    paires = cv2.BFMatcher(self.norme).knnMatch(d1, d2, k=2)
                    bons = [a[0] for a in paires if len(a) == 2 and a[0].distance < .75 * a[1].distance]
                    if len(bons) >= REPERE_POINTS:
                        A, ok = cv2.estimateAffinePartial2D(np.float32([k1[m.queryIdx].pt for m in bons]),
                                                            np.float32([k2[m.trainIdx].pt for m in bons]),
                                                            ransacReprojThreshold=4)
                        ech = 0 if A is None else float(np.hypot(A[0, 0], A[0, 1]))
                        if A is not None and int(ok.sum()) >= REPERE_POINTS and .4 < ech < 2.5:
                            x, y = A @ np.array([gw / 2, gh / 2, 1.0])
                            if 0 <= x < bgr.shape[1] and 0 <= y < bgr.shape[0]:
                                pt = (int(x), int(y))
        except cv2.error:
            pt = None
        self.cache[nom] = (time.time(), pt)
        return pt

    def _point(self, bgr, nom):
        frais = not (self.cache.get(nom) and time.time() - self.cache[nom][0] < 1.0)
        t0 = time.time()
        p = self._dans_le_decor(bgr, nom) if nom in REPERES_DECOR else self._interface(bgr, nom)
        if frais:                                  # une vraie recherche, pas une reponse gardee en memoire
            BILAN.duree("repere decor" if nom in REPERES_DECOR else "repere interface", time.time() - t0)
            BILAN.note("reperes", nom, trouve=p is not None, point=list(p) if p else None,
                       cal=nom in charger_json(F_LIEUX, {}))
            if nom in REPERES_DECOR and self.det is not None:
                BILAN.pose("systeme", "detecteur", type(self.det).__name__)
        return p

    def _visible(self, bgr, nom):
        """Le repere d'interface est-il vraiment a l'ecran (et pas cache par une autre fenetre) ? Vrai si on ne
        peut pas le savoir (pas d'image de reference)."""
        self.cache.pop(nom, None)
        self._interface(bgr, nom)
        return getattr(self, "ressemblance", {}).get(nom, 1.0) >= .35

    def _interface(self, bgr, nom):
        """Position du repere : la ou l'image de reference (fm_reperes/<nom>.png) est retrouvee a l'ecran, autour
        de l'endroit attendu. Tolerant : un personnage devant le repere ne cache qu'une partie de l'image. Si
        rien ne ressemble assez, on garde l'endroit attendu."""
        ex, ey = self._attendu(bgr, nom)
        vu = self.cache.get(nom)
        if vu and time.time() - vu[0] < 1.0:
            return vu[1]
        pt, gab = (ex, ey), self.gabarits.get(nom)
        if nom not in self.gabarits:
            gab = self.gabarits[nom] = cv2.imread(os.path.join(D_REPERES, nom + ".png"))
        if gab is not None:
            gh, gw = gab.shape[:2]
            m = REPERE_MARGE
            x0, y0 = max(0, ex - gw // 2 - m), max(0, ey - gh // 2 - m)
            zone = bgr[y0:ey + gh // 2 + m, x0:ex + gw // 2 + m]
            if zone.shape[0] >= gh and zone.shape[1] >= gw:
                r = cv2.matchTemplate(zone, gab, cv2.TM_CCOEFF_NORMED)
                _, mx, _, loc = cv2.minMaxLoc(r)
                self.__dict__.setdefault("ressemblance", {})[nom] = float(mx)
                if mx >= REPERE_SEUIL:
                    pt = (x0 + loc[0] + gw // 2, y0 + loc[1] + gh // 2)
        self.cache[nom] = (time.time(), pt)
        return pt

    @staticmethod
    def dedans(bgr):
        """Dans l'atelier : la carte est entouree de noir (bande du haut entierement noire)."""
        H, W = bgr.shape[:2]
        return (bgr[int(.05 * H):int(.14 * H), int(.3 * W):int(.75 * W)].max(axis=2) < 12).mean() > .9

    def _inventaire_ouvert(self, bgr):
        x, y = self._point(bgr, "equipement")
        return bgr[max(0, y - 8):y + 8, max(0, x - 8):x + 8].max() > 60

    def _hdv_ouvert(self, bgr, ocr):
        H, W = bgr.shape[:2]
        if abs(W - 1920) <= 8 and abs(H - 1080) <= 8:        # titre « Hôtel de vente » reconnu par son image : immediat
            if time.time() - self.t_ocr > .15:
                self.t_ocr = time.time()
                m = cv2.matchTemplate(bgr[100:270].min(axis=2), self._gabarit("titre"), cv2.TM_CCOEFF_NORMED)
                self.hdv = float(m.max()) >= .8
            return self.hdv
        if time.time() - self.t_ocr > .8:
            self.t_ocr = time.time()
            t = norm(ocr.ligne(bgr[int(.150 * H):int(.184 * H), int(.44 * W):int(.58 * W)]))
            self.hdv = "hotel" in t or "vente" in t or difflib.SequenceMatcher(None, t, "hoteldevente").ratio() > .7
        return self.hdv

    def _journal(self, encore_bas):
        """Une ligne par ravitaillement dans fm_ravitaillements.txt : ce qui etait demande, ce qui a ete vu a
        l'hotel de vente, ce qui reste sous le seuil au retour, et tout ce qui a cloche en route."""
        try:
            bas = {a["rune"] for a in encore_bas}
            runes = []
            for a in self.liste:
                etat = "ENCORE SOUS LE SEUIL" if a["rune"] in bas else "stock remonté"
                vu = (f"fiche lue, prix moyen {a['moyen']} k, max {a['plafond']} k, lots {a['lots_vus']}"
                      if a.get("moyen") else "FICHE JAMAIS LUE")
                runes.append(f"{a['rune']} (avait {a['stock']}, à acheter {a['acheter']}) : {etat} ; {vu}")
            ok = not bas and not self.alertes
            with open(os.path.join(ICI, "fm_ravitaillements.txt"), "a", encoding="utf-8") as f:
                f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} | {'OK' if ok else 'À VÉRIFIER'} | durée "
                        f"{int(time.time() - getattr(self, 't_debut', time.time()))} s | " + " || ".join(runes)
                        + (" | alertes : " + " ; ".join(dict.fromkeys(self.alertes)) if self.alertes else "") + "\n")
            BILAN.note("parcours", "OK" if ok else "à vérifier")
            if len(self.liste) >= 2:
                BILAN.note("parcours", "liste OK" if ok else "liste à vérifier", detail=", ".join(a["rune"] for a in self.liste))
            if not ok:
                SUIVI.evenement("ravito " + str(int(time.time())), "Ravitaillement à vérifier : "
                                + (", ".join(sorted(bas)) + " encore sous le seuil" if bas else self.alertes[0]), 5)
        except Exception as err:
            log(f"journal du ravitaillement non ecrit : {err}")

    def _alerte(self, msg):
        if msg not in getattr(self, "alertes", []):
            self.alertes = getattr(self, "alertes", []) + [msg]

    def _enregistrer(self, bgr, r):
        """Garde une capture du parcours de ravitaillement a chaque changement de consigne (et au moins toutes les
        PARCOURS_PAUSE s), avec le cadre propose dessine dessus, dans fm_parcours/. Sert a corriger apres coup."""
        if r is None and self.phase is None:
            return
        cle = (r[0].split("\n")[0][:60], r[1] and (r[1][0] // 20, r[1][1] // 20)) if r else None
        if cle == getattr(self, "_parc", 0):
            if time.time() - getattr(self, "_t_parc", 0) < PARCOURS_PAUSE or getattr(self, "_n_parc", 0) >= 6:
                return                               # meme consigne : 6 captures au plus, pas tout l'album
            self._n_parc = getattr(self, "_n_parc", 0) + 1
        else:
            self._n_parc = 0
        self._parc, self._t_parc = cle, time.time()
        try:
            os.makedirs(D_PARCOURS, exist_ok=True)
            nom = time.strftime("%Y%m%d_%H%M%S") + f"_{int(time.time() * 10) % 10}"
            img = bgr.copy()
            if r and r[1]:
                cv2.rectangle(img, (r[1][0] - 45, r[1][1] - 22), (r[1][0] + 45, r[1][1] + 22), (0, 255, 0), 2)
            cv2.imwrite(os.path.join(D_PARCOURS, nom + ".jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 80])
            with open(os.path.join(D_PARCOURS, "parcours.txt"), "a", encoding="utf-8") as f:
                f.write(f"{nom} | phase {self.phase} | cadre {r[1] if r else None} | "
                        f"{r[0] if r else 'rien'} | lu : {self.fiche}\n".replace("\n", " / ") + "\n")
            vieux = sorted(x for x in os.listdir(D_PARCOURS) if x.endswith(".jpg"))[:-PARCOURS_MAX]
            for x in vieux:
                os.remove(os.path.join(D_PARCOURS, x))
        except Exception as err:
            log(f"enregistrement du parcours impossible : {err}")

    def _fiche(self, bgr, ocr):
        """Ce qui est ouvert a l'hotel de vente : {"fiches": [{nom, moyen, lots: {taille: prix}, ys, qte, mx, my}],
        "dial": {nom, n, prix, pt} ou None}. Lecture de tout l'ecran, donc lente : une fois par FICHE_PAUSE s."""
        if time.time() - self.t_fiche < FICHE_PAUSE:
            return self.fiche
        gris = bgr.min(axis=2)                               # texte blanc garde, icone doree des kamas effacee
        H_, W_ = gris.shape
        # 1) On ne lit que la zone ou s'ouvrent l'hotel de vente et ses fiches : le reste de l'ecran (discussion,
        #    inventaire, carte) est noirci, donc plus aucun texte a y reconnaitre.
        zx0, zx1, zy0, zy1 = int(.08 * W_), int(.70 * W_), int(.13 * H_), int(.80 * H_)
        zone = gris[zy0:zy1, zx0:zx1]
        # 2) On ne relit que si les fenetres ont change : empreinte = quantite de texte clair par case, dans les
        #    cases sombres (fenetres du jeu). Le decor anime autour ne compte pas.
        ch, cw = zone.shape[0] // 24, zone.shape[1] // 48
        coupe = (slice(0, ch * 24), slice(0, cw * 48))
        clair = (zone[coupe] > 170).reshape(24, ch, 48, cw).sum(axis=(1, 3)).astype(int)
        sombre = (bgr[zy0:zy1, zx0:zx1].max(axis=2)[coupe] < 95).reshape(24, ch, 48, cw).mean(axis=(1, 3)) > .6
        vieux = getattr(self, "empreinte", None)
        self.t_fiche = t_debut = time.time()       # t_debut : copie locale, t_fiche peut etre remis a 0 par le telephone
        if vieux is not None and time.time() - getattr(self, "t_lu", 0) < FICHE_RELIRE:
            commun = sombre & vieux[1]
            if commun.any() and (sombre != vieux[1]).mean() < .02 and np.abs(clair - vieux[0])[commun].max() <= 4:
                self.n_evite = getattr(self, "n_evite", 0) + 1
                if self.fiche:
                    self.t_vu_fiche = time.time()
                return self.fiche                            # rien n'a bouge : la derniere lecture tient toujours
        self.empreinte, self.t_lu = (clair, sombre), time.time()
        rapide = None
        if abs(W_ - 1920) <= 8 and abs(H_ - 1080) <= 8:      # chemin rapide : fenetres reperees par leur image, puis
            try:                                             # lecture des seules lignes utiles (pas de l'ecran entier)
                rapide = self._fiche_rapide(bgr, gris, ocr)
            except Exception as err:
                BILAN.note("erreurs", f"lecture rapide hdv : {type(err).__name__} {str(err)[:80]}")
        if rapide:
            fiches, dial, res, tri = rapide
            BILAN.duree("lecture rapide hdv", time.time() - t_debut)
        else:
            self.t_lent = time.time()
            masque = gris.copy()                                 # discussion, barre du bas, inventaire, carte : effaces
            masque[zy1:], masque[:, zx1:] = 40, 40
            g3 = cv2.merge([masque, masque, masque])
            mots = ocr.tout(g3)
            utile = any(norm(u) in ("confirmer", "nom") or "moyen" in norm(u) for u, _, _ in mots)
            if not utile and time.time() - getattr(self, "t_secours", 0) > 10:   # rien d'utile avec l'ecran reduit : une lecture complete,
                g3 = cv2.merge([gris, gris, gris])               # pour ne rien rater (et le bilan compte ces cas)
                self.t_secours = time.time()
                mots = ocr.tout(g3)
                BILAN.note("hdv", "lecture complete de secours",
                           utile=any(norm(u) in ("confirmer", "nom") or "moyen" in norm(u) for u, _, _ in mots))
            k = bgr.shape[1] / 1917

            def nombre(x0, x1, y):
                t = ocr.ligne(g3[max(0, int(y - 11 * k)):int(y + 11 * k), max(0, int(x0)):int(x1)], chiffres=True)
                return int(t) if t else None

            def quantite(x0, x1, y):
                """« Quantité en inventaire » : souvent un seul chiffre, que le moteur prend volontiers pour une lettre."""
                v = nombre(x0, x1, y)
                if v is not None:
                    return v
                t = ocr.ligne(g3[max(0, int(y - 11 * k)):int(y + 11 * k), max(0, int(x0)):int(x1)])
                t = re.sub(r"[^0-9]", "", t.translate(str.maketrans("OoDQlI|", "0000111")))
                return int(t) if t else None

            def nom_a(x0, x1, y):
                return " ".join(u for x, u in sorted((x, u) for u, x, y_ in mots if abs(y_ - y) < 9 * k and x0 <= x < x1))

            fiches, dial = [], None
            for t, mx, my in mots:
                if "moyen" not in norm(t):
                    continue
                mx = min(x for u, x, y in mots if abs(y - my) < 10 * k and mx - 60 * k <= x <= mx)   # debut de « Prix »
                ligne = sorted((x, u) for u, x, y in mots if abs(y - my) < 10 * k and mx <= x < mx + 330 * k)
                m = re.search(r"moyen\D*(\d[\d  .]*)", " ".join(u for _, u in ligne).lower())
                if not m:
                    continue
                moyen = int(re.sub(r"\D", "", m.group(1)))
                relu = nombre(mx + 78 * k, mx + (92 + len(str(moyen)) * 10) * k, my)   # relecture serree, plus fiable
                if relu and len(str(relu)) == len(str(moyen)):
                    moyen = relu
                lots, ys, rangs = {}, {}, {}
                for u, x, y in mots:
                    if my + 40 * k < y < my + 330 * k and mx - 110 * k <= x < mx + 330 * k:
                        rangs.setdefault(round(y / (14 * k)), []).append((x, u, y))
                doublon_lot = False
                for r in rangs.values():
                    g = re.sub(r"\D", "", "".join(u for x, u, _ in sorted(r) if x < mx + 60 * k))
                    d = re.sub(r"\D", "", "".join(re.sub(r"\D+$", "", u) for x, u, _ in sorted(r) if x >= mx + 60 * k))
                    if g in ("1", "10", "100", "1000") and d:
                        if int(g) in lots:
                            doublon_lot = True
                            break
                        ys[int(g)] = sum(y for _, _, y in r) / len(r)
                        relu = nombre(mx + 60 * k, mx + 215 * k, ys[int(g)])     # relecture serree du prix seul
                        lots[int(g)] = relu if relu and len(str(relu)) == len(d) else int(d)
                if doublon_lot:
                    continue
                unit = sorted(p / n for n, p in lots.items() if n >= 10)
                if unit and not .5 * unit[len(unit) // 2] <= moyen <= 2 * unit[len(unit) // 2]:
                    continue                                     # prix moyen incoherent avec les lots : mal lu, on se tait
                if moyen > 0 and lots:                           # sans lots : c'est l'en-tete « Prix moyen » de la liste
                    fiches.append({"nom": nom_a(mx - 15 * k, mx + 330 * k, my - 39 * k).strip(), "moyen": moyen,
                                   "lots": lots, "ys": ys, "qte": quantite(mx + 167 * k, mx + 230 * k, my + 22 * k),
                                   "mx": mx, "my": my})
            for t, cx, cy in mots:
                if norm(t) == "confirmer":                       # fenetre « Acheter » : rune, quantite, prix, bouton
                    # La fenetre a une ligne « Prix unitaire » et, pour un lot, une ligne « Prix total » en plus :
                    # on se repere sur ces mots, pas sur des distances fixes.
                    def rang(mot):
                        return next((y for u, x, y in mots if mot in norm(u) and 25 * k < cy - y < 130 * k
                                     and cx - 230 * k < x < cx + 60 * k), None)
                    yu, yt = rang("unitaire"), rang("total")
                    yn = (yu if yu is not None else cy - 45 * k) - 43 * k           # ligne du nom, au-dessus du prix
                    ya, yb = max(0, int(yn - 12 * k)), int(yn + 12 * k)             # nom en dore : image d'origine
                    q = re.sub(r"\D", "", ocr.ligne(bgr[ya:yb, int(cx + 68 * k):int(cx + 126 * k)]))
                    total = nombre(cx - 70 * k, cx + 118 * k, yt) if yt is not None else None
                    dial = {"nom": ocr.ligne(bgr[ya:yb, int(cx - 175 * k):int(cx + 20 * k)]).strip(),
                            "n": int(q) if q else None, "total": total,
                            "prix": nombre(cx - 70 * k, cx + 118 * k, yu if yu is not None else cy - 45 * k),
                            "pt": (int(cx + 38 * k), int(cy))}
                    break
            res = []                                             # lignes de la liste de resultats : (nom, x, y)
            for u, x, y in mots:
                if not norm(u).startswith("rune") or norm(nom_a(x - 2, x + 190 * k, y)).startswith("runede"):
                    continue
                if not any(norm(u2).startswith("rune") and 15 * k < y2 - y < 26 * k and abs(x2 - x) < 60 * k
                           and norm(nom_a(x2 - 2, x2 + 190 * k, y2)).startswith("runedeforgemagie")
                           for u2, x2, y2 in mots):
                    continue                                     # pas une ligne de resultat (ex. le texte tape)
                if any(norm(u3).startswith("rune") and 30 * k < y3 - y < 50 * k and abs(x3 - x) < 60 * k for u3, x3, y3 in mots):
                    continue                                     # case a cocher des filtres (lignes serrees), pas un resultat
                if any(abs(y - (f_["my"] - 39 * k)) < 15 * k and abs(x - f_["mx"]) < 80 * k for f_ in fiches):
                    continue                                     # c'est le titre d'une fiche ouverte
                res.append((nom_a(x - 2, x + 190 * k, y).strip(), int(x + 60 * k), int(y + 9 * k)))
            if res:                                              # garde la colonne des resultats, pas les filtres a gauche
                xm = sorted(r[1] for r in res)[len(res) // 2]
                res = [r for r in res if abs(r[1] - xm) < 40 * k]
            res.sort(key=lambda r: r[2])
            tri = next(((int(x + 14 * k), int(y)) for u, x, y in mots if norm(u) == "nom" and res
                        and 20 * k < res[0][2] - y < 90 * k and abs(x - res[0][1] + 60 * k) < 60 * k), None)   # en-tete « Nom »
        self.fiche = {"fiches": fiches, "dial": dial, "res": res, "tri": tri} if fiches or dial or res else None
        if not rapide:
            BILAN.duree("lecture fiche hdv", time.time() - t_debut)
        BILAN.pose("systeme", "lectures_hdv_evitees", getattr(self, "n_evite", 0))
        if self.fiche:
            self.t_vu_fiche = time.time()
            if res:
                BILAN.note("resultats", " | ".join(r[0] for r in res[:10]), liste=[a_["recherche"] for a_ in self.liste])
            for f_ in fiches:
                BILAN.note("fiches", f_["nom"] or "(nom illisible)", dans_liste=self._voulue(f_["nom"]) is not None,
                           moyen=f_["moyen"], lots=f_["lots"], qte=f_["qte"],
                           liste=[a_["recherche"] for a_ in self.liste])
            if dial:
                f_ = next((x for x in fiches if norm(x["nom"]) == norm(dial["nom"])), None)
                lot = f_["lots"].get(dial["n"]) if f_ and dial["n"] else None
                sens = "unitaire + total cohérents" if dial.get("total") and dial["prix"] and dial["n"] \
                    and abs(dial["total"] - dial["prix"] * dial["n"]) <= .02 * dial["total"] else "?" if not (lot and dial["prix"]) else "prix du lot entier" if abs(dial["prix"] - lot) <= .02 * lot \
                    else "prix par rune" if dial["n"] and abs(dial["prix"] * dial["n"] - lot) <= .03 * lot else "ni l'un ni l'autre"
                BILAN.note("achats", f"{dial['nom'] or '?'} x{dial['n'] or '?'}", prix=dial["prix"], prix_lot=lot,
                           sens=sens, lu=dial["n"] is not None and dial["prix"] is not None,
                           conseil=self._conseil_fiche(self.fiche)[0].split("→")[-1].strip()[:80])
        return self.fiche

    _GAB = {"titre": "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",
            "qte": "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",
            "nom": "iVBORw0KGgoAAAANSUhEUgAAACYAAAASCAAAAAASvfPJAAACBklEQVQoFYXBWU8TURgG4Pc7y0zbmXJsWQ0KFpEtRholXOi1v9drYyJ6I3eomDQxYQ3gAGVp6TIzZ/Un8DykCACF0WRfVAK0MMld3YPBOxIugEBEDqQIcPGwFqp96Z2vmOqgObaIyJEwAJcoywikCLCVPM7V2ImYcj058lJ7waxnJHxpZcQ8SBHAq2lmddOzIQtICseJiHMKDxXpPIMFSBEgn00f399P11/vjlM20KmWQTsebKp1iKNgCaQIsG+T/HCkn6/8eLC1iBvy4OTBLBPIC5kYkCJAtxlG99nC4k8uZhq14XmXLTQK1thL5lTvuCcZSBEgFvngxWF3qv0pWVNHmHj6J19Lz4rZxsVQyZtby0CKALtd7LWnd6fWv/mPv3tD+cbtb5WHg9b650R/OD3zHKQIYIviiL+i6/lfYvNvEdASnTVzOZp7+TV128dX3IMUAbQsTrKljay1E212D4xslwcrxfl4fnlH8u2TSwogRYB+7/aH6ex8/IU2mhdEs1nWLjv56tJ3U9m6+KcFSBFgV0UnYr138qT0S6m6u7rON9ypWWh2jFzN+o6BFAHRuNnj1Wwm6NB/4uOCOZZ460Q05L7ZZbEBKQLk7QRsrTCMpKzeuHrBo7GthZxiVlYHFWlBigCTmOBDxdnaOE+Yi5ypFi4WzsSmqGtRCpACQHgMKQCEx/wHGSL+MwNo+zAAAAAASUVORK5CYII="}

    def _gabarit(self, nom):
        """Petite image de reference (texte fixe de l'interface en 1920x1080), gardee dans le fichier lui-meme."""
        if not isinstance(self._GAB[nom], np.ndarray):
            import base64
            type(self)._GAB[nom] = cv2.imdecode(np.frombuffer(base64.b64decode(self._GAB[nom]), np.uint8), 0)
        return self._GAB[nom]

    _CHIFFRES_HDV = "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jbluAAAAIOP3//+fUQAAACP4/f//x2wAAECC7Kil39udTACR+t0/NLj026yAyN4YBwUU2Pf1kdDaAAAAANb7/ZXR2gAAAADa/fshn/bGmpOv8+jKAHHN+c/I4PrQkgAAIObw7t/6kQAAAApMUID064UAAAAAAAxV/85xAAAAAAB0vf8kAAAAAAAAmN3uIgAAAAAAALb24iAAAABjx////+JxAABand/f4ePupFoAy+X/ubzA/+XMALizrxQUFffw6AB5c20AAAD56tsAAAAAAAAA/928AAAAAABbtv+UKQAAAAAvju7GYwAAAAAA1On/AAAAAABChPDSswAAAAAVcMz9yJQWFhYAvt7/8dvGxsbGANTp//jv5eXl5QDn8/////////8AAGLE////9HoAAFCX3tSxjfazcQC22v+fTwD5/P8A9ebXEQgAG43/AP3p1gAAADKY/wD/798AAACXy/8Ax9/3n5eP5/P/AI6/79fLwP/69gAAXbr76tr/7NkAAB49U4S0/6NIAAAAAABWrPt9AAAAAAAAf//cbgAAAAAAVqr/YTAAAAAAAJzN/wAAAAAAACT/////vWYAAECC6qim5NeXRACR+NA7N8P21JuT0N0XBgYV3fHfp9naAAAAANr05qra2gAAAADa8+MlofbAmJW19N+0AHHM9M3K6vzJgQAAIe3x8vH9kQAAAAtOUIH64H0AAAAAAA5X/79nAAAAAACCyv8kAAAAAAAAnuDkIAAAAAAAALbx0B0AAAAAQKHszAAAAAAARnS58cwAAAAAAJ612ffMAAAAAAARFBjQzAAAAAAAAAAAy8sAAAAAAAAAAMzMAAAAAAAAAADMzAAAAAAAAAAAzMwAAAAAAAAAAMzMAAAAAAAAAADMzAAAAAAAAAAAzMwAAAAAAAAAAMzMAAAAAAAAOI3o6I1+cwAAAGb/////4tAAAF++////43EAAESL0o2NjdGZYACbw+sAAAC8y9oA5oAaAAAAFIf6APV6AAAAAAB9+gD/fwAAAAAAefIA/38AAAAAAHTpAP9/AAAAAAB16gD/fwAAAAAAe/YA7qZeAAAAAH78ANy7mQAAABaI+QCQxPkAAADIzNEAP4fOjY2NzpVcAABWrf///9RqAAAAaND////SaQAAUJHTjY2Nz5NXALTG2AAAAMzIxAD2hxcAAAAWh/gA/38AAAAAAH//AP9/AAAAAAB//wD/fwAAAAAAf/8A/38AAAAAAH//AP9/AAAAAAB//wD9fgAAAAAAf/8A84YZAAAAGIf3AKjI6AAAANzLugBKjc+NjY3Nj1IAAF68////wWAAAABs2P///8djAABZldCNjY3Sj0wAysnIAAAA4MatAPmHFgAAABiH9QD/fwAAAAAAf/8A/38AAAAAAH//APl8AAAAAAB//wD5fAAAAAAAf/8A/38AAAAAAH//AP9/AAAAAAB//wD3hxcAAAAah/QAvcjUAAAA7cehAFOQzI2Njc+LRwAAY8b///+4XAAAAAAj+P3//8dsAABAguyopd/bnUwAkfrdPzS49NusgMjeGAcFFNj39ZHQ2gAAAADW+/2V0doAAAAA2v37IZ/2xpqTr/PoygBxzfnPyOD60JIAACDm8O7f+pEAAAAKTFCA9OuFAAAAAAAMVf/OcQAAAAAAc7z/JAAAAAAAAJjc7iIAAAAAAAC29uIgAACy2P//////+PEAqsHY2uTu/8KFAKKlqazD2v9/AAAREhKUx/ocDgAAAAAAtdf5OBwAAAAAAP/27qpVAAAAO3bd2NPsxZ8AADt2pKGe6+HYAAAAAAAAAKfT/wAAAAAAAACj0f8AGhscEhISrNP7AOz1/6akov/t2wBoqerX1tXjomEAAG3a////zmcAAABXp/////+vXAAAccrkpqjqz3QAAJH2wzc70PiRAKfZ3RUGBhfd3rO/49oAAAAA2ufHxubaAAAAANrlxCuk9LaVl7311JsAg+fty872/cFwAFKf+/X2//+RAAAbNVNRgv/UdQAAAAAAD1j/rVsAAAAAAI7X/yQAAAAAAACk4tgeAAAAAAAAtuu6GgAAAHLk////2GwAAGir742x1OmkYADq8/0AT5//69gA/MuZAAgR1uj6AP/IkgAAANTp/wD/zp4AAADc7f8A8e3pjpeh9/PvALjX9sXJzP/r1wAAbNn63sP/yZQAACRIU5bZ/5gxAAAAAABz5/R6AAAAAAAAf/+hUAAAAAAAe73/RyMAAAAAAN7u/wAAAAAAZbz///z1IgAASZjW6uDk+YA9AKbY+NC5x//0igCcurcXFEjO9pAAZ3l0AAA+2fONAAAAAAAASPzrhQAAAAAAb7f+UB0AAAAFKKPa6yEAAAAAGbTp5acXAAAAQIHm06E3BwAAEG29/8qHFhYTEJTR///WxsbGsZWq2v//7OXl5cKTvOL////////QkwBt2v///8hkAABcltGNjY3UkEwAz8vHAAAA5MitAPmHFgAAABmH9QD/fwAAAAAAf/8A/38AAAAAAH//APd7AAAAAAB//wD3ewAAAAAAf/8A/38AAAAAAH//AP9/AAAAAAB+/QD4hxcAAAAahvIAwcrTAAAA8MihAFWRzo2NjdCMRwAAZcr///+4XAAAAACOxPqSSQAAAAAAt9f3kkkAAAAAAOvw9ZJJAAAAAAAageiSSQAAAAAAAHPnkkkAAAAAAABz55JJAAAAAAAAc+eSSQAAAAAAAHPnkkkAAAAAAABz55JJAAAAAAAAc+eSSQAAAAAAAHPnkkkAAAAAAAB06ZNJAAAAAACNwfXPq4cAAAAA//////nzAAAAACP4/f//x2wAAECC7Kil39udTACR+t0/NLj026yAyN4YBwUU2Pf1kdDaAAAAANb7/ZXR2gAAAADa/fshn/bGmpOv8+jKAHHN+c/I4PrQkgAAIObw7t/6kQAAAApMUID064UAAAAAAAxV/85xAAAAAABzvP8kAAAAAAAAmNzuIgAAAAAAALb24iAAAAB////////58wAAf//V1dXV0s8AAH//oqKioqKiAInE/xEREREREQCl0f9VVVVNJgAAudz/////6HQAACmE3zhyrPncvwAAU6YAOXPp8PgAAAAAAAAAns7/AAAAAAAAAKjT/wAbGxwUFRW22PsA9/v/t77F/+7eAG2q5t/i5dyfYgAAadP////AYAAAAAAAevWdTgAAAAAAaq3wnU4AAAAAAO/s6p1OAAAAAAAafN2dTgAAAAAAAG3bnU4AAAAAAABu3J1OAAAAAAAAbtydTgAAAAAAAG7cnU4AAAAAAABu3J1OAAAAAAAAbtydTgAAAAAAAG7cnU4AAAAAAABu3Z9PAAAAAACNvu/Ur4kAAAAA//////v4AAAAACLx+///t2IAADx4z6CNjcd3AACI5KUvAADakQAAkNsSBQAAlbS8M5/OAAAAAF2f4pq7tQAAAAAAbf+iua4AAAAAAG3/obqvAAAAAABs/Ze8uQAAAAAAa/oyn88AAAAAYZ/cAI/aFAUAAJq1twCB3Lg0AADakQAAOXPNn42NvXAAAAAf3vX//6VWAAAAI/j9///HbAAAQILsqKXf251MAJH63T80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x2MAAFmV0I2NjdKPTADKycgAAADgxq0A+YcWAAAAGIf1AP9/AAAAAAB//wD/fwAAAAAAf/8A+XwAAAAAAH//APl8AAAAAAB//wD/fwAAAAAAf/8A/38AAAAAAH//APeHFwAAABqH9AC9yNQAAADtx6EAU5DMjY2Nz4tHAABjxv///7hcAAAAACP4/f//x2wAAECC7Kil39udTACR+t0/NLj026yAyN4YBwUU2Pf1kdDaAAAAANb7/ZXR2gAAAADa/fshn/bGmpOv8+jKAHHN+c/I4PrQkgAAIObw7t/6kQAAAApMUID064UAAAAAAAxV/85xAAAAAABzvP8kAAAAAAAAmNzuIgAAAAAAALb24iAAALLY///////48QCqwdja5O7/woUAoqWprMPa/38AABESEpTH+hwOAAAAAAC11/k4HAAAAAAA//buqVQAAAA7dt3Y0+vFnwAAO3akoZ7r4dgAAAAAAAAAp9P/AAAAAAAAAKPR/wAaGxwSEhKs0/sA7PX/pqSi/+3bAGip6tfW1eOiYQAAbdr////OZwAAAFen/////69cAABxyuSmqOrPdAAAkfbDNzvQ+JEAptjdFQYGF93es77j2gAAAADa58fG5toAAAAA2uXEK6T0tpWXvfXUmwCD5+3Lzvb9wXAAUp/79fb//5EAABs1U1GC/9R1AAAAAAAPWP+tWwAAAAAAjtf/JAAAAAAAAKTi2B4AAAAAAAC267oaAAAAcuT////YbAAAaKvvjbHU6aRgAOrz/QBPn//r2AD8y5kACBHW6PoA/8iSAAAA1On/AP/OngAAANzt/wDx7emOl6H38+8AuNf2xcnM/+vXAABs2frew//JlAAAJEhTltn/mDEAAAAAAHPn9HoAAAAAAAB//6FQAAAAAAB7vf9HIwAAAAAA3u7/AAAAAAB//////////wAAa9fZ3eD/xo0AAFOnq7K6/38AAAAJEhKF96RSAAAAAABVqf+kUgAAAAAA////ul0AAAAAAObc0u/VuwAAAACupJrG3fQAAAAAAAAAAH//AAA1awAAAAB//wAWYKsUEhAbjf8AxuL/uaiY9/v/AFea3d/Y0euucQAAYcP////jcQAAAABW2ffwtEcAAABrnun677NHAAAA8vf//++yRwAAAKpxHNHvskcAAABrQADL77FHAAAAAAAAzO+yRwAAAAAAAMzv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//+RAABQlszO3f+dUAAAABSOkrL/JAAAAAACD7LcpBcAAAAADFXO6K8ZAAAAACT///XcHwAAAAAf2sTH5spxAAAAF6GLkbX0oCIAAAAAAAAA2tScAEtxAAAAANrSlhJ9sxgUFhzeyoOj1/rcvMb//5EASJDL6d/f54JAAABYp/X88tQeAAAAAAAAabL/t2IAAAAAAIvU/7diAAAAAAC2//+3YQAAACDh6PH/t2EAACtk/re3/7dhAACB5v9ISP+3YQCYz904EEj/t2EA0eneLi5q/8B8Lv/269PT3//i2dPh4eDY2OP/597Yu7/CwsLT/+TTwgAAAAAASP+3YgAAAAAAAEXxtWEAAAAAAABC57NhAAAAHMnvtgAAAAAAACDh15YAAAAAAAAk/7hvAAAAAAB00OpPDAAAAAAAiO7vgVVVSCgAAJH//////9l4AKTY4jg4XrvsjADa6tMAACWC7aEm8+S6AAAAANrbq+LrzwAAAADa05jB5N4cGBgc3Md/AJH//97e/++HAABAgeTd2th5PAAAAB3P3de6GgAAAEaNz9DRAAAAAE6Gv+Tk5XFZQACw1///////yJIA9t/HHBwc/+jRAKmVgAAAAP/n0AAAAAAAAAD/378AAAAAAE6d/5QqAAAAACd/1up1AAAAAACz2f+iUQAAADZs5dvRNRoAABBerfjPpQAAAACSyP/IZAAAAAAAzub/5rqNjY2NAP///////////wCutr+/v7+/vr0Ar8TZ2tvb28axALHW+/3+///RowATFxscjP28ZxIAAAAAT5/wdzsAAAAAAO7i1wAAAAAARoz7+PbGnncAAEaMxsbG89GvAAAAAAAAAMzl/wAAAAAAAACn0/8AGhkXAAAAns7/AOzh1wAAAOby/wC30u2NjY3zsnEAjsb//////38AAAAAAACi2cIbAAAAAA1bxclrDwAAAAAdzvG2AAAAAAAAI/m2bwAAAAAALGf/xpRROB0AAIbt//Xy86hZAACP+fHFv93ntG4novW5jomn8tWes97aAAAAANjt2bfg2gAAAADP59mk2N0VBgURz+LSAJH1vjYtn/HVnQB41eKlodTenkUAZbz/////z3IAAEeP0M/PAAAAAFCIwOTk5HFYPgC02f//////xo0A9t3EHBwc/+TKAKmTfQAAAP/kyQAAAAAAAAD/3LkAAAAAAFCh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"      # chiffres de l'hotel de vente, appris sur tes captures (14x10 points chacun)

    def _chiffres_hdv(self):
        if isinstance(self._CHIFFRES_HDV, str):
            import base64
            brut = np.frombuffer(base64.b64decode(self._CHIFFRES_HDV), np.uint8)
            n = len(brut) // 141
            g = brut[n:].reshape(n, 140).astype(np.float32)
            g -= g.mean(axis=1, keepdims=True)
            type(self)._CHIFFRES_HDV = (brut[:n].astype(int), g / (np.linalg.norm(g, axis=1, keepdims=True) + 1e-6))
        return self._CHIFFRES_HDV

    def _nombre_hdv(self, g):
        """Nombre ecrit en clair sur fond sombre dans la zone g, lu sans moteur de lecture (chiffres compares a
        ceux appris). (valeur, sur) : valeur None si la zone est vide ; sur=False si un chiffre est douteux."""
        if g.size == 0:
            return None, True
        f = g.astype(np.float32)
        mx = float(f.max())
        if mx < 110:
            return None, True
        m = f > max(95, .55 * mx)
        lig = np.flatnonzero(m.any(axis=1))
        if len(lig) < 6:
            return None, True
        y0, y1 = lig[0], lig[-1]
        m, f, h = m[y0:y1 + 1], f[y0:y1 + 1] / mx, y1 - y0 + 1
        cols, seg, a = m.any(axis=0), [], None
        for i, c in enumerate(list(cols) + [False]):
            if c and a is None:
                a = i
            if not c and a is not None:
                seg.append((a, i - 1))
                a = None
        lab, gab = self._chiffres_hdv()
        txt, sur, fin = "", True, None
        for a, b in seg:
            if fin is not None and txt and a - fin > 1.1 * h:
                break                                        # grand vide : la suite n'est plus le nombre (icone)
            yy = np.flatnonzero(m[:, a:b + 1].any(axis=1))
            if yy[-1] - yy[0] + 1 < .75 * h:
                continue                                     # point, deux-points, eclat d'icone : pas un chiffre
            fin = b
            w = b - a + 1
            # Deux glyphes larges colles (4 et 9, largeur 15 pour hauteur 9)
            # font deux chiffres, pas trois. L'ancienne estimation .66 donnait
            # 13 499 -> 134999, parfois avec une confiance trompeuse.
            n = max(1, round(w / (.75 * h))) if w > .92 * h else 1
            for j in range(n):
                xa, xb = a + round(j * w / n), a + round((j + 1) * w / n) - 1
                gl = np.where(m[:, xa:xb + 1], f[:, xa:xb + 1], 0)
                r = cv2.resize(gl, (max(1, min(10, round(gl.shape[1] * 14 / h))), 14), interpolation=cv2.INTER_AREA)
                c = np.zeros((14, 10), np.float32)
                o = (10 - r.shape[1]) // 2
                c[:, o:o + r.shape[1]] = r
                v = (np.clip(c, 0, 1) * 255).astype(np.uint8).astype(np.float32).ravel()
                v -= v.mean()
                sc = gab @ (v / (np.linalg.norm(v) + 1e-6))
                par = [float(sc[lab == d].max()) for d in range(10)]
                d1 = int(np.argmax(par))
                reste = max(p for i, p in enumerate(par) if i != d1)
                if par[d1] < .7 or par[d1] - reste < .05:
                    sur = False
                txt += str(d1)
        return (int(txt) if txt else None), sur

    @staticmethod
    def _largeur_ok(t, larg):
        """Un nom de rune fait de 6,4 a 8,8 points par caractere a l'ecran (1920x1080)."""
        return bool(t) and 6.4 <= larg / max(1, len(t.strip())) <= 8.8

    def _nom_hdv(self, zone, ocr, budget):
        """Texte d'une ligne (nom de rune) : reconnu par sa forme s'il a deja ete lu une fois (fm_noms_hdv.json),
        sinon lu par le moteur — lent, donc au plus `budget` nouvelles lectures par passage. None = pas encore lu."""
        m = zone > max(100, .55 * float(zone.max())) if zone.size else np.zeros((1, 1), bool)
        if m.sum() < 15:
            return ""
        ys, xs = np.flatnonzero(m.any(axis=1)), np.flatnonzero(m.any(axis=0))
        m = m[ys[0]:ys[-1] + 1, xs[0]:xs[-1] + 1]
        larg = m.shape[1]
        bits = cv2.resize(m.astype(np.uint8) * 255, (96, 10), interpolation=cv2.INTER_AREA) > 100
        if self.noms_hdv is None:                    # (les lectures dont la largeur ne colle pas sont ecartees)
            self.noms_hdv = [(np.array(list(b), np.uint8) == 49, int(w), t)
                             for b, w, t in charger_json(F_NOMS_HDV, []) if self._largeur_ok(t, w)]
        for b2, w2, t in self.noms_hdv:
            if abs(w2 - larg) <= 3 and (b2.ravel() != bits.ravel()).mean() < .04:
                return t
        rejets = self.__dict__.setdefault("rejets_hdv", [])
        for r_ in rejets:                            # ligne deja illisible 2 fois : on la tient pour « pas la bonne »
            if r_[2] >= 2 and abs(r_[1] - larg) <= 3 and (r_[0].ravel() != bits.ravel()).mean() < .04:
                return "?"
        if budget[0] <= 0:
            return None
        budget[0] -= 1
        t0 = time.time()
        t = ocr.ligne(cv2.merge([zone, zone, zone])).strip()
        BILAN.duree("lecture d'un nom (moteur)", time.time() - t0)
        if not self._largeur_ok(t, larg):
            # Mot saute par le moteur : si un seul nom de la liste d'achats contient tous les mots lus ET a la bonne
            # largeur, c'est lui (« Rune Prospe » lu sur 101 points = « Rune Pa Prospe »).
            mots_lus = set(norm(x) for x in t.split() if norm(x))
            cand = [a_["recherche"] for a_ in self.liste if mots_lus
                    and mots_lus <= set(norm(x) for x in a_["recherche"].split()) and self._largeur_ok(a_["recherche"], larg)]
            if len(cand) == 1:
                BILAN.note("hdv", "nom complété par la liste", detail=f"{t} -> {cand[0]} ({larg} px)")
                t = " ".join(x[:1].upper() + x[1:] for x in cand[0].split())
        if not self._largeur_ok(t, larg):
            # Le moteur a saute un mot (ex. « Rune Pa Prospe » lu « Rune Prospe ») : la largeur du texte a l'ecran
            # ne correspond pas au nombre de lettres. On ne retient rien et on ne s'en sert pas.
            BILAN.note("hdv", "nom rejeté (largeur incohérente)", detail=f"{t} / {larg} px")
            r_ = next((r_ for r_ in rejets if abs(r_[1] - larg) <= 3 and (r_[0].ravel() != bits.ravel()).mean() < .04), None)
            if r_:
                r_[2] += 1
            else:
                rejets.append([bits, larg, 1])
            return None
        if norm(t).startswith("rune"):                       # on ne retient que ce qui ressemble a un nom de rune
            self.noms_hdv.append((bits, larg, t))
            try:
                with open(F_NOMS_HDV, "w", encoding="utf-8") as f_:
                    json.dump([["".join("1" if x else "0" for x in b3.ravel()), w3, t3] for b3, w3, t3 in self.noms_hdv],
                              f_, ensure_ascii=False)
            except OSError:
                pass
        return t

    def _fiche_rapide(self, bgr, gris, ocr):
        """Lecture de l'hotel de vente sans chercher le texte sur tout l'ecran : la fiche est reperee par son
        libelle « Quantité en inventaire », la fenetre d'achat par son bouton vert, la liste par son en-tete
        « Nom ». Les nombres sont lus par comparaison de chiffres (instantane) ; les noms par leur forme une fois
        connus. Le moteur de lecture, lent, ne sert plus qu'a lire un nom jamais vu. (fiches, dial, res, tri)"""
        H_, W_ = gris.shape
        clair = bgr.max(axis=2)
        budget = [1]                                         # nouvelles lectures de nom par le moteur, par passage

        def bande(src, x0, x1, y, h=11):
            return src[max(0, int(y - h)):int(y + h), max(0, int(x0)):max(1, int(x1))]

        def nombre(x0, x1, y):
            v, sur = self._nombre_hdv(bande(gris, x0, x1, y))
            if v is not None and not sur:                    # chiffre douteux : le moteur tranche (lent, rare),
                z = bande(gris, x0, x1, y)                   # une seule fois par image de nombre
                cle = (z > max(95, .55 * float(z.max()))).tobytes()
                memo = self.__dict__.setdefault("douteux", {})
                if cle not in memo:
                    if len(memo) > 300:
                        memo.clear()
                    t = ocr.ligne(cv2.merge([z, z, z]), chiffres=True)
                    BILAN.note("hdv", "nombre douteux relu par le moteur", detail=f"{v} / {t}")
                    # Des chiffres colles peuvent etre decoupes en deux (13 497 -> 134997).
                    # La relecture doit pouvoir corriger aussi le nombre de chiffres.
                    memo[cle] = int(t) if t and re.fullmatch(r"[0-9]+", t) else None
                v = memo[cle]
            return v

        fiches, dial, res, tri = [], None, [], None
        self.liste_incomplete = False
        m = cv2.matchTemplate(gris, self._gabarit("qte"), cv2.TM_CCOEFF_NORMED)
        while len(fiches) < 3:
            _, v, _, (tx, ty) = cv2.minMaxLoc(m)
            if v < .8:
                break
            cv2.rectangle(m, (tx - 80, ty - 25), (tx + 80, ty + 25), 0, -1)
            mx, my = tx + 2, ty - 13
            # S'arreter avant l'icone des kamas : le graphique blanc suivant
            # peut etre pris pour des chiffres (29 603 lu comme 12).
            x0, x1 = int(mx + 82), int(mx + 200)
            prix_zone = bgr[max(0, int(my - 9)):int(my + 9), max(0, x0):x1]
            dore = ((prix_zone[:, :, 0].astype(float) < .65 * prix_zone[:, :, 1])
                    & (prix_zone[:, :, 1] > 110) & (prix_zone[:, :, 2] > 140))
            colonnes = np.flatnonzero(dore.any(axis=0))
            fin_prix = x0 + int(colonnes[0]) if len(colonnes) else x1
            moyen, lots, ys = nombre(x0, fin_prix, my), {}, {}
            for i in range(4):
                y = my + 101.5 + 38.2 * i
                n, p = nombre(mx - 22, mx + 42, y), nombre(mx + 60, mx + 184, y)
                if n == (1, 10, 100, 1000)[i] and p:
                    lots[n], ys[n] = p, y
            unit = sorted(p / n for n, p in lots.items() if n >= 10)
            if not moyen or not lots or unit and not .5 * unit[len(unit) // 2] <= moyen <= 2 * unit[len(unit) // 2]:
                continue                                     # fiche cachee ou mal lue : on se tait
            nom = self._nom_hdv(bande(gris, mx - 3, mx + 300, my - 39, 12), ocr, budget)
            fiches.append({"nom": nom or "", "moyen": moyen, "lots": lots, "ys": ys,
                           "qte": nombre(mx + 167, mx + 230, my + 22), "mx": float(mx), "my": float(my)})
        hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)               # bouton CONFIRMER : seul grand rectangle vert vif
        vert = cv2.inRange(hsv, (24, 120, 100), (48, 255, 255))   # large : le bouton s'eclaircit sous la souris
        for c in cv2.findContours(vert, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0]:
            bx, by, bw, bh = cv2.boundingRect(c)
            if not (110 <= bw <= 210 and 20 <= bh <= 42 and cv2.contourArea(c) > .7 * bw * bh):
                continue
            cy, cx = by + bh / 2, bx + bw / 2 - 43
            lot = (bande(gris, cx - 207, cx - 120, cy - 68, 7) > 140).sum() > 25    # ligne « Prix unitaire » remontee :
            yu, yt = (cy - 68, cy - 45) if lot else (cy - 45, None)                 # il y a aussi « Prix total »
            prix = nombre(cx - 70, cx + 112, yu)
            total = nombre(cx - 70, cx + 112, yt) if yt is not None else None
            # quantite : 1 sans ligne « Prix total », sinon le lot dont total / unitaire est le plus proche
            n = 1 if not lot else next((q for q in (10, 100, 1000) if prix and total
                                        and abs(total - prix * q) <= .02 * total), None)
            memo = getattr(self, "fiches_vues", {})
            for f_ in fiches:
                memo[norm(f_["nom"])] = (time.time(), f_)
            self.fiches_vues = memo
            src = next((f_ for t_, f_ in memo.values() if time.time() - t_ < 90 and f_["nom"] and (
                total and total in f_["lots"].values() or not lot and prix and f_["lots"].get(1) == prix)), None)
            if src and total and n is None:                  # unitaire mal lu : le lot de la fiche donne la quantite
                n = next(q for q, p in src["lots"].items() if p == total)
            nom = src["nom"] if src else self._nom_hdv(bande(clair, cx - 175, cx + 20, yu - 43, 12), ocr, budget)
            dial = {"nom": nom or "", "n": n, "total": total, "prix": prix, "pt": (int(bx + bw / 2), int(cy))}
            break
        if dial is None and not any(self._voulue(f["nom"]) for f in fiches):
            m = cv2.matchTemplate(gris, self._gabarit("nom"), cv2.TM_CCOEFF_NORMED)   # liste : seulement si utile
            _, v, _, (tx, ty) = cv2.minMaxLoc(m)
            if v >= .85:
                nx, ny = tx + 3, ty + 9
                tri = (nx + 14, ny)
                budget[0] = max(budget[0], 2)                # la liste passe avant : deux nouvelles lignes par passage
                for i in range(8):
                    y = ny + 39 + 69.43 * i
                    if y > H_ - 20:
                        break
                    t = self._nom_hdv(bande(gris, nx - 2, nx + 190, y, 12), ocr, budget)
                    if t is None:
                        self.liste_incomplete = True         # ligne pas encore lue : au prochain passage
                    elif norm(t).startswith("rune") and not norm(t).startswith("runede"):
                        res.append((t, nx + 60, int(y + 9)))
        return fiches, dial, res, tri

    def _voulue(self, nom):
        """La rune de la liste d'achats qui porte ce nom (« Rune Age » n'est pas « Rune Pa Age »)."""
        n = norm(nom)
        for a in self.liste:
            r = norm(a["recherche"])
            if r == n or len(n) > 5 and difflib.SequenceMatcher(None, r, n).ratio() >= .93:
                return a
        return None

    def _plafond(self, a, f):
        marge = (self.regl or {}).get("_marge", {}).get("pct", MARGE_PRIX)
        d = self.derog.get(norm(f["nom"]))
        if d:
            return d, "prix accepté depuis ton téléphone"
        if a and a.get("prix"):
            return float(a["prix"]), "ton prix max"
        return f["moyen"] * (1 + marge / 100), f"prix moyen {f['moyen']} + {marge} %"

    def _conseil_fiche(self, vu, k=1.0):
        """(texte, point a encadrer ou None) : quel lot acheter, quand confirmer, quand fermer la fiche."""
        fiches, d = vu["fiches"], vu["dial"]
        if d:
            a = self._voulue(d["nom"])
            memo = getattr(self, "fiches_vues", {})
            for f_ in fiches:
                memo[norm(f_["nom"])] = (time.time(), f_)
            self.fiches_vues = memo
            f = next((f_ for f_ in fiches if norm(f_["nom"]) == norm(d["nom"])), None)
            if f is None and time.time() - memo.get(norm(d["nom"]), (0,))[0] < 90:
                f = memo[norm(d["nom"])][1]                  # fiche cachee par la fenetre d'achat : derniere lecture
            tete = f"RAVITAILLEMENT 4/7 : achat de {d['nom'] or '?'} ×{d['n'] or '?'} à {d['prix'] or '?'} k  →  "
            if not a:
                return tete + "pas dans ta liste d'achats, vérifie avant de confirmer", None
            if d["n"] is None or d["prix"] is None:
                return tete + "mal lu, vérifie toi-même", None
            if d["n"] < 10:
                return tete + "lot à l'unité : annule et prends un lot de 10, 100 ou 1000", None
            plafond = self._plafond(a, f)[0] if f or a.get("prix") else None
            unite = d["prix"]                                # « Prix unitaire » = prix d'une rune
            if d.get("total") and abs(d["total"] - unite * d["n"]) > .02 * d["total"]:
                # unitaire et total ne collent pas : le total fait foi s'il est celui du lot affiche sur la fiche
                if f and abs(d["total"] - f["lots"].get(d["n"], 0)) <= .02 * d["total"]:
                    unite = d["total"] / d["n"]
                else:
                    return tete + (f"prix incohérents (unitaire {d['prix']}, total {d['total']} pour {d['n']}) : "
                                   "vérifie toi-même"), None
            elif f and d["n"] in f["lots"] and abs(d["prix"] - f["lots"][d["n"]]) <= .02 * f["lots"][d["n"]]:
                unite = d["prix"] / d["n"]                   # seul le prix du lot entier a ete lu
            if plafond is None:
                return tete + "pas de prix de référence, vérifie toi-même", None
            if unite > plafond:
                self._alerte(f"fenêtre d'achat {d['nom']} x{d['n']} à {d['prix']} k au-dessus du max {plafond:.1f}")
                return tete + f"TROP CHER ({unite:.1f} k la rune, max {plafond:.1f}) : annule", None
            self.dial_ok = (norm(d["nom"]), d["n"])          # si la fenetre se ferme ensuite : achat compte comme fait
            return tete + f"OK ({unite:.1f} k la rune, max {plafond:.1f}) : confirme", d["pt"]
        if getattr(self, "dial_ok", None):                   # la fenetre d'achat validee vient de se fermer
            a_ = next((x for x in self.liste if norm(x["recherche"]) == self.dial_ok[0]), None)
            if a_:
                a_["pris"] = a_.get("pris", 0) + self.dial_ok[1]
            self.dial_ok = None
        res = vu.get("res") or []
        reste_a = [a_ for a_ in self.liste if not a_.get("fait")]
        vise = next(((a_, r) for a_ in reste_a for r in res if norm(r[0]) == norm(a_["recherche"])), None)
        if fiches and not any(self._voulue(f_["nom"]) for f_ in fiches):
            f = fiches[0]                                    # la fiche ouverte n'est pas une rune a acheter
            return (f"RAVITAILLEMENT 4/7 : « {f['nom']} » n'est pas dans ta liste d'achats : ferme cette fiche (X)"
                    + (f", puis ouvre « {vise[1][0]} » dans la liste" if vise else
                       f", puis trie la liste en cliquant sur « Nom » pour trouver « {reste_a[0]['recherche']} »" if reste_a else ""),
                    (int(f["mx"] + 300 * k), int(f["my"] - 82 * k)))
        if not fiches:
            if vise:
                self.tris = set()
                return (f"RAVITAILLEMENT 4/7 : clique sur « {vise[1][0]} » dans la liste (à acheter : {vise[0]['lots']})",
                        vise[1][1:])
            if not reste_a:
                return "RAVITAILLEMENT 4/7 : tous les achats sont faits, ferme l'hôtel de vente.", None
            a_ = reste_a[0]
            if getattr(self, "liste_incomplete", False):     # des lignes pas encore lues : on ne conclut pas
                return (f"RAVITAILLEMENT 4/7 : je lis la liste pour trouver « {a_['recherche']} »… "
                        f"(à acheter : {a_['lots']})", None)
            # Chaque clic sur « Nom » change l'ordre de la liste (croissant, puis decroissant) : on en propose
            # jusqu'a 2, en comptant les ordres differents deja vus pour cette rune, puis on passe a autre chose.
            if getattr(self, "tri_pour", None) != a_["recherche"]:
                self.tri_pour, self.tris = a_["recherche"], set()
            if res:
                self.tris = getattr(self, "tris", set()) | {tuple(norm(r[0]) for r in res)}
            faits = max(0, len(self.tris) - 1)
            if len(res) >= 2 and faits < 2 and vu.get("tri"):
                return (f"RAVITAILLEMENT 4/7 : « {a_['recherche']} » n'est pas visible. Clique sur l'en-tête « Nom » pour "
                        f"changer le tri (essai {faits + 1} sur 2). À acheter : {a_['lots']}", vu["tri"])
            self._alerte(f"« {a_['recherche']} » introuvable dans la liste, même après 2 tris")
            if getattr(self, "_intr", None) != a_["recherche"]:
                self._intr = a_["recherche"]
                BILAN.note("parcours", "introuvable", detail=a_["recherche"])
            return (f"RAVITAILLEMENT 4/7 : « {a_['recherche']} » n'est pas dans la partie visible de la liste "
                    f"({len(res)} résultats affichés : {', '.join(r[0] for r in res[:4])}…). Fais défiler la liste vers "
                    f"le bas, ou tape le nom exact. À acheter : {a_['lots']}", None)
        f = next((f_ for f_ in fiches if self._voulue(f_["nom"])), fiches[0])
        self.fiches_vues = dict(getattr(self, "fiches_vues", {}), **{norm(f["nom"]): (time.time(), f)})
        a = self._voulue(f["nom"])
        plafond, d_ou = self._plafond(a, f)
        if a:
            a["moyen"], a["plafond"], a["lots_vus"] = f["moyen"], round(plafond, 1), dict(f["lots"])
        croix = (int(f["mx"] + 300 * k), int(f["my"] - 82 * k))
        reste = None
        if a and f["qte"] is not None and f["qte"] >= a["stock"]:
            reste = a["acheter"] - (f["qte"] - a["stock"])
        txt = [f"RAVITAILLEMENT 4/7 : {f['nom'] or 'rune'} — max {plafond:.1f} k la rune ({d_ou})"
               + (f", à acheter : {a['lots']}" if a else "  | rune pas dans ta liste d'achats")
               + (f", en inventaire : {f['qte']}" if f["qte"] is not None else "")]
        ok = []
        for n in (1000, 100, 10):
            if n not in f["lots"]:
                continue
            u = f["lots"][n] / n
            if not .2 * f["moyen"] <= u <= 8 * f["moyen"]:
                txt.append(f"• lot de {n} : prix mal lu, vérifie toi-même")
            else:
                txt.append(f"• lot de {n} : {f['lots'][n]} k = {u:.1f} k la rune  →  "
                           + ("OK" if u <= plafond else "TROP CHER, n'achète pas"))
                if u <= plafond:
                    ok.append(n)
        if not a:
            return "\n".join(txt), None
        if reste is not None and reste <= 0:
            a["fait"] = True
            return "\n".join(txt + ["→ Quantité atteinte : ferme cette fiche (X) et passe à la rune suivante."]), croix
        if reste is None:                                    # quantite illisible : on compte les achats confirmes vus
            reste = a["acheter"] - a.get("pris", 0)
            txt[0] += f" (quantité en inventaire illisible : je compte {a.get('pris', 0)} achetées d'après les " \
                      "fenêtres d'achat confirmées ; si tu as annulé, fie-toi au jeu)"
            if reste <= 0:
                a["fait"] = True
                return "\n".join(txt + ["→ Quantité atteinte : ferme cette fiche (X) et passe à la rune suivante."]), croix
        choix = next((n for n in ok if n <= reste), None)
        if choix is None:
            chers = {n: round(f["lots"][n] / n, 1) for n in (1000, 100, 10)
                     if n in f["lots"] and n <= max(reste, 10) and .2 * f["moyen"] <= f["lots"][n] / n <= 8 * f["moyen"]}
            # au-dela de 8 fois le prix moyen (lot piege ou prix mal lu), on ne propose meme pas d'accepter
            self.demande = {"nom": f["nom"], "moyen": f["moyen"], "max": round(plafond, 1), "manque": reste,
                            "lots": chers, "t": time.time()}
            self._alerte(f"{f['nom']} hors de prix (max {plafond:.1f} k, lots {chers})")
            SUIVI.evenement("hors prix " + f["nom"], f"HORS DE PRIX : {f['nom']} — à toi de décider (accepter ou refuser)", 120)
            return "\n".join(txt + [f"→ Il manque {reste} runes mais aucun lot utile n'est sous le max : décide sur ton "
                                    "téléphone (accepter ce prix ou refuser), ou ferme la fiche."]), croix
        self.demande = None
        return ("\n".join(txt + [f"→ Il manque {reste} runes : clique ACHETER sur le lot de {choix}."]),
                (int(f["mx"] + 247 * k), int(f["ys"][choix])))

    def _lire_metier(self, bgr, etat, ocr):
        if self.metier or time.time() - self.t_metier < 5:
            return
        self.t_metier = time.time()
        x, y, w, _ = etat["rows"][0]
        H = bgr.shape[0]
        y0 = int(.165 * H)                                    # titre de la fenetre de forgemagie
        t = norm(ocr.ligne(bgr[max(0, y0 - 16):y0 + 18, x + int(.10 * w):x + int(.55 * w)]))
        p = difflib.get_close_matches(t, list(METIERS), n=1, cutoff=.7)
        if p:
            self.metier = p[0]
            log(f"metier de l'atelier : {self.metier}")

    def _jeu_couvert(self, bgr):
        """Vrai si une autre application est au premier plan et recouvre une bonne part de l'ecran du jeu.
        Lecture seule des fenetres de Windows (titre, position) ; faux si on ne peut pas le savoir."""
        if sys.platform != "win32":
            return False
        if time.time() - getattr(self, "t_couv", 0) < .5:
            return self.couvert
        self.t_couv, self.couvert = time.time(), False
        try:
            import ctypes
            from ctypes import wintypes
            u = ctypes.windll.user32
            devant = u.GetForegroundWindow()
            if not devant:
                return False
            pid = wintypes.DWORD()
            u.GetWindowThreadProcessId(devant, ctypes.byref(pid))
            classe = ctypes.create_unicode_buffer(64)
            u.GetClassNameW(devant, classe, 64)
            if pid.value == os.getpid() or classe.value == "UnityWndClass":
                return False                         # le jeu lui-meme, ou une fenetre de l'outil
            if u.IsIconic(devant):
                return False
            r = wintypes.RECT()
            u.GetWindowRect(devant, ctypes.byref(r))
            H, W = bgr.shape[:2]
            gx, gy = getattr(self, "origine", (0, 0))
            # part du centre de l'ecran du jeu (la ou sont le decor et les fenetres du jeu) recouverte
            cx0, cy0, cx1, cy1 = gx + .12 * W, gy + .12 * H, gx + .88 * W, gy + .80 * H
            lx = max(0, min(r.right, cx1) - max(r.left, cx0))
            ly = max(0, min(r.bottom, cy1) - max(r.top, cy0))
            self.couvert = lx * ly > .30 * (cx1 - cx0) * (cy1 - cy0)
        except Exception:
            self.couvert = False
        return self.couvert

    def etape(self, bgr, etat, achats, ocr, regl=None):
        """(texte, point a encadrer ou None) pour l'etape en cours, ou None s'il n'y a rien a guider."""
        if regl is not None:
            self.regl = regl
        if etat is None and self.phase is not None and self._jeu_couvert(bgr):
            if not getattr(self, "_dit_couvert", False):
                self._dit_couvert = True
                log("ravitaillement en pause : une autre fenetre couvre le jeu")
                BILAN.note("parcours", "pause (jeu couvert)")
            return ("RAVITAILLEMENT en pause : une autre fenêtre couvre le jeu. Je reprends dès qu'il est dégagé.", None)
        self._dit_couvert = False
        r = self._etape(bgr, etat, achats, ocr)
        self._enregistrer(bgr, r)
        m = re.match(r"RAVITAILLEMENT (\d)/7", r[0]) if r else None
        if m and (m.group(1), r[1] is None) != getattr(self, "_bil", None):
            self._bil = (m.group(1), r[1] is None)
            BILAN.note("etapes", m.group(1), cadre=r[1] is not None, sans_cadre=r[1] is None and bool(r[2]))
        if r and r[1] is None and r[2]:
            return r[0] + "   | repère pas trouvé à l'écran : touche Y, ou recale-le avec « Repères »", None
        return r and (r[0], r[1])

    def _etape(self, bgr, etat, achats, ocr):
        def pt(n):
            return self._point(bgr, n)
        if etat is not None:                                  # tableau de forgemagie a l'ecran
            self._lire_metier(bgr, etat, ocr)
            sans_runes = not any(l.get("dispo") for l in etat["lignes"].values())
            if self.phase == "retour":
                if sans_runes:
                    return ("RAVITAILLEMENT 7/7 : item posé. Clique l'onglet Ressources de l'inventaire pour voir tes "
                            "runes (si elles n'apparaissent pas, vide la recherche de l'inventaire avec sa croix)",
                            pt("ressources"), True)
                self.phase, self.vu_hdv = None, False
                log("ravitaillement termine")
                BILAN.note("parcours", "termine")
                self._journal(achats)
                # Termine = termine : les runes encore basses ne relancent pas de ravitaillement tout de suite.
                # Elles reviennent si leur stock change, ou dans 30 minutes ; en attendant, la FM continue.
                self.sautees = {a["rune"]: (a["stock"], time.time()) for a in achats}
                SUIVI.evenement("ravito fini " + str(int(time.time())), "Ravitaillement terminé, la FM reprend"
                                + (" (encore bas, laissé de côté 30 min : " + ", ".join(a["rune"] for a in achats) + ")"
                                   if achats else ""), 5)
            sautees = getattr(self, "sautees", {})
            achats = [a for a in achats if not (a["rune"] in sautees and sautees[a["rune"]][0] == a["stock"]
                                                and time.time() - sautees[a["rune"]][1] < 1800)]
            if self.phase is None and achats:
                self.phase, self.liste, self.vu_hdv = "sortie", list(achats), False
                self.t_debut, self.alertes, self.tris = time.time(), [], set()
                log("ravitaillement : " + ", ".join(f"{a['rune']} x{a['acheter']}" for a in achats))
            if self.phase in ("sortie", "achat") and not achats and stocks_plan_suffisants(self.liste, etat, self.regl):
                self.phase, self.liste, self.vu_hdv = None, [], False
                log("Ravitaillement annule : stocks relus suffisants, ancien plan abandonne")
                return None
            if self.phase in ("sortie", "achat"):
                self.phase, self.liste = "sortie", list(achats) or self.liste
                return ("RAVITAILLEMENT 1/7 : stock bas (" + ", ".join(f"{a['rune']} {a['stock']}" for a in self.liste[:4])
                        + "). Ferme la forgemagie.", pt("fermer"), True)
            return None
        if self.phase is None:
            return None
        dedans = self.dedans(bgr)
        if self.phase == "sortie":
            if not dedans:
                self.phase = "achat"
            elif self._inventaire_ouvert(bgr):
                return ("RAVITAILLEMENT 1/7 : ferme la fenêtre de forgemagie", pt("fermer"), True)
            else:
                return ("RAVITAILLEMENT 2/7 : sors de l'atelier par la case de sortie (touche Y pour voir les "
                        "éléments cliquables)", pt("sortie"), True)
        if self.phase == "retour" and not dedans and self._hdv_ouvert(bgr, ocr):
            self.phase, self.vu_hdv = "achat", True          # hotel de vente rouvert : on reprend les achats
        if self.phase == "achat":
            if dedans:
                if not self.vu_hdv:
                    return ("RAVITAILLEMENT 2/7 : sors de l'atelier par la case de sortie (touche Y pour voir les "
                            "éléments cliquables)", pt("sortie"), True)
                self.phase = "retour"
            elif (self._hdv_ouvert(bgr, ocr) or time.time() - max(self.t_vu_hdv, self.t_vu_fiche) < 20) \
                    and self._fiche(bgr, ocr):
                self.vu_hdv = True
                txt, p_ = self._conseil_fiche(self.fiche, bgr.shape[1] / 1917)
                return (txt, p_, False)
            elif self._hdv_ouvert(bgr, ocr):
                self.vu_hdv, self.t_vu_hdv = True, time.time()
                lignes = [("✓ " if a.get("fait") else "• ") + f"tape « {a['recherche']} »  →  achète {a['lots']}"
                          + (f"  (max {a['prix']} k la rune)" if a.get("prix") else "") for a in self.liste[:10]]
                return ("RAVITAILLEMENT 4/7 : pour chaque rune, tape son nom dans la recherche et achète les lots\n"
                        + "\n".join(lignes) + "\nPuis ferme l'hôtel de vente.", pt("recherche"), True) \
                    if self._visible(bgr, "recherche") else \
                    ("RAVITAILLEMENT 4/7 : une fenêtre cache l'hôtel de vente (je ne vois plus la barre de recherche).\n"
                     "Dégage le jeu. S'il reste une fiche de rune ouverte dessous, ferme-la (X) avant de taper la suivante.",
                     None, False)
            elif self.vu_hdv:
                return ("RAVITAILLEMENT 5/7 : achats faits ? Rentre dans l'atelier par la porte "
                        "(sinon rouvre l'hôtel de vente)", pt("porte"), True)
            else:
                return ("RAVITAILLEMENT 3/7 : ouvre l'hôtel de vente (touche Y pour voir les éléments cliquables)",
                        pt("hdv"), True)
        if self.phase == "retour":
            if not dedans:
                return ("RAVITAILLEMENT 5/7 : rentre dans l'atelier par la porte", pt("porte"), True)
            if self._inventaire_ouvert(bgr):
                nom_ = getattr(self, "nom_item", "")
                return ("RAVITAILLEMENT 7/7 : onglet Équipement"
                        + (f", tape « {nom_} » dans la recherche de l'inventaire" if nom_ else "")
                        + ", pose ton item dans la fenêtre, puis onglet Ressources pour voir tes runes",
                        pt("equipement"), True)
            cle = METIERS.get(self.metier)
            if not cle:
                return ("RAVITAILLEMENT 6/7 : ouvre l'atelier magique de ton item (touche Y pour voir les ateliers)",
                        None, False)
            return (f"RAVITAILLEMENT 6/7 : ouvre l'atelier {self.metier.capitalize()}"
                    + (f", puis choisis « {self.metier.capitalize()} » dans le menu" if cle == "multi" else "")
                    + " (touche Y pour voir les ateliers)", pt(cle), True)
        return None


GUIDE = Guide()


def mode_direct(ecran, ocr, histo):
    if tk is None:
        sys.exit("tkinter manquant : reinstalle Python avec l'option tcl/tk")
    windows = sys.platform == "win32"
    # Une seule instance a la fois : la nouvelle ecrit son jeton tout de suite, l'ancienne le voit et se ferme.
    jeton = f"{time.time()} {os.getpid()}"
    f_run = os.path.join(ICI, "fm_run.txt")
    from fm_fichiers import ecrire_texte
    ecrire_texte(f_run, jeton)
    from fm_diagnostic import Diagnostic
    diagnostic = Diagnostic(os.path.join(ICI, "fm_diagnostic"))
    from fm_phases import PhaseRemise
    phase_remise = PhaseRemise()
    diagnostic.evenement("session", version="diagnostic_v1", programme=os.path.basename(__file__))
    SUIVI.ouvrir = INTERFACE_WEB[0] and windows
    SUIVI.demarrer()
    if windows:
        import ctypes
        # FM_CLICK_PATCH:WINTYPES
        from ctypes import wintypes
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            pass
    try:
        import mss
        sct = mss.MSS()
        mons = [dict(m) for m in sct.monitors[1:]]
        if ecran and 1 <= ecran <= len(mons):
            mons = [mons[ecran - 1]]

        def capturer(m):
            nonlocal sct
            for essai in range(60):
                try:
                    t_capture = time.monotonic()
                    image = np.ascontiguousarray(np.array(sct.grab(m))[:, :, :3])
                    securite["capture"] = t_capture
                    return image
                except mss.exception.ScreenShotError:
                    time.sleep(0.5)
                    try:
                        sct = mss.MSS()
                    except Exception:
                        pass
            raise RuntimeError("capture d'ecran impossible depuis 30 s")
    except ImportError:
        from PIL import ImageGrab
        im = ImageGrab.grab()
        mons = [{"left": 0, "top": 0, "width": im.width, "height": im.height}]

        def capturer(m):
            t_capture = time.monotonic()
            image = cv2.cvtColor(np.array(ImageGrab.grab()), cv2.COLOR_RGB2BGR)
            securite["capture"] = t_capture
            return image

    VIDE = "#010101"
    root = tk.Tk()
    root.overrideredirect(True)
    i_mon, vides, ecran_vu = 0, 0, -1
    mon = mons[0]
    root.geometry(f"{mon['width']}x{mon['height']}+{mon['left']}+{mon['top']}")
    root.attributes("-topmost", True)
    cv = tk.Canvas(root, bg=VIDE, highlightthickness=0)
    cv.pack(fill="both", expand=True)

    def cacher(fen, clics=False):
        """Rend une fenetre invisible pour la capture d'ecran (et traversable par les clics)."""
        if not windows:
            return
        u = ctypes.windll.user32
        hwnd = u.GetParent(fen.winfo_id())
        if clics:
            u.SetWindowLongW(hwnd, -20, u.GetWindowLongW(hwnd, -20) | 0x80000 | 0x20)
        u.SetWindowDisplayAffinity(hwnd, 0x11)

    if windows:
        root.attributes("-transparentcolor", VIDE)
        root.update()
        cacher(root, clics=True)
    else:
        print("Calque transparent prevu pour Windows ; ici les conseils s'affichent dans la console.")
        root.withdraw()
    panneau = Panneau(root, cacher)

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

    # FM_CLICK_PATCH:CLICK_RUNTIME
    def position_souris():
        point = wintypes.POINT()
        user32 = ctypes.windll.user32
        if not user32.GetCursorPos(ctypes.byref(point)):
            log(f"lecture de la position de la souris impossible : {ctypes.WinError()}")
            return None
        return point.x, point.y

    position_souris_ref = [position_souris() if windows else None]
    mode_suivi = [panneau.mode.get()]

    def cliquer_case(rect):
        if not action_autorisee(fm=True):
            return False
        x1, y1, x2, y2 = rect
        x, y = mon["left"] + (x1 + x2) // 2, mon["top"] + (y1 + y2) // 2
        user32 = ctypes.windll.user32
        if not user32.SetCursorPos(x, y):
            log(f"clic automatique impossible : {ctypes.WinError()}")
            return False
        position_souris_ref[0] = (x, y)
        user32.mouse_event(0x0002, 0, 0, 0, 0)
        time.sleep(0.05)
        user32.mouse_event(0x0004, 0, 0, 0, 0)
        diagnostic.action_envoyee("rune", stat=reco.get("stat"), taille=reco.get("taille"), x=x, y=y)
        debut_confirmation()
        return True

    f1_ref = [False]

    def minimiser_ui():
        user32 = ctypes.windll.user32
        user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.IsWindowVisible.argtypes = [wintypes.HWND]
        proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

        def vers(h, _):
            buf = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(h, buf, 256)
            if buf.value.startswith("Forgemagie") and user32.IsWindowVisible(h):
                user32.ShowWindow(h, 6)
            return True

        user32.EnumWindows(proc(vers), 0)

    def verifier_mode_clic():
        if not windows:
            return
        f1 = bool(ctypes.windll.user32.GetAsyncKeyState(0x70) & 0x8000)
        f1_neuf, f1_ref[0] = f1 and not f1_ref[0], f1
        if f1_neuf and not dofus_actif():
            log("F1 refuse : la fenetre active n'appartient pas a Dofus (ou verification impossible).")
            return
        if f1_neuf and dofus_actif():
            if not cibler_ecran_dofus():
                return
            if panneau.mode.get() != "automatique" and confirmation_navigation.attente is not None:
                confirmation_navigation.abandonner()
                diagnostic.evenement("navigation_resynchronisee_manuellement")
            if panneau.mode.get() != "automatique" and confirmation.attente is not None:
                ancienne = confirmation.abandonner()
                diagnostic.evenement("action_resynchronisee_manuellement", id_confirmation=ancienne["id"])
            panneau.mode.set("automatique")
            panneau._mode_change()
            mode_suivi[0] = "automatique"
            position_souris_ref[0] = position_souris()
            log("Mode automatique lance (F1). Echap pour arreter.")
            try:
                minimiser_ui()
            except Exception as err:
                log(f"minimisation de la page impossible : {err}")
            return
        mode = panneau.mode.get()
        if mode != mode_suivi[0]:
            mode_suivi[0] = mode
            position_souris_ref[0] = position_souris()
            return
        if mode != "automatique":
            position_souris_ref[0] = position_souris()
            return
        user32 = ctypes.windll.user32
        if not dofus_actif():
            panneau.mode.set("manuel")
            panneau._mode_change()
            mode_suivi[0] = "manuel"
            log("Mode manuel active : Dofus n'est plus au premier plan.")
            return
        if user32.GetAsyncKeyState(0x1B) & 0x8000:
            panneau.mode.set("manuel")
            panneau._mode_change()
            mode_suivi[0] = "manuel"
            log("Mode manuel active (Echap). L'analyse continue.")
            return
        position = position_souris()
        reference = position_souris_ref[0]
        if position is not None and reference is not None:
            dx, dy = position[0] - reference[0], position[1] - reference[1]
            if dx * dx + dy * dy >= 30 * 30:
                panneau.mode.set("manuel")
                panneau._mode_change()
                mode_suivi[0] = "manuel"
                log("Mode manuel active (mouvement de souris). L'analyse continue.")

    if windows:
        log("F1 : mode automatique et page minimisee. Mouvement de souris (>30 px) ou Echap : passe en mode manuel.")

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

    SUIVI.cmds = panneau.cmds

    def curseur():
        if not windows:
            return None
        pt = wintypes.POINT()
        ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))        # lecture seule de la position
        return pt.x, pt.y

    d_runes = os.path.join(ICI, "fm_runes")
    os.makedirs(d_runes, exist_ok=True)
    runes, vu_rune = {}, {}
    for nf in os.listdir(d_runes):
        img = cv2.imread(os.path.join(d_runes, nf))
        if img is not None and nf.endswith(".png"):
            runes[nf[:-4]] = img
    RUNES_APPRISES.update(runes)

    chiffres = Chiffres()
    cache, stable, vu, n_vu, reco, dernier_txt, memo = {}, None, None, 0, {}, "", {}
    sig_item, n_autre, nom_item, dernier_rel, rel_perime = set(), 0, "", None, 0
    dernier_clic, t_clic, n_relance = None, 0.0, 0
    echecs, rune_echec, t_fige = 0, None, 0.0
    alerte = 0
    log(f"En marche ({ocr.mode}). Ecrans : " + ", ".join(
        f"{i + 1}={m['width']}x{m['height']}@{m['left']},{m['top']}" for i, m in enumerate(mons)))
    for k_, v_ in (("lecture", ocr.mode), ("opencv", cv2.__version__), ("sift", hasattr(cv2, "SIFT_create")),
                   ("ecrans", [f"{m['width']}x{m['height']}" for m in mons]), ("python", sys.version.split()[0]),
                   ("dernier_lancement", time.strftime("%Y-%m-%d %H:%M"))):
        BILAN.pose("systeme", k_, v_)
    t_fps, n_fps = time.time(), 0
    # La capture et la lecture de l'ecran tournent dans un fil a part : les fenetres de reglage restent fluides
    # (avant, chaque clic attendait la fin d'une lecture complete).
    boite, partage = queue.Queue(maxsize=1), {"mon": mon, "fin": False}

    def lecteur():
        prendre = capturer
        try:
            import mss as mss_
            sct_ = mss_.mss()                      # mss doit etre cree dans le fil qui s'en sert

            def prendre(m):
                return np.ascontiguousarray(np.array(sct_.grab(m))[:, :, :3])
        except ImportError:
            pass
        while not partage["fin"]:
            m = partage["mon"]
            try:
                t0_ = time.time()
                t_capture = time.monotonic()
                img = prendre(m)
                t1_ = time.time()
                e_ = lire_ecran(img, ocr, cache, chiffres)
                t2_ = time.time()
                GUIDE.origine = (m["left"], m["top"])
                GUIDE.nom_item = getattr(panneau, "nom_jeu", "") or ""
                g_ = GUIDE.etape(img, None, [], ocr) if e_ is None else None
                if GUIDE.phase is not None:                  # ou passe le temps pendant un ravitaillement
                    BILAN.duree("tour : capture", t1_ - t0_)
                    BILAN.duree("tour : lecture de l'atelier", t2_ - t1_)
                    BILAN.duree("tour : guide", time.time() - t2_)
                boite.put((m, img, e_, g_, t_capture))
            except KeyboardInterrupt:
                boite.put(None)
                return
            except Exception as err:
                log(f"lecture de l'ecran impossible : {type(err).__name__} {err}")
                BILAN.note("erreurs", f"lecture de l'écran : {type(err).__name__} {str(err)[:80]}")
                time.sleep(.5)

    threading.Thread(target=lecteur, daemon=True).start()
    try:
        while True:
            # FM_CLICK_PATCH:LOOP
            verifier_mode_clic()
            root.update()
            panneau.web_tick()
            BILAN.ecrire()
            try:
                recu = boite.get(timeout=.015)
            except queue.Empty:
                continue
            if recu is None:
                break
            m_recu, bgr, etat, g_hors, t_capture = recu
            if m_recu is not mon:
                continue                                   # image d'un ecran qu'on ne regarde plus
            diagnostic.observation(etat, t_capture, bgr if etat else None)
            if n_fps % 3 == 0 and charger_txt(f_run) != jeton:
                log("Une nouvelle instance a pris le relais, arret.")
                break
            if t_capture <= securite.get("reprise_apres", 0):
                continue
            securite["capture"] = securite["lecture"] = t_capture
            observer_confirmation(etat, t_capture)
            panneau.image, panneau.ecran = bgr, (mon["left"], mon["top"], bgr.shape[1], bgr.shape[0])
            panneau.tableau_visible = bool(etat)
            _EXOS_ATTENDUS[:] = [c_ for c_, n_ in ((panneau.conf or {}).get("exos") or {}).items() if n_ > 0]
            cv.delete("all")
            if preparer_file(bgr, etat, t_capture):
                root.update()
                continue
            if preparer_demarrage(bgr, etat, t_capture):
                root.update()
                continue
            if panneau.apprendre:                          # apprentissage de l'image d'une rune d'exo
                code_a, t_a, pos_a, pret_a = panneau.apprendre
                cur = curseur()
                if cur is None:
                    panneau.apprendre = None
                elif pos_a is None:
                    if time.time() >= t_a:
                        panneau.apprendre = (code_a, t_a, cur, False)
                    else:
                        panneau.etat.config(fg=panneau.ROUGE, text=f"Pose la souris au centre de la rune "
                                            f"{nom_code(code_a)} dans l'inventaire... {t_a - time.time():.0f} s")
                elif not pret_a:
                    panneau.etat.config(text="Position notée : éloigne maintenant la souris", fg=panneau.ROUGE)
                    if abs(cur[0] - pos_a[0]) + abs(cur[1] - pos_a[1]) > 150:
                        panneau.apprendre = (code_a, t_a, pos_a, True)
                else:
                    px, py = pos_a[0] - mon["left"], pos_a[1] - mon["top"]
                    vignette = bgr[py - 8:py + 22, px - 17:px + 17] if 20 <= px < mon["width"] - 20 \
                        and 12 <= py < mon["height"] - 26 else None
                    if vignette is not None and float(vignette.std()) < 25:
                        panneau.etat.config(text="Pas de rune sous la souris (case vide) : recommence, la souris "
                                                 "au centre de la rune", fg=panneau.ROUGE)
                        log(f"apprentissage refuse pour {code_a} : case vide sous la souris")
                    elif vignette is not None:
                        runes[code_a] = vignette.copy()
                        cv2.imwrite(os.path.join(d_runes, code_a + ".png"), runes[code_a])
                        panneau.etat.config(text=f"Rune {nom_code(code_a)} apprise", fg=panneau.VERT)
                        RUNES_APPRISES.add(code_a)
                        log(f"rune apprise : {code_a}")
                    else:
                        panneau.etat.config(text="La souris n'était pas sur l'écran du jeu", fg=panneau.ROUGE)
                    panneau.apprendre = None
            # popup du jeu (« Cette forgemagie est impossible »...) : cherche a chaque image, sauf pendant un
            # ravitaillement (le CONFIRMER de l'hotel de vente est gere par le guide)
            pop = trouver_popup(bgr) if GUIDE.phase is None else None
            if pop:
                # seulement le bouton OK (vert) : c'est lui qu'on clique
                cv.create_rectangle(pop[0] - 4, pop[1] - 4, pop[2] + 4, pop[3] + 4, outline="#00ff66", width=3)
                cv.create_text(pop[0], pop[3] + 22, anchor="w", text="POPUP du jeu : clique OK",
                               fill="#00ff66", font=("Segoe UI", 12, "bold"))
                continue                    # tant que le popup est la : aucun autre cadre (le tableau est cache)
            vides = 0 if etat else vides + 1
            if vides >= 2 and len(mons) > 1 and GUIDE.phase is None:   # rien ici : on regarde l'ecran suivant
                # (pendant un ravitaillement on reste sur l'ecran du jeu)
                vides, i_mon = 0, (i_mon + 1) % len(mons)
                mon = partage["mon"] = mons[i_mon]
                _COUL[0] = None
                root.geometry(f"{mon['width']}x{mon['height']}+{mon['left']}+{mon['top']}")
            elif etat and i_mon != ecran_vu:
                ecran_vu = i_mon
                log(f"Atelier trouve sur l'ecran {i_mon + 1} ({mon['width']}x{mon['height']})")
            n_fps += 1
            if time.time() - t_fps > 15:
                rows_dbg = trouver_lignes(bgr)
                BILAN.pose("systeme", "lectures_s", round(n_fps / (time.time() - t_fps), 1))
                log(f"{n_fps / (time.time() - t_fps):.1f} lectures/s | lignes du tableau vues : {len(rows_dbg)}"
                    f" | stats lues : {sorted(etat['lignes']) if etat else 'aucune'}"
                    f" | objectif : {'regle' if panneau.conf else 'a regler'}")
                log(f"PERF diagnostic : {diagnostic.stats()}")
                if not etat:
                    cv2.imwrite(os.path.join(ICI, "fm_capture_debug.png"), bgr)
                t_fps, n_fps = time.time(), 0
            if etat:
                vues = etat["lignes"]
                if nom_jeu_ui() and nom_jeu_ui() != getattr(SUIVI, "nom_reel", ""):
                    SUIVI.nom_reel = nom_jeu_ui()
                    nom_item = SUIVI.nom_reel
                sig = signature(vues)
                if file_runtime.pop("nouvel_exemplaire",False):
                    sig_item,n_autre,memo,stable,dernier_rel = set(),2,{},None,None
                    vu,n_vu = None,0
                    phase_remise.reinitialiser()
                    vu_rune.clear()
                # --- meme item ou nouvel item ?
                if sig_item and proche(sig, sig_item) >= .6:
                    n_autre = 0
                    codes = {c[0] for c in sig_item}
                    sig_item |= {c for c in sig if c[0] not in codes}
                else:
                    n_autre += 1
                    if n_autre >= 3:
                        n_autre, sig_item, memo, stable, dernier_rel = 0, set(sig), {}, None, None
                        phase_remise.reinitialiser()
                        SUIVI.n_survol, SUIVI.t_survol = 0, time.time()
                        SUIVI.nom_reel = lire_nom_survol() if windows else ""
                        nom_item = SUIVI.nom_reel or lire_nom_item(bgr, etat["rows"], ocr)
                        connu = panneau.nouvel_item(vues, sig_item, nom_item)
                        nom_item = SUIVI.nom_reel or (connu["nom"] if connu else nom_item)
                        log(f"ITEM : {nom_item or '(sans nom)'} - {'objectif charge' if connu else 'NOUVEAU'}")
                        for s, l in vues.items():
                            log(f"  {s:<14}{l['min']:>5}{l['max']:>5}{l['val']:>5}  {'/'.join(l['dispo'])}")
                        cv2.imwrite(os.path.join(ICI, "fm_lecture_debug.png"), bgr)
                    else:
                        root.update()
                        continue
                for s_, l_ in vues.items():
                    l_["rate"] = 0
                    if l_.get("occulte") and s_ in memo:      # cases cachees par l'infobulle
                        l_["dispo"] = memo[s_]["dispo"]
                # une ligne non lue sur cette image (infobulle, clic, animation) garde sa derniere valeur,
                # sa place et ses runes ; on ne demande jamais de faire defiler
                occupe = [v_["rect"][1] for v_ in vues.values() if v_.get("rect") and not v_.get("rate")]
                for s_, l_ in memo.items():
                    if s_ in vues:
                        continue
                    ry = l_["rect"][1] if l_.get("rect") else None
                    if ry is not None and any(abs(o_ - ry) <= 3 for o_ in occupe):
                        log(f"ligne fantome retiree : {s_} (sa place est lue comme une autre stat)")
                        continue
                    la = ry is not None and any(abs(r_[1] - ry) <= 3 for r_ in etat["rows"])
                    if l_["max"] == 0 and not la:
                        continue                    # exo dont la ligne a disparu du tableau : il est tombe
                    vues[s_] = dict(l_, rate=l_.get("rate", 0) + 1)
                memo = dict(vues)
                if etat["reliquat"] is None:        # illisible : on garde le dernier lu, et on le signale
                    rel_perime += 1
                    etat["reliquat"] = dernier_rel
                    if rel_perime == 40:
                        x_, y_, w_, _h = etat["rows"][0]
                        pas_ = etat["rows"][1][1] - y_ if len(etat["rows"]) > 1 else 40
                        cv2.imwrite(os.path.join(ICI, "fm_reliquat_debug.png"),
                                    bgr[max(0, int(y_ - 3.0 * pas_)):max(1, int(y_ - 1.9 * pas_)), x_:x_ + int(.27 * w_)])
                        log("reliquat illisible depuis 40 images : capture fm_reliquat_debug.png")
                else:
                    dernier_rel, rel_perime = etat["reliquat"], 0
                r = resume(etat)
                n_vu = n_vu + 1 if r == vu else 1
                vu = r
                if n_vu == 2 and (stable is None or resume(stable) != r):   # lecture confirmee
                    if stable is not None:
                        res = noter_passe(stable, etat, reco, histo, panneau.nom.get().strip())
                        if res:
                            diagnostic.evenement("passe_inferee", resultat=res,
                                avant=resume(stable), apres=resume(etat),
                                association="derniere action envoyee, non confirmee")
                            item_ = panneau.nom.get().strip()
                            l_res = etat["lignes"].get(res[0], {})
                            if res[2] < 2 and l_res.get("max", 1) == 0:
                                SUIVI.evenement(f"exo {res[0]} {l_res.get('val')}", f"EXO PASSÉ : {nom_code(res[0])} "
                                                f"à {l_res.get('val')} sur {item_ or 'l item'}", 5)
                            elif res[2] < 2 and 0 < l_res.get("max", 0) < l_res.get("val", 0) \
                                    and (panneau.conf or {}).get("cibles", {}).get(res[0], 0) > l_res["max"]:
                                SUIVI.evenement(f"over {res[0]} {l_res['val']}", f"Over passé : {nom_code(res[0])} "
                                                f"à {l_res['val']} (max {l_res['max']})", 5)
                            SUIVI.maj_exos(item_, objectifs_rares(panneau.conf, etat["lignes"]))
                            echecs = echecs + 1 if res[2] == 2 and res[:2] == rune_echec else int(res[2] == 2)
                            rune_echec = res[:2]
                    stable = etat
                x, y, w, h = etat["rows"][0]
                rel = "?" if etat["reliquat"] is None else f"{etat['reliquat']:g}"
                panneau.maj(etat["lignes"])
                panneau.ecran = (mon["left"], mon["top"], bgr.shape[1], bgr.shape[0])
                regl_stock = getattr(panneau, "stock_regl", None) or charger_json(F_STOCK, {})
                achats = liste_achats(lignes_stock(etat["lignes"], panneau.conf, getattr(panneau, "stock_exos", {})), regl_stock) if ravito_actif(regl_stock) else []
                if verifier_stock_exos():
                    continue
                achats = filtrer_achats_file(achats)
                calque_ravitaillement(panneau.mode.get() == "automatique" and (GUIDE.phase is not None or bool(achats)))
                g = GUIDE.etape(bgr, etat, achats, ocr, regl_stock)
                # FM_CLICK_PATCH:RAVITO_HOOK
                if g:
                    diagnostic.decision({"texte": g[0], "guide": True, "phase": GUIDE.phase}, etat, panneau.mode.get(), 0.)
                g = auto_ravitaillement(g, bgr)
                if panneau.conf is None:
                    reco, c = {}, None
                    txt = "NOUVEL ITEM : regle l'objectif dans la fenetre FM"
                    if getattr(SUIVI, "suivant", None):
                        panneau.cmds.put({"cmd": "preselection", "nom": SUIVI.suivant})
                        panneau.cmds.put({"cmd": "enregistrer"})
                        log(f"item suivant choisi sur le telephone : objectifs de {SUIVI.suivant} appliques")
                        SUIVI.evenement("suivant ok", f"Objectifs de {SUIVI.suivant} appliqués au nouvel item", 5)
                        SUIVI.suivant = None
                else:
                    t_decision = time.perf_counter()
                    reco = phase_remise.conseiller(recommander_live, etat, panneau.conf, histo, panneau.nom.get().strip())
                    duree_decision_ms = 1000 * (time.perf_counter() - t_decision)
                    txt = f"{reco['texte']}   | reliquat {rel}"
                    if panneau.prochain and reco["texte"].startswith("OBJECTIF ATTEINT"):
                        txt += f"   | prochain item : {panneau.prochain}" \
                               + (f" (+{len(panneau.file) - 1} dans la file)" if len(panneau.file) > 1 else "")
                    vieux = etat["lignes"].get(reco.get("stat"), {}).get("rate", 0)
                    if vieux > 6 or rel_perime > 6 and dernier_rel is not None:
                        quoi = "la ligne" if vieux > 6 else "le reliquat"
                        txt = f"ATTENDS : {quoi} n'est plus relu, conseil peut-être périmé   | " + txt
                        reco = dict(reco, stop=True)
                        if time.time() - t_fige > 20:          # garde une image entiere pour comprendre
                            t_fige = time.time()
                            cv2.imwrite(os.path.join(ICI, "fm_fige_debug.png"), bgr)
                            log(f"lecture figee ({quoi}) : capture fm_fige_debug.png | lignes lues : "
                                f"{sorted(k for k, v in etat['lignes'].items() if not v.get('rate'))}")
                    rare_ = next((o for o in objectifs_rares(panneau.conf, etat["lignes"])
                                  if o[0] == reco.get("stat")), None)
                    if rare_ and reco["texte"][:5] in ("EXO D", "OVER ") or rare_ and reco["texte"].startswith("EXO"):
                        v_ = etat["lignes"].get(reco["stat"], {"val": 0})["val"]
                        _, vise_, dep_ = rare_
                        if v_ == vise_ - 1:          # on ne compte que les tentatives du dernier point vise
                            n_, r_, d_ = compteur_exos(panneau.nom.get().strip()).get((reco["stat"], v_), (0, 0, 0))
                            quoi_ = f" du {vise_}e %" if dep_ == 0 and vise_ > 1 else f" pour {v_} → {vise_}" if dep_ else ""
                            txt += f"   | tentative n°{n_ + 1}{quoi_} ({r_} passée{'s' if r_ > 1 else ''})"
                        elif dep_ == 0:
                            txt += f"   | {v_}/{vise_} posé, pas encore une tentative du {vise_}e %"
                        else:
                            txt += f"   | à {v_} pour un objectif de {vise_}, pas encore la dernière marche"
                    if echecs >= 10 and rune_echec == (reco.get("stat"), reco.get("taille")):
                        # On n'arrete que si la serie est anormale pour cette rune : moins d'1 chance sur 100
                        # d'apres ses chances de depart. Un exo a 1 % ou une rune hors palier ratent
                        # normalement plusieurs fois de suite ; une rune qui passe d'habitude, non.
                        l_ = etat["lignes"].get(reco["stat"], {"max": 0, "val": 0})
                        p_ec = probas({}, reco["stat"], reco["taille"], l_)[0][2]
                        if p_ec ** echecs < .01:
                            txt = (f"STOP : {echecs} échecs de suite sur cette rune (anormal, elle passe "
                                   f"{1 - p_ec:.0%} du temps), vérifie la lecture et l'objectif   | ") + txt
                            reco = dict(reco, stop=True)
                    mode_diag = panneau.mode.get() if hasattr(panneau, "mode") else "conseil"
                    diagnostic.decision(reco, etat, mode_diag, duree_decision_ms)
                    signaler_objectif_confirme(reco)
                    c = None if g else case_rune(etat, reco)
                    if c:
                        cv.create_rectangle(*c, outline="#ff3b30" if reco.get("stop") else "#00ff66", width=3)
                        # FM_CLICK_PATCH:CLICK_HOOK
                        verifier_mode_clic()
                        cle_clic = (tuple(sorted(sig_item)), resume(etat),
                                    reco.get("stat"), reco.get("taille"))
                        if panneau.mode.get() == "automatique" and not reco.get("stop") and n_vu >= 2 \
                                and confirmation.attente is None:
                            dernier_clic, t_clic = cle_clic, time.time()
                            if cliquer_case(c):
                                log(f"Clic automatique : {reco['texte']}")
                    elif "stat" in reco and not g:
                        if reco.get("virtuel"):
                            gab = runes.get(reco["stat"])
                            ou = trouver_rune(bgr, gab, vu_rune.get(reco["stat"])) if gab is not None else None
                            if ou:
                                vu_rune[reco["stat"]] = ou
                                cx, cy, r_ = ou[0] + 17, ou[1] + 8, int(.8 * h)
                                cv.create_rectangle(cx - r_, cy - r_, cx + r_, cy + r_, outline="#00ff66", width=3)
                                txt += "   (exo : rune encadrée dans l'inventaire)"
                                # FM_CLICK_PATCH:EXO_HOOK
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
                            elif gab is None and not reco.get("petit_exo"):
                                txt += "   (exo : rune pas encore apprise, bouton « Apprendre la rune »)"
                            else:
                                txt += "   (exo : rune introuvable dans l'inventaire affiché)"
                if g:                               # ravitaillement : le guide remplace le conseil de rune
                    txt, reco, c = g[0], {"texte": g[0], "guide": True}, None
                    if g[1]:
                        cv.create_rectangle(g[1][0] - 26, g[1][1] - 26, g[1][0] + 26, g[1][1] + 26,
                                            outline="#00ff66", width=3)
                # FM_CLICK_PATCH:MANUAL_LABEL
                if panneau.mode.get() == "manuel":
                    txt += "   | MODE MANUEL"
                cv.create_text(x + 4, y - int(1.15 * h), anchor="w", text=txt, fill="#00ff66",
                               font=("Segoe UI", max(9, int(.36 * h)), "bold"))
                if txt != dernier_txt:
                    log(txt)
                    dernier_txt = txt
                if achats != SUIVI.achats:
                    for a_ in achats:
                        SUIVI.evenement("stock " + a_["rune"], f"Stock bas : {a_['rune']} ({a_['stock']} en stock), "
                                        f"acheter {a_['acheter']} ({a_['lots']})"
                                        + (f", max {a_['prix']} k la rune" if a_["prix"] else ""), 900)
                    SUIVI.achats = achats
                    try:
                        with open(os.path.join(ICI, "fm_achats.txt"), "w", encoding="utf-8") as f_:
                            f_.write("\n".join(f"{a_['rune']} : {a_['stock']} en stock, acheter {a_['acheter']} "
                                               f"({a_['lots']})" + (f", max {a_['prix']} k la rune, budget "
                                                                    f"{a_['budget']} k" if a_["prix"] else "")
                                               for a_ in achats) or "rien a acheter")
                    except OSError:
                        pass
                if achats and not g:
                    txt_stock = "STOCK BAS : " + ", ".join(f"{a_['rune']} ({a_['stock']})" for a_ in achats[:4])
                    cv.create_text(x + 4, y - int(1.75 * h), anchor="w", text=txt_stock, fill="#ffd166",
                                   font=("Segoe UI", max(8, int(.30 * h)), "bold"))
                SUIVI.maj(bgr, etat, txt, reco, c, panneau.nom.get().strip())
                if time.time() - SUIVI.t_exo > 5:
                    SUIVI.t_exo = time.time()
                    SUIVI.maj_exos(panneau.nom.get().strip(), objectifs_rares(panneau.conf, etat["lignes"]))
            else:
                g = g_hors
                if g:
                    diagnostic.decision({"texte": g[0], "guide": True, "phase": GUIDE.phase}, etat, panneau.mode.get(), 0.)
                g = auto_ravitaillement(g, bgr)
                if g:                               # hors de la forgemagie : etape du ravitaillement
                    H_, W_ = bgr.shape[:2]
                    cv.create_text(int(.30 * W_), int(.115 * H_), anchor="nw", text=g[0], fill="#00ff66",
                                   font=("Segoe UI", max(10, int(.014 * H_)), "bold"))
                    if g[1]:
                        cv.create_rectangle(g[1][0] - 30, g[1][1] - 30, g[1][0] + 30, g[1][1] + 30,
                                            outline="#00ff66", width=3)
                    SUIVI.texte, SUIVI.stop, SUIVI.t = g[0], False, time.time()
                    if g[0] != dernier_txt:
                        log(g[0].replace("\n", "  "))
                        dernier_txt = g[0]
                elif time.time() - alerte > 5:
                    if not alerte:
                        cv2.imwrite(os.path.join(ICI, "fm_capture_debug.png"), bgr)
                        log("Tableau non trouve. Capture enregistree : fm_capture_debug.png")
                        SUIVI.evenement("perdu", "Fenêtre de forgemagie non visible", 300)
                    alerte = time.time()
            diagnostic.evenement("orchestration", tableau=bool(etat), guide=GUIDE.phase,
                mode=panneau.mode.get() if hasattr(panneau, "mode") else "conseil", profil=panneau.nom.get().strip(),
                file=list(panneau.file), stop=bool(reco.get("stop")) if etat else False,
                termine=bool(etat and reco.get("texte", "").startswith("OBJECTIF ATTEINT")))
            root.update()
    except KeyboardInterrupt:
        pass
    except tk.TclError:
        pass
    finally:
        partage["fin"] = True
        diagnostic.fermer()


def main():
    ap = argparse.ArgumentParser(description="Assistant de forgemagie en direct")
    ap.add_argument("--image")
    ap.add_argument("--ecran", type=int, default=0, help="0 = cherche sur tous les ecrans")
    ap.add_argument("--codes", action="store_true")
    ap.add_argument("--tk", action="store_true", help="anciennes fenetres de reglage au lieu de la page web")
    a = ap.parse_args()
    if a.codes:
        print(" ".join(f"{s}({p:g})" for s, p in sorted(POIDS.items(), key=lambda x: x[1])))
        return
    histo = histo_depuis_passes()
    try:
        ocr = Ocr()
    except SystemExit as e:
        log(str(e))
        raise
    if a.image:
        mode_image(a.image, ocr, histo)
    else:
        INTERFACE_WEB[0] = not a.tk
        mode_direct(a.ecran, ocr, histo)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        log(traceback.format_exc())
        raise
