import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest import mock
from types import SimpleNamespace

from fm_diagnostic import Diagnostic, resume_observation

ROOT = Path(__file__).resolve().parent


class DiagnosticTests(unittest.TestCase):
    def test_correlation_et_donnees_figees(self):
        lignes = []
        with mock.patch.object(Diagnostic, "_ecrire", side_effect=lambda ligne, im, nom: lignes.append(ligne)):
            d = Diagnostic("inutilise")
            etat = {"lignes": {"fo": {"val": 5, "rate": 2}}, "reliquat": 3}
            d.observation(etat, time.monotonic())
            d.decision({"stat": "fo", "taille": "base"}, etat, "automatique", .3)
            decision_id = d.decision_id
            d.action_envoyee("rune", stat="fo")
            d.evenement("passe_inferee", resultat="SC")
            etat["lignes"]["fo"]["val"] = 99
            d.fermer()
        events = [json.loads(l) for l in lignes]
        self.assertEqual(len({e["session"] for e in events}), 1)
        self.assertEqual(len({e["capture_id"] for e in events}), 1)
        self.assertEqual(events[2]["decision_id"], decision_id)
        self.assertEqual(events[3]["action_id"], events[2]["id"])
        self.assertEqual(events[0]["donnees"]["observation"]["lignes"]["fo"]["val"], 5)
        self.assertIsNone(events[0]["donnees"]["observation"]["confiance_ocr"])

    def test_panne_disque_ne_remonte_pas(self):
        with mock.patch.object(Diagnostic, "_ecrire", side_effect=OSError("disque indisponible")):
            d = Diagnostic("inutilise")
            d.evenement("test")
            d.fermer()
            self.assertEqual(d.erreurs, 1)

    def test_file_pleine_ne_bloque_pas(self):
        entre = threading.Event()
        liberer = threading.Event()
        def ecrire(*_):
            entre.set()
            liberer.wait(2)
        with mock.patch.object(Diagnostic, "_ecrire", side_effect=ecrire):
            d = Diagnostic("inutilise", file_max=1)
            try:
                d.evenement("premier")
                self.assertTrue(entre.wait(1))
                d.evenement("deuxieme")
                self.assertIsNone(d.evenement("perdu"))
                self.assertEqual(d.perdus, 1)
            finally:
                liberer.set()
                d.fermer()

    def test_rotation_bornee(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            self.assertTrue(Path(tmp).resolve().is_relative_to(ROOT))
            d = Diagnostic(tmp, limite_octets=500, archives=2)
            for i in range(15):
                d.evenement("rotation", numero=i)
            d.fermer()
            fichiers = list(Path(tmp).glob("*.jsonl"))
            self.assertEqual(d.erreurs, 0)
            self.assertLessEqual(len(fichiers), 3)
            self.assertTrue(all(f.stat().st_size <= 500 for f in fichiers))
            for f in fichiers:
                for l in f.read_text(encoding="utf-8").splitlines():
                    json.loads(l)

    def test_pas_image_autre_fenetre(self):
        with mock.patch.object(Diagnostic, "_ecrire"), \
             mock.patch("fm_securite.fenetre_dofus_active", return_value=False):
            d = Diagnostic("inutilise")
            image = mock.Mock()
            d.observation({"lignes": {}}, time.monotonic(), image)
            d.fermer()
            image.copy.assert_not_called()

    def test_diagnostic_invalide_reste_passif(self):
        with mock.patch.object(Diagnostic, "_ecrire"):
            d = Diagnostic("inutilise")
            self.assertIsNone(d.observation({"lignes": None}, time.monotonic()))
            self.assertEqual(d.erreurs, 1)
            d.fermer()

    def test_desactivation_sans_fil_ni_ecriture(self):
        with mock.patch.dict("os.environ", {"FM_DIAGNOSTIC": "0"}), \
             mock.patch.object(Diagnostic, "_ecrire") as ecrire:
            d = Diagnostic("inutilise")
            self.assertIsNone(d.evenement("session"))
            d.observation({"lignes": {}}, time.monotonic())
            d.fermer()
            self.assertIsNone(d._thread.ident)
            ecrire.assert_not_called()

    def test_nombre_captures_borne(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            self.assertTrue(Path(tmp).resolve().is_relative_to(ROOT))
            d = Diagnostic(tmp, captures_max=2)
            d.fermer()
            faux_cv2 = SimpleNamespace(IMWRITE_JPEG_QUALITY=1,
                imencode=lambda *a: (True, SimpleNamespace(nbytes=4, tobytes=lambda: b"jpeg")))
            with mock.patch.dict("sys.modules", {"cv2": faux_cv2}):
                for i in range(5):
                    d._ecrire(None, SimpleNamespace(shape=(10, 10, 3)), f"capture_{i}.jpg")
            self.assertEqual(len(list(Path(tmp).glob("capture_*.jpg"))), 2)


if __name__ == "__main__":
    unittest.main()
