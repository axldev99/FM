"""Phase de remise en memoire pour la session courante (aucune action)."""


class PhaseRemise:
    def __init__(self):
        self.lourdes = frozenset(("invo", "pa", "pm", "po"))
        self.reinitialiser()

    def reinitialiser(self):
        self.stat = None
        self.item = None

    def conseiller(self, moteur, etat, conf, histo, item):
        if self.item != item:
            self.stat = None
            self.item = item
        if self.stat:
            l = etat["lignes"].get(self.stat)
            if l and l["val"] >= min(conf.get("cibles", {}).get(self.stat, l["max"]), l["max"]):
                self.stat = None
        contexte = dict(conf, _remise_lourde=self.stat)
        reco = moteur(etat, contexte, histo)
        s = reco.get("stat")
        if s in self.lourdes and reco.get("texte", "").startswith("REMETS") \
                and etat["lignes"].get(s, {}).get("max", 0) > 0:
            self.stat = s
        return reco
