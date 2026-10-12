#!/usr/bin/env python3
"""Lecture de l'API DofusDB (noms exacts des runes, lignes min/max des items) avec cache local.

Usage : python dofusdb.py runes | python dofusdb.py item "Nom de l'item"
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request

ICI = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(ICI, "fm_dofusdb.json")
API = "https://api.dofusdb.fr"
ENTETES = {"Referer": "FM-assistant (outil perso de forgemagie)", "User-Agent": "FM-assistant"}
VALIDITE = 7 * 86400
TYPE_RUNE = 78

# identifiant d'effet DofusDB -> code de stat de l'assistant
EFFETS = {
    118: "fo", 119: "agi", 123: "cha", 124: "sa", 125: "vi", 126: "int", 111: "pa", 128: "pm", 115: "cri",
    178: "soin", 112: "do", 138: "pui", 220: "renvoi", 117: "po", 182: "invo", 158: "pods", 225: "do_pieges",
    226: "pui_pieges", 174: "ini", 176: "pp", 243: "re_feu", 242: "re_air", 241: "re_eau", 240: "re_terre",
    244: "re_neutre", 213: "re_per_feu", 212: "re_per_air", 210: "re_per_terre", 211: "re_per_eau",
    214: "re_per_neutre", 752: "fuite", 753: "tacle", 160: "esq_pa", 161: "esq_pm", 410: "ret_pa", 412: "ret_pm",
    414: "do_pou", 416: "re_pou", 418: "do_cri", 420: "re_cri", 422: "do_terre", 424: "do_feu", 426: "do_eau",
    428: "do_air", 430: "do_neutre", 2800: "do_per_me", 2804: "do_per_di", 2808: "do_per_ar", 2812: "do_per_so",
    2803: "re_per_me", 2807: "re_per_di",
}


def _get(url):
    req = urllib.request.Request(url, headers=ENTETES)
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def _taille(nom):
    n = nom.lower()
    return "pa" if n.startswith("rune pa ") else "ra" if n.startswith("rune ra ") else "base"


def telecharger_runes():
    """{"stat/taille": "nom exact de la rune"} d'apres l'API."""
    runes, debut = {}, 0
    while True:
        d = _get(f"{API}/items?$limit=50&$skip={debut}&typeId={TYPE_RUNE}&lang=fr")
        for x in d["data"]:
            nom = (x.get("name") or {}).get("fr") or ""
            for e in x.get("possibleEffects") or []:
                code = EFFETS.get(e.get("actionId") or e.get("effectId"))
                if code and nom:
                    runes[f"{code}/{_taille(nom)}"] = nom
                    break
        debut += 50
        if debut >= d["total"] or not d["data"]:
            return runes


def charger(forcer=False):
    """Noms de runes en cache, rafraichis au plus une fois par semaine. Retourne {} si l'API est injoignable."""
    try:
        with open(CACHE, encoding="utf-8") as f:
            c = json.load(f)
    except (OSError, ValueError):
        c = {}
    if forcer or time.time() - c.get("t", 0) > VALIDITE:
        try:
            runes = telecharger_runes()
            if len(runes) > 50:
                c = {"t": time.time(), "runes": runes}
                with open(CACHE, "w", encoding="utf-8") as f:
                    json.dump(c, f, ensure_ascii=False, indent=1)
        except Exception:
            pass
    return c.get("runes", {})


def chercher_item(nom, limite=5):
    """Items dont le nom contient `nom` : [{nom, niveau, lignes: {stat: (min, max)}}]."""
    q = urllib.parse.quote(nom.replace(" ", ".*"))
    d = _get(f"{API}/items?$limit={limite}&lang=fr&name.fr[$regex]={q}&typeId[$ne]={TYPE_RUNE}&$sort[level]=-1")
    out = []
    for x in d.get("data", []):
        lignes = {}
        for e in x.get("possibleEffects") or []:
            code = EFFETS.get(e.get("actionId") or e.get("effectId"))
            if code and e.get("diceSide"):
                lignes[code] = (e.get("diceNum", 0), e.get("diceSide"))
            elif code and e.get("diceNum"):
                lignes[code] = (e["diceNum"], e["diceNum"])
        out.append({"nom": (x.get("name") or {}).get("fr", "?"), "niveau": x.get("level"), "lignes": lignes})
    return out


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) >= 2 and sys.argv[1] == "runes":
        for k, v in sorted(charger(True).items()):
            print(f"{k:<20} {v}")
    elif len(sys.argv) >= 3 and sys.argv[1] == "item":
        for it in chercher_item(" ".join(sys.argv[2:])):
            print(f"{it['nom']} (niv. {it['niveau']})")
            for s, (a, b) in it["lignes"].items():
                print(f"   {s}: {a} à {b}")
    else:
        print(__doc__)
