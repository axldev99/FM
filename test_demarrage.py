import ast
from pathlib import Path
from types import SimpleNamespace
import unittest

import activer_clics
from fm_demarrage import (DemarrageAtelier, DESTINATION, COMMANDE,
                         metier_pour_objet,position_depuis_texte,profil_correspond,profil_incompatible,texte_confirmation_trajet)


class DemarrageTests(unittest.TestCase):
    def test_preselection_hors_atelier_charge_toutes_lignes_sans_modifier_profil(self):
        import copy
        class Case:
            def __init__(self,val=''):self.val=str(val)
            def get(self):return self.val
            def set(self,v):self.val=v
            def current(self,i):self.val=i
            def config(self,**kw):
                if 'text' in kw:self.val=str(kw['text'])
        it={'nom':'Anneau exo PA','nom_jeu':'Anneau en Grithrill','metier_depart':'joaillomager',
            'sig':[['vi',201,250],['fo',31,50]],'cibles':{'vi':240,'fo':48},'mins':{'fo':47},
            'remonte':{'vi':230},'regles':{'vi':{'pa':[0,235]},'fo':{'pa':[0,47]}},'exos':{'pa':1}}
        original=copy.deepcopy(it)
        for fichier in ('assistant_sans_clic.py','fm_avec_clics.py'):
            ar=ast.parse(Path(fichier).read_text(encoding='utf8'))
            cls=next(n for n in ar.body if isinstance(n,ast.ClassDef) and n.name=='Panneau')
            fns=[n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name in ('appliquer','charger_preselection')]
            ns=dict(POIDS={'vi':.2,'fo':1,'pa':100},nom_code=lambda s:s,tailles=lambda _:['base','pa','ra'],
                    PETITS_EXOS=('agi','fo','int','cha','ini'))
            exec(compile(ast.Module(body=fns,type_ignores=[]),'profil_hors_atelier','exec'),ns)
            messages=[]
            p=SimpleNamespace(tableau_visible=False,grille=SimpleNamespace(winfo_children=lambda:[]),
                _entetes=lambda:None,rangs={},nom=Case(),finition=Case(),plan_b=Case(),petit_exo=Case(),codes_exo=['pa'],
                mode=Case('automatique'),_mode_change=lambda:None,VERT='vert',ROUGE='rouge',
                etat=SimpleNamespace(config=lambda **kw:messages.append(kw)),_conf=lambda it:copy.deepcopy(it))
            p._met=lambda case,v:case.set('' if v is None else str(v))
            def rang(s,nom,mini,maxi,val,exo=False):
                p.rangs[s]=dict(exo=exo,max=maxi,obj=Case(),tol=Case(),rem=Case(),actuel=Case(val),
                    plages={t:(Case(),Case()) for t in ['base','pa','ra']})
            p._rang=rang
            p.ajouter_exo=lambda s,q:rang(s,s,0,0,0,True) or p._met(p.rangs[s]['obj'],q)
            p.retirer_exo=lambda s:p.rangs.pop(s)
            p.appliquer=lambda it:ns['appliquer'](p,it)
            ns['charger_preselection'](p,it)
            self.assertEqual(set(p.rangs),{'vi','fo','pa'})
            self.assertEqual(p.rangs['vi']['obj'].get(),'240')
            self.assertEqual(p.rangs['fo']['tol'].get(),'47')
            self.assertEqual(p.rangs['vi']['rem'].get(),'230')
            self.assertEqual([c.get() for c in p.rangs['vi']['plages']['pa']],['0','235'])
            self.assertTrue(all(r['actuel'].get()=='?' for r in p.rangs.values()))
            self.assertEqual(p.conf,it)
            self.assertEqual(it,original)
            self.assertIn('Objet prévu au prochain F1',messages[-1]['text'])

    def test_selection_dans_atelier_ne_reconstruit_pas_jet_actuel(self):
        for fichier in ('assistant_sans_clic.py','fm_avec_clics.py'):
            ar=ast.parse(Path(fichier).read_text(encoding='utf8'))
            cls=next(n for n in ar.body if isinstance(n,ast.ClassDef) and n.name=='Panneau')
            fn=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='charger_preselection')
            appels=[];p=SimpleNamespace(tableau_visible=True,appliquer=appels.append,
                conf={'actuelle':True},etat=SimpleNamespace(config=lambda **kw:None),ROUGE='rouge')
            ns={};exec(compile(ast.Module(body=[fn],type_ignores=[]),'profil_en_atelier','exec'),ns)
            ns['charger_preselection'](p,{'nom':'A'})
            self.assertEqual(appels,[{'nom':'A'}]);self.assertEqual(p.conf,{'actuelle':True})

    def test_coordonnees_signees_et_ambiguites(self):
        for texte,attendu in [('Port de givre -83,-40 Niveau 80',DESTINATION),
                              ('−83, −40',DESTINATION),('3; -5',(3,-5)),
                              ('- 83, - 40 - Niveau 80',DESTINATION),
                              ('Niveau 80 55%',None),('-83,-40 et 1,2',None)]:
            self.assertEqual(position_depuis_texte(texte),attendu)

    def test_metier_explicite_et_noms_connus(self):
        for nom,m in [('Anneau en Grithrill','joaillomager'),('Sandales circulaires du Kimbo','cordomager'),
                      ('Cape inconnue','costumager'),("Marteau R’ture",'forgemager'),
                      ('Bâton inconnu','sculptemager'),('Bouclier inconnu','facomager')]:
            self.assertEqual(metier_pour_objet(nom),m)
        self.assertIsNone(metier_pour_objet('Psikopompe'))
        self.assertEqual(metier_pour_objet('Psikopompe','costumager'),'costumager')

    def test_arrivee_deux_captures_fraiches_et_timeout(self):
        d=DemarrageAtelier();d.choisir('A');d.trajet_envoye(10.)
        for capture,now in [(9.,10.),(11.,15.),(20.,12.)]:
            self.assertFalse(d.observer_position(DESTINATION,capture,now))
        self.assertFalse(d.observer_position(DESTINATION,11.,11.1))
        self.assertFalse(d.observer_position(DESTINATION,11.,11.2))
        self.assertTrue(d.observer_position(DESTINATION,12.,12.1))
        self.assertEqual(d.phase,'ATELIER')
        self.assertTrue(d.expire(911))
        d.choisir('B');self.assertEqual(d.phase,'VERIFICATION')

    def contexte(self,position=(0,0),nom='Anneau en Grithrill',guide_phase=None):
        clock=[10.];modes=['automatique'];actions=[];position_vue=[position];messages=[]
        fiche={'nom':'Objectif A','nom_jeu':nom,'sig':[['vi',201,250]],'cibles':{'vi':240}}
        p=SimpleNamespace(nom=SimpleNamespace(get=lambda:'Objectif A'),items=[fiche],nom_jeu=nom,
            mode=SimpleNamespace(get=lambda:modes[0],set=lambda m:modes.__setitem__(0,m)),
            _mode_change=lambda:None,_conf=lambda f:{'cibles':f['cibles']})
        g=SimpleNamespace(phase=guide_phase,liste=[],vu_hdv=False,dedans=lambda _:False,
            etape=lambda *a:('RAVITAILLEMENT 6/7 : ouvre atelier',(100,100)))
        def message(t,erreur=False):
            messages.append(t)
            if erreur:modes[0]='manuel'
        def pause(_):clock[0]+=.15;return True
        ns=dict(demarrage=DemarrageAtelier(),securite={},METIERS={'joaillomager':'joaillomager','forgemager':'multi'},panneau=p,GUIDE=g,confirmation=SimpleNamespace(attente=None),
            confirmation_navigation=SimpleNamespace(attente=None),stock_session=['ancien'],
            verifier_mode_clic=lambda:None,metier_pour_objet=metier_pour_objet,profil_correspond=profil_correspond,profil_incompatible=profil_incompatible,
            time=SimpleNamespace(monotonic=lambda:clock[0]),message_demarrage=message,
            calque_ravitaillement=lambda _:None,mon={'left':0,'top':0},ocr=None,
            point_fermeture_inventaire=lambda _:None,position_demarrage=lambda _:position_vue[0],
            point_saisie_chat=lambda _:(200,1000),clic_point=lambda *p:actions.append(('chat',p)) or True,
            capturer=lambda _:actions.append(('capture',)),
            popup_confirmation_trajet=lambda _:False,
            touche=lambda *a:actions.append(('touche',a)) or True,pause_auto=pause,
            ctrl_a=lambda:actions.append(('ctrl_a',)),taper_texte=lambda t:actions.append(('texte',t)),
            SUIVI=SimpleNamespace(),ravito={},COMMANDE=COMMANDE,DESTINATION=DESTINATION,
            auto_ravitaillement=lambda *a:actions.append(('guide',)))
        ar=ast.parse('def runtime():\n'+activer_clics.RUNTIME_DEMARRAGE)
        fn=next(n for n in ast.walk(ar) if isinstance(n,ast.FunctionDef) and n.name=='preparer_demarrage')
        exec(compile(ast.Module(body=[fn],type_ignores=[]),'demarrage_isole','exec'),ns)
        def taper_chat():
            if not ns['touche'](0x20,.06):return False
            ns['ctrl_a']();ns['taper_texte'](COMMANDE)
            return True
        ns['taper_commande_chat']=taper_chat
        ns['verifier_commande_chat']=lambda:True
        def tour(lecture=None,capture=None):
            clock[0]+=1.1
            return ns['preparer_demarrage'](object(),lecture,clock[0] if capture is None else capture)
        return ns,tour,actions,modes,position_vue,messages,clock

    def test_trajet_unique_arrivee_guide_pose_et_stock(self):
        ns,tour,actions,modes,pos,_,_=self.contexte()
        self.assertTrue(tour())
        for _ in range(3):self.assertTrue(tour())
        self.assertEqual([a for a in actions if a[0]=='texte'],[('texte',COMMANDE)])
        pos[0]=DESTINATION
        self.assertTrue(tour());self.assertTrue(tour())
        self.assertEqual(ns['demarrage'].phase,'ATELIER')
        self.assertTrue(tour());self.assertIn(('guide',),actions)
        e={'lignes':{'vi':{'min':201,'max':250,'val':209}}}
        self.assertTrue(tour(e));self.assertFalse(tour(e))
        self.assertEqual(ns['demarrage'].phase,'PRET')
        self.assertIsNone(ns['stock_session'][0])
        self.assertEqual(ns['panneau'].profil_demarrage['nom'],'Objectif A')
        self.assertEqual(modes,['automatique'])

    def test_deja_dans_atelier_pas_de_travel(self):
        ns,tour,actions,_,_,_,_=self.contexte(position=DESTINATION)
        tour();tour();tour()
        self.assertEqual(ns['demarrage'].phase,'ATELIER')
        self.assertEqual(actions,[('capture',),('capture',),('guide',)])

    def test_arrivee_relit_capture_locale_avant_delegation_porte(self):
        ns,tour,actions,_,pos,_,clock=self.contexte()
        tour()
        image_arrivee=object()
        ns['capturer']=lambda _:image_arrivee
        def lire_position(image):
            self.assertIs(image,image_arrivee)
            clock[0]+=.3
            return DESTINATION
        ns['position_demarrage']=lire_position
        # L'ancienne image est encore recevable a l'entree, mais expire
        # pendant l'OCR : seule la capture locale fraiche doit etre comptee.
        for _ in range(2):
            tour(capture=clock[0]-.6)
        self.assertEqual(ns['demarrage'].phase,'ATELIER')
        tour()
        self.assertIn(('guide',),actions)

    def test_lecture_position_ligne_seule_et_secours_journalise(self):
        import numpy as np
        ar=ast.parse('def runtime():\n'+activer_clics.RUNTIME_DEMARRAGE)
        fn=next(n for n in ast.walk(ar) if isinstance(n,ast.FunctionDef) and n.name=='position_demarrage')
        images=[];evenements=[]
        ocr=SimpleNamespace(ligne=lambda z:images.append(z.shape) or '- 83, - 40 - Niveau 80',
                            tout=lambda z:self.fail('Pas de detection complete si la ligne est lisible'))
        ns=dict(ocr=ocr,position_depuis_texte=position_depuis_texte,
                diagnostic=SimpleNamespace(evenement=lambda *a,**kw:evenements.append(kw)))
        exec(compile(ast.Module(body=[fn],type_ignores=[]),'lecture_position','exec'),ns)
        image=np.zeros((1080,1920,3),dtype=np.uint8)
        self.assertEqual(ns['position_demarrage'](image),DESTINATION)
        self.assertEqual(images,[(23,307,3)])
        ocr.ligne=lambda z:'illisible'
        ocr.tout=lambda z:[('-81, -40',0,0)]
        self.assertEqual(ns['position_demarrage'](image),(-81,-40))
        self.assertEqual(evenements[-1]['position'],(-81,-40))

    def test_objet_deja_pose_et_capture_rejouee(self):
        ns,tour,actions,_,_,_,clock=self.contexte()
        e={'lignes':{'vi':{'min':201,'max':250,'val':209}}}
        tour(e);capture=clock[0]
        self.assertTrue(tour(e,capture))
        self.assertFalse(tour(e))
        self.assertEqual(actions,[])

    def test_pas_de_commande_sans_profil_metier_ou_coordonnees(self):
        for cause in ('profil','metier','coordonnees'):
            ns,tour,actions,modes,_,_,_=self.contexte(position=None if cause=='coordonnees' else (0,0),
                nom='Objet inconnu' if cause=='metier' else 'Anneau en Grithrill')
            if cause=='profil':ns['panneau'].items=[]
            for _ in range(3):tour()
            self.assertEqual([a for a in actions if a[0]!='capture'],[])
            self.assertEqual(modes,['manuel'])

    def test_interruption_ne_renvoie_pas_travel(self):
        ns,tour,actions,modes,_,_,_=self.contexte()
        tour();modes[0]='manuel';self.assertFalse(tour())
        modes[0]='automatique';tour()
        self.assertEqual([a for a in actions if a[0]=='texte'],[('texte',COMMANDE)])

    def test_ravitaillement_deja_engage_conserve(self):
        ns,tour,actions,_,_,_,_=self.contexte(guide_phase='achat')
        self.assertFalse(tour());self.assertEqual(actions,[])
        self.assertEqual(ns['GUIDE'].phase,'achat')

    def test_nouveau_f1_hors_atelier_rearme_apres_session_prete(self):
        ns,tour,actions,modes,_,_,_=self.contexte()
        ns['demarrage'].choisir('Objectif A');ns['demarrage'].phase='PRET'
        modes[0]='manuel';tour();modes[0]='automatique';tour()
        self.assertIn(('texte',COMMANDE),actions)

    def test_saisie_interrompue_pas_de_commande_dupliquee(self):
        ns,tour,actions,modes,_,_,_=self.contexte()
        ns['touche']=lambda *a:False
        tour();self.assertEqual(ns['demarrage'].phase,'SAISIE')
        tour();self.assertEqual(modes,['manuel'])
        self.assertEqual([a for a in actions if a[0]=='texte'],[])

    def test_raccourci_espace_ne_depend_pas_de_la_detection_du_champ(self):
        ns,tour,actions,modes,_,_,_=self.contexte()
        ns['point_saisie_chat']=lambda _:None
        tour()
        self.assertEqual([a for a in actions if a[0]=='touche'],
                         [('touche',(0x20,.06)),('touche',(0x0D,.06))])
        commandes=[a for a in actions if a[0] in ('touche','texte','ctrl_a')]
        self.assertEqual(commandes,[('touche',(0x20,.06)),('ctrl_a',),('texte',COMMANDE),
                                   ('touche',(0x0D,.06))])
        self.assertFalse(any(a[0]=='chat' for a in actions))
        self.assertEqual(modes,['automatique'])

    def test_interruption_avant_confirmation_ne_renvoie_pas_commande(self):
        ns,tour,actions,modes,_,_,_=self.contexte()
        tour()
        ns['popup_confirmation_trajet']=lambda _:True
        modes[0]='manuel';tour()
        self.assertEqual([a for a in actions if a[0]=='touche'],
                         [('touche',(0x20,.06)),('touche',(0x0D,.06))])
        self.assertEqual(modes,['manuel'])
        self.assertEqual([a for a in actions if a[0]=='texte'],[('texte',COMMANDE)])
        modes[0]='automatique';tour()
        self.assertEqual([a for a in actions if a[0]=='texte'],[('texte',COMMANDE)])
        self.assertEqual([a[1][0] for a in actions if a[0]=='touche'],[0x20,0x0D,0x0D])

    def test_captures_reelles_avant_touches_apres_ocr(self):
        ns,tour,actions,_,_,_,clock=self.contexte()
        fraicheur=[0.]
        def capturer(_):fraicheur[0]=clock[0]
        def touche(*a):
            self.assertLessEqual(clock[0]-fraicheur[0],2.)
            actions.append(('touche',a));return True
        ns['capturer']=capturer;ns['touche']=touche
        tour()
        ns['popup_confirmation_trajet']=lambda _:True
        tour()
        self.assertEqual([a[1][0] for a in actions if a[0]=='touche'],[0x20,0x0D,0x0D])

    def test_popup_facultatif_retarde_et_confirme_une_seule_fois(self):
        ns,tour,actions,_,_,_,_=self.contexte()
        tour();tour();tour()
        self.assertEqual([a[1][0] for a in actions if a[0]=='touche'],[0x20,0x0D])
        ns['popup_confirmation_trajet']=lambda _:True
        tour();tour();tour()
        self.assertEqual([a[1][0] for a in actions if a[0]=='touche'],[0x20,0x0D,0x0D])
        self.assertEqual([a for a in actions if a[0]=='texte'],[('texte',COMMANDE)])

    def test_commande_absente_du_chat_interdit_entree_et_trajet(self):
        ns,tour,actions,modes,_,_,_=self.contexte()
        ns['verifier_commande_chat']=lambda:False
        tour()
        self.assertEqual([a[1][0] for a in actions if a[0]=='touche'],[0x20])
        self.assertEqual(ns['demarrage'].phase,'SAISIE')
        self.assertEqual(modes,['manuel'])

    def test_texte_popup_voyage_pas_achat_ni_autre_destination(self):
        for t,attendu in [
            ('Voulez-vous lancer le deplacement automatique vers -83,-40 ? Confirmer',True),
            ('Souhaitez-vous continuer le voyage automatique ?',True),
            ('Confirmer le voyage vers -84,-40 automatique',False),
            ('Acheter rune Ga Pa, prix total, confirmer',False),
            ('Mode automatique, inventaire',False),('Confirmer',False)]:
            self.assertEqual(texte_confirmation_trajet(t),attendu)

    def test_chat_sur_capture_reelle(self):
        import sys
        try:import cv2
        except ImportError:
            for p in (Path.home()/'AppData/Local/Packages').glob('PythonSoftwareFoundation.Python.*/LocalCache/local-packages/Python*/site-packages'):
                if (p/'cv2').exists():sys.path.append(str(p))
            try:import cv2
            except ImportError:self.skipTest('OpenCV indisponible')
        from fm_demarrage import point_saisie_chat
        im=cv2.imread(str(Path(__file__).parent/'tests_retour_item_inventaire.jpg'))
        x,y=point_saisie_chat(im)
        self.assertTrue(10<x<600 and 990<y<1025)
        im[850:1040,:780]=0
        self.assertIsNone(point_saisie_chat(im))

    def test_mauvais_objet_ferme_avant_toute_rune(self):
        ns,tour,actions,_,_,_,_=self.contexte()
        ns['point_fermeture_inventaire']=lambda _:(1500,180)
        ns['clic_point']=lambda *p:actions.append(('fermer',p)) or True
        e={'lignes':{'vi':{'min':1,'max':100,'val':10}}}
        tour(e);self.assertEqual(actions,[])
        tour(e)
        self.assertEqual(actions,[('fermer',(1500,180))])

    def test_lecture_incomplete_ne_ferme_pas_objet(self):
        ns,tour,actions,_,_,_,_=self.contexte()
        ns['panneau'].items[0]['sig'].append(['fo',31,50])
        ns['point_fermeture_inventaire']=lambda _:(1500,180)
        for _ in range(3):tour({'lignes':{'vi':{'min':201,'max':250,'val':209}}})
        self.assertEqual(actions,[])

    def test_metier_menu_commun(self):
        ns,tour,actions,_,_,_,_=self.contexte(nom="Marteau R'ture")
        ns['demarrage'].choisir('Objectif A');ns['demarrage'].phase='ATELIER'
        ns['barre_inventaire']=lambda _:None
        ns['trouver_texte']=lambda *a:(900,500)
        ns['clic_point']=lambda *p:actions.append(('menu',p)) or True
        tour();self.assertEqual(actions,[('menu',(900,500))])

    def test_profil_choisi_conserve_mode_et_file(self):
        for fichier in ('assistant_sans_clic.py','fm_avec_clics.py'):
            ar=ast.parse(Path(fichier).read_text(encoding='utf8'))
            cls=next(n for n in ar.body if isinstance(n,ast.ClassDef) and n.name=='Panneau')
            fn=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='nouvel_item')
            a={'nom':'A','nom_jeu':'Anneau','sig':[['vi',201,250]]}
            b=dict(a,nom='B');mode=['automatique'];appliques=[]
            p=SimpleNamespace(finition=SimpleNamespace(current=lambda _:None),
                grille=SimpleNamespace(winfo_children=lambda:[]),_entetes=lambda:None,_rang=lambda *a:None,
                _met=lambda *a:None,proposer=lambda:None,items=[b,a],profil_demarrage=a,file=['B'],
                nom=object(),mode=SimpleNamespace(get=lambda:mode[0],set=lambda v:mode.__setitem__(0,v)),
                _mode_change=lambda:None,_conf=lambda it:{'profil':it['nom']},
                etat=SimpleNamespace(config=lambda **kw:None),VERT='vert')
            def appliquer(it):appliques.append(it['nom']);mode[0]='manuel'
            p.appliquer=appliquer
            ns=dict(trouver_item=lambda *a:b,norm=lambda s:s,proche=lambda *a:1.,log=lambda _:None)
            exec(compile(ast.Module(body=[fn],type_ignores=[]),'profil_depart','exec'),ns)
            resultat=ns['nouvel_item'](p,{'vi':{'min':201,'max':250,'val':209,'nom':'Vitalite'}},
                                       {('vi',201,250)},'Anneau')
            self.assertEqual(resultat,a)
            self.assertEqual(appliques,['A'])
            self.assertEqual(mode,['automatique'])
            self.assertEqual(p.file,['B'])

    def test_signature_naturelle_seulement(self):
        f={'sig':[['vi',201,250],['pa',0,0]]}
        self.assertTrue(profil_correspond(f,{'vi':{'min':201,'max':250}}))
        self.assertFalse(profil_correspond(f,{'vi':{'min':201,'max':300}}))
        self.assertFalse(profil_correspond(f,{'vi':{'min':201,'max':250,'rate':1}}))

    def test_preparation_ne_desactive_jamais_stop_des_passes_fm(self):
        from fm_securite import motif_blocage
        ar=ast.parse('def runtime():\n'+activer_clics.RUNTIME_SECURITE)
        fn=next(n for n in ast.walk(ar) if isinstance(n,ast.FunctionDef) and n.name=='action_autorisee')
        ns=dict(motif_blocage=motif_blocage,verifier_mode_clic=lambda:None,
            panneau=SimpleNamespace(mode=SimpleNamespace(get=lambda:'automatique')),
            dofus_actif=lambda:True,securite={'capture':10.,'lecture':10.,'motif':None,'preparation':True},
            mesures_securite={'blocages':{}},diagnostic=SimpleNamespace(evenement=lambda *a,**kw:None),
            confirmation=SimpleNamespace(attente=None),confirmation_navigation=SimpleNamespace(attente=None),
            time=SimpleNamespace(monotonic=lambda:10.),reco={'stop':True},log=lambda _:None)
        exec(compile(ast.Module(body=[fn],type_ignores=[]),'garde_preparation','exec'),ns)
        self.assertTrue(ns['action_autorisee']())
        self.assertFalse(ns['action_autorisee'](fm=True))
        ns['securite']['preparation']=False
        self.assertFalse(ns['action_autorisee']())
        self.assertFalse(ns['action_autorisee'](fm=True))

    def test_hook_avant_moteur_et_interface_metier(self):
        source=Path('fm_avec_clics.py').read_text(encoding='utf8')
        self.assertLess(source.index('if preparer_demarrage(bgr, etat, t_capture):'),
                        source.index('                vues = etat["lignes"]'))
        self.assertIn('id="metierdepart"',source)
        self.assertIn('metier_depart:$',source)


if __name__=='__main__':unittest.main()
