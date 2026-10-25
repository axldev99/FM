import ast
import copy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

import activer_clics
from fm_demarrage import DemarrageAtelier
from fm_file_atelier import JournalFile,FileIncertaine,empreinte,correspond,minimums,exo_protege

ROOT=Path(__file__).parent


def profil(nom='Grithrill PA',stat='fo'):
    return {'nom':nom,'nom_jeu':nom.split(' PA')[0],'sig':[[stat,31,50]],
            'cibles':{stat:48},'mins':{stat:47},'exos':{'pa':1},'regles':{},'metier_depart':'joaillomager'}


def jet(val=47,pa=0,stat='fo'):
    l={stat:{'min':31,'max':50,'val':val,'dispo':['base','pa','ra'],'stock':{}}}
    if pa:l['pa']={'min':0,'max':0,'val':pa,'dispo':[]}
    return l


class FileAtelierTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=ROOT)
        self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'journal.json'
        self.a,self.b=profil(),profil('Autre anneau PA','int')

    def test_trois_doublons_puis_autre_item_et_reprise(self):
        j=JournalFile(self.path)
        j.planifier([self.a['nom']]*3+[self.b['nom']],[self.a,self.b])
        ids=[t['id'] for t in j.attentes]
        self.assertEqual(len(set(ids)),4)
        for i,p in enumerate([self.a]*3+[self.b]):
            s=p['sig'][0][0]
            a=j.commencer(p,jet(stat=s))
            self.assertEqual(a['id'],ids[i])
            # Ravitaillement et redemarrage : tache active et jet conserves.
            j=JournalFile(self.path)
            self.assertEqual(j.active['id'],ids[i])
            self.assertTrue(j.candidat(p,jet(stat=s),retour=True))
            self.assertFalse(j.candidat(p,jet(46,stat=s),retour=True))
            j.observer(jet(pa=1,stat=s))
            j.terminer(jet(pa=1,stat=s))
            j=JournalFile(self.path)
            self.assertIsNone(j.active)
            self.assertTrue(j.protege(jet(pa=1,stat=s)))
            self.assertFalse(j.candidat(p,jet(pa=1,stat=s)))
        self.assertEqual(j.attentes,[])
        self.assertEqual([t['etat'] for t in j.d['taches']],['termine']*4)

    def test_taches_sont_distinctes_mais_exemplaires_identiques_interchangeables(self):
        j=JournalFile(self.path)
        j.planifier([self.a['nom']]*3,[self.a])
        j.commencer(self.a,jet())
        self.assertTrue(j.candidat(self.a,jet(),True))
        self.assertFalse(j.candidat(self.a,jet(48),True))
        self.assertFalse(j.candidat(self.a,jet(pa=1),True))

    def test_protection_exo_avant_meme_creation_du_journal(self):
        j=JournalFile(self.path)
        for s in ('pa','pm','po','invo'):
            l=jet();l[s]={'min':0,'max':0,'val':1}
            self.assertTrue(j.protege(l))
            with self.assertRaises(FileIncertaine):j.commencer(self.a,l)
        l=jet();l['pa']={'min':1,'max':1,'val':1}
        self.assertIsNone(exo_protege(l))

    def test_exo_observe_reste_protege_si_ocr_perd_la_ligne_ensuite(self):
        j=JournalFile(self.path);j.commencer(self.a,jet())
        j.proteger(jet(pa=1))
        j=JournalFile(self.path)
        self.assertTrue(j.active['protege'])
        self.assertFalse(j.candidat(self.a,jet(),True))
        ns,tour,clock,modes,traces=self.runtime(j)
        tour(jet());ns['demarrage'].phase='PRET'
        tour(jet())
        self.assertEqual(modes,['manuel'])
        ns['reco']={'stat':'fo','taille':'pa'}
        self.assertFalse(ns['autoriser_file']())

    def test_ligne_exo_non_decodee_ne_passe_pas_pour_un_objet_sans_exo(self):
        from fm_file_atelier import lecture_complete
        l=jet()
        self.assertFalse(lecture_complete({'lignes':l,'rows':[None,None]}))
        self.assertTrue(lecture_complete({'lignes':l,'rows':[None]}))

    def test_profil_fige_ordre_strict_et_modification_des_attentes(self):
        j=JournalFile(self.path)
        j.planifier([self.a['nom'],self.b['nom']],[self.a,self.b])
        with self.assertRaises(FileIncertaine):j.commencer(self.b,jet(stat='int'))
        j.commencer(self.a,jet())
        change=copy.deepcopy(self.a);change['cibles']['fo']=50
        j.planifier([self.a['nom'],self.b['nom']],[change,self.b])
        self.assertEqual(j.active['profil'],self.a)
        self.assertEqual(j.attentes[0]['profil'],change)

    def test_aucune_fin_sans_exo_minimum_ou_lecture_complete(self):
        j=JournalFile(self.path);j.commencer(self.a,jet())
        for l in (jet(),jet(46,1),jet(stat='int'),{}):
            with self.assertRaises(FileIncertaine):j.terminer(l)
        l=jet(pa=1);l['fo']['rate']=1
        self.assertIsNone(empreinte(l))
        with self.assertRaises(FileIncertaine):j.terminer(l)
        l=jet(pa=1);l['fo']['occulte']=True
        self.assertIsNotNone(empreinte(l)) # case rune survolee, valeur relue a gauche
        self.assertTrue(minimums(self.a,jet(47,1)))

    def test_echec_ecriture_ne_consomme_pas_la_tache_ni_la_reussite(self):
        j=JournalFile(self.path);j.planifier([self.a['nom']]*3,[self.a])
        avant=self.path.read_bytes()
        with mock.patch('fm_file_atelier.os.replace',side_effect=OSError('disque')):
            with self.assertRaises(OSError):j.commencer(self.a,jet())
        self.assertIsNone(j.active);self.assertEqual(len(j.attentes),3)
        self.assertEqual(self.path.read_bytes(),avant)
        j.commencer(self.a,jet())
        with mock.patch('fm_file_atelier.os.replace',side_effect=OSError('disque')):
            with self.assertRaises(OSError):j.terminer(jet(pa=1))
        self.assertIsNotNone(JournalFile(self.path).active)

    def test_journal_corrompu_ou_schema_inconnu_bloque_sans_ecraser(self):
        for texte in ('{','{"version":9,"taches":[]}',
                      '{"version":1,"taches":[{"id":"x","etat":"termine"}]}'):
            self.path.write_text(texte,encoding='utf8')
            j=JournalFile(self.path)
            with self.assertRaises(FileIncertaine):j.planifier([],[self.a])
            self.assertEqual(self.path.read_text(encoding='utf8'),texte)

    def runtime(self,j):
        traces=[];modes=['automatique'];nom=[''];clock=[100.]
        p=SimpleNamespace(journal_file=j,items=[self.a,self.b],file=[],rev=0,stock_exos={},
            mode=SimpleNamespace(get=lambda:modes[0],set=lambda v:modes.__setitem__(0,v)),
            nom=SimpleNamespace(get=lambda:nom[0]),_mode_change=lambda:None,_conf=lambda f:f)
        def charger(f):nom[0]=f['nom'];p.conf=f
        p.charger_preselection=charger
        ns=dict(panneau=p,SUIVI=SimpleNamespace(),time=SimpleNamespace(time=lambda:clock[0],monotonic=lambda:clock[0]),
            diagnostic=SimpleNamespace(evenement=lambda *a,**kw:traces.append((a,kw))),log=lambda _:None,
            json=json,F_FILE=str(Path(self.tmp.name)/'miroir.json'),fin_signalee=[None],stock_session=['ancien'],
            _RUNES_VUES={'fo/base'},_ACHATS_PREC=[{'cle':'fo/base'}],
            ravito={},demarrage=DemarrageAtelier(),GUIDE=SimpleNamespace(phase=None,liste=[],vu_hdv=False),
            securite={},mon={'left':0,'top':0},point_fermeture_inventaire=lambda _:(100,100),
            clic_point=lambda *a:traces.append(('clic',a)) or True)
        ar=ast.parse('def runtime():\n'+activer_clics.RUNTIME_FILE)
        exec(compile(ast.Module(body=ar.body[0].body,type_ignores=[]),'file_runtime','exec'),ns)
        def tour(lignes):
            clock[0]+=1
            ns.update(etat={'lignes':lignes,'rows':[None]*len(lignes)},t_capture=clock[0])
            return ns['preparer_file'](None,ns['etat'] if lignes else None,clock[0])
        return ns,tour,clock,modes,traces

    def test_runtime_liaison_reprise_fin_double_confirmation_et_transition(self):
        j=JournalFile(self.path);j.planifier([self.a['nom']]*3+[self.b['nom']],[self.a,self.b])
        ns,tour,clock,modes,traces=self.runtime(j)
        tour(jet()) # charge la copie du profil, laisse le demarrage confirmer l'atelier
        ns['demarrage'].phase='PRET'
        self.assertTrue(tour(jet()))
        self.assertFalse(tour(jet()))
        premiere=j.active['id']
        self.assertEqual(len(j.attentes),3)
        ns['reco']={'stat':'fo','taille':'base'}
        self.assertTrue(ns['autoriser_file']())
        self.assertEqual(JournalFile(self.path).active['action']['stat'],'fo')
        j.observer(jet(48)) # confirmation d'une action, pas une reemission
        tour(jet(48,1))
        self.assertFalse(ns['autoriser_file']()) # coupe des la premiere lecture de PA
        self.assertFalse(ns['confirmer_fin_file']({'texte':'OBJECTIF ATTEINT'}))
        tour(jet(48,1))
        self.assertTrue(ns['confirmer_fin_file']({'texte':'OBJECTIF ATTEINT'}))
        self.assertEqual(JournalFile(self.path).d['taches'][0]['etat'],'termine')
        self.assertEqual(modes,['automatique'])
        tour(jet(48,1)) # charge le prochain profil, ferme l'objet reussi
        self.assertIn(('clic',(100,100)),traces)
        self.assertNotEqual(ns['file_runtime']['profil'],premiere)
        self.assertEqual(ns['_RUNES_VUES'],set())
        self.assertEqual(ns['_ACHATS_PREC'],[])
        self.assertIsNone(ns['stock_session'][0])

    def test_runtime_candidat_reussi_ecarte_sans_compter_une_tache(self):
        j=JournalFile(self.path);j.planifier([self.a['nom']]*3,[self.a])
        ns,tour,*_=self.runtime(j);tour(jet())
        ns['ravito']['lignes_pose']=jet(pa=1)
        self.assertFalse(ns['verifier_candidat_pose'](True))
        self.assertEqual(ns['ravito']['indice_selection'],1)
        self.assertIsNone(j.active)
        self.assertEqual(len(j.attentes),3)
        self.assertTrue(ns['file_runtime']['fermer'])

    def test_runtime_reprise_jet_modifie_et_action_interrompue_bloquent(self):
        for pending,val in ((False,48),(True,47)):
            j=JournalFile(self.path)
            if not j.active:j.commencer(self.a,jet())
            if pending:j.observer(jet(),action={'stat':'fo','taille':'base'})
            ns,tour,clock,modes,traces=self.runtime(JournalFile(self.path))
            tour(jet(val));ns['demarrage'].phase='PRET'
            tour(jet(val));tour(jet(val))
            self.assertEqual(modes,['manuel'])
            self.assertTrue(any(t[0]==('file_bloquee',) for t in traces if isinstance(t[0],tuple)))

    def test_runtime_redemarrage_apres_succes_avant_sauvegarde_protege_et_termine(self):
        j=JournalFile(self.path);j.planifier([self.a['nom']]*3,[self.a])
        j.commencer(self.a,jet())
        j.observer(jet(),action={'stat':'pa','taille':'base'})
        ns,tour,clock,modes,traces=self.runtime(JournalFile(self.path))
        tour(jet(pa=1));ns['demarrage'].phase='PRET'
        tour(jet(pa=1));ns['reco']={'stat':'fo','taille':'pa'}
        self.assertFalse(ns['autoriser_file']())
        self.assertFalse(ns['confirmer_fin_file']({'texte':'OBJECTIF ATTEINT'}))
        tour(jet(pa=1))
        self.assertTrue(ns['confirmer_fin_file']({'texte':'OBJECTIF ATTEINT'}))
        self.assertIsNone(JournalFile(self.path).active)
        self.assertEqual(len(JournalFile(self.path).attentes),2)

    def test_runtime_reussite_non_ecrite_ne_declenche_pas_transition(self):
        j=JournalFile(self.path);j.planifier([self.a['nom']]*3,[self.a]);j.commencer(self.a,jet())
        ns,tour,clock,modes,traces=self.runtime(j)
        tour(jet(pa=1));ns['demarrage'].phase='PRET'
        tour(jet(pa=1));ns['confirmer_fin_file']({'texte':'OBJECTIF ATTEINT'})
        tour(jet(pa=1))
        with mock.patch('fm_file_atelier.os.replace',side_effect=OSError('disque')):
            self.assertFalse(ns['confirmer_fin_file']({'texte':'OBJECTIF ATTEINT'}))
        self.assertFalse(ns['file_runtime']['fermer'])
        self.assertEqual(modes,['manuel'])
        self.assertIsNotNone(JournalFile(self.path).active)

    def test_stock_autre_item_et_rune_jamais_vue_ne_sont_pas_zero(self):
        from test_fm_reference import charger_moteur
        import re,unicodedata,difflib
        for fichier in ('assistant_sans_clic.py','fm_avec_clics.py'):
            m=charger_moteur(fichier)
            ar=ast.parse((ROOT/fichier).read_text(encoding='utf8'))
            nom='_liste_achats_brut' if fichier=='fm_avec_clics.py' else 'liste_achats'
            fn=next(n for n in ar.body if isinstance(n,ast.FunctionDef) and n.name==nom)
            ns=dict(m,_RUNES_VUES=set(),_ACHATS_PREC=[],STOCK_ALERTE=20,STOCK_CIBLE=100,
                    recherche_rune=lambda *a:'rune')
            exec(compile(ast.Module(body=[fn],type_ignores=[]),'stock_file','exec'),ns)
            f=ns[fn.name]
            lignes=jet();lignes['fo'].update(dispo=['base'],stock={'base':100})
            # La Pa est configuree, mais n'a jamais ete vue sur cet item.
            self.assertEqual(f(lignes,{'fo/pa':{'alerte':20,'cible':100}}),[])
            # Le profil suivant n'a pas de Force : aucun achat pour l'ancien item.
            lignes=jet(stat='int');lignes['int'].update(dispo=['base'],stock={'base':100})
            self.assertEqual(f(lignes,{'fo/pa':{'alerte':20,'cible':100}}),[])

    def test_runtime_changement_item_charge_metier_et_vide_achats_precedents(self):
        j=JournalFile(self.path);j.planifier([self.a['nom'],self.b['nom']],[self.a,self.b])
        j.commencer(self.a,jet());j.terminer(jet(pa=1))
        ns,tour,clock,modes,traces=self.runtime(JournalFile(self.path))
        ns['GUIDE'].liste=[{'rune':'ancienne rune'}]
        tour(jet(stat='int'))
        self.assertEqual(ns['panneau'].profil_file,self.b)
        self.assertEqual(ns['GUIDE'].liste,[])
        self.assertEqual(ns['panneau'].stock_exos,{})
        ns['demarrage'].phase='PRET'
        tour(jet(stat='int'));tour(jet(stat='int'))
        self.assertEqual(ns['panneau'].journal_file.active['profil'],self.b)

    def test_reussite_prioritaire_sur_ravitaillement_stock_bas(self):
        j=JournalFile(self.path);j.commencer(self.a,jet())
        ns,tour,*_=self.runtime(j)
        tour(jet());ns['demarrage'].phase='PRET'
        achats=[{'rune':'Pa Force','stock':0}]
        self.assertEqual(ns['filtrer_achats_file'](achats),achats)
        ns['etat']={'lignes':jet(pa=1),'rows':[None,None]}
        ns['GUIDE'].phase='sortie';ns['GUIDE'].liste=achats
        self.assertEqual(ns['filtrer_achats_file'](achats),[])
        self.assertIsNone(ns['GUIDE'].phase)

    def test_reconfiguration_explicite_conserve_id_attentes_et_reussites(self):
        j=JournalFile(self.path)
        j.planifier([self.a['nom']]*3,[self.a])
        j.commencer(self.a,jet());j.terminer(jet(pa=1))
        identifiant=j.commencer(self.a,jet())['id']
        ancien=copy.deepcopy(j.d['taches'][0])
        attentes=j.attentes
        nouveau=copy.deepcopy(self.a);nouveau['petit_exo']=None;nouveau['cibles']['fo']=49
        j.reconfigurer(nouveau,jet(48))
        reprise=JournalFile(self.path)
        self.assertEqual(reprise.active['id'],identifiant)
        self.assertEqual(reprise.active['profil'],nouveau)
        self.assertEqual(reprise.active['jet'],empreinte(jet(48)))
        self.assertEqual(reprise.attentes,attentes)
        self.assertEqual(reprise.d['taches'][0],ancien)
        self.assertEqual(reprise.active['revisions'][0]['profil'],self.a)

    def test_reconfiguration_refuse_protection_action_incertaine_et_autre_objet(self):
        for cause in ('action','protege','exo','mauvais_profil','autre_objet','incomplet'):
            with self.subTest(cause=cause):
                p=Path(self.tmp.name)/(cause+'.json');j=JournalFile(p)
                j.commencer(self.a,jet())
                if cause=='action':j.observer(jet(),action={'stat':'fo','taille':'pa'})
                if cause=='protege':j.proteger(jet(pa=1))
                profil_nouveau=self.b if cause=='mauvais_profil' else self.a
                lignes=jet(pa=1) if cause=='exo' else jet(stat='int') if cause=='autre_objet' else {} if cause=='incomplet' else jet()
                avant=p.read_bytes()
                with self.assertRaises(FileIncertaine):j.reconfigurer(profil_nouveau,lignes)
                self.assertEqual(p.read_bytes(),avant)

    def test_reconfiguration_ecriture_echouee_conserve_ancien_profil(self):
        j=JournalFile(self.path);j.commencer(self.a,jet())
        nouveau=copy.deepcopy(self.a);nouveau['petit_exo']='agi'
        with mock.patch('fm_file_atelier.os.replace',side_effect=OSError('disque')):
            with self.assertRaises(OSError):j.reconfigurer(nouveau,jet(48))
        self.assertEqual(j.active['profil'],self.a)
        self.assertEqual(JournalFile(self.path).active['jet'],empreinte(jet()))

    def test_runtime_enregistrer_puis_f1_reconcilie_sur_deux_captures(self):
        ancien=copy.deepcopy(self.a);ancien['petit_exo']='agi'
        j=JournalFile(self.path);j.commencer(ancien,jet())
        ns,tour,clock,modes,traces=self.runtime(j)
        p=ns['panneau'];nouveau=copy.deepcopy(self.a);nouveau['petit_exo']=None
        p.charger_preselection(nouveau)
        p.reconciliation_file={'id':1,'profil':nouveau}
        ns['confirmation']=SimpleNamespace(attente=None)
        ns['confirmation_navigation']=SimpleNamespace(attente=None)
        self.assertTrue(tour(jet(48)))
        self.assertEqual(j.active['profil'],ancien)
        tour(jet(48))
        self.assertEqual(j.active['profil'],nouveau)
        self.assertEqual(j.active['jet'],empreinte(jet(48)))
        self.assertIsNone(p.reconciliation_file)
        ns['demarrage'].phase='PRET'
        tour(jet(48));tour(jet(48))
        ns['reco']={'stat':'fo','taille':'base'}
        self.assertTrue(ns['autoriser_file']())
        self.assertEqual(modes,['automatique'])

    def test_runtime_f1_seul_ne_reconfigure_jamais_le_profil(self):
        ancien=copy.deepcopy(self.a);ancien['petit_exo']='agi'
        j=JournalFile(self.path);j.commencer(ancien,jet())
        ns,tour,clock,modes,traces=self.runtime(j)
        tour(jet());ns['demarrage'].phase='PRET'
        tour(jet());tour(jet())
        nouveau=copy.deepcopy(self.a);nouveau['petit_exo']=None
        ns['panneau'].conf=nouveau
        tour(jet())
        self.assertEqual(modes,['manuel'])
        self.assertEqual(j.active['profil'],ancien)

    def test_enregistrer_demande_la_reprise_seulement_apres_sauvegarde_reussie(self):
        import os,time
        for fichier in ('assistant_sans_clic.py','fm_avec_clics.py'):
            arbre=ast.parse((ROOT/fichier).read_text(encoding='utf8'))
            cls=next(n for n in arbre.body if isinstance(n,ast.ClassDef) and n.name=='Panneau')
            fn=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='enregistrer')
            chemin=Path(self.tmp.name)/(fichier+'.json')
            ns=dict(os=os,time=time,json=json,F_ITEMS=str(chemin),charger_items=lambda:[copy.deepcopy(self.a)],
                    proche=lambda *a:1,nom_code=lambda s:s,plafond=lambda *a:101,pds=lambda s,n:n,
                    PLAFOND=101,log=lambda _:None)
            exec(compile(ast.Module(body=[fn],type_ignores=[]),'enregistrer_reprise','exec'),ns)
            def case(v):return SimpleNamespace(get=lambda:str(v))
            for echec in (False,True):
                with self.subTest(fichier=fichier,echec=echec):
                    messages=[]
                    p=SimpleNamespace(rangs={
                        'fo':dict(obj=case(48),exo=False,max=50,tol=case(47),rem=case(''),plages={}),
                        'pa':dict(obj=case(1),exo=True,max=0,plages={})},
                        nom=case(self.a['nom']),nom_jeu=self.a['nom_jeu'],mode=case('manuel'),
                        sig={tuple(s) for s in self.a['sig']},plan_b=SimpleNamespace(current=lambda:0),
                        _petit_exo=lambda:None,_finition=lambda:None,_conf=lambda f:copy.deepcopy(f),
                        choix=SimpleNamespace(config=lambda **kw:None),
                        etat=SimpleNamespace(config=lambda **kw:messages.append(kw)),VERT='vert',ROUGE='rouge',conf='ancienne')
                    if echec:
                        with mock.patch('builtins.open',side_effect=OSError('disque')):
                            ns['enregistrer'](p)
                        self.assertFalse(hasattr(p,'reconciliation_file'))
                        self.assertEqual(p.conf,'ancienne')
                        self.assertEqual(messages[-1]['fg'],'rouge')
                    else:
                        ns['enregistrer'](p)
                        demande=p.reconciliation_file
                        self.assertEqual(demande['profil']['petit_exo'],None)
                        self.assertEqual(demande['profil']['nom'],self.a['nom'])
                        self.assertEqual(json.loads(chemin.read_text(encoding='utf8'))['items'][-1],
                                         json.loads(json.dumps(demande['profil'])))


if __name__=='__main__':unittest.main()
