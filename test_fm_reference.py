"""Caracterisation du moteur actuel, sans OCR, interface, fichiers metier ou clics.

Ces attentes preservent le comportement observe ; elles ne prouvent pas les
probabilites ou les mecaniques du jeu. Les sequences partagent l'etat du moteur.
"""
import ast
import copy
import difflib
import json
import pathlib
import re
import unicodedata
import unittest

ROOT = pathlib.Path(__file__).resolve().parent


def charger_moteur(nom="assistant_sans_clic.py"):
    arbre = ast.parse((ROOT / nom).read_text(encoding="utf-8"))
    debut = next(n.lineno for n in arbre.body if isinstance(n, ast.Assign)
                 and any(isinstance(t, ast.Name) and t.id == "ELEMS" for t in n.targets))
    fin = next(n.lineno for n in arbre.body if isinstance(n, ast.Assign)
               and any(isinstance(t, ast.Name) and t.id == "_ALGO" for t in n.targets))
    fonctions = {"recommander", "nom_code", "nom_rune"}
    noeuds = [n for n in arbre.body if
              (debut <= n.lineno < fin and not isinstance(n, ast.FunctionDef))
              or (isinstance(n, ast.FunctionDef) and
                  (debut <= n.lineno < fin and n.name != "histo_depuis_passes"
                   or n.name in fonctions))]
    ns = dict(re=re, difflib=difflib, unicodedata=unicodedata,
              PETITS_EXOS=("agi", "fo", "int", "cha", "ini"), RUNES_APPRISES=set())
    exec(compile(ast.Module(body=noeuds, type_ignores=[]), nom, "exec"), ns)
    return ns


def ligne(val, maxi, mini=0, dispo=("base",)):
    return dict(val=val, max=maxi, min=mini, dispo=list(dispo))


def observer(moteur, lignes, conf, rel=0, histo=None):
    etat = {"lignes": copy.deepcopy(lignes), "reliquat": rel}
    for s, l in etat["lignes"].items():
        l["nom"] = moteur["nom_code"](s)
    return moteur["recommander"](etat, copy.deepcopy(conf), copy.deepcopy(histo or {}))


SCENARIOS = {
    "remontee_simple": ({"fo": ligne(5, 20)}, {"cibles": {"fo": 20}}, 0),
    "objectif_naturel_atteint": ({"fo": ligne(20, 20)}, {"cibles": {"fo": 20}}, 0),
    "stock_epuise": ({"fo": ligne(5, 20, dispo=())}, {"cibles": {"fo": 20}}, 0),
    "remise_pa_avec_puits": ({"pa": ligne(0, 1), "fo": ligne(10, 20)}, {}, 100),
    "remise_pa_sans_puits": ({"pa": ligne(0, 1), "fo": ligne(10, 20)}, {}, 0),
    "exo_virtuel": ({"fo": ligne(20, 20)}, {"exos": {"po": 1}}, 0),
    "gros_exo_pose_jet_incomplet": ({"po": ligne(1, 0), "fo": ligne(5, 20)}, {"exos": {"po": 1}}, 0),
    "deuxieme_pourcent": ({"fo": ligne(20, 20), "do_per_so": ligne(1, 0)}, {"exos": {"do_per_so": 2}}, 0),
    "exo_atteint": ({"fo": ligne(20, 20), "do_per_so": ligne(2, 0)}, {"exos": {"do_per_so": 2}}, 0),
    "bonus_over": ({"vi": ligne(440, 350, dispo=("base", "pa", "ra"))}, {"cibles": {"vi": 440}}, 10),
    "over_atteint_sans_puits": ({"vi": ligne(440, 350, dispo=("base", "pa", "ra"))}, {"cibles": {"vi": 440}}, 0),
    "malus": ({"ini": ligne(-350, -400, -301)}, {"cibles": {"ini": -301}}, 0),
    "petit_exo_avant_po": ({"fo": ligne(20, 20)}, {"exos": {"po": 1}, "petit_exo": "agi"}, 2),
    "plan_b": ({"vi": ligne(360, 350, dispo=("base", "pa", "ra"))}, {"cibles": {"vi": 440}, "mins": {"vi": 435}, "plan_b": "po"}, 0),
    "over_parasite": ({"fo": ligne(25, 20), "agi": ligne(10, 20)}, {}, 0),
    "carburant_bas": ({"fo": ligne(1, 100, dispo=("base", "pa", "ra")), "agi": ligne(0, 100)}, {"cibles": {"fo": 100, "agi": 0}}, 0),
    "minimum_avant_exo": ({"fo": ligne(15, 20)}, {"cibles": {"fo": 20}, "mins": {"fo": 15}, "exos": {"po": 1}}, 0),
}


class ReferenceFMTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reference = json.loads((ROOT / "tests_fm_reference.json").read_text(encoding="utf-8"))

    def test_decisions_de_reference(self):
        self.assertEqual(set(SCENARIOS), set(self.reference["decisions"]))
        for fichier in ("assistant_sans_clic.py", "fm_avec_clics.py"):
            for nom, (lignes, conf, rel) in SCENARIOS.items():
                with self.subTest(moteur=fichier, scenario=nom):
                    moteur = charger_moteur(fichier)
                    self.assertEqual(observer(moteur, lignes, conf, rel),
                                     self.reference["decisions"][nom])

    def test_cycle_remontee_persistant_entre_decisions(self):
        conf = {"cibles": {"fo": 20}, "mins": {"fo": 10},
                "remonte": {"fo": 18}, "exos": {"po": 1}}
        for fichier in ("assistant_sans_clic.py", "fm_avec_clics.py"):
            moteur = charger_moteur(fichier)
            for val, stat, cycle in [(9, "fo", True), (10, "fo", True),
                                     (17, "fo", True), (18, "po", False),
                                     (12, "po", False), (9, "fo", True)]:
                with self.subTest(moteur=fichier, valeur=val, cycle=cycle):
                    reco = observer(moteur, {"fo": ligne(val, 20)}, conf)
                    self.assertEqual(reco["stat"], stat)
                    self.assertEqual(moteur["_CYCLE"][0], cycle)

    def test_minimum_ne_declenche_pas_un_cycle_a_froid(self):
        moteur = charger_moteur()
        conf = {"cibles": {"fo": 20}, "mins": {"fo": 10},
                "remonte": {"fo": 18}, "exos": {"po": 1}}
        self.assertEqual(observer(moteur, {"fo": ligne(10, 20)}, conf)["stat"], "po")
        self.assertFalse(moteur["_CYCLE"][0])

    def test_sequence_carburant_et_seuils(self):
        for fichier in ("assistant_sans_clic.py", "fm_avec_clics.py"):
            moteur = charger_moteur(fichier)
            conf = {"cibles": {"fo": 100, "agi": 0}}
            for val, stat, suivie in [(0, "agi", True), (30, "fo", True),
                                      (50, "fo", False), (30, "fo", False),
                                      (0, "agi", True)]:
                with self.subTest(moteur=fichier, valeur=val, suivie=suivie):
                    reco = observer(moteur, {"fo": ligne(1, 100, dispo=("base", "pa", "ra")),
                                             "agi": ligne(val, 100)}, conf)
                    self.assertEqual(reco["stat"], stat)
                    self.assertEqual("agi" in moteur["_EN_REMONTEE"], suivie)

    def test_exo_entame_interrompt_cycle_complet(self):
        for fichier in ("assistant_sans_clic.py", "fm_avec_clics.py"):
            moteur = charger_moteur(fichier)
            conf = {"cibles": {"fo": 20}, "mins": {"fo": 10},
                    "remonte": {"fo": 18}, "exos": {"do_per_so": 2}}
            observer(moteur, {"fo": ligne(9, 20)}, conf)
            self.assertTrue(moteur["_CYCLE"][0])
            reco = observer(moteur, {"fo": ligne(10, 20),
                                     "do_per_so": ligne(1, 0)}, conf)
            self.assertFalse(moteur["_CYCLE"][0])
            self.assertEqual(reco["stat"], "do_per_so")

    def test_arrets_et_runes_virtuelles(self):
        r = self.reference["decisions"]
        for nom in ("objectif_naturel_atteint", "gros_exo_pose_jet_incomplet",
                    "exo_atteint", "over_atteint_sans_puits"):
            self.assertNotIn("stat", r[nom])
            self.assertTrue(r[nom]["texte"].startswith("OBJECTIF ATTEINT"))
        self.assertEqual(r["exo_virtuel"]["stat"], "po")
        self.assertTrue(r["exo_virtuel"]["virtuel"])
        self.assertTrue(r["plan_b"]["texte"].startswith("PLAN B"))
        self.assertTrue(r["stock_epuise"]["texte"].startswith("A ACHETER"))

    def test_invariants_mecaniques_et_probas(self):
        m = charger_moteur()
        self.assertEqual(m["qte"]("vi", "ra"), 50)
        self.assertEqual(m["pds"]("vi", 50), 10)
        self.assertEqual(m["palier"]("fo", "pa"), 60)
        self.assertEqual(m["plafond"]("vi"), 505)
        self.assertEqual(m["tailles"]("po"), ["base"])
        self.assertEqual(m["tailles"]("tacle"), ["base", "pa"])
        for stat, val, maxi, ctx in [("po", 0, 0, "exo+"),
                                     ("do_per_so", 0, 0, "exo"),
                                     ("do_per_so", 1, 0, "exo+"),
                                     ("ini", -350, -400, "malus")]:
            l = ligne(val, maxi)
            self.assertEqual(m["contexte"](stat, "base", l), ctx)
            probas, _ = m["probas"]({}, stat, "base", l)
            self.assertAlmostEqual(sum(probas), 1.)
            if ctx == "exo+":
                self.assertEqual(probas, [.01, 0., .99])

    def test_apprentissage_et_parite_des_bases(self):
        a, b = charger_moteur(), charger_moteur("fm_avec_clics.py")
        histo = {"b0": [20, 5, 5], "fo|b0": [10, 2, 3]}
        l = ligne(5, 20)
        self.assertNotEqual(a["probas"]({}, "fo", "base", l),
                            a["probas"](histo, "fo", "base", l))
        for _, (lignes, conf, rel) in SCENARIOS.items():
            self.assertEqual(observer(a, lignes, conf, rel, histo),
                             observer(b, lignes, conf, rel, histo))

    def test_entrees_non_modifiees(self):
        m = charger_moteur()
        etat = {"lignes": {"fo": dict(ligne(5, 20), nom="Force")}, "reliquat": 0}
        conf, histo = {"cibles": {"fo": 20}}, {"b0": [10, 5, 2]}
        avant = copy.deepcopy((etat, conf, histo))
        m["recommander"](etat, conf, histo)
        self.assertEqual((etat, conf, histo), avant)



    def test_invo_aucune_depense_sur_jetable_ou_stock_absent(self):
        for fichier in ("assistant_sans_clic.py", "fm_avec_clics.py"):
            for dispo, cible in [((), 15), (("base",), 0)]:
                m = charger_moteur(fichier)
                r = observer(m, {"invo": ligne(0, 1), "do_air": ligne(13, 15, dispo=dispo)},
                             {"cibles": {"do_air": cible}}, 9.2)
                self.assertEqual(r["stat"], "invo")

    def test_premier_pourcent_remet_invo_puis_tente_deuxieme(self):
        conf = {"cibles": {"invo": 1, "do_air": 15},
                "mins": {"do_air": 13}, "exos": {"do_per_so": 2},
                "regles": {"do_air": {"base": [0, 11], "pa": [12, 12]}}}
        for fichier in ("assistant_sans_clic.py", "fm_avec_clics.py"):
            m = charger_moteur(fichier)
            lignes = {"invo": ligne(0, 1), "do_air": ligne(13, 15),
                      "do_per_so": ligne(1, 0)}
            # Meme avec assez de puits pour Do air, le 1er % interdit ce bonus.
            r = observer(m, lignes, conf, 9.2)
            self.assertEqual(r["stat"], "invo")
            lignes["invo"]["val"] = 1
            r = observer(m, lignes, conf, 0)
            self.assertEqual(r["stat"], "do_per_so")
            lignes["do_per_so"]["val"] = 2
            r = observer(m, lignes, conf, 0)
            self.assertNotIn("stat", r)
            self.assertTrue(r["texte"].startswith("OBJECTIF ATTEINT"))


    def test_premier_pourcent_protege_avec_toutes_lourdes(self):
        for fichier in ("assistant_sans_clic.py", "fm_avec_clics.py"):
            for lourde in ("do", "invo", "po", "pm", "pa"):
                with self.subTest(moteur=fichier, lourde=lourde):
                    m = charger_moteur(fichier)
                    conf = {"mins": {"do_air": 13}, "exos": {"do_per_so": 2}}
                    ls = {lourde: ligne(0, 1), "do_air": ligne(13, 15), "do_per_so": ligne(1, 0)}
                    self.assertEqual(observer(m, ls, conf, 9.2)["stat"], lourde)
                    ls[lourde]["val"] = 1
                    self.assertEqual(observer(m, ls, conf, 0)["stat"], "do_per_so")

    def test_seuil_lourd_20_inclus(self):
        for fichier in ("assistant_sans_clic.py", "fm_avec_clics.py"):
            m = charger_moteur(fichier)
            self.assertEqual(m["POIDS"]["do"], m["LOURD"])
            self.assertEqual({s for s, poids in m["POIDS"].items() if poids >= m["LOURD"]},
                             {"do", "invo", "po", "pm", "pa"})

    def test_petit_reliquat_pas_de_vi_simple_hors_palier(self):
        for fichier in ("assistant_sans_clic.py", "fm_avec_clics.py"):
            for pm, do, rel in [(0, 10, 1.8), (1, 9, 2.6)]:
                with self.subTest(moteur=fichier, pm=pm, rel=rel):
                    m = charger_moteur(fichier)
                    r = observer(m, {"vi": ligne(267, 300, 251, ("base", "pa", "ra")),
                                     "pm": ligne(pm, 1), "do": ligne(do, 10)},
                                 {"cibles": {"vi": 297}, "regles": {"vi": {"pa": [0, 285]}}}, rel)
                    self.assertNotEqual((r.get("stat"), r.get("taille")), ("vi", "base"))
                    self.assertEqual(r["stat"], "pm" if pm == 0 else "do")


    def test_ra_finition_pas_sans_budget_ni_avec_exo(self):
        for fichier in ("assistant_sans_clic.py", "fm_avec_clics.py"):
            for rel, exo in [(9, False), (30, True)]:
                m = charger_moteur(fichier)
                ls = {"cha": ligne(65, 70, 51, ("base", "pa", "ra")),
                      "vi": ligne(267, 300, 251, ("base", "pa", "ra")), "pm": ligne(0, 1)}
                conf = {"cibles": {"cha": 70, "vi": 297}, "regles": {"cha": {"ra": [35, 60]}}}
                if exo:
                    ls["do_per_so"] = ligne(1, 0)
                    conf["exos"] = {"do_per_so": 2}
                r = observer(m, ls, conf, rel)
                self.assertFalse(r["texte"].startswith("FINIS LA CARAC"))



if __name__ == "__main__":
    unittest.main()
