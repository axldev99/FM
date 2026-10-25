import copy
import json
import unittest

from fm_phases import PhaseRemise
from test_fm_reference import ROOT, charger_moteur, observer, ligne


class ExoPuitsTests(unittest.TestCase):
    def test_tourthon_rejoue_puits_98_puis_remise_pa(self):
        cas = json.loads((ROOT / "tests_tourthon_puits.json").read_text(encoding="utf-8"))
        for fichier in ("assistant_sans_clic.py", "fm_avec_clics.py"):
            m = charger_moteur(fichier)
            ls, conf = copy.deepcopy(cas["lignes"]), cas["conf"]
            for rel in (98.2,83.2,68.2,15):
                with self.subTest(fichier=fichier,rel=rel):
                    r = observer(m,ls,conf,rel)
                    self.assertEqual((r["stat"],r["taille"]),("do_per_so","base"))
                    self.assertTrue(r["virtuel"])
            self.assertEqual(observer(m,ls,conf,14.9)["stat"],"pa")
            ls["do_per_so"] = ligne(1,0)
            r = observer(m,ls,conf,83.2)
            self.assertEqual(r["stat"],"pa")
            ls["pa"]["val"] = 1
            # Cas d'un SN ayant abime les lignes pendant la sequence.
            ls["do_neutre"]["val"], ls["do_terre"]["val"] = 18,19
            r = observer(m,ls,conf,0)
            self.assertFalse(r["texte"].startswith("OBJECTIF ATTEINT"))
            self.assertTrue(r["stop"])
            ls["do_neutre"]["val"] = ls["do_terre"]["val"] = 20
            self.assertTrue(observer(m,ls,conf,0)["texte"].startswith("OBJECTIF ATTEINT"))

    def test_premier_pourcent_sn_repare_jet_et_sarrete_aux_minima(self):
        for fichier in ("assistant_sans_clic.py", "fm_avec_clics.py"):
            m = charger_moteur(fichier)
            self.assertGreater(m["probas"]({},"do_per_so","base",ligne(0,0))[0][1],0)
            self.assertEqual(m["probas"]({},"do_per_so","base",ligne(1,0))[0][1],0)
            conf = {"exos":{"do_per_so":1},"cibles":{"fo":100},"mins":{"fo":98}}
            ls = {"do_per_so":ligne(1,0),"fo":ligne(90,100,81,("base","pa","ra"))}
            self.assertEqual(observer(m,ls,conf,50)["stat"],"fo")
            ls["fo"]["val"] = 98
            self.assertTrue(observer(m,ls,conf,50)["texte"].startswith("OBJECTIF ATTEINT"))

    def test_premier_pourcent_jet_bloque_ne_declenche_pas_carburant(self):
        for fichier in ("assistant_sans_clic.py", "fm_avec_clics.py"):
            m = charger_moteur(fichier)
            ls = {"do_per_so":ligne(1,0),"do_terre":ligne(18,20,16,("base","pa")),
                  "pp":ligne(5,15,11,("base","pa"))}
            conf = {"exos":{"do_per_so":1},"cibles":{"pp":0},
                    "regles":{"do_terre":{"base":[0,16],"pa":[17,17]}}}
            r = observer(m,ls,conf,20)
            self.assertNotIn("stat",r)
            self.assertTrue(r["stop"])
            self.assertTrue(r["texte"].startswith("JET A REPRENDRE"))

    def test_quatre_lignes_structurelles_et_puits_superieur_a_leur_rune(self):
        for fichier in ("assistant_sans_clic.py", "fm_avec_clics.py"):
            m = charger_moteur(fichier)
            for stat in ("pa","pm","po","invo"):
                ls = {stat:ligne(0,1,1),"fo":ligne(100,100,81)}
                conf = {"exos":{"do_per_so":1}}
                self.assertEqual(observer(m,ls,conf,120)["stat"],"do_per_so")
                self.assertEqual(observer(m,ls,conf,0)["stat"],stat)
                # Aucun changement de la strategie historique pour deux %.
                self.assertEqual(observer(m,ls,{"exos":{"do_per_so":2}},0)["stat"],stat)

    def test_ne_declenche_pas_sur_dommages_et_remontee_utile_avant_exo(self):
        for fichier in ("assistant_sans_clic.py", "fm_avec_clics.py"):
            m = charger_moteur(fichier)
            self.assertEqual(observer(m,{"do":ligne(9,10,6)}, {"exos":{"do_per_so":1}},98)["stat"],"do")
            ls = {"pa":ligne(0,1,1),"fo":ligne(50,100,81,("base","pa","ra"))}
            self.assertEqual(observer(m,ls,{"exos":{"do_per_so":1}},98)["stat"],"fo")

    def test_verrou_non_engage_pendant_exo_et_insiste_apres_remise(self):
        for fichier in ("assistant_sans_clic.py", "fm_avec_clics.py"):
            m = charger_moteur(fichier)
            phase = PhaseRemise()
            ls = {"pa":dict(ligne(0,1,1),nom="PA"),"fo":dict(ligne(100,100,81),nom="Force")}
            e = {"lignes":ls,"reliquat":98}
            conf = {"exos":{"do_per_so":1}}
            self.assertEqual(phase.conseiller(m["recommander"],e,conf,{},"A")["stat"],"do_per_so")
            self.assertIsNone(phase.stat)
            e["reliquat"] = 8
            self.assertEqual(phase.conseiller(m["recommander"],e,conf,{},"A")["stat"],"pa")
            self.assertEqual(phase.stat,"pa")
            e["reliquat"] = 98
            self.assertEqual(phase.conseiller(m["recommander"],e,conf,{},"A")["stat"],"pa")


if __name__ == "__main__":
    unittest.main()
