"""Selection de source et echec de lancement, sans demarrer le bot."""
import contextlib
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import activer_clics


class LancementTests(unittest.TestCase):
    def test_source_stable_meme_si_sauvegarde_plus_recente(self):
        with tempfile.TemporaryDirectory() as tmp:
            dossier = Path(tmp)
            source = dossier / "assistant_sans_clic.py"
            ancienne = dossier / "assistant_sans_clic_avant_ui.py"
            source.write_text("def mode_direct(): pass", encoding="utf-8")
            ancienne.write_text("def mode_direct(): pass", encoding="utf-8")
            os.utime(source, (1, 1))
            os.utime(ancienne, (2, 2))
            self.assertEqual(activer_clics.choisir_source(dossier), source)

    def test_source_absente_aucun_repli_sur_sauvegarde(self):
        with tempfile.TemporaryDirectory() as tmp:
            dossier = Path(tmp)
            (dossier / "assistant_sans_clic_avant_ui.py").write_text(
                "def mode_direct(): pass", encoding="utf-8")
            source = activer_clics.choisir_source(dossier)
            self.assertEqual(source.name, "assistant_sans_clic.py")
            self.assertFalse(source.exists())

    def test_chemin_explicite_conserve(self):
        chemin = Path("assistant_sans_clic_avant_ui.py")
        self.assertEqual(activer_clics.choisir_source(Path("autre"), str(chemin)), chemin.resolve())

    def test_echec_source_ne_touche_pas_sortie(self):
        with tempfile.TemporaryDirectory() as tmp:
            dossier = Path(tmp)
            sortie = dossier / activer_clics.SORTIE
            sortie.write_text("sortie precedente", encoding="utf-8")
            with mock.patch.object(activer_clics, "__file__", str(dossier / "activer_clics.py")), \
                 mock.patch("sys.argv", ["activer_clics.py"]), \
                 contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(activer_clics.main(), 1)
            self.assertEqual(sortie.read_text(encoding="utf-8"), "sortie precedente")

    def test_lanceur_source_et_transmission_arguments(self):
        texte = Path(__file__).with_name("lancer_assistant.bat").read_text(encoding="utf-8")
        self.assertIn("%FM_PYTHON% activer_clics.py assistant_sans_clic.py", texte)
        self.assertIn("%FM_PYTHON% fm_avec_clics.py %*", texte)
        self.assertLess(texte.index("if errorlevel 1"), texte.index("%FM_PYTHON% fm_avec_clics.py"))

    def test_python_313_64bits_verifie_avant_generation(self):
        texte=Path(__file__).with_name('lancer_assistant.bat').read_text(encoding='utf8')
        avant=texte.split('%FM_PYTHON% activer_clics.py',1)[0]
        self.assertIn('py -3.13 -c',avant)
        self.assertIn('python -c',avant)
        self.assertEqual(avant.count("sys.version_info[:2] == (3,13) and struct.calcsize('P') == 8"),2)
        self.assertIn('if not defined FM_PYTHON (',avant)
        self.assertIn('exit /b 1',avant)

    def test_precontrole_refuse_python_315_et_32bits(self):
        import builtins,re
        from types import SimpleNamespace
        texte=Path(__file__).with_name('lancer_assistant.bat').read_text(encoding='utf8')
        controles=re.findall(r'-c "([^"]+)"',texte)
        self.assertEqual(len(controles),2)
        def terminer(code):raise SystemExit(code)
        for controle in controles:
            for version,bits,attendu in [((3,13,17),64,0),((3,15,1),64,1),((3,13,17),32,1),((3,12,8),64,1)]:
                modules={'sys':SimpleNamespace(version_info=version,exit=terminer),
                         'struct':SimpleNamespace(calcsize=lambda _,b=bits:b//8)}
                ns={'__builtins__':dict(vars(builtins),__import__=lambda nom,*a:modules[nom])}
                with self.assertRaises(SystemExit) as fin:exec(controle,ns)
                self.assertEqual(fin.exception.code,attendu)


if __name__ == "__main__":
    unittest.main()
