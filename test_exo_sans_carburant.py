import copy
import json
import unittest
from test_fm_reference import ROOT, charger_moteur, observer, ligne


class ExoSansCarburantTests(unittest.TestCase):
    def test_session_grithrill_jet_atteint(self):
        cas = json.loads((ROOT / 'tests_grithrill_exo.json').read_text(encoding='utf-8'))
        for fichier in ('assistant_sans_clic.py', 'fm_avec_clics.py'):
            m = charger_moteur(fichier)
            for stat in ('pa', 'pm', 'po', 'invo'):
                for rel in (0, 1.6):
                    with self.subTest(fichier=fichier, stat=stat, rel=rel):
                        conf = copy.deepcopy(cas['conf'])
                        conf['exos'] = {stat: 1}
                        r = observer(m, cas['etat']['lignes'], conf, rel)
                        self.assertEqual((r.get('stat'), r.get('virtuel')), (stat, True))
                        self.assertTrue(r['texte'].startswith('EXO'))

    def test_minimum_accepte_et_jet_incomplet(self):
        for fichier in ('assistant_sans_clic.py', 'fm_avec_clics.py'):
            for stat in ('pa', 'pm', 'po', 'invo'):
                m = charger_moteur(fichier)
                conf = {'cibles': {'fo': 50, 'cha': 0}, 'mins': {'fo': 48}, 'exos': {stat: 1}}
                ls = {'fo': ligne(48, 50), 'cha': ligne(0, 50)}
                self.assertEqual(observer(m, ls, conf)['stat'], stat)
                ls['fo']['val'] = 5
                self.assertNotEqual(observer(m, ls, conf)['stat'], stat)


if __name__ == '__main__':
    unittest.main()
