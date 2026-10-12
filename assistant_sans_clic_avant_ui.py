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
import sys
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
AVEC_RA = {"vi", "ini", "pods", "fo", "int", "cha", "agi", "sa", "pui", "pui_pieges", "do_pou"} | \
          {"re_" + e for e in _EL}
AVEC_PA = AVEC_RA | {"pp", "tacle", "fuite", "do_cri", "do_pieges", "re_cri", "re_pou",
                     "ret_pa", "ret_pm", "esq_pa", "esq_pm"} | {"do_" + e for e in _EL}


def tailles(s):
    return ["base", "pa", "ra"] if s in AVEC_RA else ["base", "pa"] if s in AVEC_PA else ["base"]
SEUIL_ATTENTE = .30                               # sous cette chance de reussite, on prefere attendre
SEUIL_RA = 60                                     # Fo/Int/Cha/Agi : au-dela de 60, seules les Ra passent bien
CARBU_BAS, CARBU_HAUT = .20, .50                  # ligne jetable : on la remonte a partir de 20 % du max, jusqu'a 50 %
_CYCLE = [False]                                  # True = on remonte le jet jusqu'a « Remonter a »
_EN_REMONTEE = set()                              # lignes jetables en cours de remontee
LOURD = 20                                        # puits a partir duquel une ligne est "lourde"
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
        proche = difflib.get_close_matches(n, list(NOMS), n=1, cutoff=0.8)
        code = NOMS[proche[0]] if proche else None
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
    return [x / sum(c) for x in c], sum(h)


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
                histo.setdefault(contexte(c[2], c[3], l), [0, 0, 0])[("SC", "SN", "EC").index(c[7])] += 1
    except OSError:
        pass
    return histo


def recommander(etat, conf, histo):
    """Retourne {stat, taille, texte} ou {texte} seulement."""
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

    # Tous les exos demandes sont poses (ex. les 2 % dommages aux sorts) : on ne propose PLUS RIEN, quels
    # que soient le reliquat et l'etat du jet. Toute rune de plus pourrait piocher dans l'exo et le casser.
    # (un over voulu sur une ligne de l'item compte pareil : 6 % dommages aux sorts sur une ligne a 4 max)
    voulus = [s for s, c in conf.get("exos", {}).items() if c > 0 and s in L] \
        + [s for s, l in L.items() if l["cible"] > l["max"] > 0 and s not in conf.get("exos", {})]
    if voulus and all(L[s]["val"] >= L[s]["cible"] > 0 for s in voulus) \
            and all(s in etat["lignes"] for s in voulus):
        bas = [f"{l['nom']} {l['val']} (min {conf['mins'][s]})" for s, l in L.items()
               if l["max"] > 0 and l["val"] < min(conf.get("mins", {}).get(s, 0), l["max"])]
        return {"texte": "OBJECTIF ATTEINT : " + ", ".join(f"{L[s]['nom']} à {L[s]['val']}" for s in voulus)
                + " — ne touche plus à rien" + ("   | sous le minimum : " + ", ".join(bas) if bas else "")
                + (f"   | {rel:g} de reliquat : il est perdu si tu équipes ou mets en vente l'item" if rel >= 1 else "")}
    # Ligne haute coincee entre la fin de sa plage Ra et son objectif (ex. Puissance a 113 pour 118,
    # Ra permise jusqu'a 110) : les petites runes n'y passent plus. On n'y touche pas, on continue de
    # runer les autres lignes pour qu'elle redescende dans la plage de la Ra.
    bloquees = {}
    for s, l in L.items():
        g = tailles(s)[-1]
        plage = conf.get("regles", {}).get(s, {}).get(g) if g != "base" else None
        if not plage or l["max"] <= 0:
            continue
        fin = min(plage[1], plafond(s, l["max"]) - qte(s, g))        # derniere valeur ou la grosse rune tient
        if pds(s, l["val"]) >= SEUIL_RA and fin < l["val"] < l["cible"]:
            bloquees[s] = fin
    # Over a la grosse rune mal aligne : a 417 vita (max 400, plafond 505) une Ra mene a 467, la suivante
    # depasserait 505.  Il faut d'abord redescendre a 405 avec des runes a 1 de puits, puis 405 -> 455 -> 505.
    alignes = {}
    for s, l in L.items():
        g = tailles(s)[-1]
        if g == "base" or s in bloquees or not (0 < l["max"] < l["val"] < l["cible"]):
            continue
        q, haut = qte(s, g), plafond(s, l["max"])
        but = conf.get("mins", {}).get(s, l["cible"])
        n = int((haut - l["val"]) // q)                      # nombre de grosses runes qui rentrent encore
        if l["val"] + q * n >= but:
            continue                                         # on arrive au but sans rien toucher
        v = haut - q * (n + 1)
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
            f"{tailles(s)[-1].capitalize()}" for s, v in tous.items())

    attente = {}

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

    def degat(s, t):
        """Lignes en over non voulu que cette rune ferait retomber sous leur max."""
        # Le reliquat ne protege pas : sur un echec critique la perte tombe sur les lignes, l'over en premier
        # (vu en jeu : Retrait PM rate avec 12 de reliquat, vita 458 -> 423, reliquat inchange).
        w = pds(s, qte(s, t))
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
        return all(l["val"] + qte(s, t) > l["max"] or l["val"] >= 1.2 * palier(s, t) for t in ts[:-1])

    # Un exo est pose sur l'item (1er % dommages aux sorts...) : le jeu refuse toute rune qui ferait passer une
    # ligne normale au-dessus de son max (constate : Ra Vi impossible au-dessus de 400/450 avec le % pose).
    exo_pose = any(l["max"] <= 0 and l["val"] > 0 and not l.get("virtuel") for l in L.values())

    def essais(lignes, borne, over=True, libre=False):
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
                if not over and sous_max and l["val"] + qte(s, voulu) > l["max"]:
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
                    plus_petit = [t for t in l["dispo"] if MULT[t] < MULT[voulu] and not degat(s, t)]
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
            ligne = []
            en_over = libre and grosse_t != "base" and 0 < l["max"] <= l["val"] < l["cible"]
            for t in permis:
                q = qte(s, t)
                if l["val"] + q > limite:
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
                    if l["val"] + q > max(l["cible"], l["max"]) and not (t == tp and l["val"] < l["cible"]):
                        continue
                if not over and sous_max and l["val"] + q > l["max"]:
                    # franchir le max pendant la remontee du jet : la grosse rune d'un over voulu quand
                    # c'est son tour, ou la taille adaptee qui finit une ligne sans over
                    if vise_over and not (grosse(s, t) and peut_franchir(s, l)):
                        continue
                    if not vise_over and t not in (tp, "base"):
                        continue
                (psc, psn, pec), n = probas(histo, s, t, l)
                cout = min(max(0.0, pds(s, q) - rel), autres)
                perte = cout * (utiles / autres if autres else 0)
                note = (psc + psn) * pds(s, min(q, besoin)) - .15 * (psn + pec) * perte
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
            txt += "   | ATTENTION : fera retomber sous son max " + ", ".join(
                f"{L[x]['nom']} (over de {parasites[x]})" for x in casse)
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
        if entame or not any(L[x]["cible"] > 0 for x in parasites):       # (une ligne jetable en over : on s'en fiche)
            return None
        exc = sum(pds(x, n) for x, n in parasites.items())
        cands = []
        for x, y in L.items():
            if x in parasites or y["max"] <= 0 or x == "pods" or x in intouchables:
                continue                             # (Vi et Ini a 1 de densite sont permises ; l'over lui-meme non)
            for t in y["dispo"]:
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
        utile = lambda k: L[k[2]]["val"] < L[k[2]]["cible"]
        if tient:
            return max(tient, key=lambda k: (utile(k), par_poids(k)[0], k[4]))
        petit = [k for k in cands if par_poids(k)[0] <= 2]
        return min(petit, key=lambda k: (not utile(k), par_poids(k)[0], -k[4])) if petit else None

    def joue(k, prefixe):
        """Sortie normale, sauf si cette rune casserait un over non voulu : on gere l'over d'abord."""
        if degat(k[2], k[3]):
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
    if c or jet_obj:
        # a) ce que le reliquat paie en entier sur les lignes du jet, la plus grosse rune d'abord
        #    (1 Dommage a 20 de puits passe dans 98 de reliquat ; le PA a 100 attend)
        #    Un over non voulu (vita 480 pour un max de 450) se depense pareil : la rune suivante pioche
        #    dedans en premier. On choisit donc une rune qui tient dans reliquat + excedent, la plus grosse
        #    d'abord (un Do air a 5 de puits ramene la vita a 455), et jamais une rune plus grosse que ce qui
        #    reste (a 451, un Do air la ferait retomber a 426 : une petite rune a la place).
        payes = [k for k in essais(jet_obj, lambda l: min(l["cible"], l["max"]), over=False, libre=True)[0]
                 if (pds(k[2], qte(k[2], k[3])) <= rel or recycle(k))
                 and (k[2] in jet or not degat(k[2], k[3]))     # rune facultative : jamais si elle peut casser un over
                 and (k[2] in jet or not deja)      # exo/over deja pose : aucune rune facultative, meme payee par le
                                                    # reliquat (son echec critique tomberait sur l'exo)
                 and (POIDS.get(k[2], 0) <= LOURD or not leger)]   # PO/PM/PA : jamais tant qu'une ligne legere manque
        if [k for k in payes if POIDS.get(k[2], 0) < LOURD]:    # le PO attend que tout le reste soit utilise
            payes = [k for k in payes if POIDS.get(k[2], 0) < LOURD]
        if payes:
            # d'abord les lignes encore sous leur minimum, puis celles qu'on finit vers l'objectif
            k = meilleur(payes, lambda k: (k[2] in jet, lourdes_d_abord(k), par_poids(k)))
            if pds(k[2], qte(k[2], k[3])) <= rel:
                return joue(k, "DANS LE RELIQUAT")
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
                r = sortie(max(rec, key=par_poids), "REMONTE", sans)
                r["texte"] += "   | réutilise l'excédent de " + ", ".join(L[x]["nom"] for x in parasites if x != r["stat"])
                return r
            if [k for k in leger if not degat(k[2], k[3])]:      # pas de rune qui casse un over si une autre existe
                leger = [k for k in leger if not degat(k[2], k[3])]
            k = None if lourd or entame else carburant()   # (pas quand PO/PM/PA a saute : retour a l'exo au plus vite)
            # on jongle : une jetable tombee bas remonte avant les lignes utiles
            if k:
                return sortie(k, "CARBURANT (ligne jetable basse)", sans)
            # remonter toutes les lignes petit a petit plutot qu'une ligne a fond : la moins remplie d'abord
            gros = [k for k in leger if lourdes_d_abord(k)]
            leger = gros or leger
            vide = min(L[k[2]]["val"] / L[k[2]]["max"] for k in leger)
            return joue(meilleur([k for k in leger if L[k[2]]["val"] / L[k[2]]["max"] <= vide + .1]), "REMONTE")
        # c) il ne manque plus que des lignes lourdes : le reliquat restant part d'abord dans les over voulus
        k = dans_reliquat()
        if k:
            return sortie(k, "DANS LE RELIQUAT", sans)
        return joue(meilleur(lourd), "REMETS")
    k = dans_reliquat(True)                  # jet complet : le reliquat part d'abord dans les over voulus
    if k:
        return sortie(k, "DANS LE RELIQUAT", sans)
    # jet au minimum : on tente l'exo / l'over tout de suite, sans remonter une ligne jetable avant
    if bloquees or attente:
        # plus rien d'autre a monter : la plus petite rune jouable ailleurs, juste pour faire des pertes
        petites = [((x in ("vi", "ini", "pods"), pds(x, qte(x, "base"))), x) for x, y in L.items()
                   if x not in bloquees and x not in attente and "base" in y["dispo"] and y["max"] > 0
                   and y["val"] + qte(x, "base") <= plafond(x, y["max"])]
        if petites and (min(petites)[0][1] <= 2 or not alignes):
            x = min(petites)[1]
            return {"stat": x, "taille": "base", "virtuel": False,
                    "texte": f"DESCENTE {L[x]['nom']} +{qte(x, 'base')}{note_blocage()}"}
        if alignes:                                # aucune petite rune sur l'item : une rune a 1 de puits en exo
            x = next((c for c in CARAC if c not in L), "ini")
            return {"stat": x, "taille": "base", "virtuel": True,
                    "texte": f"DESCENTE {nom_code(x)} +{qte(x, 'base')} (exo à 1 de puits){note_blocage()}"}
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
    vises = [s for s in vises if s not in entames or s in rates]
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
        propre = not any(l["max"] <= 0 < l["val"] or l["val"] > l["max"] > 0 for l in L.values())
        return {"texte": "OBJECTIF ATTEINT"
                + ("   | ni exo ni over sur l'item : tu peux le finir avec une rune de transcendance "
                   "(100 % de réussite, mais elle verrouille l'item)" if propre else "")
                + (f"   | {rel:g} de reliquat : il est perdu si tu équipes ou mets en vente l'item" if rel >= 1 else "")}
    # l'over d'une ligne du jet passe avant les exos lourds (PO, PM, PA) : le PO toujours apres l'over
    s = max(vises, key=lambda x: (L[x]["max"] > 0 and POIDS.get(x, 0) < LOURD, pds(x, qte(x, "base"))))
    c, sans = essais([s], lambda l: l["cible"])
    if not c:
        return {"texte": f"A ACHETER : runes {L[s]['nom']}" if sans else f"{L[s]['nom']} : plafond atteint"}
    best = meilleur(c)
    # 3) pas assez de carburant : remonter d'abord les lignes sacrifiables
    sacrif = sum(pds(x, max(0, y["val"] - y["cible"])) for x, y in L.items() if x != s)
    if L[s]["max"] <= 0 and not entame and rel + sacrif < pds(s, qte(s, best[3])):      # exo seulement
        f, _ = essais([x for x, y in L.items() if y["max"] > 0 and y["cible"] <= 0 and x not in intouchables
                       and y["val"] < y["max"] and x != s], lambda l: l["max"])
        f = [k for k in f if L[k[2]]["val"] + qte(k[2], k[3]) <= L[k[2]]["max"]]
        if f:
            return sortie(max(f), "CARBURANT", sans)
    return joue(best, "EXO") if L[s]["max"] <= 0 else sortie(best, "OVER", sans)


# ---------------------------------------------------------------- lecture d'ecran
class Ocr:
    def __init__(self):
        self.mode, self.eng = None, None
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
        self.douteux = 0

    def classer(self, g, dump=True):
        v = _canevas(g).ravel()
        v -= v.mean()
        sc = self.gab @ (v / (np.linalg.norm(v) + 1e-6))
        i = int(sc.argmax())
        if dump and sc[i] < .75 and self.douteux < 150:          # garde une trace pour ameliorer les gabarits
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
            if sc < seuil:
                return None
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
            garde = [i for i, n in enumerate(self.noms) if n]      # purge les anciens « nom illisible »
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
STOCK_ALERTE, STOCK_CIBLE = 20, 100          # par defaut : alerte sous 20 runes, racheter pour remonter a 100
_RUNES_VUES = set()                          # runes deja vues en stock (pour reperer une case qui se vide)


def nom_rune(s, t):
    return ("" if t == "base" else t.capitalize() + " ") + nom_code(s)


def liste_achats(lignes, regl):
    """Runes de l'item en cours passees sous leur seuil d'alerte : [{rune, stock, acheter, lots, prix, budget}].
    regl : {"stat/taille": {"alerte": n, "cible": n, "prix": kamas par rune}} ; alerte 0 = rune non suivie."""
    out = []
    if not any(l.get("dispo") for l in lignes.values()):
        return out                                   # aucune case de rune visible : l'onglet Ressources n'est pas actif
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
            elif cle in _RUNES_VUES or cle in regl:
                n = 0                                # la case s'est videe (ou rune suivie jamais en stock)
            else:
                continue
            r = regl.get(cle, {})
            alerte, cible = int(r.get("alerte", STOCK_ALERTE)), int(r.get("cible", STOCK_CIBLE))
            if alerte <= 0 or n >= alerte or cible <= n:
                continue
            q = -(-(cible - n) // 10) * 10           # jamais a l'unite : arrondi au lot de 10 superieur
            prix = r.get("prix")
            lots = [f"{k}×{t_}" for k, t_ in ((q // 1000, 1000), (q % 1000 // 100, 100), (q % 100 // 10, 10)) if k]
            out.append({"rune": nom_rune(s, t), "stock": n, "acheter": q, "lots": " + ".join(lots),
                        "recherche": recherche_rune(s, t, regl),
                        "prix": prix, "budget": q * prix if prix else None})
    return sorted(out, key=lambda a: a["stock"])


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
        sub = e[:, xa + cx:xa + cx + cw].copy()
        sub[:max(0, cy - 1)] = 0
        sub[cy + ch_ + 1:] = 0
        t = chiffres.nombre(sub, [(0, cw - 1)], penche=.2)
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


def charger_json(chemin, defaut):
    try:
        with open(chemin, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return defaut


def noter_passe(avant, apres, reco, histo, item=""):
    """Deduit la rune passee et son resultat en comparant deux lectures stables, et l'apprend."""
    A, B = avant["lignes"], apres["lignes"]
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
    reco = recommander(etat, connu or {}, histo)
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


class Panneau:
    """Fenetre de reglage : objectif ligne par ligne, plages Pa/Ra, exos, sauvegarde par item."""
    FOND, CARTE, TXT, GRIS, VERT, ROUGE = "#1b1c27", "#262838", "#ecebf5", "#8d8fa6", "#35c46a", "#ff6b6b"

    def __init__(self, root, cacher):
        self.items, self.conf, self.sig = charger_items(), None, set()
        self.lignes, self.rangs, self.n_rang = {}, {}, 0
        self.apprendre = None            # (code, heure limite, position notee, pret) pendant l'apprentissage
        F = self.FOND
        self.win = w = tk.Toplevel(root)
        w.title("FM - objectif de l'item")
        w.configure(bg=F)
        w.attributes("-topmost", True)
        w.geometry("+8+110")
        w.protocol("WM_DELETE_WINDOW", w.iconify)
        self.etat = tk.Label(w, text="En attente d'un item dans l'atelier...", bg=F, fg=self.TXT,
                             font=("Segoe UI", 11, "bold"), anchor="w")
        self.etat.pack(fill="x", padx=10, pady=(8, 4))
        haut = tk.Frame(w, bg=F)
        haut.pack(fill="x", padx=10)
        tk.Label(haut, text="Item", bg=F, fg=self.GRIS).pack(side="left")
        self.nom = tk.Entry(haut, width=28)
        self.nom.pack(side="left", padx=(4, 14))
        tk.Label(haut, text="Présélection", bg=F, fg=self.GRIS).pack(side="left")
        self.choix = ttk.Combobox(haut, state="readonly", width=26, values=[it["nom"] for it in self.items])
        self.choix.pack(side="left", padx=4)
        self.choix.bind("<<ComboboxSelected>>", self._choisi)
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
        self.exo_qte = tk.Spinbox(exo, from_=1, to=20, width=3)
        self.exo_qte.pack(side="left", padx=4)
        tk.Button(exo, text="+ Ajouter", command=self.ajouter_exo).pack(side="left", padx=4)
        tk.Label(exo, text="Plan B", bg=F, fg=self.GRIS).pack(side="left", padx=(16, 0))
        self.plan_b = ttk.Combobox(exo, state="readonly", width=18,
                                   values=["(aucun)"] + [nom_code(c) for c in self.codes_exo])
        self.plan_b.current(0)
        self.plan_b.pack(side="left", padx=4)
        tk.Label(w, bg=F, fg=self.GRIS, justify="left", anchor="w", font=("Segoe UI", 8),
                 text="Objectif sous le max ou « jetable » = ligne dont on se fout : remontée seulement comme "
                      "carburant d'un exo   |   au-dessus du max = over (plafond : puits 101)\n"
                      "Min accepté : over considéré réussi à partir de cette valeur quand le reliquat est vide ; "
                      "en dessous, on passe au Plan B (exo de rechange)\n"
                      "Normale / Pa / Ra de...à : utiliser cette rune seulement quand la valeur actuelle est dans "
                      "la plage (tout vide = choix automatique ; hors plages = taille adaptée au palier)").pack(fill="x", padx=10, pady=(6, 0))
        bas = tk.Frame(w, bg=F)
        bas.pack(fill="x", padx=10, pady=8)
        tk.Button(bas, text="Tout au max", command=lambda: self.remplir("max")).pack(side="left")
        tk.Button(bas, text="Tout au min", command=lambda: self.remplir("min")).pack(side="left", padx=4)
        tk.Button(bas, text="Proposer Pa / Ra", command=self.proposer).pack(side="left", padx=4)
        tk.Button(bas, text="Laisser l'algo choisir", command=self.vider_plages).pack(side="left", padx=4)
        tk.Button(bas, text="Statistiques", command=self.statistiques).pack(side="left", padx=4)
        tk.Button(bas, text="Stock de runes", command=self.fenetre_stock).pack(side="left", padx=4)
        tk.Button(bas, text="Repères", command=self.fenetre_reperes).pack(side="left", padx=4)
        tk.Button(bas, text="  ENREGISTRER  ", command=self.enregistrer, bg="#2e7d32", fg="white",
                  font=("Segoe UI", 10, "bold")).pack(side="right")
        w.update()
        cacher(w)

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
        obj = tk.Entry(g, width=6, justify="center")
        obj.grid(row=r, column=4, padx=4)
        w.append(obj)
        tol = None
        if not exo:
            tol = tk.Entry(g, width=6, justify="center")
            tol.grid(row=r, column=5, padx=4)
            w.append(tol)
        rem = None
        if not exo:
            rem = tk.Entry(g, width=6, justify="center")
            rem.grid(row=r, column=6, padx=4)
            w.append(rem)
        raccourcis = tk.Frame(g, bg=fond)
        raccourcis.grid(row=r, column=7, padx=2)
        w.append(raccourcis)
        if not exo:
            for txt, v in (("min", mini), ("max", maxi), ("jetable", 0)):
                tk.Button(raccourcis, text=txt, font=("Segoe UI", 7), padx=2, pady=0,
                          command=lambda v=v: self._met(obj, v)).pack(side="left")
        plages = {}
        for t, c in (("base", 8), ("pa", 10), ("ra", 12)):
            if t in tailles(s):
                de, a = tk.Entry(g, width=4, justify="center"), tk.Entry(g, width=4, justify="center")
                de.grid(row=r, column=c, padx=2)
                a.grid(row=r, column=c + 1, padx=2)
                w += [de, a]
                plages[t] = (de, a)
            else:
                lab(c, "-", fg=self.GRIS)
                lab(c + 1, "", fg=self.GRIS)
        if exo:
            x = tk.Button(g, text="x", font=("Segoe UI", 7), padx=3, pady=0, fg=self.ROUGE,
                          command=lambda: self.retirer_exo(s))
            x.grid(row=r, column=14, padx=4)
            w.append(x)
            x = tk.Button(g, text="Apprendre la rune", font=("Segoe UI", 7), padx=3, pady=0,
                          command=lambda: self.demander_rune(s))
            x.grid(row=r, column=15, padx=4)
            w.append(x)
        self.rangs[s] = {"obj": obj, "tol": tol, "rem": rem, "plages": plages, "exo": exo, "widgets": w, "actuel": actuel,
                         "min": mini, "max": maxi}
        return obj

    def nouvel_item(self, lignes, sig, nom_lu):
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
        self._met(self.nom, nom_lu)
        if connu:
            self.appliquer(connu)
            self.conf = self._conf(connu)
            self.etat.config(text=f"Objectif chargé : {connu['nom']}", fg=self.VERT)
        else:
            self.conf = None
            self.etat.config(text="NOUVEL ITEM : règle l'objectif puis ENREGISTRER", fg=self.ROUGE)
            self.win.deiconify()
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
            if "ra" in r["plages"]:
                q = qte(s, "ra")
                debut = obj - q                       # par defaut : le dernier saut vers l'objectif
                # la Ra reste permise jusqu'au plafond quand la ligne vise haut (over voulu, ligne
                # au-dela de 60) ; sinon elle s'arrete assez tot pour atterrir pres de l'objectif
                fin = haut if obj > r["max"] else obj - q // 2
                if s not in ("pui", "sa") and obj > palier(s, "pa"):
                    debut, fin = min(debut, palier(s, "pa")), haut   # au-dela du palier des Pa (60, 300 vita)
                elif s == "pui":
                    debut, fin = (SEUIL_RA + 1 if obj > SEUIL_RA + 1 else -1), haut
                elif s == "sa":
                    debut, fin = (48 if obj > 48 else -1), haut   # Ra Sagesse : ligne deja haute seulement
                if debut >= 0 and debut + q <= haut:
                    self._met(r["plages"]["ra"][0], debut)
                    self._met(r["plages"]["ra"][1], fin)
                    fin_pa = min(fin_pa, debut - 1)
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
        return {"cibles": dict(it.get("cibles", {})), "exos": dict(it.get("exos", {})),
                "regles": dict(it.get("regles", {})), "mins": dict(it.get("mins", {})),
                "remonte": dict(it.get("remonte", {})), "plan_b": it.get("plan_b")}

    def _choisi(self, _evt=None):
        i = self.choix.current()
        if 0 <= i < len(self.items):
            self.appliquer(self.items[i])
            self.etat.config(text="Présélection appliquée : vérifie puis ENREGISTRER", fg=self.ROUGE)

    def appliquer(self, it):
        self._met(self.nom, it["nom"])
        pb = it.get("plan_b")
        self.plan_b.current(self.codes_exo.index(pb) + 1 if pb in self.codes_exo else 0)
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
        nom = self.nom.get().strip() or f"Item {len(self.items) + 1}"
        i_pb = self.plan_b.current()
        fiche = {"nom": nom, "sig": sorted(self.sig), "cibles": cibles, "exos": exos, "regles": regles,
                 "mins": mins, "remonte": remonte, "plan_b": self.codes_exo[i_pb - 1] if i_pb > 0 else None}
        self.items = [it for it in self.items if it["nom"] != nom and proche(it["sig"], self.sig) < .7]
        self.items.append(fiche)
        try:
            with open(F_ITEMS, "w", encoding="utf-8") as f:
                json.dump({"items": self.items}, f, indent=1, ensure_ascii=False)
        except OSError as err:
            log(f"sauvegarde impossible : {err}")
        self.conf = self._conf(fiche)
        self.choix.config(values=[it["nom"] for it in self.items])
        self.etat.config(text=f"Objectif enregistré : {nom}", fg=self.VERT)
        log(f"objectif enregistre pour {nom} : {cibles} exos {exos} regles {regles} mins {mins} remonte {remonte} "
            f"plan B {fiche['plan_b']}")

    # ---- reperes du guide de ravitaillement : ou sont la porte, l'hotel de vente, les ateliers...
    def fenetre_reperes(self):
        w = tk.Toplevel(self.win)
        w.title("FM - repères du ravitaillement")
        w.attributes("-topmost", True)
        g = tk.Frame(w, bg=self.CARTE)
        g.pack(fill="both", expand=True, padx=8, pady=8)
        info = tk.Label(w, text="Pour recaler un repère : clique « Calibrer », puis place ta souris dessus dans "
                                "le jeu et ne bouge plus pendant 4 secondes.", fg=self.GRIS)
        info.pack(pady=(0, 6))
        etiq = {}

        def montrer():
            lieux = Guide.lieux()
            for k, lab in etiq.items():
                lab.config(text=f"{lieux[k][0]:.3f} ; {lieux[k][1]:.3f}")

        def calibrer(k):
            info.config(text=f"Place ta souris sur : {LIEUX_DEFAUT[k][2]} (4 secondes)...", fg=self.ROUGE)

            def prendre():
                try:
                    import ctypes
                    from ctypes import wintypes
                    p_ = wintypes.POINT()
                    ctypes.windll.user32.GetCursorPos(ctypes.byref(p_))
                    gx, gy, W, H = getattr(self, "ecran", (0, 0, 1920, 1080))
                    d = charger_json(F_LIEUX, {})
                    d[k] = [round((p_.x - gx) / W, 4), round((p_.y - gy) / H, 4)]
                    with open(F_LIEUX, "w", encoding="utf-8") as f:
                        json.dump(d, f, indent=1)
                    img = getattr(self, "image", None)       # image de reference autour du point, pour le retrouver
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
                    info.config(text=f"Repère enregistré : {LIEUX_DEFAUT[k][2]}", fg=self.VERT)
                except Exception as err:
                    info.config(text=f"Calibrage impossible ici : {err}", fg=self.ROUGE)
                montrer()

            w.after(4000, prendre)

        for r, (k, v) in enumerate(LIEUX_DEFAUT.items()):
            tk.Label(g, text=v[2], bg=self.CARTE, fg=self.TXT, anchor="w").grid(row=r, column=0, padx=6, sticky="we")
            etiq[k] = tk.Label(g, text="", bg=self.CARTE, fg=self.GRIS)
            etiq[k].grid(row=r, column=1, padx=6)
            tk.Button(g, text="Calibrer", font=("Segoe UI", 8), command=lambda k=k: calibrer(k)).grid(
                row=r, column=2, padx=6, pady=1)
        montrer()

    # ---- stock de runes : seuils d'alerte, quantite a racheter, prix maximum
    def fenetre_stock(self):
        regl = charger_json(F_STOCK, {})
        lignes = getattr(self, "lignes", None) or {}
        w = tk.Toplevel(self.win)
        w.title("FM - stock de runes")
        w.attributes("-topmost", True)
        g = tk.Frame(w, bg=self.CARTE)
        g.pack(fill="both", expand=True, padx=8, pady=8)
        for c, t in enumerate(("Rune", "En stock", "Alerte sous", "Remonter à", "Prix max / rune",
                               "Texte à taper à l'hôtel de vente")):
            tk.Label(g, text=t, bg=self.CARTE, fg=self.GRIS, font=("Segoe UI", 8, "bold")).grid(
                row=0, column=c, padx=6, pady=(4, 2), sticky="w")
        champs, r = {}, 0
        for s, l in lignes.items():
            if s not in POIDS:
                continue
            for t in tailles(s):
                cle, r = f"{s}/{t}", r + 1
                n = l.get("stock", {}).get(t, 0 if t not in l.get("dispo", ()) else "?")
                tk.Label(g, text=nom_rune(s, t), bg=self.CARTE, fg=self.TXT, anchor="w",
                         font=("Segoe UI", 10, "bold")).grid(row=r, column=0, padx=6, sticky="we")
                tk.Label(g, text=str(n), bg=self.CARTE, fg=self.VERT).grid(row=r, column=1, padx=6)
                e3 = []
                for c, (k, d) in enumerate((("alerte", STOCK_ALERTE), ("cible", STOCK_CIBLE), ("prix", "")), 2):
                    e = tk.Entry(g, width=8, justify="center")
                    e.grid(row=r, column=c, padx=6, pady=1)
                    self._met(e, regl.get(cle, {}).get(k, d))
                    e3.append(e)
                e = tk.Entry(g, width=22)
                e.grid(row=r, column=5, padx=6, pady=1)
                self._met(e, recherche_rune(s, t, regl))
                e3.append(e)
                champs[cle] = e3
        bm = tk.Frame(w, bg=self.CARTE)
        bm.pack(pady=(0, 4))
        tk.Label(bm, text="Sans prix max : accepter jusqu'au prix moyen de l'hôtel de vente +", bg=self.CARTE,
                 fg=self.TXT).pack(side="left", padx=4)
        e_marge = tk.Entry(bm, width=5, justify="center")
        e_marge.pack(side="left")
        self._met(e_marge, regl.get("_marge", {}).get("pct", MARGE_PRIX))
        tk.Label(bm, text="%", bg=self.CARTE, fg=self.TXT).pack(side="left", padx=4)
        info = tk.Label(w, text="Alerte sous 0 = rune non suivie. Le prix sert à calculer le budget maximum.",
                        bg=self.FOND if hasattr(self, "FOND") else None, fg=self.GRIS)
        info.pack(pady=(0, 4))

        def enregistrer():
            for cle, (a, c, p_, rech) in champs.items():
                va, vc, vp = a.get().strip(), c.get().strip(), p_.get().strip().replace(" ", "")
                if not (va.isdigit() and vc.isdigit()) or vp and not vp.isdigit():
                    info.config(text=f"A corriger : {cle} (nombres entiers seulement)", fg=self.ROUGE)
                    return
                regl[cle] = {"alerte": int(va), "cible": int(vc)}
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

        tk.Button(w, text="ENREGISTRER", command=enregistrer).pack(pady=(0, 8))

    # ---- statistiques des passes observees
    def statistiques(self):
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
        w = tk.Toplevel(self.win)
        w.title("FM - statistiques de tes passes")
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
            tk.Label(w, text="Aucune passe enregistrée pour l'instant.").pack(pady=(0, 8))


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
#c{padding:12px 14px;font-weight:700;font-size:17px;color:#3ddc84;border-bottom:1px solid #2a2d36}
#c.stop{color:#ff5a4f}#m{padding:6px 14px;color:#9aa0ad;font-size:13px}
img{width:100%;display:block}h2{font-size:13px;margin:14px 14px 4px;color:#9aa0ad;text-transform:uppercase}
table{border-collapse:collapse;margin:0 14px}td,th{padding:3px 12px 3px 0;text-align:left;font-size:14px}
#e div{padding:5px 14px;border-bottom:1px solid #22252d}#e b{color:#ffd166}#e span{color:#9aa0ad;margin-right:8px}
button{margin:8px 14px;padding:8px 12px;background:#2a2d36;color:#e8e8ea;border:0;border-radius:6px}</style>
<div id=c>connexion...</div><div id=m></div><img id=i alt="">
<button id=b>Activer le son et la vibration</button>
<h2>Tentatives d'exo</h2><div id=p style="padding:0 14px 6px;font-size:22px;font-weight:700"></div><table id=x></table><h2>À acheter</h2><table id=a></table><h2>Événements</h2><div id=e></div>
<script>
let vu=-1,ac=null,vi=-1,occ=false;const K=location.pathname.split('/')[1];
document.getElementById('b').onclick=()=>{ac=new (window.AudioContext||window.webkitAudioContext)();bip();
 document.getElementById('b').style.display='none'};
function bip(){if(navigator.vibrate)navigator.vibrate([200,100,200]);if(!ac)return;
 const o=ac.createOscillator(),g=ac.createGain();o.connect(g);g.connect(ac.destination);o.frequency.value=880;
 g.gain.value=.2;o.start();o.stop(ac.currentTime+.35)}
function esc(t){return t.replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]))}
async function maj(){if(occ)return;occ=true;try{const r=await fetch('/'+K+'/etat');const d=await r.json();
 const c=document.getElementById('c');c.textContent=d.texte;c.className=d.stop?'stop':'';
 document.getElementById('m').textContent=d.item+'  |  lu il y a '+d.age+' s';
 document.getElementById('p').textContent=d.exos.length?d.exos[0][1]+' tentative'+(d.exos[0][1]>1?'s':'')+' — '+d.exos[0][0]:'aucun exo demandé';
 document.getElementById('x').innerHTML='<tr><th>Exo visé<th>Tentatives<th>Passés<th>Depuis le dernier<th>Marche d'avant passée</tr>'+
  d.exos.map(x=>'<tr><td>'+esc(x[0])+'<td>'+x[1]+'<td>'+x[2]+'<td>'+x[3]+'<td>'+(x[4]===null?'':x[4]+' fois')+'</tr>').join('');
 document.getElementById('a').innerHTML=d.achats.length?'<tr><th>Rune<th>Stock<th>Acheter<th>Lots<th>Budget max</tr>'+
  d.achats.map(x=>'<tr><td>'+esc(x.rune)+'<td>'+x.stock+'<td>'+x.acheter+'<td>'+x.lots+'<td>'+(x.budget?x.budget.toLocaleString('fr-CA')+' k':'')+'</tr>').join(''):'<tr><td>rien, le stock est bon</tr>';
 document.getElementById('e').innerHTML=d.evenements.map(x=>'<div><span>'+x[0]+'</span><b>'+esc(x[1])+'</b></div>').join('');
 if(vu>=0&&d.n>vu)bip();vu=d.n;if(d.img!=vi){vi=d.img;document.getElementById('i').src='/'+K+'/ecran.jpg?'+vi;}
 }catch(e){document.getElementById('c').textContent='PC injoignable';}occ=false;}
setInterval(maj,300);maj();
</script>"""

    def __init__(self):
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
                else:
                    corps, typ = suivi.PAGE.encode(), "text/html; charset=utf-8"
                self.send_response(200)
                self.send_header("Content-Type", typ)
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(corps)))
                self.end_headers()
                self.wfile.write(corps)

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

    def etat(self):
        return {"texte": self.texte, "stop": self.stop, "item": self.item, "age": int(time.time() - self.t),
                "exos": self.exos, "evenements": self.evs[:40], "n": self.n, "img": self.n_img,
                "achats": self.achats}

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
MARGE_PRIX, FICHE_PAUSE = 20, 1.5     # % tolere au-dessus du prix moyen quand aucun prix max n'est regle ; secondes
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
        if nom in REPERES_DECOR:
            return self._dans_le_decor(bgr, nom)
        return self._interface(bgr, nom)

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
        if time.time() - self.t_ocr > .8:
            self.t_ocr = time.time()
            H, W = bgr.shape[:2]
            t = norm(ocr.ligne(bgr[int(.150 * H):int(.184 * H), int(.44 * W):int(.58 * W)]))
            self.hdv = "hotel" in t or "vente" in t or difflib.SequenceMatcher(None, t, "hoteldevente").ratio() > .7
        return self.hdv

    def _enregistrer(self, bgr, r):
        """Garde une capture du parcours de ravitaillement a chaque changement de consigne (et au moins toutes les
        PARCOURS_PAUSE s), avec le cadre propose dessine dessus, dans fm_parcours/. Sert a corriger apres coup."""
        if r is None and self.phase is None:
            return
        cle = (r[0].split("\n")[0][:60], r[1] and (r[1][0] // 20, r[1][1] // 20)) if r else None
        if cle == getattr(self, "_parc", 0) and time.time() - getattr(self, "_t_parc", 0) < PARCOURS_PAUSE:
            return
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
        self.t_fiche = time.time()
        gris = bgr.min(axis=2)                               # texte blanc garde, icone doree des kamas effacee
        g3 = cv2.merge([gris, gris, gris])
        mots = ocr.tout(g3)
        k = bgr.shape[1] / 1917

        def nombre(x0, x1, y):
            t = ocr.ligne(g3[max(0, int(y - 11 * k)):int(y + 11 * k), max(0, int(x0)):int(x1)], chiffres=True)
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
            for r in rangs.values():
                g = re.sub(r"\D", "", "".join(u for x, u, _ in sorted(r) if x < mx + 60 * k))
                d = re.sub(r"\D", "", "".join(re.sub(r"\D+$", "", u) for x, u, _ in sorted(r) if x >= mx + 60 * k))
                if g in ("1", "10", "100", "1000") and d:
                    ys[int(g)] = sum(y for _, _, y in r) / len(r)
                    relu = nombre(mx + 60 * k, mx + 215 * k, ys[int(g)])     # relecture serree du prix seul
                    lots[int(g)] = relu if relu and len(str(relu)) == len(d) else int(d)
            unit = sorted(p / n for n, p in lots.items() if n >= 10)
            if unit and not .5 * unit[len(unit) // 2] <= moyen <= 2 * unit[len(unit) // 2]:
                continue                                     # prix moyen incoherent avec les lots : mal lu, on se tait
            if moyen > 0:
                fiches.append({"nom": nom_a(mx - 15 * k, mx + 330 * k, my - 39 * k).strip(), "moyen": moyen,
                               "lots": lots, "ys": ys, "qte": nombre(mx + 167 * k, mx + 230 * k, my + 22 * k),
                               "mx": mx, "my": my})
        for t, cx, cy in mots:
            if norm(t) == "confirmer":                       # fenetre « Acheter » : rune, quantite, prix, bouton
                ya, yb = max(0, int(cy - 99 * k)), int(cy - 75 * k)       # nom en dore : lu sur l'image d'origine
                q = re.sub(r"\D", "", ocr.ligne(bgr[ya:yb, int(cx + 85 * k):int(cx + 122 * k)]))
                dial = {"nom": ocr.ligne(bgr[ya:yb, int(cx - 175 * k):int(cx)]).strip(), "n": int(q) if q else None,
                        "prix": nombre(cx - 60 * k, cx + 105 * k, cy - 45 * k), "pt": (int(cx + 38 * k), int(cy))}
                break
        self.fiche = {"fiches": fiches, "dial": dial} if fiches or dial else None
        if self.fiche:
            self.t_vu_fiche = time.time()
        return self.fiche

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
        if a and a.get("prix"):
            return float(a["prix"]), "ton prix max"
        return f["moyen"] * (1 + marge / 100), f"prix moyen {f['moyen']} + {marge} %"

    def _conseil_fiche(self, vu, k=1.0):
        """(texte, point a encadrer ou None) : quel lot acheter, quand confirmer, quand fermer la fiche."""
        fiches, d = vu["fiches"], vu["dial"]
        if d:
            a = self._voulue(d["nom"])
            f = next((f_ for f_ in fiches if norm(f_["nom"]) == norm(d["nom"])), None)
            tete = f"RAVITAILLEMENT 4/7 : achat de {d['nom'] or '?'} ×{d['n'] or '?'} à {d['prix'] or '?'} k  →  "
            if not a:
                return tete + "pas dans ta liste d'achats, vérifie avant de confirmer", None
            if d["n"] is None or d["prix"] is None:
                return tete + "mal lu, vérifie toi-même", None
            if d["n"] < 10:
                return tete + "lot à l'unité : annule et prends un lot de 10, 100 ou 1000", None
            plafond = self._plafond(a, f)[0] if f or a.get("prix") else None
            unite = d["prix"]
            if f and d["n"] in f["lots"] and abs(d["prix"] - f["lots"][d["n"]]) <= .02 * f["lots"][d["n"]]:
                unite = d["prix"] / d["n"]                   # la fenetre affiche le prix du lot entier
            if plafond is None:
                return tete + "pas de prix de référence, vérifie toi-même", None
            if unite > plafond:
                return tete + f"TROP CHER ({unite:.1f} k la rune, max {plafond:.1f}) : annule", None
            return tete + f"OK ({unite:.1f} k la rune, max {plafond:.1f}) : confirme", d["pt"]
        f = next((f_ for f_ in fiches if self._voulue(f_["nom"])), fiches[0])
        a = self._voulue(f["nom"])
        plafond, d_ou = self._plafond(a, f)
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
        if reste is None:
            return "\n".join(txt + ["→ Quantité en inventaire illisible : achète les lots OK, puis ferme la fiche."]), None
        choix = next((n for n in ok if n <= reste), None)
        if choix is None:
            return "\n".join(txt + [f"→ Il manque {reste} runes mais aucun lot utile n'est sous le max : ferme la "
                                    "fiche, on réessaiera plus tard."]), croix
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

    def etape(self, bgr, etat, achats, ocr, regl=None):
        """(texte, point a encadrer ou None) pour l'etape en cours, ou None s'il n'y a rien a guider."""
        if regl is not None:
            self.regl = regl
        r = self._etape(bgr, etat, achats, ocr)
        self._enregistrer(bgr, r)
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
                    return ("RAVITAILLEMENT 7/7 : active l'onglet Ressources de l'inventaire pour voir tes runes",
                            pt("ressources"), True)
                self.phase, self.vu_hdv = None, False
                log("ravitaillement termine")
            if self.phase is None and achats:
                self.phase, self.liste, self.vu_hdv = "sortie", list(achats), False
                log("ravitaillement : " + ", ".join(f"{a['rune']} x{a['acheter']}" for a in achats))
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
                        + "\n".join(lignes) + "\nPuis ferme l'hôtel de vente.", pt("recherche"), True)
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
                return ("RAVITAILLEMENT 7/7 : onglet Équipement, pose ton item dans la fenêtre, puis onglet "
                        "Ressources", pt("equipement"), True)
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
    with open(f_run, "w") as f:
        f.write(jeton)
    SUIVI.demarrer()
    if windows:
        import ctypes
        from ctypes import wintypes
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            pass
    try:
        import mss
        sct = mss.mss()
        mons = [dict(m) for m in sct.monitors[1:]]
        if ecran and 1 <= ecran <= len(mons):
            mons = [mons[ecran - 1]]

        def capturer(m):
            return np.ascontiguousarray(np.array(sct.grab(m))[:, :, :3])
    except ImportError:
        from PIL import ImageGrab
        im = ImageGrab.grab()
        mons = [{"left": 0, "top": 0, "width": im.width, "height": im.height}]

        def capturer(m):
            return cv2.cvtColor(np.array(ImageGrab.grab()), cv2.COLOR_RGB2BGR)

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

    chiffres = Chiffres()
    cache, stable, vu, n_vu, reco, dernier_txt, memo = {}, None, None, 0, {}, "", {}
    sig_item, n_autre, nom_item, dernier_rel, rel_perime = set(), 0, "", None, 0
    echecs, rune_echec, t_fige = 0, None, 0.0
    alerte = 0
    log(f"En marche ({ocr.mode}). Ecrans : " + ", ".join(
        f"{i + 1}={m['width']}x{m['height']}@{m['left']},{m['top']}" for i, m in enumerate(mons)))
    t_fps, n_fps = time.time(), 0
    try:
        while True:
            if n_fps % 3 == 0 and charger_txt(f_run) != jeton:
                log("Une nouvelle instance a pris le relais, arret.")
                break
            bgr = capturer(mon)
            panneau.image, panneau.ecran = bgr, (mon["left"], mon["top"], bgr.shape[1], bgr.shape[0])
            _EXOS_ATTENDUS[:] = [c_ for c_, n_ in ((panneau.conf or {}).get("exos") or {}).items() if n_ > 0]
            etat = lire_ecran(bgr, ocr, cache, chiffres)
            cv.delete("all")
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
                    if 20 <= px < mon["width"] - 20 and 12 <= py < mon["height"] - 26:
                        runes[code_a] = bgr[py - 8:py + 22, px - 17:px + 17].copy()
                        cv2.imwrite(os.path.join(d_runes, code_a + ".png"), runes[code_a])
                        panneau.etat.config(text=f"Rune {nom_code(code_a)} apprise", fg=panneau.VERT)
                        log(f"rune apprise : {code_a}")
                    else:
                        panneau.etat.config(text="La souris n'était pas sur l'écran du jeu", fg=panneau.ROUGE)
                    panneau.apprendre = None
            pop = trouver_popup(bgr) if not etat or len(etat["lignes"]) < len(memo) else None
            if pop:
                cv.create_rectangle(pop[0] - 4, pop[1] - 4, pop[2] + 4, pop[3] + 4, outline="#00ff66", width=3)
                lb = pop[2] - pop[0]                       # la croix de fermeture, en haut a droite du popup
                kx, ky, kr = int((pop[0] + pop[2]) / 2 + 1.257 * lb), int(pop[1] - .473 * lb), max(10, int(.09 * lb))
                cv.create_rectangle(kx - kr, ky - kr, kx + kr, ky + kr, outline="#00ff66", width=3)
                cv.create_text(pop[0], pop[1] - 22, anchor="w", text="POPUP du jeu : ferme-le (X ou OK)",
                               fill="#00ff66", font=("Segoe UI", 12, "bold"))
            vides = 0 if etat else vides + 1
            if vides >= 2 and len(mons) > 1 and GUIDE.phase is None:   # rien ici : on regarde l'ecran suivant
                # (pendant un ravitaillement on reste sur l'ecran du jeu)
                vides, i_mon = 0, (i_mon + 1) % len(mons)
                mon = mons[i_mon]
                _COUL[0] = None
                root.geometry(f"{mon['width']}x{mon['height']}+{mon['left']}+{mon['top']}")
            elif etat and i_mon != ecran_vu:
                ecran_vu = i_mon
                log(f"Atelier trouve sur l'ecran {i_mon + 1} ({mon['width']}x{mon['height']})")
            n_fps += 1
            if time.time() - t_fps > 15:
                rows_dbg = trouver_lignes(bgr)
                log(f"{n_fps / (time.time() - t_fps):.1f} lectures/s | lignes du tableau vues : {len(rows_dbg)}"
                    f" | stats lues : {sorted(etat['lignes']) if etat else 'aucune'}"
                    f" | objectif : {'regle' if panneau.conf else 'a regler'}")
                if not etat:
                    cv2.imwrite(os.path.join(ICI, "fm_capture_debug.png"), bgr)
                t_fps, n_fps = time.time(), 0
            if etat:
                vues = etat["lignes"]
                sig = signature(vues)
                # --- meme item ou nouvel item ?
                if sig_item and proche(sig, sig_item) >= .6:
                    n_autre = 0
                    codes = {c[0] for c in sig_item}
                    sig_item |= {c for c in sig if c[0] not in codes}
                else:
                    n_autre += 1
                    if n_autre >= 3:
                        n_autre, sig_item, memo, stable, dernier_rel = 0, set(sig), {}, None, None
                        nom_item = lire_nom_item(bgr, etat["rows"], ocr)
                        connu = panneau.nouvel_item(vues, sig_item, nom_item)
                        nom_item = connu["nom"] if connu else nom_item
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
                achats = liste_achats(etat["lignes"], regl_stock)
                g = GUIDE.etape(bgr, etat, achats, ocr, regl_stock)
                if panneau.conf is None:
                    reco, c = {}, None
                    txt = "NOUVEL ITEM : regle l'objectif dans la fenetre FM"
                else:
                    reco = recommander(etat, panneau.conf, histo)
                    txt = f"{reco['texte']}   | reliquat {rel}"
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
                    c = None if g else case_rune(etat, reco)
                    if c:
                        cv.create_rectangle(*c, outline="#ff3b30" if reco.get("stop") else "#00ff66", width=3)
                    elif "stat" in reco and not g:
                        if reco.get("virtuel"):
                            gab = runes.get(reco["stat"])
                            ou = trouver_rune(bgr, gab, vu_rune.get(reco["stat"])) if gab is not None else None
                            if ou:
                                vu_rune[reco["stat"]] = ou
                                cx, cy, r_ = ou[0] + 17, ou[1] + 8, int(.8 * h)
                                cv.create_rectangle(cx - r_, cy - r_, cx + r_, cy + r_, outline="#00ff66", width=3)
                                txt += "   (exo : rune encadrée dans l'inventaire)"
                            elif gab is None:
                                txt += "   (exo : rune pas encore apprise, bouton « Apprendre la rune »)"
                            else:
                                txt += "   (exo : rune introuvable dans l'inventaire affiché)"
                if g:                               # ravitaillement : le guide remplace le conseil de rune
                    txt, reco, c = g[0], {"texte": g[0], "guide": True}, None
                    if g[1]:
                        cv.create_rectangle(g[1][0] - 26, g[1][1] - 26, g[1][0] + 26, g[1][1] + 26,
                                            outline="#00ff66", width=3)
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
                g = GUIDE.etape(bgr, None, [], ocr)
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
            root.update()
    except KeyboardInterrupt:
        pass
    except tk.TclError:
        pass


def main():
    ap = argparse.ArgumentParser(description="Assistant de forgemagie en direct")
    ap.add_argument("--image")
    ap.add_argument("--ecran", type=int, default=0, help="0 = cherche sur tous les ecrans")
    ap.add_argument("--codes", action="store_true")
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
        mode_direct(a.ecran, ocr, histo)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        log(traceback.format_exc())
        raise
