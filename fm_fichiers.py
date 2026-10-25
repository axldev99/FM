"""Ecriture complete avant remplacement, avec reprise des erreurs transitoires."""
import errno
import os
from pathlib import Path
import tempfile
import time


def ecrire_texte(chemin, texte, essais=6):
    """Ne jamais exposer un fichier vide ou partiel aux lecteurs concurrents."""
    if essais < 1:
        raise ValueError("essais doit etre positif")
    cible = Path(chemin)
    for tentative in range(essais):
        temporaire = None
        try:
            fd, temporaire = tempfile.mkstemp(prefix=cible.name + ".", suffix=".tmp", dir=cible.parent)
            with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
                f.write(texte)
                f.flush()
            os.replace(temporaire, cible)
            return
        except OSError as err:
            transitoire = err.errno in (errno.EINVAL, errno.EACCES, errno.EBUSY) or getattr(err, "winerror", None) in (32, 33)
            if not transitoire or tentative == essais - 1:
                raise
            time.sleep(.15)
        finally:
            if temporaire is not None:
                try:
                    os.unlink(temporaire)
                except FileNotFoundError:
                    pass
