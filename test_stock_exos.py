import ast
from pathlib import Path
import sys
import queue
import unittest
from types import SimpleNamespace

import activer_clics
from fm_stock_exos import StockExos, runes_a_verifier, barre_inventaire, quantite_filtrage, chiffres_stock, recherche_effacee, point_ressources, nettoyage_confirme


class StockExosTests(unittest.TestCase):
    def test_sequence_recherche_exo_et_petit_exo_avant_reprise(self):
        ar=ast.parse('def runtime():\n'+activer_clics.RUNTIME_RAVITO)
        fn=next(n for n in ast.walk(ar) if isinstance(n,ast.FunctionDef) and n.name=='verifier_stock_exos')
        for lisible, texte_ok in ((True,True),(False,True),(True,False)):
            commandes=[];nettoyages=[];mode=['automatique'];texte=[''];clock=[0.];clics=[]
            def maintenant():clock[0]+=.1;return clock[0]
            def taper(t):texte[0]=t;commandes.append(t)
            panneau=SimpleNamespace(conf={'exos':{'pa':1},'petit_exo':'agi'},
                nom=SimpleNamespace(get=lambda:'anneau'),mode=SimpleNamespace(get=lambda:mode[0],set=lambda m:mode.__setitem__(0,m)),
                _mode_change=lambda:None)
            ns=dict(runes_a_verifier=runes_a_verifier,etat={'lignes':{}},panneau=panneau,signature=lambda _:(),
                    stock_session=[None],stock_exos=StockExos(),confirmation=SimpleNamespace(attente=None),
                    confirmation_navigation=SimpleNamespace(attente=None),calque_ravitaillement=lambda _:None,
                    capturer=lambda _:SimpleNamespace(),mon={'left':0,'top':0},barre_inventaire=lambda _: (1000,80,260,28),
                    clic_point=lambda *a:clics.append(a) or True,point_ressources=lambda *a:(960,230),pause_auto=lambda _:True,ctrl_a=lambda:None,taper_texte=taper,
                    recherche_rune=lambda c,t:'rune '+c,time=SimpleNamespace(monotonic=maintenant),
                    norm=lambda x:x.replace(' ',''),ocr=SimpleNamespace(ligne=lambda _:texte[0]),
                    zone_filtre=lambda *a:None,quantite_filtrage=lambda *a:20 if lisible else None,
                    diagnostic=SimpleNamespace(evenement=lambda *a,**kw:None),
                    vider_recherche_inventaire=lambda:nettoyages.append(True) or True,
                    nom_code=lambda c:c,log=lambda _:None,boite=queue.Queue(),queue=queue,securite={},runes={},
                    SUIVI=SimpleNamespace(reglages={'stock':{'rows':[{'cle':'pa/base','n':'?'}]}}))
            exec(compile(ast.Module(body=[fn],type_ignores=[]),'verification_isolee','exec'),ns)
            if not texte_ok:
                class ImageTest:
                    def __getitem__(self, cle):return SimpleNamespace(shape=(60,65,3))
                ns['capturer']=lambda _:ImageTest()
                ns['ocr']=SimpleNamespace(ligne=lambda _:self.fail('Gabarit reconnu : OCR inutile'))
                ns['runes']={'pa':SimpleNamespace(shape=(30,34,3)),'agi':SimpleNamespace(shape=(30,34,3))}
                ns['trouver_rune']=lambda *a:(10,10)
            self.assertTrue(ns['verifier_stock_exos']())
            self.assertEqual(clics[0],(960,230))
            self.assertNotIn((960,100),clics)  # ancienne cible du signe infini
            if lisible:
                self.assertEqual(mode[0],'automatique')
                self.assertEqual(commandes,['rune pa','rune agi'])
                self.assertEqual(panneau.stock_exos,{'pa':20,'agi':20})
                self.assertEqual(len(nettoyages),2)
                self.assertEqual(ns['SUIVI'].reglages['stock']['rows'][0]['n'],20)
                self.assertFalse(ns['verifier_stock_exos']())
            else:
                self.assertEqual(mode[0],'manuel')
                self.assertEqual(panneau.stock_exos,{})
                self.assertEqual(len(nettoyages),1)

    def test_exo_et_petit_exo_sans_doublon_ni_stat_naturelle(self):
        conf={'exos':{'pa':1,'pm':0},'petit_exo':'agi'}
        self.assertEqual(runes_a_verifier(conf,{}),('pa','agi'))
        self.assertEqual(runes_a_verifier(conf,{'agi':{}}),('pa',))
        self.assertEqual(runes_a_verifier({'exos':{'agi':1},'petit_exo':'agi'},{}),('agi',))

    def test_stock_confirme_sur_deux_captures_et_filtre_exact(self):
        s=StockExos();s.session('profil')
        self.assertFalse(s.observer('pa',False,0,1))
        self.assertFalse(s.observer('pa',True,None,2))
        self.assertFalse(s.observer('pa',True,20,3))
        self.assertFalse(s.observer('pa',True,20,3))
        self.assertTrue(s.observer('pa',True,20,4))
        self.assertEqual(s.valeurs,{'pa':20})
        s.consommer('pa');self.assertEqual(s.valeurs['pa'],19)
        s.session('autre');self.assertEqual(s.valeurs,{})

    def test_images_inventaire_stock_et_vide(self):
        try:import cv2
        except ImportError:
            for p in (Path.home()/'AppData/Local/Packages').glob('PythonSoftwareFoundation.Python.*/LocalCache/local-packages/Python*/site-packages'):
                if (p/'cv2').exists():sys.path.append(str(p))
            try:import cv2
            except ImportError:self.skipTest('OpenCV indisponible')
        root=Path(__file__).parent
        im=cv2.imread(str(root/'tests_inventaire_stock.png'))
        barre=barre_inventaire(im)
        self.assertIsNotNone(barre)
        ressources=point_ressources(im,barre)
        self.assertIsNotNone(ressources)
        self.assertTrue(barre[1]+130 < ressources[1] < barre[1]+170)
        self.assertTrue(recherche_effacee(im,barre))
        self.assertEqual(quantite_filtrage(im,barre,lambda z:'20'),20)
        self.assertIsNone(quantite_filtrage(im,barre,lambda z:''))
        # Vraie reconnaissance des chiffres avec le modele existant, sans OCR simule.
        import numpy as np
        import os
        ar=ast.parse((root/'assistant_sans_clic.py').read_text(encoding='utf-8'))
        noeuds=[n for n in ar.body if isinstance(n,(ast.FunctionDef,ast.ClassDef)) and n.name in ('Chiffres','_canevas')]
        ns=dict(cv2=cv2,np=np,os=os,ICI=str(root),CW=32,CH=28)
        exec(compile(ast.Module(body=noeuds,type_ignores=[]),'chiffres_reels','exec'),ns)
        chiffres=ns['Chiffres']()
        # Capture de la session bloquee : le second 1 est sous le seuil 200.
        # La quantite doit etre lue sans aucun appel au moteur OCR.
        onze=cv2.imread(str(root/'tests_stock_ga_pa_11.png'))
        self.assertEqual(chiffres_stock(onze,chiffres),'11')
        self.assertIsNone(chiffres_stock(np.zeros_like(onze),chiffres))
        self.assertEqual(quantite_filtrage(im,barre,lambda z:chiffres_stock(z,chiffres)),20)
        # Capture exacte ayant echoue : le titre coupe ne ferme plus son contour.
        filtre=cv2.imread(str(root/'tests_inventaire_ga_pa_filtre.png'))
        barre_filtree=barre_inventaire(filtre)
        self.assertIsNotNone(barre_filtree)
        self.assertFalse(recherche_effacee(filtre,barre_filtree))
        self.assertIsNotNone(point_ressources(filtre,barre_filtree))
        apres=cv2.imread(str(root/'tests_inventaire_apres_x.png'))
        self.assertTrue(nettoyage_confirme(filtre,barre_filtree,apres,barre_filtree))
        self.assertFalse(nettoyage_confirme(filtre,barre_filtree,filtre,barre_filtree))
        # Deux captures concordantes, sans dependance a l'OCR du placeholder.
        arbre=ast.parse('def runtime():\n'+activer_clics.RUNTIME_RAVITO)
        fn=next(n for n in ast.walk(arbre) if isinstance(n,ast.FunctionDef) and n.name=='vider_recherche_inventaire')
        images=iter((filtre,apres,apres));captures=[]
        def capturer(_):captures.append(True);return next(images)
        def ocr_interdit(*a):self.fail('La preuve visuelle suffit sans OCR')
        runtime=dict(capturer=capturer,mon={'left':0,'top':0},barre_inventaire=lambda _:barre_filtree,
                     clic_point=lambda *a:True,pause_auto=lambda _:True,nettoyage_confirme=nettoyage_confirme,
                     diagnostic=SimpleNamespace(evenement=lambda *a,**kw:None),recherche_effacee=ocr_interdit)
        exec(compile(ast.Module(body=[fn],type_ignores=[]),'vider_sans_ocr','exec'),runtime)
        self.assertTrue(runtime['vider_recherche_inventaire']())
        self.assertEqual(len(captures),3)
        self.assertEqual(quantite_filtrage(filtre,barre_filtree,lambda z:chiffres_stock(z,chiffres)),20)
        self.assertIsNone(barre_inventaire(cv2.imread(str(root/'tests_hdv_menu.png'))))
        vide=cv2.imread(str(root/'tests_inventaire_vide.png'))
        self.assertEqual(quantite_filtrage(vide,barre_inventaire(vide),lambda z:self.fail('OCR sur case vide')),0)

    def test_nettoyage_utilise_x_et_verifie_filtre(self):
        arbre=ast.parse('def runtime():\n'+activer_clics.RUNTIME_RAVITO)
        fn=next(n for n in ast.walk(arbre) if isinstance(n,ast.FunctionDef) and n.name=='vider_recherche_inventaire')
        for texte,attendu,visuel in [('Recherche',True,False),('rune ga pa',False,False),('OCR incertain',True,True)]:
            clics=[]
            ns=dict(capturer=lambda _:object(),mon={'left':-1920,'top':0},
                    barre_inventaire=lambda _: (1000,80,260,28),
                    clic_point=lambda *xy:clics.append(xy) or True,pause_auto=lambda _:True,
                    norm=lambda s:s.lower().replace(' ',''), zone_filtre=lambda *a:None,
                    ocr=SimpleNamespace(ligne=lambda _:texte),recherche_effacee=lambda *a:visuel,
                    nettoyage_confirme=lambda *a:False,
                    diagnostic=SimpleNamespace(evenement=lambda *a,**kw:None))
            exec(compile(ast.Module(body=[fn],type_ignores=[]),'nettoyage_isole','exec'),ns)
            self.assertEqual(ns['vider_recherche_inventaire'](),attendu)
            self.assertEqual(clics,[(-677,94)])

    def test_stock_inconnu_ne_declare_pas_zero(self):
        ar=ast.parse(Path('assistant_sans_clic.py').read_text(encoding='utf-8'))
        fn=next(n for n in ar.body if isinstance(n,ast.FunctionDef) and n.name=='lignes_stock')
        ns=dict(POIDS={'pa':100,'agi':1},PETITS_EXOS=('agi',))
        exec(compile(ast.Module(body=[fn],type_ignores=[]),'vue_stock','exec'),ns)
        conf={'exos':{'pa':1},'petit_exo':'agi'}
        vue=ns['lignes_stock']({},conf,{'pa':20})
        self.assertEqual(vue['pa']['stock'],{'base':20})
        self.assertEqual(vue['agi']['stock'],{})


if __name__=='__main__':unittest.main()
