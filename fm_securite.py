"""Conditions d'execution, independantes de Windows et testables sans clics."""
import math
import ntpath


def executable_dofus(chemin):
    """Le titre peut contenir uniquement le personnage ; verifier le processus."""
    return ntpath.basename(chemin).casefold() in ("dofus.exe", "dofus unity.exe")


def ecran_de_rectangle(rectangle,ecrans):
    """Ecran couvrant la plus grande partie de la fenetre, coordonnees signees."""
    if not rectangle or len(rectangle)!=4:return None
    x0,y0,x1,y1=rectangle
    if x1<=x0 or y1<=y0:return None
    scores=[]
    for i,m in enumerate(ecrans):
        aire=max(0,min(x1,m['left']+m['width'])-max(x0,m['left'])) * max(
            0,min(y1,m['top']+m['height'])-max(y0,m['top']))
        scores.append((aire,i))
    scores.sort(reverse=True)
    if not scores or scores[0][0]<=0 or len(scores)>1 and scores[0][0]==scores[1][0]:return None
    return scores[0][1]


def rectangle_dofus_actif():
    import ctypes
    from ctypes import wintypes
    u=ctypes.windll.user32
    u.GetForegroundWindow.restype=wintypes.HWND
    u.GetWindowRect.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.RECT)]
    h=u.GetForegroundWindow()
    if not h or not fenetre_dofus_active():return None
    r=wintypes.RECT()
    if not u.GetWindowRect(h,ctypes.byref(r)) or u.GetForegroundWindow()!=h:return None
    return r.left,r.top,r.right,r.bottom


def fenetre_dofus_active():
    """Lecture seule de la fenetre Windows active. Aucun evenement d'entree."""
    import ctypes
    from ctypes import wintypes
    u, k = ctypes.windll.user32, ctypes.windll.kernel32
    u.GetForegroundWindow.restype = wintypes.HWND
    u.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    k.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    k.OpenProcess.restype = wintypes.HANDLE
    k.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD,
                                            wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    k.CloseHandle.argtypes = [wintypes.HANDLE]
    pid = wintypes.DWORD()
    u.GetWindowThreadProcessId(u.GetForegroundWindow(), ctypes.byref(pid))
    h = k.OpenProcess(0x1000, False, pid.value)
    if not h:
        raise ctypes.WinError()
    try:
        taille = wintypes.DWORD(32768)
        chemin = ctypes.create_unicode_buffer(taille.value)
        if not k.QueryFullProcessImageNameW(h, 0, chemin, ctypes.byref(taille)):
            raise ctypes.WinError()
        return executable_dofus(chemin.value)
    finally:
        k.CloseHandle(h)
def motif_blocage(*, automatique, dofus_actif, capture, maintenant,
                  stop=False, age_max=2.0):
    if not automatique:
        return "mode manuel"
    if stop:
        return "arret demande par l'analyse"
    if not dofus_actif:
        return "Dofus n'est pas au premier plan"
    if capture is None or not math.isfinite(capture):
        return "aucune capture valide"
    age = maintenant - capture
    if not math.isfinite(age) or age < 0 or age > age_max:
        return "lecture perimee"
    return None
