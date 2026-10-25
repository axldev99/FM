"""Tests hors jeu : aucun import de l'assistant ni appel aux API Windows."""
import ast
import pathlib
import unittest
from types import SimpleNamespace

import activer_clics
from fm_securite import motif_blocage, executable_dofus

ROOT = pathlib.Path(__file__).resolve().parent


class SecuriteTests(unittest.TestCase):
    def test_identite_processus(self):
        self.assertTrue(executable_dofus(r"C:\Ankama\Dofus.exe"))
        self.assertTrue(executable_dofus(r"C:\Jeux\DOFUS UNITY.EXE"))
        self.assertFalse(executable_dofus(r"C:\Dofus\notepad.exe"))
        self.assertFalse(executable_dofus(r"C:\Jeux\DofusLauncher.exe"))

    def test_conditions(self):
        base = dict(automatique=True, dofus_actif=True, capture=99., maintenant=100.)
        self.assertIsNone(motif_blocage(**base))
        for changements in ({"stop": True}, {"automatique": False},
                             {"dofus_actif": False}, {"capture": None},
                             {"capture": 97.9}, {"capture": 101.},
                             {"capture": float("nan")}):
            with self.subTest(changements=changements):
                self.assertIsNotNone(motif_blocage(**dict(base, **changements)))

    def test_generation_et_idempotence(self):
        source = (ROOT / "assistant_sans_clic.py").read_text(encoding="utf-8")
        genere, _ = activer_clics.patch(source)
        compile(genere, "fm_avec_clics.py", "exec")
        self.assertEqual(activer_clics.patch(genere), (genere, False))
        self.assertEqual(genere, (ROOT / "fm_avec_clics.py").read_text(encoding="utf-8"))

    def test_actions_bloquees_sans_api_windows(self):
        source, _ = activer_clics.patch(
            (ROOT / "assistant_sans_clic.py").read_text(encoding="utf-8"))
        arbre = ast.parse(source)
        noms = {"cliquer_case", "clic_point", "tenter_exo", "touche", "ctrl_a", "taper_texte"}
        fonctions = {n.name: n for n in ast.walk(arbre)
                     if isinstance(n, ast.FunctionDef) and n.name in noms}
        self.assertEqual(set(fonctions), noms)
        for nom, args in {"cliquer_case": [(0, 0, 10, 10)], "clic_point": [1, 1],
                          "tenter_exo": [None, None], "touche": [13],
                          "ctrl_a": [], "taper_texte": ["abc"]}.items():
            with self.subTest(action=nom):
                ns = {"action_autorisee": lambda **kw: False}
                exec(compile(ast.Module(body=[fonctions[nom]], type_ignores=[]),
                             "action_isolee", "exec"), ns)
                # L'absence de ctypes est volontaire : toute injection ferait echouer le test.
                self.assertFalse(ns[nom](*args))

    def test_crochets_fm_respectent_stop(self):
        source, _ = activer_clics.patch(
            (ROOT / "assistant_sans_clic.py").read_text(encoding="utf-8"))
        self.assertEqual(source.count('and not reco.get("stop") and n_vu >= 2'), 2)
        self.assertIn('securite["capture"] = securite["lecture"] = t_capture', source)

    def test_controle_central(self):
        arbre = ast.parse("def runtime():\n" + activer_clics.RUNTIME_SECURITE)
        fonction = next(n for n in ast.walk(arbre)
                        if isinstance(n, ast.FunctionDef) and n.name == "action_autorisee")
        ns = dict(motif_blocage=motif_blocage,
                  verifier_mode_clic=lambda: None,
                  panneau=SimpleNamespace(mode=SimpleNamespace(get=lambda: "automatique")),
                  dofus_actif=lambda: True,
                  securite={"capture": 99., "lecture": 99., "motif": None},
                  mesures_securite={"blocages": {}},
                  diagnostic=SimpleNamespace(evenement=lambda *a, **kw: None),
                  confirmation=SimpleNamespace(attente=None),
                  confirmation_navigation=SimpleNamespace(attente=None),
                  time=SimpleNamespace(monotonic=lambda: 100.), reco={}, log=lambda _: None)
        exec(compile(ast.Module(body=[fonction], type_ignores=[]), "controle", "exec"), ns)
        self.assertTrue(ns["action_autorisee"](fm=True))
        ns["reco"]["stop"] = True
        self.assertFalse(ns["action_autorisee"](fm=True))
        self.assertFalse(ns["action_autorisee"]())

        ns["reco"].clear()
        ns["securite"]["lecture"] = 95.
        self.assertFalse(ns["action_autorisee"](fm=True))
        self.assertTrue(ns["action_autorisee"]())
        ns["dofus_actif"] = lambda: False
        self.assertFalse(ns["action_autorisee"]())

    def test_confirmation_en_attente_bloque_toutes_les_entrees(self):
        arbre = ast.parse("def runtime():\n" + activer_clics.RUNTIME_SECURITE)
        fn = next(n for n in ast.walk(arbre) if isinstance(n, ast.FunctionDef) and n.name == "action_autorisee")
        for rune, navigation in [(True,False),(False,True)]:
            ns = dict(verifier_mode_clic=lambda:None,
                      confirmation=SimpleNamespace(attente={} if rune else None),
                      confirmation_navigation=SimpleNamespace(attente={} if navigation else None))
            exec(compile(ast.Module(body=[fn], type_ignores=[]), "controle_attente", "exec"), ns)
            self.assertFalse(ns["action_autorisee"]())
            self.assertFalse(ns["action_autorisee"](fm=True))



if __name__ == "__main__":
    unittest.main()
