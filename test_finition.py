"""Finition d'un jet naturel, apres les objectifs principaux uniquement."""
import ast
import copy
import json
import unittest

from test_fm_reference import ROOT, charger_moteur, ligne, observer


class FinitionTests(unittest.TestCase):
    def test_prospection_bonus_et_maximum_naturel(self):
        for fichier in ("assistant_sans_clic.py", "fm_avec_clics.py"):
            m = charger_moteur(fichier)
            conf = {"cibles": {"fo": 20, "pp": 10}, "finition": "pp"}
            for pp, rel, taille in [(12, 9, "pa"), (19, 9, "base"), (18, 9, "base")]:
                with self.subTest(moteur=fichier, pp=pp):
                    r = observer(m, {"fo": ligne(20, 20), "pp": ligne(pp, 20, dispo=("base", "pa"))}, conf, rel)
                    self.assertEqual((r["stat"], r["taille"]), ("pp", taille))
                    self.assertTrue(r["texte"].startswith("FINITION RELIQUAT"))
                    self.assertLessEqual(m["pds"]("pp", m["qte"]("pp", taille)), rel)
                    self.assertLessEqual(pp + m["qte"]("pp", taille), 20)

    def test_pas_de_puits_ou_stock_ou_bonus_au_max(self):
        for fichier in ("assistant_sans_clic.py", "fm_avec_clics.py"):
            for pp, rel, dispo in [(12, 0, ("base",)), (12, 2.9, ("base",)),
                                   (12, 9, ()), (20, 9, ("base", "pa"))]:
                m = charger_moteur(fichier)
                r = observer(m, {"fo": ligne(20, 20), "pp": ligne(pp, 20, dispo=dispo)},
                             {"cibles": {"pp": 10}, "finition": "pp"}, rel)
                self.assertNotIn("stat", r)
                self.assertTrue(r["texte"].startswith("OBJECTIF ATTEINT"))

    def test_bonus_ne_supprime_pas_objectif_ni_carburant(self):
        for fichier in ("assistant_sans_clic.py", "fm_avec_clics.py"):
            m = charger_moteur(fichier)
            # PP 10 obligatoire reste a remonter, meme avec PP choisie en bonus.
            r = observer(m, {"fo": ligne(20, 20), "pp": ligne(0, 20)},
                         {"cibles": {"pp": 10}, "finition": "pp"}, 9)
            self.assertEqual(r["stat"], "pp")
            self.assertFalse(r["texte"].startswith("FINITION RELIQUAT"))
            m = charger_moteur(fichier)
            # Si PP est jetable dans le profil, son role de carburant reste intact.
            r = observer(m, {"fo": ligne(1, 100, dispo=("base", "pa", "ra")), "pp": ligne(0, 20)},
                         {"cibles": {"pp": 0}, "finition": "pp"}, 0)
            self.assertEqual(r["stat"], "pp")
            self.assertTrue(r["texte"].startswith("CARBURANT"))
            self.assertIn("pp", m["_EN_REMONTEE"])

    def test_bonus_attend_tout_le_jet_principal(self):
        for fichier in ("assistant_sans_clic.py", "fm_avec_clics.py"):
            m = charger_moteur(fichier)
            r = observer(m, {"fo": ligne(19, 20), "pp": ligne(10, 20)},
                         {"cibles": {"fo": 20, "pp": 10}, "finition": "pp"}, 9)
            self.assertEqual(r["stat"], "fo")
            self.assertFalse(r["texte"].startswith("FINITION RELIQUAT"))

    def test_pas_de_bonus_sur_exo_ou_over_pose(self):
        for fichier in ("assistant_sans_clic.py", "fm_avec_clics.py"):
            for supplement in ({"do_per_so": ligne(1, 0)}, {"fo": ligne(21, 20)}):
                m = charger_moteur(fichier)
                lignes = dict({"fo": ligne(20, 20), "pp": ligne(12, 20)}, **supplement)
                r = observer(m, lignes, {"finition": "pp"}, 9)
                self.assertFalse(r["texte"].startswith("FINITION RELIQUAT"))

    def test_minimum_seul_ne_declenche_pas_finition(self):
        m = charger_moteur()
        r = observer(m, {"fo": ligne(15, 20), "pp": ligne(12, 20)},
                     {"cibles": {"fo": 20}, "mins": {"fo": 15}, "finition": "pp"}, 9)
        self.assertFalse(r["texte"].startswith("FINITION RELIQUAT"))

    def test_option_non_configuree_comportement_conserve(self):
        m = charger_moteur()
        r = observer(m, {"fo": ligne(20, 20), "pp": ligne(12, 20)}, {}, 9)
        self.assertEqual(r["stat"], "pp")
        self.assertFalse(r["texte"].startswith("FINITION RELIQUAT"))

    def test_configuration_persistable_et_transmise(self):
        # Extraire uniquement _conf : aucun Tk ni demarrage de l'application.
        for fichier in ("assistant_sans_clic.py", "fm_avec_clics.py"):
            arbre = ast.parse((ROOT / fichier).read_text(encoding="utf-8"))
            classe = next(n for n in arbre.body if isinstance(n, ast.ClassDef) and n.name == "Panneau")
            classe.body = [n for n in classe.body if isinstance(n, ast.FunctionDef) and n.name in ("_conf", "_conf_base")]
            ns = {}
            exec(compile(ast.Module(body=[classe], type_ignores=[]), "configuration", "exec"), ns)
            profil = {"cibles": {"pp": 20}, "finition": "pp"}
            avant = copy.deepcopy(profil)
            self.assertEqual(ns["Panneau"]._conf(json.loads(json.dumps(profil)))["finition"], "pp")
            self.assertEqual(profil, avant)


if __name__ == "__main__":
    unittest.main()
