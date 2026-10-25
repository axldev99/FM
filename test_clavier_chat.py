import unittest
from types import SimpleNamespace

from fm_clavier_chat import remplacer_ascii
from fm_demarrage import COMMANDE,commande_chat_lue


class ClavierChatTests(unittest.TestCase):
    def test_entree_maintenue_utilise_scan_physique_et_relache_touche(self):
        import ast
        import activer_clics
        ar=ast.parse('def runtime():\n'+activer_clics.RUNTIME_RAVITO)
        fn=next(n for n in ast.walk(ar) if isinstance(n,ast.FunctionDef) and n.name=='touche')
        for interrompu in (False,True):
            touches=[]
            def pause(_):
                if interrompu:raise KeyboardInterrupt
            ns=dict(action_autorisee=lambda:True,
                ctypes=SimpleNamespace(windll=SimpleNamespace(user32=SimpleNamespace(
                    MapVirtualKeyW=lambda *a:0x1c,keybd_event=lambda *a:touches.append(a)))),
                time=SimpleNamespace(sleep=pause),diagnostic=SimpleNamespace(action_envoyee=lambda *a,**kw:None))
            exec(compile(ast.Module(body=[fn],type_ignores=[]),'entree_clavier','exec'),ns)
            if interrompu:
                with self.assertRaises(KeyboardInterrupt):ns['touche'](0x0d,.06)
            else:self.assertTrue(ns['touche'](0x0d,.06))
            self.assertEqual(touches,[(0x0d,0x1c,0,0),(0x0d,0x1c,2,0)])

    def cv(self):
        import sys
        from pathlib import Path
        try:import cv2
        except ImportError:
            for p in (Path.home()/'AppData/Local/Packages').glob('PythonSoftwareFoundation.Python.*/LocalCache/local-packages/Python*/site-packages'):
                if (p/'cv2').exists():sys.path.append(str(p))
            try:import cv2
            except ImportError:self.skipTest('OpenCV indisponible')
        return cv2

    def test_commande_capture_reconnue_sans_curseur_ni_croix_et_pas_autre_destination(self):
        from pathlib import Path
        from fm_demarrage import commande_chat_reconnue,preparer_lecture_chat
        cv2=self.cv()
        im=cv2.imread(str(Path(__file__).parent/'tests_chat_travel_saisi.png'))
        self.assertTrue(commande_chat_reconnue(im))
        im[:,91:93]=255 # le curseur peut clignoter ou changer de place
        self.assertTrue(commande_chat_reconnue(im))
        self.assertLess(preparer_lecture_chat(im).shape[1],110)
        autre=im.copy();autre[:,61:67]=im[:,54:60] # remplacer le 3 par le glyphe 8 : -88,-40
        self.assertFalse(commande_chat_reconnue(autre))
        autre=im.copy();autre[:,50:53]=0 # signe moins absent : destination differente
        self.assertFalse(commande_chat_reconnue(autre))
        self.assertFalse(commande_chat_reconnue(im*0))

    def test_capture_correcte_debloque_validation_meme_si_ocr_echoue(self):
        import ast
        from pathlib import Path
        import activer_clics
        from fm_demarrage import commande_chat_reconnue,preparer_lecture_chat
        cv2=self.cv()
        im=cv2.imread(str(Path(__file__).parent/'tests_chat_travel_saisi.png'))
        image=cv2.copyMakeBorder(im,2,2,3,3,cv2.BORDER_CONSTANT,value=(0,0,0))
        ar=ast.parse('def runtime():\n'+activer_clics.RUNTIME_DEMARRAGE)
        fn=next(n for n in ast.walk(ar) if isinstance(n,ast.FunctionDef) and n.name=='verifier_commande_chat')
        preuves=[]
        ns=dict(capturer=lambda _:image,mon={},pause_auto=lambda _:True,
            point_saisie_chat=lambda *a,**kw:(0,0,image.shape[1],image.shape[0]),
            commande_chat_reconnue=commande_chat_reconnue,preparer_lecture_chat=preparer_lecture_chat,
            commande_chat_lue=commande_chat_lue,COMMANDE=COMMANDE,
            ocr=SimpleNamespace(ligne=lambda _:self.fail('La capture exacte ne doit pas dependre de l OCR')),
            diagnostic=SimpleNamespace(evenement=lambda *a,**kw:preuves.append(kw['preuve'])))
        exec(compile(ast.Module(body=[fn],type_ignores=[]),'capture_chat_reelle','exec'),ns)
        self.assertTrue(ns['verifier_commande_chat']())
        self.assertEqual(preuves,['image_exacte'])

    def clavier(self):
        evenements=[];maintenues=set()
        def traduire(c,_):
            if c=='/':return 0xBF | 256
            if c=='-':return 0xBD
            if c==',':return 0xBC
            return ord(c.upper())
        def touche(vk,scan,flags,_):
            evenements.append((vk,scan,flags))
            if flags & 2:maintenues.discard(vk)
            else:maintenues.add(vk)
        return SimpleNamespace(VkKeyScanExW=traduire,MapVirtualKeyExW=lambda vk,*a:vk+1,
                               keybd_event=touche),evenements,maintenues

    def test_espace_ctrl_a_touches_physiques_selon_disposition(self):
        c,evt,maintenues=self.clavier();captures=[]
        self.assertTrue(remplacer_ascii(COMMANDE,c,1,lambda:True,lambda:captures.append(True),lambda _:None))
        self.assertEqual(evt[:2],[(0x20,0x21,0),(0x20,0x21,2)])
        self.assertEqual(evt[2:6],[(0x11,0x12,0),(0x41,0x42,0),(0x41,0x42,2),(0x11,0x12,2)])
        self.assertEqual(evt[6:10],[(0x10,0x11,0),(0xBF,0xC0,0),(0xBF,0xC0,2),(0x10,0x11,2)])
        self.assertFalse(maintenues)
        self.assertEqual(len(captures),len(COMMANDE)+2)
        self.assertTrue(all(flags in (0,2) for _,_,flags in evt)) # pas de VK_PACKET Unicode

    def test_annulation_ne_laisse_pas_de_modificateur_enfonce(self):
        c,evt,maintenues=self.clavier()
        def pause(_):
            if 0x41 in maintenues:raise KeyboardInterrupt
        with self.assertRaises(KeyboardInterrupt):
            remplacer_ascii(COMMANDE,c,1,lambda:True,lambda:None,pause)
        self.assertFalse(maintenues)

    def test_disposition_non_supportee_ou_garde_bloquee_aucune_touche(self):
        c,evt,_=self.clavier()
        c.VkKeyScanExW=lambda *a:-1
        self.assertFalse(remplacer_ascii(COMMANDE,c,1,lambda:True,lambda:None,lambda _:None))
        self.assertEqual(evt,[])
        c,evt,_=self.clavier()
        self.assertFalse(remplacer_ascii(COMMANDE,c,1,lambda:False,lambda:None,lambda _:None))
        self.assertEqual(evt,[])

    def test_lecture_exige_la_commande_complete_et_exacte(self):
        for texte,ok in [('/travel -83,-40',True),('/travel −83, −40',True),
                         ('/travel -81,-40',False),('travel -83,-40',False),
                         ('bonjour /travel -83,-40',False),('',False)]:
            self.assertEqual(commande_chat_lue(texte),ok)

    def test_relecture_du_champ_avant_validation(self):
        import ast
        import activer_clics
        import numpy as np
        ar=ast.parse('def runtime():\n'+activer_clics.RUNTIME_DEMARRAGE)
        fn=next(n for n in ast.walk(ar) if isinstance(n,ast.FunctionDef) and n.name=='verifier_commande_chat')
        for lectures,attendu in [(['',COMMANDE],True),(['','',''],False)]:
            appels=[];traces=[]
            def lire(_):
                i=len(appels);appels.append(i)
                return lectures[min(i,len(lectures)-1)]
            ns=dict(capturer=lambda _:np.zeros((100,200,3),np.uint8),mon={},pause_auto=lambda _:True,
                point_saisie_chat=lambda *a,**kw:(1,2,100,24),ocr=SimpleNamespace(ligne=lire),
                commande_chat_lue=commande_chat_lue,COMMANDE=COMMANDE,
                commande_chat_reconnue=lambda _:False,preparer_lecture_chat=lambda z:z,
                diagnostic=SimpleNamespace(evenement=lambda *a,**kw:traces.append(a[0])),
                dofus_actif=lambda:False)
            exec(compile(ast.Module(body=[fn],type_ignores=[]),'chat_relu','exec'),ns)
            self.assertEqual(ns['verifier_commande_chat'](),attendu)
            self.assertEqual(len(appels),2 if attendu else 3)
            self.assertEqual(traces,['commande_trajet_lue'] if attendu else [])


if __name__=='__main__':unittest.main()
