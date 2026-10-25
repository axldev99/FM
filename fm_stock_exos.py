"""Stock observe des runes hors tableau ; aucune decision de forgemagie."""


def runes_a_verifier(conf, lignes):
    codes = [c for c, n in (conf or {}).get('exos', {}).items()
             if n > 0 and c not in lignes]
    petit = (conf or {}).get('petit_exo')
    if petit in ('agi', 'fo', 'int', 'cha', 'ini') and petit not in lignes and petit not in codes:
        codes.append(petit)
    return tuple(codes)


def barre_inventaire(image):
    import cv2
    gris = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    rects = [cv2.boundingRect(c) for c in cv2.findContours(
        cv2.Canny(gris, 40, 100), cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)[0]]
    barres = []
    for hx, hy, hw, hh in rects:
        if not (350 <= hw <= 500 and 30 <= hh <= 48 and hy < image.shape[0] * .3):
            continue
        for x, y, w, h in rects:
            if 210 <= w <= 340 and 20 <= h <= 34 and 50 <= x-hx <= 95 and 30 <= y-hy <= 65:
                barres.append((x, y, w, h))
    # Un titre coupe par le bord de la capture ne forme plus un contour ferme.
    # La recherche reste identifiable par les DEUX listes deroulantes sous elle.
    for x,y,w,h in rects:
        if not (210 <= w <= 340 and 20 <= h <= 34 and y < image.shape[0]*.35):
            continue
        dessous=[r for r in rects if 140 <= r[2] <= 190 and 20 <= r[3] <= 36 and 25 <= r[1]-y <= 50]
        if any(abs(r[0]-x) <= 8 for r in dessous) and any(155 <= r[0]-x <= 190 for r in dessous):
            barres.append((x,y,w,h))
    return max(barres, key=lambda r:(r[0],r[2])) if barres else None


def zone_filtre(image, barre):
    x,y,w,h=barre
    return image[y+2:y+h-2, x+23:x+w-25]


def case_inventaire(barre, idx=0):
    """Centre d'une case filtrée depuis la barre reelle, jamais le centre de l'ecran."""
    x,y,w,h = barre
    k = w / 252
    idx = max(0,min(int(idx),14))
    return round(x+(30+64*(idx%5))*k),round(y+(101+63*(idx//5))*k)


def point_fermeture_inventaire(image):
    """X du titre Inventaire, ancre sur sa recherche et ses deux menus.

    Aucune coordonnee globale : le X de la recherche et l'engrenage HDV
    sont en dehors de la zone de recherche.
    """
    import cv2
    from pathlib import Path
    barre = barre_inventaire(image)
    if barre is None:
        return None
    ref = cv2.imread(str(Path(__file__).parent/'fm_reperes/inventaire_fermer.png'),
                     cv2.IMREAD_GRAYSCALE)
    if ref is None:
        return None
    x,y,w,h = barre
    x0,y0 = x+w+35,max(0,y-55)
    zone = image[y0:max(0,y-8),x0:min(image.shape[1],x+w+110)]
    if zone.size == 0:
        return None
    gris = cv2.cvtColor(zone,cv2.COLOR_BGR2GRAY)
    meilleur = None
    for echelle in (.9,1.,1.1):
        g = cv2.resize(ref,None,fx=echelle,fy=echelle)
        gh,gw = g.shape
        if gh>gris.shape[0] or gw>gris.shape[1]:
            continue
        _,score,_,pos = cv2.minMaxLoc(cv2.matchTemplate(gris,g,cv2.TM_CCOEFF_NORMED))
        if score >= .85 and (meilleur is None or score>meilleur[0]):
            meilleur = score,(x0+pos[0]+gw//2,y0+pos[1]+gh//2)
    return meilleur[1] if meilleur else None


def croix_recherche_visible(image, barre):
    x,y,w,h=barre
    zone=image[y+h//2-7:y+h//2+7,x+w-23:x+w-6]
    return bool(zone.size and (zone.min(axis=2)>90).sum() >= 5)


def nettoyage_confirme(avant, barre_avant, apres, barre_apres):
    import cv2
    import numpy as np
    if any(abs(a-b)>3 for a,b in zip(barre_avant,barre_apres)):
        return False
    if not croix_recherche_visible(avant,barre_avant) or croix_recherche_visible(apres,barre_apres):
        return False
    a,b=zone_filtre(avant,barre_avant),zone_filtre(apres,barre_apres)
    if not a.size or not b.size:
        return False
    b=cv2.resize(b,(a.shape[1],a.shape[0]))
    return float(np.abs(a.astype(float)-b.astype(float)).mean()) >= 2


def recherche_effacee(image, barre):
    import cv2
    from pathlib import Path
    ref=cv2.imread(str(Path(__file__).parent/'fm_reperes/inventaire_recherche_vide.png'),cv2.IMREAD_GRAYSCALE)
    zone=zone_filtre(image,barre)
    if ref is None or zone.size == 0:
        return False
    gris=cv2.cvtColor(zone,cv2.COLOR_BGR2GRAY)
    if gris.shape[0] < ref.shape[0] or gris.shape[1] < ref.shape[1]:
        return False
    return float(cv2.matchTemplate(gris,ref,cv2.TM_CCOEFF_NORMED).max()) >= .90


def point_ressources(image, barre):
    import cv2
    from pathlib import Path
    refs=[cv2.imread(str(Path(__file__).parent/'fm_reperes'/nom),cv2.IMREAD_GRAYSCALE)
          for nom in ('inventaire_ressources.png','inventaire_ressources_actif.png')]
    if all(r is None for r in refs):
        return None
    x,y,w,h=barre
    x0,y0=max(0,x-65),y+45
    zone=image[y0:y+210,x0:max(0,x-8)]
    if zone.size == 0:
        return None
    gris=cv2.cvtColor(zone,cv2.COLOR_BGR2GRAY)
    meilleur=None
    for ref in refs:
        if ref is None:continue
        for echelle in (.85,1.,1.15):
            g=cv2.resize(ref,None,fx=echelle,fy=echelle)
            gh,gw=g.shape
            if gh>gris.shape[0] or gw>gris.shape[1]:continue
            _,score,_,pos=cv2.minMaxLoc(cv2.matchTemplate(gris,g,cv2.TM_CCOEFF_NORMED))
            if score >= .75 and (meilleur is None or score>meilleur[0]):
                meilleur=score,(x0+pos[0]+gw//2,y0+pos[1]+gh//2)
    return meilleur[1] if meilleur else None


def quantite_filtrage(image, barre, lire):
    """Une recherche exacte et deux captures concordantes sont exigees par l'appelant."""
    import numpy as np
    x,y,w,h=barre
    k=w/260
    gx,gy=x,round(y+75*k)
    # Toutes les cases visibles doivent etre vides pour conclure zero.
    vides=True
    for row in range(9):
        for col in range(5):
            x0,y0=round(gx+(col*65+12)*k),round(gy+(row*64+22)*k)
            z=image[y0:y0+round(25*k),x0:x0+round(30*k)]
            if z.size == 0 or float(z.max()) > 65 or float(z.std()) > 8:
                vides=False
    if vides:
        return 0
    z=image[round(gy+2*k):round(gy+26*k),round(gx+4*k):round(gx+53*k)]
    if z.size == 0:
        return None
    txt=lire(z)
    return int(txt) if isinstance(txt,str) and txt.isdigit() else None


def chiffres_stock(zone, chiffres):
    import numpy as np
    if zone.size == 0:
        return None
    # Les traits fins (notamment le second 1 de 11) sont anticreneles et
    # peuvent rester sous 200. Isoler la bande de texte avant les glyphes
    # evite d'inclure les reflets clairs de l'icone situee en dessous.
    masque = zone.min(axis=2) >= 150
    lignes = np.flatnonzero(masque.any(axis=1))
    bandes = np.split(lignes,np.where(np.diff(lignes)>1)[0]+1)
    bande = next((b for b in bandes if len(b)>=5 and masque[b].sum()>=8),None)
    if bande is None:
        return None
    masque = masque[bande[0]:bande[-1]+1]
    idx = np.flatnonzero(masque.any(axis=0))
    runs = []
    if len(idx):
        a = b = int(idx[0])
        for x in idx[1:]:
            if x != b + 1:
                if masque[:,a:b+1].sum() >= 4:
                    runs.append((a,b))
                a=int(x)
            b=int(x)
        if masque[:,a:b+1].sum() >= 4:
            runs.append((a,b))
    return chiffres.nombre(masque.astype(np.float32),runs,dump=False,seuil=.5) if runs else None


class StockExos:
    def __init__(self):
        self.cle = None
        self.valeurs = {}
        self.precedent = None
        self.nombre = 0

    def session(self, cle):
        if cle != self.cle:
            self.cle, self.valeurs = cle, {}
        self.precedent, self.nombre = None, 0

    def observer(self, code, filtre_ok, quantite, capture):
        # Jamais convertir une lecture absente en zero.
        if not filtre_ok or not isinstance(quantite, int) or isinstance(quantite, bool) or quantite < 0:
            self.precedent, self.nombre = None, 0
            return False
        precedent = self.precedent
        if precedent and precedent[:2] == (code, quantite) and capture > precedent[2]:
            self.nombre += 1
        else:
            self.nombre = 1
        self.precedent = (code, quantite, capture)
        if self.nombre >= 2:
            self.valeurs[code] = quantite
            return True
        return False

    def consommer(self, code):
        if code in self.valeurs:
            self.valeurs[code] = max(0, self.valeurs[code] - 1)
