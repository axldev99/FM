"""Controle les confirmations d'achat sans jeu, clic ni depense."""
import ast
import difflib
import copy
import json
import tempfile
import os
import sys
import re
import unittest
from types import SimpleNamespace
from pathlib import Path
import activer_clics


class RavitaillementTests(unittest.TestCase):
    def test_case_retour_depuis_recherche_deja_remplie(self):
        try:import cv2
        except ImportError:
            for p in (Path.home()/'AppData/Local/Packages').glob('PythonSoftwareFoundation.Python.*/LocalCache/local-packages/Python*/site-packages'):
                if (p/'cv2').exists():sys.path.append(str(p))
            try:import cv2
            except ImportError:self.skipTest('OpenCV indisponible')
        from fm_stock_exos import barre_inventaire,case_inventaire
        im=cv2.imread(str(Path(__file__).parent/'tests_retour_item_inventaire.jpg'))
        b=barre_inventaire(im)
        self.assertEqual(case_inventaire(b),(1290,308))
        self.assertEqual(case_inventaire(b,1),(1354,308))
        self.assertLess(case_inventaire(b)[0],1400) # ancien clic 1500 : quatrieme case vide

    def test_pose_confirmee_avant_ressources_et_pas_de_repli_fixe(self):
        from fm_stock_exos import case_inventaire
        ar=ast.parse('def runtime():\n'+activer_clics.RUNTIME_RAVITO)
        fn=next(n for n in ast.walk(ar) if isinstance(n,ast.FunctionDef) and n.name=='poser_item')
        for barre_ok,pose_ok in [(True,True),(True,False),(False,False)]:
            commandes=[];modes=[]
            ns=dict(capturer=lambda _:object(),mon={'left':100,'top':20},
                barre_inventaire=lambda _:(1260,207,251,24) if barre_ok else None,
                case_inventaire=case_inventaire,ravito={'jet_retour':{'vi':209}},
                clic_point=lambda *p:commandes.append(('clic',p)) or True,
                pause_auto=lambda _:True,ctrl_a=lambda:commandes.append(('ctrl_a',)),
                taper_texte=lambda t:commandes.append(('texte',t)),marquer=lambda *a:None,
                time=SimpleNamespace(monotonic=lambda:10.),log=lambda _:None,
                attendre_item_pose=lambda *a:commandes.append(('confirmation',)) or pose_ok,
                vider_recherche_inventaire=lambda:commandes.append(('vider',)) or True,
                trouver_gabarit=lambda *a:(1222,353),
                panneau=SimpleNamespace(mode=SimpleNamespace(set=modes.append),_mode_change=lambda:None))
            exec(compile(ast.Module(body=[fn],type_ignores=[]),'pose_item','exec'),ns)
            ns['poser_item'](None,None,'Anneau en Grithrill',0,True)
            clics=[c[1] for c in commandes if c[0]=='clic']
            if not barre_ok:self.assertEqual(clics,[])
            else:
                self.assertEqual(clics[:2],[(1390,239),(1390,328,True)])
                self.assertIn(('vider',),commandes)
                if pose_ok:
                    self.assertEqual(clics[-1],(1322,373))
                    self.assertLess(commandes.index(('confirmation',)),len(commandes)-1)
                else:self.assertEqual(len(clics),2)
            self.assertEqual(modes,[] if barre_ok and pose_ok else ['manuel'])

    def test_attente_pose_rejette_ancien_jet_different_et_tableau_vide(self):
        import queue
        from collections import deque
        ar=ast.parse('def runtime():\n'+activer_clics.RUNTIME_RAVITO)
        fn=next(n for n in ast.walk(ar) if isinstance(n,ast.FunctionDef) and n.name=='attendre_item_pose')
        for valeurs,attendu in [([None,None],False),([200,200],False),([209,209],True)]:
            clock=[2.];traces=[];mon={}
            lectures=deque([(mon,None,{'lignes':{'vi':{'val':209}}},None,.5)]) # avant le clic
            for i,v in enumerate(valeurs):
                lectures.append((mon,None,{'lignes':{'vi':{'val':v}}} if v is not None else None,None,2.1+i*.2))
            def pause(_):clock[0]+=.3;return True
            def prendre(**_):
                if not lectures:raise queue.Empty
                return lectures.popleft()
            ns=dict(mon=mon,ravito={},boite=SimpleNamespace(get=prendre,put=lambda _:None),queue=queue,
                time=SimpleNamespace(monotonic=lambda:clock[0]),pause_auto=pause,log=lambda _:None,
                diagnostic=SimpleNamespace(evenement=lambda *a,**kw:traces.append(a[0])))
            exec(compile(ast.Module(body=[fn],type_ignores=[]),'preuve_pose','exec'),ns)
            self.assertEqual(ns['attendre_item_pose'](1.,{'vi':209}),attendu)
            self.assertEqual(traces,['item_pose_confirme'] if attendu else [])

    def test_croix_inventaire_sur_capture_reelle_et_fenetre_deplacee(self):
        try:import cv2
        except ImportError:
            for p in (Path.home()/'AppData/Local/Packages').glob('PythonSoftwareFoundation.Python.*/LocalCache/local-packages/Python*/site-packages'):
                if (p/'cv2').exists():sys.path.append(str(p))
            try:import cv2
            except ImportError:self.skipTest('OpenCV indisponible')
        import numpy as np
        from fm_stock_exos import point_fermeture_inventaire
        im=cv2.imread(str(Path(__file__).parent/'tests_hdv_fermeture_inventaire.png'))
        self.assertEqual(point_fermeture_inventaire(im),(1365,132))
        deplace=np.zeros((im.shape[0]+60,im.shape[1]+80,3),np.uint8)
        deplace[30:30+im.shape[0],40:40+im.shape[1]]=im
        self.assertEqual(point_fermeture_inventaire(deplace),(1405,162))
        im[122:144,1355:1377]=0
        self.assertIsNone(point_fermeture_inventaire(im))
        self.assertIsNone(point_fermeture_inventaire(np.zeros_like(im)))

    def test_fermeture_hdv_clique_x_inventaire_et_attend_disparition(self):
        ar=ast.parse('def runtime():\n'+activer_clics.RUNTIME_RAVITO)
        fn=next(n for n in ast.walk(ar) if isinstance(n,ast.FunctionDef) and n.name=='fermer_hdv')
        for interrompu in (False,True):
            clock=[0.];clics=[];echaps=[];observations=[];traces=[]
            def pause(_):clock[0]+=.3;return not interrompu
            def ouvert(*_):observations.append(True);return len(observations)==1
            guide=SimpleNamespace(phase='achat',vu_hdv=True,fiche={'ancienne':True},_hdv_ouvert=ouvert)
            ns=dict(time=SimpleNamespace(monotonic=lambda:clock[0]),pause_auto=pause,dofus_actif=lambda:True,
                touche=echaps.append,capturer=lambda _:object(),mon={'left':100,'top':20},ocr=None,
                point_fermeture_inventaire=lambda _:(1365,132),clic_point=lambda *p:clics.append(p) or True,
                GUIDE=guide,diagnostic=SimpleNamespace(evenement=lambda *a:traces.append(a[0])),log=lambda _:None,
                panneau=SimpleNamespace(mode=SimpleNamespace(set=lambda _:None),_mode_change=lambda:None))
            exec(compile(ast.Module(body=[fn],type_ignores=[]),'fermeture_x','exec'),ns)
            self.assertEqual(ns['fermer_hdv'](),not interrompu)
            self.assertEqual(clics,[(1465,152)])
            self.assertEqual(echaps,[])
            self.assertEqual(guide.phase,'achat' if interrompu else 'retour')
            self.assertEqual(traces,[] if interrompu else ['hdv_fermeture_confirmee'])

    def test_popup_mauvais_lot_ou_mauvaise_rune_annule_sans_acheter(self):
        ar=ast.parse('def runtime():\n'+activer_clics.RUNTIME_RAVITO)
        fn=next(n for n in ast.walk(ar) if isinstance(n,ast.FunctionDef) and n.name=='acheter_lot')
        for conf in [('runedoterre',100,1333,133320),('runepavi',10,1350,13497)]:
            clock=[0.];clics=[];touches=[]
            f={'nom':'Rune Do Terre','qte':30,'lots':{10:13497},'ys':{10:320},'mx':240}
            def pause(_):clock[0]+=.2;return True
            ns=dict(ravito={},GUIDE=SimpleNamespace(regl={},fiche={'fiches':[f]}),
                mon={'left':0,'top':0},lire_fiche=lambda:(SimpleNamespace(shape=(1080,1920)),{'fiches':[f]}),
                pause_auto=pause,time=SimpleNamespace(time=lambda:clock[0]),capturer=lambda _:None,
                lire_dialogue=lambda _:conf,lire_confirmation=lambda _:None,
                clic_point=lambda *a:clics.append(a) or True,clic_fr=lambda *a:self.fail('Confirmation fixe'),
                touche=touches.append,norm=lambda s:s.lower().replace(' ',''),log=lambda _:None,
                diagnostic=SimpleNamespace(evenement=lambda *a,**kw:None),
                SUIVI=SimpleNamespace(evenement=lambda *a:None))
            exec(compile(ast.Module(body=[fn],type_ignores=[]),'popup_incorrect','exec'),ns)
            a={'rune':'Do terre','recherche':'Rune Do Terre','acheter':70,'prix':1734}
            self.assertIn(ns['acheter_lot'](a,'10'),('lecture',False))
            self.assertEqual(len(clics),1)
            self.assertEqual(touches,[0x1B])
            self.assertEqual(ns['ravito']['achete'],{})

    def test_enchainement_popup_direct_popup_retarde(self):
        ar=ast.parse('def runtime():\n'+activer_clics.RUNTIME_RAVITO)
        fns=[n for n in ast.walk(ar) if isinstance(n,ast.FunctionDef)
             and n.name in ('acheter_lot','confirmer_achat')]
        for scenario in ([True,False,False,True,False,False,False,False,False],
                         [False]*9,[True]*9):
            clock=[0.]; stock=[10]; pending=[None]; debut=[0.]; clics=[]; modes=[]
            guide=SimpleNamespace(regl={},fiche=None)
            ravito={}
            def fiche():
                return {'fiches':[{'nom':'Rune Do Terre','qte':stock[0],
                    'lots':{10:13497},'ys':{10:320},'mx':240}]}
            def lire():
                guide.fiche=fiche()
                return SimpleNamespace(shape=(1080,1920)),guide.fiche
            def pause(_):clock[0]+=.2;return True
            def clic(*xy):
                if xy==(900,600):
                    self.assertIsNotNone(pending[0])
                    stock[0]+=10;pending[0]=None;clics.append('confirmer')
                else:
                    self.assertIsNone(pending[0])
                    index=clics.count('acheter');clics.append('acheter');debut[0]=clock[0]
                    if scenario[index]:pending[0]=10
                    else:stock[0]+=10
                return True
            def dialogue(_):
                guide.fiche=fiche()
                # Le popup revient lentement alors qu'on a deja achete sans popup.
                if pending[0] and clock[0]-debut[0]>=1.2:
                    ravito['dialogue_pt']=(900,600)
                    return 'runedoterre',10,1350,13497
                return None
            ns=dict(ravito=ravito,GUIDE=guide,mon={'left':0,'top':0},lire_fiche=lire,
                pause_auto=pause,time=SimpleNamespace(time=lambda:clock[0],monotonic=lambda:clock[0]),
                capturer=lambda _:None,lire_dialogue=dialogue,lire_confirmation=lambda _:None,
                clic_point=clic,clic_fr=lambda *a:self.fail('Position fixe utilisee'),
                norm=lambda s:s.lower().replace(' ',''),log=lambda _:None,
                stock_exos=SimpleNamespace(valeurs={}),
                diagnostic=SimpleNamespace(evenement=lambda *a,**kw:None),
                panneau=SimpleNamespace(mode=SimpleNamespace(set=modes.append),_mode_change=lambda:None),
                SUIVI=SimpleNamespace(evenement=lambda *a:None))
            exec(compile(ast.Module(body=fns,type_ignores=[]),'flux_achats','exec'),ns)
            a={'rune':'Do terre','recherche':'Rune Do Terre','acheter':90,'prix':1734}
            for _ in scenario:self.assertTrue(ns['acheter_lot'](a,'10'))
            self.assertEqual(stock[0],100)
            self.assertEqual(ravito['achete']['Do terre'],90)
            self.assertEqual(clics.count('acheter'),9)
            self.assertEqual(clics.count('confirmer'),sum(scenario))
            self.assertEqual(modes,[])

    def test_prix_do_terre_chiffres_colles_sur_capture(self):
        try:import cv2
        except ImportError:
            for p in (Path.home()/'AppData/Local/Packages').glob('PythonSoftwareFoundation.Python.*/LocalCache/local-packages/Python*/site-packages'):
                if (p/'cv2').exists():sys.path.append(str(p))
            try:import cv2
            except ImportError:self.skipTest('OpenCV indisponible')
        import numpy as np
        for fichier in ('assistant_sans_clic.py','fm_avec_clics.py'):
            ar=ast.parse(Path(fichier).read_text(encoding='utf-8'))
            guide=next(n for n in ar.body if isinstance(n,ast.ClassDef) and n.name=='Guide')
            ns=dict(cv2=cv2,np=np,re=re,time=__import__('time'),difflib=difflib,
                    BILAN=SimpleNamespace(note=lambda *a,**kw:None),norm=lambda s:s.lower().replace(' ',''))
            exec(compile(ast.Module(body=[guide],type_ignores=[]),'prix_reel','exec'),ns)
            im=cv2.imread(str(Path(__file__).parent/'tests_hdv_do_terre.jpg'))
            g=ns['Guide']();g._nom_hdv=lambda *a:'Rune Do Terre';g._voulue=lambda _:True
            f,_,_,_=g._fiche_rapide(im,im.min(axis=2),SimpleNamespace(
                ligne=lambda *a,**kw:self.fail('Le prix reel doit etre lu sans OCR de secours')))
            self.assertEqual(f[0]['lots'],{1:1250,10:13497,100:133320,1000:1329000})
            mx,my=f[0]['mx'],f[0]['my'];y=int(my+139.7)
            prix=im[y-11:y+11,int(mx+60):int(mx+184)].min(axis=2)
            self.assertEqual(g._nombre_hdv(prix),(13497,True))
            # Variante 13499 : copie du vrai glyphe 9 sur le 7 de la capture.
            # Le raccord 4/9 est deja colle dans cette capture reelle.
            prix99=prix.copy();prix99[:,113:120]=prix[:,106:113]
            for qualite in (75,85,90,95,100):
                _,jpeg=cv2.imencode('.jpg',prix99,[cv2.IMWRITE_JPEG_QUALITY,qualite])
                self.assertEqual(g._nombre_hdv(cv2.imdecode(jpeg,0)),(13499,True))
            for relecture,attendu in [('13497',13497),('',None)]:
                g=ns['Guide']();g._nom_hdv=lambda *a:'Rune Do Terre';g._voulue=lambda _:True
                lire=g._nombre_hdv
                g._nombre_hdv=lambda z:(134999,False) if np.array_equal(z,prix) else lire(z)
                f,_,_,_=g._fiche_rapide(im,im.min(axis=2),SimpleNamespace(ligne=lambda *a,**kw:relecture))
                self.assertEqual(f[0]['lots'].get(10),attendu)
                self.assertEqual(f[0]['qte'],30)
            g=ns['Guide']();g._nom_hdv=lambda *a:'Rune Do Terre';g._voulue=lambda _:True
            im=cv2.imread(str(Path(__file__).parent/'tests_hdv_confirmation_do_terre.png'))
            _,dial,_,_=g._fiche_rapide(im,im.min(axis=2),SimpleNamespace(ligne=lambda *a,**kw:''))
            self.assertEqual(dial,{'nom':'Rune Do Terre','n':100,'total':133320,
                                   'prix':1333,'pt':(913,531)})

    def test_ancien_plan_ra_vi_1_annule_si_stock457_relu(self):
        for fichier in ('assistant_sans_clic.py','fm_avec_clics.py'):
            ar=ast.parse(Path(fichier).read_text(encoding='utf-8'))
            fn=next(n for n in ar.body if isinstance(n,ast.FunctionDef) and n.name=='stocks_plan_suffisants')
            ns=dict(STOCK_ALERTE=20,STOCK_CIBLE=100)
            exec(compile(ast.Module(body=[fn],type_ignores=[]),'plan_stock','exec'),ns)
            plan=[{'cle':'vi/ra','stock':1,'acheter':100}]
            for n,rate,occulte,attendu in [(457,0,False,True),(1,0,False,False),(None,0,False,False),
                                           (457,1,False,False),(457,0,True,False)]:
                etat={'lignes':{'vi':{'stock':{'ra':n},'rate':rate,'occulte':occulte}}}
                self.assertEqual(ns['stocks_plan_suffisants'](plan,etat,{}),attendu)
            guide=next(n for n in ar.body if isinstance(n,ast.ClassDef) and n.name=='Guide')
            etape=next(n for n in guide.body if isinstance(n,ast.FunctionDef) and n.name=='_etape')
            ns['log']=lambda _:None
            exec(compile(ast.Module(body=[etape],type_ignores=[]),'guide_stock','exec'),ns)
            g=SimpleNamespace(phase='sortie',liste=plan,regl={},vu_hdv=False,
                              _lire_metier=lambda *a:None)
            etat={'lignes':{'vi':{'stock':{'ra':457},'dispo':['ra']}}}
            self.assertIsNone(ns['_etape'](g,None,etat,[],None))
            self.assertIsNone(g.phase)
            self.assertEqual(g.liste,[])

    def test_capture_stock_ra_vi_457(self):
        try:import cv2
        except ImportError:
            for p in (Path.home()/'AppData/Local/Packages').glob('PythonSoftwareFoundation.Python.*/LocalCache/local-packages/Python*/site-packages'):
                if (p/'cv2').exists():sys.path.append(str(p))
            try:import cv2
            except ImportError:self.skipTest('OpenCV indisponible')
        import numpy as np
        noms={'trouver_lignes','_lignes_de_couleur','_trouver_lignes','_completer',
              'encre','_runs','_canevas','Chiffres','_stocks'}
        for fichier in ('assistant_sans_clic.py','fm_avec_clics.py'):
            ar=ast.parse(Path(fichier).read_text(encoding='utf-8'))
            ns=dict(cv2=cv2,np=np,os=os,ICI=str(Path(__file__).parent),CW=32,CH=28,
                    COLS={'base':.810,'pa':.880,'ra':.947},_COUL=[None],_GEOM=[[]],
                    _COUL_REF=[None],_ABSENT={},_OCCULTES=set())
            exec(compile(ast.Module(body=[n for n in ar.body if getattr(n,'name',None) in noms],
                                    type_ignores=[]),'stock_capture','exec'),ns)
            im=cv2.imread(str(Path(__file__).parent/'tests_stock_ra_vi_457.png'))
            self.assertIsNotNone(im)
            rect=ns['trouver_lignes'](im)[0]
            self.assertEqual(ns['_stocks'](im,rect,['base','pa','ra'],ns['Chiffres']()),
                             {'base':206,'pa':459,'ra':457})

    def test_achat_partiel_nest_pas_annonce_complet(self):
        ar=ast.parse('def runtime():\n'+activer_clics.RUNTIME_RAVITO)
        fn=next(n for n in ast.walk(ar) if isinstance(n,ast.FunctionDef) and n.name=='noter_achat_incomplet')
        traces=[]
        ns=dict(ravito={'achete':{'Do terre':20}},log=lambda _:None,
                diagnostic=SimpleNamespace(evenement=lambda *a,**kw:traces.append(kw)))
        exec(compile(ast.Module(body=[fn],type_ignores=[]),'achat_partiel','exec'),ns)
        self.assertTrue(ns['noter_achat_incomplet']({'rune':'Do terre','acheter':90}))
        self.assertEqual(traces[0]['reste'],70)
        ns['ravito']['achete']['Do terre']=90
        self.assertFalse(ns['noter_achat_incomplet']({'rune':'Do terre','acheter':90}))

    def test_fermeture_hdv_echap_et_confirmation_avant_retour(self):
        arbre=ast.parse('def runtime():\n'+activer_clics.RUNTIME_RAVITO)
        fn=next(n for n in ast.walk(arbre) if isinstance(n,ast.FunctionDef) and n.name=='fermer_hdv')
        for sequence, attendu,echaps in [([True,False,True,False,False],True,1),([True],False,2),([True]*5+[False,False],True,2)]:
            clock=[0.]; touches=[]; lectures=[]; modes=[]; traces=[]
            def pause(_):clock[0]+=.3;return True
            def ouvert(*a):
                i=min(len(lectures),len(sequence)-1);lectures.append(i);return sequence[i]
            guide=SimpleNamespace(phase='achat',vu_hdv=True,fiche={'ancienne':True},_hdv_ouvert=ouvert)
            ns=dict(point_fermeture_inventaire=lambda _:None,time=SimpleNamespace(monotonic=lambda:clock[0]),pause_auto=pause,dofus_actif=lambda:True,
                    touche=lambda vk:touches.append(vk),capturer=lambda _:object(),mon={},ocr=None,
                    GUIDE=guide,diagnostic=SimpleNamespace(evenement=lambda *a:traces.append(a[0])),
                    panneau=SimpleNamespace(mode=SimpleNamespace(set=modes.append),_mode_change=lambda:None),log=lambda _:None)
            exec(compile(ast.Module(body=[fn],type_ignores=[]),'fermeture_isolee','exec'),ns)
            self.assertEqual(ns['fermer_hdv'](),attendu)
            self.assertEqual(touches,[0x1B]*echaps)
            self.assertEqual(guide.phase,'retour' if attendu else 'achat')
            self.assertEqual(modes,[] if attendu else ['manuel'])
            if attendu:
                self.assertEqual(len(lectures),len(sequence))
                self.assertEqual(traces,['hdv_fermeture_confirmee'])
        acheter=next(n for n in ast.walk(arbre) if isinstance(n,ast.FunctionDef) and n.name=='acheter_liste')
        self.assertNotIn('clic_fr(928 / 1366',ast.unparse(acheter))
        self.assertIn('fermer_hdv()',ast.unparse(acheter))

    def test_fiche_ga_pa_prix_moyen_ignore_graphique(self):
        try:import cv2
        except ImportError:
            for p in (Path.home()/'AppData/Local/Packages').glob('PythonSoftwareFoundation.Python.*/LocalCache/local-packages/Python*/site-packages'):
                if (p/'cv2').exists():sys.path.append(str(p))
            try:import cv2
            except ImportError:self.skipTest('OpenCV indisponible')
        import numpy as np
        for fichier in ('assistant_sans_clic.py','fm_avec_clics.py'):
            ar=ast.parse(Path(fichier).read_text(encoding='utf-8'))
            guide=next(n for n in ar.body if isinstance(n,ast.ClassDef) and n.name=='Guide')
            ns=dict(cv2=cv2,np=np,re=re,time=__import__('time'),difflib=difflib,
                    BILAN=SimpleNamespace(note=lambda *a,**kw:None),norm=lambda s:s.lower().replace(' ',''))
            exec(compile(ast.Module(body=[guide],type_ignores=[]),'lecture_hdv','exec'),ns)
            g=ns['Guide']()
            # Isole les nombres reels ; aucun moteur OCR ni cache de noms modifie.
            g._nom_hdv=lambda *a:'Rune Ga Pa'
            g._voulue=lambda _:True
            im=cv2.imread(str(Path(__file__).parent/'tests_hdv_ga_pa.png'))
            self.assertIsNotNone(im)
            fiches,_,_,_=g._fiche_rapide(im,im.min(axis=2),SimpleNamespace(ligne=lambda *a,**kw:''))
            self.assertEqual(len(fiches),1)
            f=fiches[0]
            self.assertEqual(f['moyen'],29603)
            self.assertEqual(f['qte'],0)
            self.assertEqual(f['lots'],{1:29898,10:319992,100:3099965,1000:33999999})
            # Le label 100 est mal lu comme 10 : ne jamais ecraser le vrai prix du lot 10.
            mx,my=round(f['mx']),round(f['my'])
            y10=round(my+101.5+38.2)
            y100=round(my+101.5+38.2*2)
            im[y100-11:y100+11,mx-22:mx+42]=im[y10-11:y10+11,mx-22:mx+42]
            fiches,_,_,_=g._fiche_rapide(im,im.min(axis=2),SimpleNamespace(ligne=lambda *a,**kw:''))
            self.assertEqual(fiches[0]['lots'][10],319992)
            self.assertNotIn(100,fiches[0]['lots'])

    def test_calque_masque_pendant_ravito_et_restaure_ensuite(self):
        arbre=ast.parse('def runtime():\n'+activer_clics.RUNTIME_RAVITO)
        fn=next(n for n in ast.walk(arbre) if isinstance(n,ast.FunctionDef) and n.name=='calque_ravitaillement')
        actions=[]
        ns=dict(ravito={},root=SimpleNamespace(withdraw=lambda:actions.append('cacher'),
                deiconify=lambda:actions.append('montrer'),update_idletasks=lambda:None))
        exec(compile(ast.Module(body=[fn],type_ignores=[]),'calque_isole','exec'),ns)
        for actif in (True,True,False,False):ns['calque_ravitaillement'](actif)
        self.assertEqual(actions,['cacher','montrer'])

    def test_menu_hdv_sur_capture_reelle(self):
        try:
            import cv2
        except ImportError:
            candidats=(Path.home()/'AppData/Local/Packages').glob('PythonSoftwareFoundation.Python.*/LocalCache/local-packages/Python*/site-packages')
            for p in candidats:
                if (p/'cv2').exists():sys.path.append(str(p))
            try:import cv2
            except ImportError:self.skipTest('OpenCV indisponible')
        arbre=ast.parse('def runtime():\n'+activer_clics.RUNTIME_RAVITO)
        fn=next(n for n in ast.walk(arbre) if isinstance(n,ast.FunctionDef) and n.name=='menu_hdv_consulter')
        racine=Path(__file__).resolve().parent
        ns=dict(cv2=cv2,os=os,ICI=str(racine))
        exec(compile(ast.Module(body=[fn],type_ignores=[]),'menu_isole','exec'),ns)
        im=cv2.imread(str(racine/'tests_hdv_menu.png'))
        self.assertIsNotNone(im)
        pos=ns['menu_hdv_consulter'](im)
        self.assertIsNotNone(pos)
        self.assertTrue(39<pos[0]<228 and 69<pos[1]<93)
        im[43:93,39:228]=0
        self.assertIsNone(ns['menu_hdv_consulter'](im))

    def test_activation_sauvegardee_sans_perdre_seuils(self):
        arbre=ast.parse(Path('assistant_sans_clic.py').read_text(encoding='utf-8'))
        fn=next(n for n in ast.walk(arbre) if isinstance(n,ast.FunctionDef) and n.name=='sauver_stock')
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as d:
            ns=dict(F_STOCK=str(Path(d)/'stock.json'),json=json,time=__import__('time'),
                    POIDS={'pa':100},recherche_rune=lambda *a:'Rune Ga Pa',log=lambda _:None)
            exec(compile(ast.Module(body=[fn],type_ignores=[]),'sauvegarde_stock','exec'),ns)
            panneau=SimpleNamespace(stock_regl={'pa/base':{'alerte':5,'cible':10,'prix':100,'actif':True}})
            row={'alerte':'5','cible':'10','prix':'100','actif':False,'rech':'Rune Ga Pa'}
            self.assertTrue(ns['sauver_stock'](panneau,{'pa/base':row},20)[1])
            self.assertEqual(json.loads(Path(ns['F_STOCK']).read_text())['pa/base'],
                             {'alerte':5,'cible':10,'prix':100,'actif':False})
            row['actif']=True
            self.assertTrue(ns['sauver_stock'](panneau,{'pa/base':row},20)[1])
            self.assertTrue(panneau.stock_regl['pa/base']['actif'])

    def test_desactivation_et_exos_absents_du_tableau(self):
        for fichier in ('assistant_sans_clic.py', 'fm_avec_clics.py'):
            arbre=ast.parse(Path(fichier).read_text(encoding='utf-8'))
            fns=[n for n in arbre.body if isinstance(n,ast.FunctionDef) and n.name in ('lignes_stock','liste_achats','_liste_achats_brut')]
            ns=dict(POIDS={'fo':1,'pa':100,'pm':90,'po':51,'invo':30,'do_per_so':15},
                    tailles=lambda s:['base'], _RUNES_VUES=set(),_ACHATS_PREC=[],
                    STOCK_ALERTE=20,STOCK_CIBLE=100,nom_rune=lambda s,t:s,
                    recherche_rune=lambda s,t,r:s, PETITS_EXOS=('agi','fo','int','cha','ini'), RUNES_SAUTEES={}, time=__import__('time'), SAUT_DUREE=1800)
            exec(compile(ast.Module(body=fns,type_ignores=[]),'stock_isole','exec'),ns)
            naturelles={'fo':{'dispo':['base'],'stock':{'base':5}}}
            original=copy.deepcopy(naturelles)
            for exo in ('pa','pm','po','invo','do_per_so'):
                vue=ns['lignes_stock'](naturelles,{'exos':{exo:1}}, {exo:0})
                inconnu=ns['lignes_stock'](naturelles,{'exos':{exo:1}})
                self.assertEqual(ns['liste_achats'](inconnu,{'fo/base':{'actif':False}}),[])
                regl={'fo/base':{'actif':False},exo+'/base':{'alerte':1,'cible':10,'prix':100}}
                achats=ns['liste_achats'](vue,regl)
                self.assertEqual([a['rune'] for a in achats],[exo])
                self.assertTrue(achats[0]['verifier_stock'])
                self.assertEqual(achats[0]['lots'],'1×10')
                regl[exo+'/base']['actif']=False
                self.assertEqual(ns['liste_achats'](vue,regl),[])
            self.assertEqual(naturelles,original)
            self.assertEqual(ns['lignes_stock'](naturelles,{'exos':{'pa':0}}),naturelles)

    def test_quantite_exo_inconnue_est_verifiee_avant_achat(self):
        arbre=ast.parse('def runtime():\n'+activer_clics.RUNTIME_RAVITO)
        fn=next(n for n in ast.walk(arbre) if isinstance(n,ast.FunctionDef) and n.name=='preparer_stock_exo')
        modes=[]
        ns=dict(norm=lambda x:x.lower(),log=lambda _:None,
                panneau=SimpleNamespace(mode=SimpleNamespace(set=modes.append),_mode_change=lambda:None),
                diagnostic=SimpleNamespace(evenement=lambda *a,**kw:None))
        exec(compile(ast.Module(body=[fn],type_ignores=[]),'besoin_exo','exec'),ns)
        for stock,nom,attendu in [(0,'Rune Ga Pa',10),(3,'Rune Ga Pa',10),(5,'Rune Ga Pa',0),
                                  (50,'Rune Ga Pa',0),(None,'Rune Ga Pa',None),(0,'Rune Pa Vi',None)]:
            a={'rune':'PA','recherche':'Rune Ga Pa','alerte':5,'cible':10,'verifier_stock':True}
            ok=ns['preparer_stock_exo'](a,{'fiches':[{'nom':nom,'qte':stock}]})
            self.assertEqual(ok,attendu is not None)
            if ok:self.assertEqual(a['acheter'],attendu)

    def test_prix_avant_tout_clic_premier_achat_et_suivants(self):
        arbre = ast.parse('def runtime():\n' + activer_clics.RUNTIME_RAVITO)
        fn = next(n for n in ast.walk(arbre) if isinstance(n, ast.FunctionDef) and n.name == 'acheter_lot')
        class PremierClic(Exception):
            pass
        base = {'nom':'Rune Pa Vi', 'qte':5, 'lots':{10:1000}, 'ys':{10:100}, 'mx':100}
        for direct in (False, True):
            for cas in ('ok','limite','cher','recupere','absent','nan','negatif','autre','erreur','plafond_absent','stock_absent'):
                with self.subTest(direct=direct,cas=cas):
                    f = copy.deepcopy(base); clics=[]; modes=[]; traces=[]; lectures=[]
                    prix = 100
                    if cas == 'ok': f['lots'][10]=999
                    if cas in ('cher','recupere'): f['lots'][10]=1001
                    if cas == 'absent': f['lots']={}
                    if cas == 'nan': f['lots'][10]=float('nan')
                    if cas == 'negatif': f['lots'][10]=-1
                    if cas == 'autre': f['nom']='Rune Ga Pa'
                    if cas == 'stock_absent': f['qte']=None
                    if cas == 'plafond_absent': prix=0
                    def lire():
                        lectures.append(True)
                        if cas=='recupere' and len(lectures)>1:f['lots'][10]=999
                        if cas == 'erreur': raise ValueError('OCR')
                        return SimpleNamespace(shape=(1080,1920)), {'fiches':[f]}
                    def clic(*args):
                        clics.append(args)
                        raise PremierClic()
                    ns=dict(ravito={'direct':direct}, GUIDE=SimpleNamespace(regl={}),pause_auto=lambda _:True,
                            lire_fiche=lire,norm=lambda x:x.lower(),log=lambda _:None,
                            diagnostic=SimpleNamespace(evenement=lambda *a,**kw:traces.append(a[0])),
                            SUIVI=SimpleNamespace(evenement=lambda *a:None),
                            panneau=SimpleNamespace(mode=SimpleNamespace(set=modes.append),_mode_change=lambda:None),
                            mon={'left':0,'top':0},clic_point=clic,clic_fr=clic)
                    exec(compile(ast.Module(body=[fn],type_ignores=[]),'prix_isole','exec'),ns)
                    # Une ancienne fiche bon marche ne doit jamais remplacer la lecture actuelle.
                    a={'rune':'Pa Vi','recherche':'Rune Pa Vi','acheter':10,'prix':prix,'_f':copy.deepcopy(base)}
                    if cas in ('ok','limite','recupere'):
                        with self.assertRaises(PremierClic): ns['acheter_lot'](a,'10')
                        self.assertEqual(len(clics),1)
                    else:
                        self.assertIn(ns['acheter_lot'](a,'10'),(None,False))
                        self.assertEqual(clics,[])
                    self.assertEqual(len(lectures),3 if cas=='cher' else (2 if cas=='recupere' else 1))

    def executer_confirmation(self, lectures, interruption=False):
        arbre = ast.parse('def runtime():\n' + activer_clics.RUNTIME_RAVITO)
        fn = next(n for n in ast.walk(arbre) if isinstance(n, ast.FunctionDef) and n.name == 'confirmer_achat')
        clock = [0.]
        trace = []; modes = []; appels = []
        def pause(_):
            clock[0] += .2
            return not interruption
        def lire():
            i = min(len(appels), len(lectures)-1)
            appels.append(i)
            nom, qte = lectures[i]
            return None, {'fiches': [{'nom': nom, 'qte': qte}]}
        ns = dict(stock_exos=SimpleNamespace(valeurs={}), time=SimpleNamespace(monotonic=lambda: clock[0]), pause_auto=pause,
                  lire_fiche=lire, norm=lambda s:s.lower(), difflib=difflib,
                  diagnostic=SimpleNamespace(evenement=lambda *a, **kw:trace.append(a[0])),
                  panneau=SimpleNamespace(mode=SimpleNamespace(set=modes.append), _mode_change=lambda:None),
                  log=lambda _:None)
        exec(compile(ast.Module(body=[fn], type_ignores=[]), 'achat_isole', 'exec'), ns)
        a = {'rune':'vi/pa', 'recherche':'Rune Pa Vi'}
        resultat = ns['confirmer_achat'](a, 5, 10)
        return resultat, trace, modes, appels, a

    def test_deux_lectures_exactes_requises(self):
        ok, trace, modes, appels, a = self.executer_confirmation([
            ('Rune Pa Vi', 15), ('Rune Pa Vi', 5), ('Rune Pa Vi', 15), ('Rune Pa Vi', 15)])
        self.assertTrue(ok)
        self.assertEqual(len(appels), 4)
        self.assertEqual(trace, ['achat_confirme'])
        self.assertEqual(modes, [])
        self.assertEqual(a['_attendu'], 15)

    def test_absence_achat_mauvais_nom_ou_quantite_arrete(self):
        for nom, qte in [('Rune Pa Vi',5), ('Rune Ga Pa',15), ('Rune Pa Vi',16), ('Rune Pa Vi',None)]:
            with self.subTest(nom=nom,qte=qte):
                ok, trace, modes, _, a = self.executer_confirmation([(nom,qte)])
                self.assertFalse(ok)
                self.assertEqual(trace, ['achat_non_confirme'])
                self.assertEqual(modes, ['manuel'])
                self.assertNotIn('_attendu', a)

    def test_interruption_ne_confirme_pas(self):
        ok, trace, _, appels, _ = self.executer_confirmation([('Rune Pa Vi',15)], True)
        self.assertFalse(ok)
        self.assertEqual(appels, [])
        self.assertNotIn('achat_confirme', trace)


if __name__ == '__main__':
    unittest.main()
