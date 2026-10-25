"""Confirmation d'effets observes, sans choix de rune ni entree dans le jeu."""
import copy
import math


def signature(etat):
    return tuple(sorted((s, l.get("min"), l.get("max")) for s, l in
                        (etat or {}).get("lignes", {}).items() if l.get("max", 0) > 0))


def stock(etat, stat, taille):
    l = (etat or {}).get("lignes", {}).get(stat, {})
    if l.get("rate", 0) or l.get("occulte"):
        return None
    n = l.get("stock", {}).get(taille)
    if isinstance(n, int) and not isinstance(n, bool) and n >= 0:
        return n
    return 0 if l and taille not in l.get("dispo", []) else None


def valeurs(etat):
    # occulte signale une ligne retrouvee hors detection couleur (survol),
    # pas un echec de lecture de sa valeur. rate signale les valeurs reprises.
    # Les stocks restent refuses sur une ligne occultee dans stock().
    if not etat or any(l.get("rate", 0) for l in etat.get("lignes", {}).values()):
        return None
    if any(not isinstance(l.get("val"), (int, float)) or not math.isfinite(l["val"])
           for l in etat.get("lignes", {}).values()):
        return None
    return (tuple(sorted((s, l.get("val")) for s, l in etat.get("lignes", {}).items())),
            etat.get("reliquat"))


def revalider_fusion(avant, apres, capture, maintenant, selection):
    """Autoriser la fin d'une commande composee seulement sur une vraie relecture."""
    if not isinstance(capture, (int, float)) or not math.isfinite(capture) \
            or not selection < capture <= maintenant or maintenant - capture > 2:
        return False
    if not signature(avant) or signature(avant) != signature(apres):
        return False
    v0, v1 = valeurs(avant), valeurs(apres)
    if v0 is None or v1 is None or v0 != v1:
        return False
    return True


class ConfirmationActions:
    def __init__(self, delai=10.):
        self.delai = delai
        self.attente = None
        self.numero = 0

    def commencer(self, etat, reco, profil, maintenant):
        if self.attente is not None:
            raise RuntimeError("une action attend deja sa confirmation")
        self.numero += 1
        self.attente = dict(id=self.numero, avant=copy.deepcopy(etat),
                            stat=reco.get("stat"), taille=reco.get("taille", "base"),
                            profil=profil, debut=maintenant, capture=None, preuve=None, n=0)
        return self.numero

    def abandonner(self):
        ancienne, self.attente = self.attente, None
        return ancienne

    def observer(self, etat, capture, profil, maintenant):
        a = self.attente
        if a is None:
            return None
        if profil != a["profil"] or etat and signature(etat) != signature(a["avant"]):
            return dict(type="action_ambigue", id=a["id"], motif="item ou profil different")
        preuve = None
        if isinstance(capture, (int, float)) and math.isfinite(capture) \
                and a["debut"] < capture <= maintenant and maintenant - capture <= 2 \
                and (a["capture"] is None or capture > a["capture"]):
            a["capture"] = capture
            avant = stock(a["avant"], a["stat"], a["taille"])
            apres = stock(etat, a["stat"], a["taille"])
            if avant is not None and apres is not None and apres == avant - 1:
                preuve = ("stock_consomme", apres)
            elif avant is not None and apres is not None and apres != avant:
                return dict(type="action_ambigue", id=a["id"], motif="variation de stock inattendue")
            else:
                v0, v1 = valeurs(a["avant"]), valeurs(etat)
                rel_change = v0 is not None and v1 is not None and all(
                    isinstance(v[1], (int, float)) and math.isfinite(v[1]) for v in (v0, v1)) and v0[1] != v1[1]
                if v0 is not None and v1 is not None and (v0[0] != v1[0] or rel_change):
                    # Effet observe, sans pretendre identifier SC/SN/EC.
                    preuve = ("tableau_modifie", v1)
            a["n"] = a["n"] + 1 if preuve is not None and preuve == a["preuve"] else int(preuve is not None)
            a["preuve"] = preuve
            if a["n"] >= 2:
                self.attente = None
                return dict(type="action_confirmee", id=a["id"], preuve=preuve[0])
        if maintenant - a["debut"] >= self.delai:
            return dict(type="action_non_confirmee", id=a["id"], motif="delai depasse sans preuve stable")
        return None


class ConfirmationTransition:
    """Attend une nouvelle etape reconnue du guide, pas un changement de pixels."""
    def __init__(self, delai=15.):
        self.delai = delai
        self.attente = None

    def commencer(self, cle, maintenant):
        if self.attente is not None:
            raise RuntimeError("transition deja en attente")
        self.attente = dict(avant=copy.deepcopy(cle), debut=maintenant, capture=None, preuve=None, n=0)

    def abandonner(self):
        ancienne, self.attente = self.attente, None
        return ancienne

    def observer(self, cle, capture, maintenant):
        a = self.attente
        if a is None:
            return None
        if isinstance(capture, (int, float)) and math.isfinite(capture) \
                and a["debut"] < capture <= maintenant and maintenant - capture <= 2 \
                and (a["capture"] is None or capture > a["capture"]):
            a["capture"] = capture
            preuve = cle if cle is not None and cle != a["avant"] else None
            a["n"] = a["n"] + 1 if preuve is not None and preuve == a["preuve"] else int(preuve is not None)
            a["preuve"] = copy.deepcopy(preuve)
            if a["n"] >= 2:
                self.attente = None
                return dict(type="navigation_confirmee", etape=cle)
        if maintenant - a["debut"] >= self.delai:
            return dict(type="navigation_non_confirmee", motif="etape suivante non reconnue")
        return None
