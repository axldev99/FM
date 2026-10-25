"""Preparation de l'atelier, independante du moteur FM et des clics Windows."""
import re
import unicodedata

DESTINATION = (-83, -40)
COMMANDE = '/travel -83,-40'
METIERS = ('joaillomager','cordomager','costumager','forgemager','sculptemager','facomager')


def position_depuis_texte(texte):
    texte = str(texte).replace('−','-').replace('–','-')
    # L'OCR peut separer le signe du nombre : ne pas perdre le signe negatif.
    texte = re.sub(r'-\s+(?=\d)', '-', texte)
    positions = set((int(x),int(y)) for x,y in re.findall(
        r'(?<![\d.])(-?\d{1,3})\s*[,;]\s*(-?\d{1,3})(?!\d)',texte))
    return next(iter(positions)) if len(positions)==1 else None


def texte_confirmation_trajet(texte):
    """Ne pas confondre le dialogue de voyage avec une confirmation d'achat."""
    t = ''.join(c for c in unicodedata.normalize('NFD',str(texte).lower()) if not unicodedata.combining(c))
    voyage = any(m in t for m in ('deplac','voyag','trajet','pilotage'))
    demande = bool(re.search(r'\b(confirmer|continuer|accepter|oui|valider|souhaitez|voulez)\b',t))
    position = position_depuis_texte(t)
    if position is not None and position != DESTINATION:
        return False
    destination = position == DESTINATION
    return voyage and demande and (destination or 'automatique' in t)


def commande_chat_lue(texte):
    t=re.sub(r'\s+','',str(texte).lower()).replace('−','-').replace('–','-')
    return t == '/travel-83,-40'


def masque_texte_chat(champ):
    """Le texte de commande cyan, sans le curseur blanc ni le X gris a droite."""
    import numpy as np
    if not champ.size:
        return None
    b,g,r = (champ[:,:,i].astype(int) for i in range(3))
    masque=(b>80)&(g>80)&(b-r>35)&(g-r>35)
    yy,xx=np.nonzero(masque)
    if len(xx)<20:
        return None
    return masque[yy.min():yy.max()+1,xx.min():xx.max()+1].astype(np.uint8)*255


def commande_chat_reconnue(champ):
    """Comparaison exacte a la commande verifiee sur la capture utilisateur.

    Aucun seuil tolerant : une autre coordonnee ne doit jamais etre acceptee.
    L'OCR reste disponible pour une police ou une taille differente.
    """
    import cv2
    import numpy as np
    from pathlib import Path
    masque=masque_texte_chat(champ)
    ref=cv2.imread(str(Path(__file__).parent/'fm_reperes/commande_travel_m83_m40.png'),0)
    return bool(masque is not None and ref is not None and masque.shape==ref.shape
                and np.array_equal(masque,ref))


def preparer_lecture_chat(champ):
    import cv2
    masque=masque_texte_chat(champ)
    if masque is None:
        return champ
    masque=cv2.copyMakeBorder(masque,4,4,4,4,cv2.BORDER_CONSTANT,value=0)
    return cv2.cvtColor(masque,cv2.COLOR_GRAY2BGR)


def metier_pour_objet(nom, explicite=''):
    if explicite in METIERS:
        return explicite
    texte = ''.join(c for c in unicodedata.normalize('NFD',nom.lower()) if not unicodedata.combining(c))
    mots = set(re.findall(r'[a-z]+',texte))
    familles = (
        ('joaillomager',{'anneau','amulette','collier'}),
        ('cordomager',{'bottes','sandales','ceinture','souliers'}),
        ('costumager',{'cape','coiffe','chapeau','casque'}),
        ('forgemager',{'marteau','epee','hache','pelle','dagues','dague'}),
        ('sculptemager',{'arc','baton','baguette'}),
        ('facomager',{'bouclier'}))
    trouves = [m for m,noms in familles if mots & noms]
    return trouves[0] if len(trouves)==1 else None


def point_saisie_chat(image, rectangle=False):
    """Champ de saisie en bas a gauche ; ne jamais valider un ancien brouillon avec Entree."""
    import cv2
    h,w = image.shape[:2]
    gris = cv2.cvtColor(image,cv2.COLOR_BGR2GRAY)
    candidats = []
    for c in cv2.findContours(cv2.Canny(gris,40,100),cv2.RETR_LIST,cv2.CHAIN_APPROX_SIMPLE)[0]:
        x,y,largeur,hauteur = cv2.boundingRect(c)
        if (x < .08*w and .16*w <= largeur <= .4*w and .80*h < y < .96*h
                and .014*h <= hauteur <= .04*h and y+hauteur < .97*h):
            candidats.append((y,x,largeur,hauteur))
    if not candidats:
        return None
    y,x,largeur,hauteur = max(candidats)
    if rectangle:
        return x,y,largeur,hauteur
    return x+largeur//2,y+hauteur//2


def profil_correspond(fiche, lignes):
    attendus = {tuple(s) for s in fiche.get('sig',[]) if len(s)==3 and s[2]>0}
    lus = {(s,l.get('min'),l.get('max')) for s,l in lignes.items() if not l.get('hors') and l.get('max',0)>0}
    return bool(attendus) and attendus == lus and all(not l.get('rate') for l in lignes.values())


def profil_incompatible(fiche, lignes):
    attendus = {tuple(s) for s in fiche.get('sig',[]) if len(s)==3 and s[2]>0}
    lus = {(s,l.get('min'),l.get('max')) for s,l in lignes.items() if not l.get('hors') and l.get('max',0)>0}
    return bool(attendus and lus-attendus)


class DemarrageAtelier:
    def __init__(self):
        self.profil = None
        self.phase = 'VERIFICATION'
        self.debut_trajet = None
        self.precedent = None
        self.nombre = 0
        self.derniere_capture = -1.

    def choisir(self, profil):
        if profil != self.profil:
            self.__init__()
            self.profil = profil

    def trajet_envoye(self, maintenant):
        self.phase = 'TRAJET'
        self.debut_trajet = maintenant
        self.precedent,self.nombre = None,0

    def observer_position(self, position, capture, maintenant):
        if capture <= self.derniere_capture or maintenant-capture > 2 or capture > maintenant:
            return False
        self.derniere_capture = capture
        if self.debut_trajet is not None and capture <= self.debut_trajet:
            return False
        self.nombre = self.nombre+1 if position == DESTINATION and position == self.precedent else (1 if position == DESTINATION else 0)
        self.precedent = position
        if self.nombre >= 2:
            self.phase = 'ATELIER'
            return True
        return False

    def expire(self, maintenant):
        return self.debut_trajet is not None and maintenant-self.debut_trajet > 900
