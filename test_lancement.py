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
        self.assertIn("python activer_clics.py assistant_sans_clic.py", texte)
        self.assertIn("python fm_avec_clics.py %*", texte)
        self.assertLess(texte.index("if errorlevel 1"), texte.index("python fm_avec_clics.py"))


if __name__ == "__main__":
    unittest.main()
