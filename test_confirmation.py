import ast
import copy
import difflib
import json
from pathlib import Path
from types import SimpleNamespace
import unittest

import activer_clics
from fm_confirmation import ConfirmationActions, ConfirmationTransition, revalider_fusion


def etat(stock=10, val=5, rel=0):
    return {"lignes": {"fo": {"val":val,"max":20,"min":1,"dispo":["base"],"stock":{"base":stock}}}, "reliquat":rel}


class ConfirmationTests(unittest.TestCase):
    def test_fusion_relecture_fraiche_sans_changer_item_ni_jet(self):
        avant = etat()
        self.assertTrue(revalider_fusion(avant,etat(),103,103.2,102.5))
        for apres,capture,maintenant in [(etat(),102,103),(etat(),103,106),
                                        (etat(val=6),103,103.2),(None,103,103.2)]:
            self.assertFalse(revalider_fusion(avant,apres,capture,maintenant,102.5))
        perime = etat()
        perime["lignes"]["fo"]["rate"] = 1
        self.assertFalse(revalider_fusion(avant,perime,103,103.2,102.5))

    def test_sequence_exo_rafraichit_lecture_avant_fusion(self):
        arbre = ast.parse("def runtime():\n" + activer_clics.RUNTIME_EXO)
        fn = next(n for n in ast.walk(arbre) if isinstance(n,ast.FunctionDef) and n.name=="tenter_exo")
        for change in (False,True):
            clock=[100.]; clics=[]; traces=[]
            mon={"left":0,"top":0}; sec={"lecture":99.5,"capture":99.5}
            appels=[0]
            def lire(**kw):
                appels[0]+=1
                if appels[0]==1:
                    clock[0]=102.7
                    return (mon,"ancienne",etat(),None,101.)
                clock[0]+=.3
                return (mon,"fraiche",etat(val=6 if change else 5),None,clock[0]-.1)
            def cliquer(x,y,double=False):
                clics.append((x,y,double))
                if double:
                    clock[0]=102.5  # selection + capture de debug : ancienne lecture >2 s
                return True
            boutons=[0]
            def bouton(im):
                boutons[0]+=1
                return None if boutons[0]==1 else (20,30)
            def ocr_interdit(*a):
                raise AssertionError('Pas de recherche OCR bloquante pour Fusionner')
            ns=dict(action_autorisee=lambda **kw:clock[0]-sec["lecture"]<=2,
                    mon=mon,clic_point=cliquer,placer_souris_haut_gauche=lambda:None,
                    time=SimpleNamespace(monotonic=lambda:clock[0]),
                    panneau=SimpleNamespace(nom=SimpleNamespace(get=lambda:"A"),mode=SimpleNamespace(get=lambda:"automatique")),
                    boite=SimpleNamespace(get=lire),verifier_mode_clic=lambda:None,dofus_actif=lambda:True,
                    queue=__import__("queue"),etat=etat(),trouver_bouton_vert=bouton,
                    trouver_texte=ocr_interdit,securite=sec,
                    diagnostic=SimpleNamespace(evenement=lambda *a,**kw:traces.append(a[0])),log=lambda _:None)
            exec(compile(ast.Module(body=[fn],type_ignores=[]),"fusion_isolee","exec"),ns)
            self.assertEqual(ns["tenter_exo"](SimpleNamespace(shape=(30,30)),(10,10)),not change)
            self.assertEqual(len(clics),1 if change else 2)
            if not change:
                self.assertEqual(clics[-1],(20,30,False))
                self.assertIn("fusion_revalidee",traces)
                self.assertGreater(sec["lecture"],102.5)
    def test_file_attend_objectif_valide_et_action_confirmee(self):
        arbre = ast.parse("def runtime():\n" + activer_clics.RUNTIME_SECURITE)
        fn = next(n for n in ast.walk(arbre) if isinstance(n,ast.FunctionDef) and n.name=="signaler_objectif_confirme")
        suites=[]; mouvements=[]
        ns=dict(fin_signalee=[None], confirmation=SimpleNamespace(attente=None),
                confirmation_navigation=SimpleNamespace(attente=None),
                panneau=SimpleNamespace(nom=SimpleNamespace(get=lambda:"Tourthon"),conf={'cibles':{'fo':10},'mins':{'fo':5}}),
                etat=etat(val=5),placer_souris_haut_gauche=lambda:mouvements.append(True),
                proposer_suite=lambda *a:suites.append(a))
        exec(compile(ast.Module(body=[fn],type_ignores=[]),"file_isolee","exec"),ns)
        f=ns["signaler_objectif_confirme"]
        f({"texte":"EXO DANS LE PUITS"})
        f({"texte":"JET A REPRENDRE", "stop":True})
        self.assertEqual(suites,[])
        ns["confirmation"].attente={}
        f({"texte":"OBJECTIF ATTEINT"})
        self.assertEqual(suites,[])
        ns["confirmation"].attente=None
        f({"texte":"OBJECTIF ATTEINT"})
        f({"texte":"OBJECTIF ATTEINT"})
        self.assertEqual(suites,[("Objectif atteint","Tourthon")])
        self.assertEqual(mouvements,[True])
        ns['fin_signalee'][0]=None
        ns['etat']=etat(val=4)
        f({"texte":"OBJECTIF ATTEINT"})
        self.assertEqual(mouvements,[True])

    def test_deplacement_reserve_a_objectif_confirme(self):
        arbre = ast.parse('def runtime():\n' + activer_clics.RUNTIME_EXO + activer_clics.RUNTIME_SECURITE)
        appels = []
        for fn in ast.walk(arbre):
            if isinstance(fn, ast.FunctionDef):
                for n in ast.walk(fn):
                    if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == 'placer_souris_haut_gauche':
                        if fn.name != 'runtime':
                            appels.append(fn.name)
        self.assertEqual(appels, ['signaler_objectif_confirme'])
    def test_rejoue_trois_passes_reelles_avec_survol(self):
        cas = json.loads((Path(__file__).parent / "tests_confirmation_session.json").read_text(encoding="utf-8"))
        self.assertEqual(len(cas), 3)
        for c in cas:
            m = ConfirmationActions()
            m.commencer(c["avant"], c["reco"], "A", c["debut"])
            resultats = [m.observer(o["etat"], o["capture"], "A", o["maintenant"]) for o in c["observations"]]
            self.assertEqual([r["type"] for r in resultats if r], ["action_confirmee"])
            self.assertIsNone(m.attente)

    def test_survol_ninvalide_pas_valeurs_relues_mais_stock_reste_exclu(self):
        avant = etat(10)
        avant["lignes"]["fo"]["occulte"] = True
        m = self.nouvelle(avant)
        apres = etat(9)
        apres["lignes"]["fo"]["occulte"] = True
        for t in (101,102):
            self.assertIsNone(m.observer(apres,t,"A",t))
        apres["lignes"]["fo"]["val"] = 6
        self.assertIsNone(m.observer(apres,103,"A",103))
        self.assertEqual(m.observer(apres,104,"A",104)["preuve"], "tableau_modifie")

    def test_navigation_attend_etape_reconnue_sur_deux_images(self):
        m = ConfirmationTransition()
        m.commencer(("guide","sortir"),100)
        for cle,t in [(None,101),(("guide","sortir"),102),(("guide","hdv"),99)]:
            self.assertIsNone(m.observer(cle,t,max(t,102)))
        self.assertIsNone(m.observer(("guide","hdv"),103,103))
        self.assertIsNone(m.observer(("guide","hdv"),103,103))
        self.assertEqual(m.observer(("guide","hdv"),104,104)["type"],"navigation_confirmee")
        self.assertIsNone(m.attente)

    def test_navigation_non_confirmee_bloque_jusqua_resynchronisation(self):
        m = ConfirmationTransition(delai=2)
        m.commencer(("guide","sortir"),100)
        self.assertEqual(m.observer(None,103,103)["type"],"navigation_non_confirmee")
        self.assertIsNotNone(m.attente)
        m.abandonner()
        self.assertIsNone(m.attente)

    def nouvelle(self, e=None):
        m = ConfirmationActions(delai=10)
        m.commencer(e or etat(), {"stat":"fo","taille":"base"}, "A", 100)
        return m

    def test_stock_consomme_confirme_ec_sans_changement_jet(self):
        m = self.nouvelle()
        self.assertIsNone(m.observer(etat(9),101,"A",101))
        r = m.observer(etat(9),102,"A",102)
        self.assertEqual(r["preuve"],"stock_consomme")
        self.assertIsNone(m.attente)

    def test_anciennes_images_doublons_et_lectures_perimees(self):
        m = self.nouvelle()
        for capture, now in [(99,101),(100,101),(101,105),(float("nan"),105)]:
            self.assertIsNone(m.observer(etat(9),capture,"A",now))
        self.assertIsNone(m.observer(etat(9),106,"A",106))
        self.assertIsNone(m.observer(etat(9),106,"A",106))
        self.assertIsNotNone(m.attente)
        self.assertEqual(m.observer(etat(9),107,"A",107)["type"],"action_confirmee")

    def test_ecran_identique_ne_relance_pas_et_expire(self):
        m = self.nouvelle()
        self.assertIsNone(m.observer(etat(),101,"A",101))
        self.assertEqual(m.observer(etat(),111,"A",111)["type"],"action_non_confirmee")
        with self.assertRaises(RuntimeError):
            m.commencer(etat(),{},"A",112)
        self.assertEqual(m.abandonner()["id"],1)
        m.commencer(etat(),{},"A",113)

    def test_ambiguite_item_et_stock(self):
        for e, profil in [(etat(8),"A"),(etat(11),"A"),(etat(9),"B")]:
            self.assertEqual(self.nouvelle().observer(e,101,profil,101)["type"],"action_ambigue")
        e = etat(9)
        e["lignes"]["fo"]["max"] = 30
        self.assertEqual(self.nouvelle().observer(e,101,"A",101)["type"],"action_ambigue")

    def test_ocr_instable_ne_confirme_pas(self):
        m = self.nouvelle()
        for i, e in enumerate([etat(9),etat(),etat(9),etat()],101):
            self.assertIsNone(m.observer(e,i,"A",i))
        e = etat(9)
        e["lignes"]["fo"]["rate"] = 1
        self.assertIsNone(m.observer(e,105,"A",105))
        self.assertIsNotNone(m.attente)

    def test_effet_tableau_sans_stock_et_reliquat_illisible(self):
        avant = etat(None)
        m = self.nouvelle(avant)
        apres = etat(None,6)
        self.assertIsNone(m.observer(apres,101,"A",101))
        self.assertEqual(m.observer(apres,102,"A",102)["preuve"],"tableau_modifie")
        m = self.nouvelle(avant)
        apres = etat(None,5,None)
        self.assertIsNone(m.observer(apres,101,"A",101))
        self.assertIsNone(m.observer(apres,102,"A",102))
        self.assertIsNotNone(m.attente)

    def test_entrees_figees_et_derniere_rune(self):
        avant = etat(1)
        m = self.nouvelle(avant)
        avant["lignes"]["fo"]["stock"]["base"] = 500
        apres = etat(None)
        apres["lignes"]["fo"]["dispo"] = []
        self.assertIsNone(m.observer(apres,101,"A",101))
        self.assertEqual(m.observer(apres,102,"A",102)["preuve"],"stock_consomme")

    def test_achat_confirmation_exacte_sur_bonne_fiche(self):
        arbre = ast.parse("def runtime():\n" + activer_clics.RUNTIME_RAVITO)
        fn = next(n for n in ast.walk(arbre) if isinstance(n,ast.FunctionDef) and n.name=="confirmer_achat")
        for mauvais in (False,True):
            temps=[0.]
            def maintenant():
                temps[0] += .25
                return temps[0]
            modes=[]; events=[]
            fiche={"fiches":[{"nom":"autre rune" if mauvais else "rune fo","qte":110}]}
            ns=dict(time=SimpleNamespace(monotonic=maintenant), pause_auto=lambda _:True,
                    lire_fiche=lambda:(None,copy.deepcopy(fiche)), norm=lambda s:s.lower(), difflib=difflib,
                    diagnostic=SimpleNamespace(evenement=lambda *a,**k:events.append(a[0])),
                    panneau=SimpleNamespace(mode=SimpleNamespace(set=modes.append),_mode_change=lambda:None),log=lambda _:None)
            exec(compile(ast.Module(body=[fn],type_ignores=[]),"achat_isole","exec"),ns)
            self.assertEqual(ns["confirmer_achat"]({"rune":"Fo","recherche":"rune fo"},100,10),not mauvais)
            self.assertEqual(events,["achat_non_confirme" if mauvais else "achat_confirme"])
            self.assertEqual(modes,["manuel"] if mauvais else [])

    def test_generation_sans_relance_aveugle_et_avec_confirmation(self):
        source=(Path(__file__).parent/"assistant_sans_clic.py").read_text(encoding="utf-8")
        genere,_=activer_clics.patch(source)
        self.assertIn("observer_confirmation(etat, t_capture)",genere)
        self.assertNotIn('origine="relance"',genere)
        self.assertNotIn("time.time() - t_clic > 3",genere)
        self.assertEqual(genere.count("        debut_confirmation()"),2)


if __name__ == "__main__":
    unittest.main()
