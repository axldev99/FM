"""Etat persistant observe : aucun controle du jeu, aucune reprise automatique."""
import json
from pathlib import Path
import time

from fm_fichiers import ecrire_texte


class OrchestrationObservee:
    ETATS = frozenset(("VERIFICATION", "FM", "SORTIE", "ACHAT", "RETOUR",
                       "ATTENTE", "PAUSE", "TERMINE"))

    def __init__(self, chemin):
        self.chemin = Path(chemin)
        self.precedent = None
        self.lecture_invalide = False
        try:
            if self.chemin.stat().st_size > 100_000:
                raise ValueError("etat trop grand")
            ancien = json.loads(self.chemin.read_text(encoding="utf-8"))
            if not isinstance(ancien, dict) or ancien.get("schema") != 1 or ancien.get("etat") not in self.ETATS:
                raise ValueError("schema ou etat inconnu")
            self.precedent = ancien
        except FileNotFoundError:
            pass
        except (OSError, ValueError, TypeError):
            self.lecture_invalide = True
        self.courant = None
        self.revision = 0

    def observer(self, contexte):
        phase = {"sortie": "SORTIE", "achat": "ACHAT", "retour": "RETOUR"}.get(contexte.get("guide"))
        if contexte.get("stop"):
            observe = "ATTENTE"
        elif phase:
            observe = phase
        elif not contexte.get("tableau"):
            observe = "ATTENTE"
        elif contexte.get("termine"):
            observe = "TERMINE"
        else:
            observe = "FM"
        mode = contexte.get("mode", "manuel")
        nouveau = dict(etat=observe if mode == "automatique" else "PAUSE",
                       phase_observee=observe, mode=mode,
                       profil=contexte.get("profil", ""),
                       file=list(contexte.get("file", [])))
        if nouveau == self.courant:
            return False
        document = dict(nouveau, schema=1, revision=self.revision + 1, t=time.time(),
                        observation_seulement=True, reprise_automatique=False,
                        verification_requise_au_redemarrage=True,
                        lecture_precedente_invalide=self.lecture_invalide)
        # Ecrit uniquement par le fil de diagnostic, jamais par la boucle FM.
        self.chemin.parent.mkdir(parents=True, exist_ok=True)
        ecrire_texte(self.chemin, json.dumps(document, ensure_ascii=False, allow_nan=False) + "\n")
        self.courant = nouveau
        self.revision += 1
        return True
