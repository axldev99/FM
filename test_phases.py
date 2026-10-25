"""Non-regression des priorites : reference fournie par Alex, avec verrou limite aux quatre lignes autorisees."""
import ast
import json
import unittest
from test_fm_reference import ROOT, charger_moteur, observer, ligne


class PrioritesOrigineTests(unittest.TestCase):
    def test_plage_sagesse_objectif32_ra_jusqua22(self):
        conf={'cibles':{'sa':32},'regles':{'sa':{'pa':[0,37],'ra':[0,22]}}}
        for fichier in ('assistant_sans_clic.py','fm_avec_clics.py'):
            m=charger_moteur(fichier)
            for val,taille in ((15,'ra'),(22,'ra'),(30,'pa')):
                with self.subTest(fichier=fichier,val=val):
                    r=observer(m,{'sa':ligne(val,40,31,('base','pa','ra'))},conf)
                    self.assertEqual((r.get('stat'),r.get('taille')),('sa',taille))

    def test_finition_pa_dommages_ne_pas_passer_17_a_18(self):
        for fichier in ("assistant_sans_clic.py", "fm_avec_clics.py"):
            m = charger_moteur(fichier)
            for stat in ("do_neutre", "do_terre", "do_eau", "do_feu", "do_air"):
                for rel in (0,5,10,15,20):
                    with self.subTest(fichier=fichier,stat=stat,rel=rel):
                        ls = {stat:ligne(17,20,16,("base","pa")),
                              "vi":ligne(320,400,301,("base","pa","ra"))}
                        conf = {"cibles":{stat:20,"vi":390},
                                "regles":{stat:{"base":[0,16],"pa":[17,17]},"vi":{"ra":[200,350]}}}
                        r = observer(m,ls,conf,rel)
                        self.assertNotEqual((r.get("stat"),r.get("taille")),(stat,"base"))
                        if rel == 15:
                            seul = observer(m,{stat:ls[stat]},conf,rel)
                            self.assertEqual((seul["stat"],seul["taille"]),(stat,"pa"))

    def test_finition_pa_preserve_petites_runes_valides_et_stock(self):
        for fichier in ("assistant_sans_clic.py", "fm_avec_clics.py"):
            for val,dispo,fin in [(16,("base","pa"),16),(19,("base","pa"),19)]:
                m = charger_moteur(fichier)
                ls = {"do_neutre":ligne(val,20,16,dispo)}
                conf = {"cibles":{"do_neutre":20},
                        "regles":{"do_neutre":{"base":[0,fin],"pa":[17,17]}}}
                r = observer(m,ls,conf,5)
                self.assertEqual((r["stat"],r["taille"]),("do_neutre","base"))
            m = charger_moteur(fichier)
            r = observer(m,{"do_neutre":ligne(17,20,16,("base",))},
                         {"cibles":{"do_neutre":20},"regles":{"do_neutre":{"base":[0,16],"pa":[17,17]}}},5)
            self.assertNotIn("stat",r)
            self.assertIn("ACHETER",r["texte"])

    def test_decisions_identiques_aux_168_etats_origine(self):
        reference = json.loads((ROOT / "tests_fm_origine.json").read_text(encoding="utf-8"))
        for fichier in ("assistant_sans_clic.py", "fm_avec_clics.py"):
            moteur = charger_moteur(fichier)
            for i, cas in enumerate(reference["cas"]):
                with self.subTest(fichier=fichier, cas=i):
                    self.assertEqual(observer(moteur, cas["lignes"], reference["conf"], cas["reliquat"]), cas["attendu"])

    def test_pm_absent_petit_reliquat_respecte_le_palier_vi_du_profil(self):
        for fichier in ("assistant_sans_clic.py", "fm_avec_clics.py"):
            m = charger_moteur(fichier)
            ls = {"vi": ligne(1, 300, 251, ("base", "pa", "ra")),
                  "pm": ligne(0, 1, 1), "do": ligne(9, 10, 6),
                  "pp": ligne(1, 20, 11)}
            for rel in (0, 1.2, 1.8):
                with self.subTest(fichier=fichier, rel=rel):
                    conf = {"cibles": {"vi": 297, "pp": 10},
                            "regles": {"vi": {"pa": [0, 285]}}}
                    self.assertEqual(observer(m, ls, conf, rel)["stat"], "pm")
                    # Sans plage configuree, l'origine permet encore la Vi simple.
                    # Ne pas transformer la restauration en nouvelle regle universelle.
                    if rel >= 1:
                        self.assertEqual(observer(m, ls, {"cibles": conf["cibles"]}, rel)["stat"], "vi")

    def test_verrou_insiste_sur_les_quatre_lignes_seulement(self):
        from fm_phases import PhaseRemise
        for fichier in ("assistant_sans_clic.py", "fm_avec_clics.py"):
            m = charger_moteur(fichier)
            for stat in ("invo", "pa", "pm", "po"):
                with self.subTest(fichier=fichier, stat=stat):
                    phase = PhaseRemise()
                    ls = {stat: dict(ligne(0, 1, 1), nom=m["nom_code"](stat)),
                          "vi": dict(ligne(1, 300, 251, ("base", "pa", "ra")), nom="Vitalite")}
                    etat = {"lignes": ls, "reliquat": 0}
                    self.assertEqual(phase.conseiller(m["recommander"], etat, {}, {}, "A")["stat"], stat)
                    # Apres un EC, meme si le reliquat pourrait payer une Vi simple.
                    etat["reliquat"] = 1.8
                    self.assertEqual(phase.conseiller(m["recommander"], etat, {}, {}, "A")["stat"], stat)
                    ls[stat]["val"] = 1
                    phase.conseiller(m["recommander"], etat, {}, {}, "A")
                    self.assertIsNone(phase.stat)

    def test_dommages_ne_verrouillent_jamais(self):
        from fm_phases import PhaseRemise
        phase = PhaseRemise()
        etat = {"lignes": {"do": ligne(9, 10, 6)}, "reliquat": 0}
        phase.conseiller(lambda *a: {"stat": "do", "texte": "REMETS Dommages"}, etat, {}, {}, "A")
        self.assertIsNone(phase.stat)
        for fichier in ("assistant_sans_clic.py", "fm_avec_clics.py"):
            m = charger_moteur(fichier)
            ls = {"do": ligne(9, 10, 6), "vi": ligne(1, 300, 251, ("base", "pa", "ra"))}
            self.assertEqual(observer(m, ls, {}, 1.8), observer(m, ls, {"_remise_lourde": "do"}, 1.8))

    def test_verrou_lecture_stock_item_et_reset(self):
        from fm_phases import PhaseRemise
        m = charger_moteur()
        phase = PhaseRemise()
        etat = {"lignes": {"pm": dict(ligne(0, 1, 1), nom="PM")}, "reliquat": 0}
        phase.conseiller(m["recommander"], etat, {}, {}, "A")
        absent = {"lignes": {"vi": dict(ligne(1, 300), nom="Vitalite")}, "reliquat": 1.8}
        self.assertTrue(phase.conseiller(m["recommander"], absent, {}, {}, "A")["stop"])
        etat["lignes"]["pm"]["dispo"] = []
        self.assertTrue(phase.conseiller(m["recommander"], etat, {}, {}, "A")["texte"].startswith("A ACHETER"))
        self.assertEqual(phase.stat, "pm")
        phase.conseiller(lambda e,c,h: {"texte": "attente"}, absent, {}, {}, "B")
        self.assertIsNone(phase.stat)
        phase.stat = "po"
        phase.reinitialiser()
        self.assertIsNone(phase.stat)

    def test_overs_et_recyclage_identiques_sur_toutes_les_caracs(self):
        for fichier in ("assistant_sans_clic.py", "fm_avec_clics.py"):
            for stat in ("fo", "int", "cha", "agi"):
                m = charger_moteur(fichier)
                conf = {"cibles": {stat: 70, "vi": 297},
                        "regles": {stat: {"ra": [35, 60]}, "vi": {"pa": [0, 285]}}}
                for val, vi, attendu in [(65,267,(stat,"ra")), (75,267,("vi","pa")),
                                          (72,282,("vi","base")), (71,287,("vi","base"))]:
                    with self.subTest(fichier=fichier, stat=stat, valeur=val):
                        ls = {stat: ligne(val,70,51,("base","pa","ra")),
                              "vi": ligne(vi,300,251,("base","pa","ra"))}
                        r = observer(m,ls,conf,20)
                        self.assertEqual((r["stat"],r["taille"]),attendu)

    def test_boucle_passe_par_la_phase(self):
        for fichier in ("assistant_sans_clic.py", "fm_avec_clics.py"):
            arbre = ast.parse((ROOT / fichier).read_text(encoding="utf-8"))
            boucle = next(n for n in arbre.body if isinstance(n, ast.FunctionDef) and n.name == "mode_direct")
            self.assertTrue(any(isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                                and isinstance(n.func.value, ast.Name) and n.func.value.id == "phase_remise"
                                and n.func.attr == "conseiller" for n in ast.walk(boucle)))

    def test_petit_over_re_critiques_pas_de_ra_vi_si_rune_adaptee(self):
        for fichier in ("assistant_sans_clic.py", "fm_avec_clics.py"):
            for stat, val, maxi in [("re_cri",26,25),("pui",41,40),("re_per_eau",11,10)]:
                for rel in (0,2,20):
                    with self.subTest(fichier=fichier,stat=stat,rel=rel):
                        m = charger_moteur(fichier)
                        ls = {stat:ligne(val,maxi,1), "vi":ligne(314,400,301,("base","pa","ra")),
                              "re_pou":ligne(10,20,1)}
                        conf = {"cibles":{stat:maxi,"vi":390},"regles":{"vi":{"ra":[300,350]}}}
                        r = observer(m,ls,conf,rel)
                        self.assertNotEqual((r.get("stat"),r.get("taille")),("vi","ra"))
                        self.assertLessEqual(m["pds"](r["stat"],m["qte"](r["stat"],r["taille"])),m["pds"](stat,val-maxi))

    def test_over_recycle_avec_dommage_elementaire_utile(self):
        for fichier in ("assistant_sans_clic.py", "fm_avec_clics.py"):
            for stat in ("fo", "int", "cha", "agi"):
                m = charger_moteur(fichier)
                ls = {stat: ligne(75,70,51,("base","pa","ra")),
                      "do_eau": ligne(9,10,6), "re_per_eau": ligne(9,10,6)}
                r = observer(m, ls, {"cibles": {stat:69}}, 0)
                self.assertEqual((r["stat"],r["taille"]),("do_eau","base"))

    def test_over_puissance_puissance_vi_sans_entamer_max(self):
        for fichier in ("assistant_sans_clic.py", "fm_avec_clics.py"):
            m = charger_moteur(fichier)
            for cha,pui,attendu in [(75,10,"pui"),(73,11,"pui"),(71,12,"vi")]:
                ls = {"cha":ligne(cha,70,51,("base","pa","ra")),
                      "pui":ligne(pui,20,dispo=("base",)), "vi":ligne(267,300,251),
                      "re_per_eau":ligne(9,10,6)}
                r = observer(m,ls,{"cibles":{"cha":69,"vi":297}},0)
                self.assertEqual((r["stat"],r["taille"]),(attendu,"base"))
                self.assertLessEqual(m["pds"](r["stat"],m["qte"](r["stat"],r["taille"])),cha-70)

    def test_bruler_ne_prend_pas_la_marge_jusqua_objectif(self):
        for fichier in ("assistant_sans_clic.py", "fm_avec_clics.py"):
            m = charger_moteur(fichier)
            # Puissance deja au max : disponible pour recycler, sans gain utile.
            # La Re % utile coute 6, mais l'over ne fournit que 5, pas 6.
            ls = {"cha":ligne(75,70,51,("base","pa","ra")),
                  "pui":ligne(20,20), "re_per_eau":ligne(9,10,6)}
            for objectif in (69,70):
                r = observer(m,ls,{"cibles":{"cha":objectif}},0)
                self.assertEqual((r["stat"],r["taille"]),("pui","base"))


if __name__ == "__main__":
    unittest.main()
