"""Frappe par touches physiques pour le chat Unity, sans VK_PACKET Unicode.

Le clavier, les gardes et les attentes sont injectes pour tester sans toucher au jeu.
"""


def remplacer_ascii(texte, clavier, disposition, autorise, rafraichir, pause):
    if not texte or not texte.isascii() or any(ord(c)<32 for c in texte):
        return False
    frappes=[]
    for c in texte:
        code=clavier.VkKeyScanExW(c,disposition)
        if code == -1 or code & 0xffff == 0xffff or (code >> 8) & ~7:
            return False
        frappes.append((code & 255,(code >> 8) & 7))

    def frapper(vk,modificateurs):
        rafraichir()
        if not autorise():
            return False
        maintenues=[]
        try:
            for bit,touche in ((1,0x10),(2,0x11),(4,0x12)):
                if modificateurs & bit:
                    scan=clavier.MapVirtualKeyExW(touche,0,disposition)
                    clavier.keybd_event(touche,scan,0,0)
                    maintenues.append((touche,scan))
            pause(.02)
            scan=clavier.MapVirtualKeyExW(vk,0,disposition)
            clavier.keybd_event(vk,scan,0,0)
            try:
                pause(.05)
            finally:
                clavier.keybd_event(vk,scan,2,0)
        finally:
            for touche,scan in reversed(maintenues):
                clavier.keybd_event(touche,scan,2,0)
        pause(.02)
        return True

    if not frapper(0x20,0): # Espace : ouverture de la saisie selon le raccourci Dofus
        return False
    pause(.2)
    if not frapper(0x41,2):  # Ctrl+A, une fois le chat ouvert par Espace
        return False
    return all(frapper(vk,mods) for vk,mods in frappes)
