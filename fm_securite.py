"""Conditions d'execution, independantes de Windows et testables sans clics."""
import math
import ntpath


def executable_dofus(chemin):
    """Le titre peut contenir uniquement le personnage ; verifier le processus."""
    return ntpath.basename(chemin).casefold() in ("dofus.exe", "dofus unity.exe")


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
