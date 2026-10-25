import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from fm_diagnostic import Diagnostic
from fm_orchestration import OrchestrationObservee

ROOT = Path(__file__).resolve().parent


class OrchestrationTests(unittest.TestCase):
    def test_moteur_fm_valide_reste_inchange(self):
        import ast
        import hashlib
        noms = {"recommander", "probas", "contexte", "qte", "pds", "palier", "plafond"}
        for fichier in ("assistant_sans_clic.py", "fm_avec_clics.py"):
            arbre = ast.parse((ROOT / fichier).read_text(encoding="utf-8"))
            contenu = "\n".join(ast.dump(n, include_attributes=False) for n in arbre.body
                                if isinstance(n, ast.FunctionDef) and n.name in noms)
            self.assertEqual(hashlib.sha256(contenu.encode()).hexdigest(), "83c2fa5c6cc8d850b4b198dacc6e0f5d499c657fcb612410bdd999c49f249b68")

    def test_parcours_pause_file_et_retour(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            m = OrchestrationObservee(Path(tmp) / "etat.json")
            c = dict(mode="automatique", tableau=True, profil="Kimbo", file=["A", "A"])
            for guide, etat in [(None,"FM"),("sortie","SORTIE"),("achat","ACHAT"),("retour","RETOUR"),(None,"FM")]:
                m.observer(dict(c, guide=guide))
                self.assertEqual(m.courant["etat"], etat)
            m.observer(dict(c, guide="achat", mode="manuel"))
            self.assertEqual(m.courant["etat"], "PAUSE")
            self.assertEqual(m.courant["phase_observee"], "ACHAT")
            self.assertEqual(m.courant["file"], ["A", "A"])
            m.observer(dict(c, stop=True))
            self.assertEqual(m.courant["etat"], "ATTENTE")
            m.observer(dict(c, termine=True))
            self.assertEqual(m.courant["etat"], "TERMINE")

    def test_redemarrage_ne_reprend_jamais_achat(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            p = Path(tmp) / "etat.json"
            m = OrchestrationObservee(p)
            m.observer(dict(mode="automatique", guide="achat", profil="A"))
            reprise = OrchestrationObservee(p)
            self.assertEqual(reprise.precedent["etat"], "ACHAT")
            self.assertIsNone(reprise.courant)
            reprise.observer(dict(mode="manuel", tableau=True, profil="B"))
            d = json.loads(p.read_text(encoding="utf-8"))
            self.assertEqual(d["etat"], "PAUSE")
            self.assertEqual(d["profil"], "B")
            self.assertFalse(d["reprise_automatique"])
            self.assertTrue(d["verification_requise_au_redemarrage"])

    def test_fichier_corrompu_ou_schema_inconnu(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            p = Path(tmp) / "etat.json"
            for texte in ("{", '[]', '{"schema":99,"etat":"ACHAT"}'):
                p.write_text(texte, encoding="utf-8")
                m = OrchestrationObservee(p)
                self.assertTrue(m.lecture_invalide)
                self.assertIsNone(m.precedent)
                m.observer({})
                self.assertEqual(m.courant["phase_observee"], "ATTENTE")

    def test_pas_de_reecriture_sans_changement(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            m = OrchestrationObservee(Path(tmp) / "etat.json")
            c = dict(mode="automatique", tableau=True)
            self.assertTrue(m.observer(c))
            with mock.patch("fm_orchestration.ecrire_texte") as ecrire:
                self.assertFalse(m.observer(c))
                ecrire.assert_not_called()
            self.assertNotIn("etat", c)

    def test_panne_ecriture_ne_valide_pas_transition(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            m = OrchestrationObservee(Path(tmp) / "etat.json")
            with mock.patch("fm_orchestration.ecrire_texte", side_effect=OSError("disque")):
                with self.assertRaises(OSError):
                    m.observer({})
            self.assertIsNone(m.courant)
            self.assertTrue(m.observer({}))

    def test_diagnostic_persiste_en_arriere_plan_et_reste_passif(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            d = Diagnostic(tmp)
            d.evenement("orchestration", mode="automatique", guide="achat", file=["A"])
            d.evenement("orchestration", mode="automatique", guide="achat", file=["A"])
            d.fermer()
            p = Path(tmp) / "etat_orchestration.json"
            self.assertEqual(json.loads(p.read_text(encoding="utf-8"))["etat"], "ACHAT")
            self.assertEqual(d.erreurs, 0)
            self.assertEqual(d.ecrits, 1)
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            with mock.patch("fm_orchestration.ecrire_texte", side_effect=OSError("disque")):
                d = Diagnostic(tmp)
                d.evenement("orchestration", tableau=True)
                d.fermer()
                self.assertEqual(d.erreurs, 1)


if __name__ == "__main__":
    unittest.main()
