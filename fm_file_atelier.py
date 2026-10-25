"""Journal de taches d'atelier. Les identifiants sont des taches, pas des UID Dofus.

Une case d'inventaire ne constitue jamais une preuve d'identite. A jet strictement
identique, deux exemplaires du meme profil sont interchangeables ; sinon la
reprise exige le jet sauvegarde. Aucune politique de choix de rune ici.
"""
import copy
import errno
import json
import math
import os
from pathlib import Path
import tempfile
import time
import uuid


class FileIncertaine(RuntimeError):
    pass


def configurations_identiques(gauche,droite):
    """Le mode d'execution change avec F1/Echap, sans modifier les objectifs."""
    if not isinstance(gauche,dict) or not isinstance(droite,dict):return False
    return {k:v for k,v in gauche.items() if k!='mode'} == {k:v for k,v in droite.items() if k!='mode'}


def empreinte(lignes):
    # "occulte" concerne aussi la couleur/le stock de la case sous la souris.
    # Une valeur et ses bornes reellement relues restent utilisables. "rate"
    # signale au contraire une valeur reprise de la memoire : toujours refusee.
    if not lignes or any(l.get('rate') for l in lignes.values()):
        return None
    resultat = []
    for s,l in sorted(lignes.items()):
        if s=='?':return None
        valeurs = [l.get(k) for k in ('min','max','val')]
        if any(not isinstance(v,(int,float)) or isinstance(v,bool) or not math.isfinite(v) for v in valeurs):
            return None
        # Une ligne exo a zero peut etre presente ou absente selon le lecteur.
        if valeurs[1] == valeurs[2] == 0:
            continue
        resultat.append([s,*valeurs])
    return resultat


def exo_protege(lignes):
    return next((s for s in ('pa','pm','po','invo') if lignes.get(s,{}).get('max',1)<=0
                 and lignes[s].get('val',0)>0),None)


def correspond(profil,lignes):
    from fm_demarrage import profil_correspond
    return empreinte(lignes) is not None and profil_correspond(profil,lignes)


def lecture_complete(etat):
    lignes=(etat or {}).get('lignes',{})
    rows=(etat or {}).get('rows')
    return bool(rows and len(rows)==len(lignes) and empreinte(lignes) is not None)


def minimums(profil,lignes):
    if not correspond(profil,lignes):
        return False
    for s,c in profil.get('cibles',{}).items():
        if c>0 and (s not in lignes or lignes[s]['val'] < min(c,profil.get('mins',{}).get(s,c))):
            return False
    return all(c<=0 or lignes.get(s,{}).get('val',0)>=c for s,c in profil.get('exos',{}).items())


class JournalFile:
    def __init__(self,chemin):
        self.chemin=Path(chemin)
        self.d={'version':1,'taches':[]}
        self.erreur=None
        if self.chemin.exists():
            try:
                self.d=json.loads(self.chemin.read_text(encoding='utf8'))
                assert self.d['version']==1 and isinstance(self.d['taches'],list)
                ids=set()
                for t in self.d['taches']:
                    assert t['etat'] in ('attente','en_cours','suspendu','termine','annule')
                    assert isinstance(t['profil'],dict) and t['profil'].get('nom')
                    assert t['id'] not in ids
                    ids.add(t['id'])
                assert sum(t['etat']=='en_cours' for t in self.d['taches'])<=1
            except (OSError,ValueError,KeyError,TypeError,AssertionError) as err:
                self.erreur='journal de file illisible : '+str(err)

    def _valider(self):
        if self.erreur:
            raise FileIncertaine(self.erreur)

    def _sauver(self,d):
        self._valider()
        # Ne publier en memoire qu'apres ecriture durable et remplacement reussi.
        fd,tmp=tempfile.mkstemp(prefix=self.chemin.name+'.',suffix='.tmp',dir=self.chemin.parent)
        try:
            with os.fdopen(fd,'w',encoding='utf8') as f:
                json.dump(d,f,ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            for essai in range(6):
                try:
                    os.replace(tmp,self.chemin)
                    break
                except OSError as err:
                    transitoire=err.errno in (errno.EACCES,errno.EBUSY,errno.EINVAL) or getattr(err,'winerror',None) in (5,32,33)
                    if not transitoire or essai==5:raise
                    time.sleep(.05*(essai+1))
        finally:
            if os.path.exists(tmp):os.unlink(tmp)
        self.d=d

    @property
    def active(self):
        self._valider()
        return copy.deepcopy(next((t for t in self.d['taches'] if t['etat']=='en_cours'),None))

    @property
    def attentes(self):
        self._valider()
        return copy.deepcopy([t for t in self.d['taches'] if t['etat']=='attente'])

    def planifier(self,noms,profils):
        self._valider()
        profils={p['nom']:p for p in profils}
        if any(n not in profils for n in noms):raise FileIncertaine('profil de file absent')
        d=copy.deepcopy(self.d)
        anciens=[t for t in d['taches'] if t['etat']=='attente']
        restants=[t for t in d['taches'] if t['etat']!='attente']
        nouveaux=[]
        for n in noms:
            t=next((t for t in anciens if t['profil']['nom']==n),None)
            if t:anciens.remove(t)
            else:t={'id':uuid.uuid4().hex,'etat':'attente','profil':copy.deepcopy(profils[n]),'jet':None}
            nouveaux.append(t)
        for t in anciens:t['etat']='annule'
        d['taches']=restants+anciens+nouveaux
        self._sauver(d)

    def commencer(self,profil,lignes):
        self._valider()
        if self.active:return self.active
        if not correspond(profil,lignes) or exo_protege(lignes):
            raise FileIncertaine('objet incomplet, incompatible ou exo deja present')
        d=copy.deepcopy(self.d)
        t=next((t for t in d['taches'] if t['etat']=='attente'),None)
        if t and t['profil']!=profil:
            raise FileIncertaine('le profil ne correspond pas a la premiere tache')
        if not t:
            t={'id':uuid.uuid4().hex,'profil':copy.deepcopy(profil)}
            d['taches'].append(t)
        t.update(etat='en_cours',jet=empreinte(lignes),action=None)
        self._sauver(d)
        return self.active

    def observer(self,lignes,action=None):
        self._valider()
        a=self.active
        if not a or not correspond(a['profil'],lignes):raise FileIncertaine('objet en cours non confirme')
        jet=empreinte(lignes)
        if a['jet']==jet and a.get('action')==action:return
        d=copy.deepcopy(self.d)
        t=next(t for t in d['taches'] if t['id']==a['id'])
        t.update(jet=jet,action=copy.deepcopy(action))
        if exo_protege(lignes):t['protege']=True
        self._sauver(d)

    def proteger(self,lignes):
        a=self.active
        if not a or not correspond(a['profil'],lignes) or not exo_protege(lignes):
            raise FileIncertaine('exo protege non identifie')
        if not a.get('protege'):
            d=copy.deepcopy(self.d)
            t=next(t for t in d['taches'] if t['id']==a['id'])
            t['protege']=True
            t['jet_protege']=empreinte(lignes)
            self._sauver(d)

    def reconfigurer(self,profil,lignes):
        """Adopter l'objet relu apres un Enregistrer explicite, jamais au simple F1.

        Le controleur exige deux captures fraiches. Cette operation ne termine,
        n'annule et ne remplace aucune tache ; les reussites restent inchangees.
        """
        self._valider()
        a=self.active
        if not a or profil.get('nom')!=a['profil']['nom']:
            raise FileIncertaine('la reprise doit concerner la meme tache et le meme profil')
        if a.get('protege') or self.protege(lignes):
            raise FileIncertaine('objet protege : reconfiguration interdite')
        if a.get('action'):
            raise FileIncertaine('action non confirmee : Enregistrer ne peut pas effacer cette incertitude')
        if not correspond(a['profil'],lignes) or not correspond(profil,lignes):
            raise FileIncertaine('objet different ou lecture incomplete : reprise refusee')
        d=copy.deepcopy(self.d)
        t=next(t for t in d['taches'] if t['id']==a['id'])
        t.setdefault('revisions',[]).append({'motif':'enregistrer_explicite',
                                            'profil':t['profil'],'jet':t['jet']})
        t['profil']=copy.deepcopy(profil)
        t['jet']=empreinte(lignes)
        self._sauver(d)
        return self.active

    def changer_objet(self,profil,lignes):
        """Enregistrer explicite sur un autre profil : conserver l'ancien en pause."""
        self._valider()
        a=self.active
        if not a or profil.get('nom')==a['profil']['nom']:
            raise FileIncertaine('utilise la reconciliation du meme profil')
        if a.get('action') or a.get('protege'):
            raise FileIncertaine('ancienne tache protegee ou action incertaine : changement refuse')
        if not correspond(profil,lignes) or self.protege(lignes):
            raise FileIncertaine('nouvel objet incomplet, incompatible ou deja protege')
        d=copy.deepcopy(self.d)
        ancien=next(t for t in d['taches'] if t['id']==a['id'])
        candidat=next((t for t in d['taches'] if t['etat']=='suspendu'
                       and t['profil']['nom']==profil['nom']),None)
        if candidat and (candidat.get('action') or candidat.get('protege')
                         or candidat.get('jet')!=empreinte(lignes)):
            raise FileIncertaine('exemplaire suspendu non retrouve avec certitude')
        if candidat is None:
            premier=next((t for t in d['taches'] if t['etat']=='attente'),None)
            candidat=premier if premier and premier['profil']['nom']==profil['nom'] else None
        if candidat is None:
            candidat={'id':uuid.uuid4().hex}
            d['taches'].append(candidat)
        ancien['etat']='suspendu'
        candidat.update(etat='en_cours',profil=copy.deepcopy(profil),jet=empreinte(lignes),action=None)
        self._sauver(d)
        return self.active

    def terminer(self,lignes):
        self._valider()
        a=self.active
        if not a or not minimums(a['profil'],lignes):
            raise FileIncertaine('reussite et minimums non confirmes')
        d=copy.deepcopy(self.d)
        t=next(t for t in d['taches'] if t['id']==a['id'])
        t.update(etat='termine',jet=empreinte(lignes),action=None)
        self._sauver(d)
        return t['id']

    def protege(self,lignes):
        self._valider()
        jet=empreinte(lignes)
        return bool(exo_protege(lignes) or jet is not None and any(
            t['etat']=='termine' and t.get('jet')==jet for t in self.d['taches']))

    def candidat(self,profil,lignes,retour=False):
        if not correspond(profil,lignes) or self.protege(lignes):return False
        a=self.active
        if a and a.get('protege'):return False
        return not (retour and a and a.get('jet')!=empreinte(lignes))
