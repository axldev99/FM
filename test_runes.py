import unittest

from test_fm_reference import charger_moteur


class RunesTests(unittest.TestCase):
    def test_ra_resistances_fixes_et_poussee_dix_points(self):
        for fichier in ("assistant_sans_clic.py", "fm_avec_clics.py"):
            m = charger_moteur(fichier)
            for stat in ("re_pou","re_feu","re_terre","re_neutre","re_eau","re_air"):
                with self.subTest(fichier=fichier,stat=stat):
                    self.assertEqual(m["tailles"](stat),["base","pa","ra"])
                    self.assertEqual(m["qte"](stat,"ra"),10)
                    self.assertEqual(m["pds"](stat,10),20)
            for e in ("feu","terre","neutre","eau","air"):
                self.assertEqual(m["tailles"]("re_per_"+e),["base"])


if __name__ == "__main__":
    unittest.main()
