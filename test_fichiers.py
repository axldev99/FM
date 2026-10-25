import errno
import io
import unittest
from unittest import mock

import fm_fichiers


class FichiersTests(unittest.TestCase):
    def test_reprise_erreur_22_creation(self):
        with mock.patch.object(fm_fichiers.tempfile, "mkstemp", side_effect=[OSError(errno.EINVAL, "transitoire"), (12, "temporaire")]), \
             mock.patch.object(fm_fichiers.os, "fdopen", return_value=io.StringIO()), \
             mock.patch.object(fm_fichiers.os, "replace") as remplacer, \
             mock.patch.object(fm_fichiers.os, "unlink"), \
             mock.patch.object(fm_fichiers.time, "sleep") as attendre:
            fm_fichiers.ecrire_texte("fm_run.txt", "jeton")
            remplacer.assert_called_once()
            attendre.assert_called_once()

    def test_reprise_verrou_remplacement(self):
        with mock.patch.object(fm_fichiers.tempfile, "mkstemp", side_effect=[(12, "temp1"), (13, "temp2")]), \
             mock.patch.object(fm_fichiers.os, "fdopen", side_effect=[io.StringIO(), io.StringIO()]), \
             mock.patch.object(fm_fichiers.os, "replace", side_effect=[PermissionError(errno.EACCES, "occupe"), None]) as remplacer, \
             mock.patch.object(fm_fichiers.os, "unlink") as nettoyer, \
             mock.patch.object(fm_fichiers.time, "sleep"):
            fm_fichiers.ecrire_texte("fm_run.txt", "jeton")
            self.assertEqual(remplacer.call_count, 2)
            self.assertEqual(nettoyer.call_count, 2)

    def test_echec_persistant_remonte(self):
        with mock.patch.object(fm_fichiers.tempfile, "mkstemp", side_effect=OSError(errno.EINVAL, "persistant")) as creer, \
             mock.patch.object(fm_fichiers.time, "sleep"):
            with self.assertRaises(OSError):
                fm_fichiers.ecrire_texte("fm_run.txt", "jeton", essais=3)
            self.assertEqual(creer.call_count, 3)

    def test_erreur_permanente_pas_de_boucle(self):
        with mock.patch.object(fm_fichiers.tempfile, "mkstemp", side_effect=OSError(errno.ENOSPC, "plein")), \
             mock.patch.object(fm_fichiers.time, "sleep") as attendre:
            with self.assertRaises(OSError):
                fm_fichiers.ecrire_texte("fm_run.txt", "jeton")
            attendre.assert_not_called()


if __name__ == "__main__":
    unittest.main()
