"""Traces passives, bornees et asynchrones ; aucune decision ni action de jeu."""
import json
import os
from pathlib import Path
import queue
import threading
import time
import uuid
from functools import wraps


def passif(fn):
    @wraps(fn)
    def appel(self, *args, **kw):
        if not self.actif:
            return None
        try:
            return fn(self, *args, **kw)
        except Exception:
            self.erreurs += 1
            return None
    return appel


def resume_observation(etat):
    if not etat:
        return {"tableau": False, "confiance_ocr": None}
    return {"tableau": True, "reliquat": etat.get("reliquat"),
            "confiance_ocr": None,  # Le lecteur actuel ne fournit pas un score global calibre.
            "lignes": {s: {k: l.get(k) for k in
                        ("val", "min", "max", "dispo", "stock", "rate", "occulte")}
                       for s, l in etat.get("lignes", {}).items()}}


class Diagnostic:
    def __init__(self, dossier, *, limite_octets=5_000_000, archives=2,
                 captures_max=40, file_max=64):
        self.dossier = Path(dossier)
        self.actif = os.environ.get("FM_DIAGNOSTIC", "1") != "0"
        self.session = uuid.uuid4().hex
        self.capture_id = self.decision_id = self.action_id = None
        self.limite_octets, self.archives = limite_octets, archives
        self.captures_max = captures_max
        self.file = queue.Queue(maxsize=file_max)
        self.perdus = self.erreurs = self.ecrits = 0
        self.temps_emission = self.max_emission = 0.
        self.nombre_emissions = 0
        self._image_occupee = threading.BoundedSemaphore(1)
        self._t_image = 0.
        self._fin = threading.Event()
        self._orchestration = None
        self._thread = threading.Thread(target=self._boucle, daemon=True, name="fm-diagnostic")
        try:
            if self.actif:
                self._thread.start()
        except RuntimeError:
            self.erreurs += 1

    def evenement(self, type_, **champs):
        if not self.actif:
            return None
        debut = time.perf_counter()
        try:
            identifiant = uuid.uuid4().hex
            # Figer le contenu avant passage au fil d'ecriture.
            ligne = json.dumps(dict(session=self.session, id=identifiant, type=type_,
                t=time.time(), monotonic=time.monotonic(), capture_id=self.capture_id,
                decision_id=self.decision_id, action_id=self.action_id, donnees=champs),
                ensure_ascii=False, allow_nan=False) + "\n"
            self.file.put_nowait((ligne, None, None))
            return identifiant
        except Exception:
            self.perdus += 1
            return None
        finally:
            duree = time.perf_counter() - debut
            self.nombre_emissions += 1
            self.temps_emission += duree
            self.max_emission = max(self.max_emission, duree)

    @passif
    def observation(self, etat, capture_t, image=None):
        self.capture_id = uuid.uuid4().hex
        self.decision_id = None
        self.evenement("observation", capture_t=capture_t,
                       age_ms=max(0., 1000 * (time.monotonic() - capture_t)),
                       observation=resume_observation(etat))
        # Jamais de capture d'une autre application. Aucun score OCR invente.
        if image is not None and time.monotonic() - self._t_image >= 2:
            self._proposer_image(image)

    def _proposer_image(self, image):
        if not self._image_occupee.acquire(blocking=False):
            return
        try:
            from fm_securite import fenetre_dofus_active
            if not fenetre_dofus_active():
                self._image_occupee.release()
                return
            nom = "capture_" + self.capture_id + ".jpg"
            self.file.put_nowait((None, image.copy(), nom))
            self._t_image = time.monotonic()
            self.evenement("capture_proposee", fichier=nom)
        except Exception:
            self._image_occupee.release()
            self.erreurs += 1

    @passif
    def decision(self, reco, etat, mode, duree_ms):
        self.decision_id = None
        self.decision_id = self.evenement("decision", recommandation=reco,
            observation=resume_observation(etat), mode=mode, calcul_ms=duree_ms)

    @passif
    def action_envoyee(self, type_, **champs):
        # "envoyee" n'est pas une confirmation : les passes restent des inferences.
        self.action_id = None
        self.action_id = self.evenement("action_envoyee", commande=type_, **champs)

    def stats(self):
        return dict(ecrits=self.ecrits, perdus=self.perdus, erreurs=self.erreurs,
                    attente=self.file.qsize(), emission_moyenne_ms=
                    1000 * self.temps_emission / max(1, self.nombre_emissions),
                    emission_max_ms=1000 * self.max_emission)

    def _ecrire(self, ligne, image, nom):
        self.dossier.mkdir(parents=True, exist_ok=True)
        if image is None:
            evenement = json.loads(ligne)
            if evenement.get("type") == "orchestration":
                if self._orchestration is None:
                    from fm_orchestration import OrchestrationObservee
                    self._orchestration = OrchestrationObservee(self.dossier / "etat_orchestration.json")
                if not self._orchestration.observer(evenement["donnees"]):
                    return
        if image is not None:
            import cv2
            h, w = image.shape[:2]
            if w > 1280:
                image = cv2.resize(image, (1280, max(1, round(h * 1280 / w))))
            ok, donnees = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 55])
            if not ok or donnees.nbytes > 1_000_000:
                raise OSError("capture trop grande ou encodage impossible")
            (self.dossier / nom).write_bytes(donnees.tobytes())
            for ancien in sorted(self.dossier.glob("capture_*.jpg"),
                                 key=lambda p: p.stat().st_mtime_ns)[:-self.captures_max]:
                ancien.unlink()
            return
        chemin = self.dossier / "evenements.jsonl"
        taille = len(ligne.encode("utf-8"))
        if taille > self.limite_octets:
            raise ValueError("evenement trop grand")
        if chemin.exists() and chemin.stat().st_size + taille > self.limite_octets:
            for i in range(self.archives, 0, -1):
                src = chemin if i == 1 else self.dossier / f"evenements.{i - 1}.jsonl"
                if src.exists():
                    src.replace(self.dossier / f"evenements.{i}.jsonl")
        with chemin.open("a", encoding="utf-8", newline="") as f:
            f.write(ligne)
        self.ecrits += 1

    def _boucle(self):
        while not self._fin.is_set() or not self.file.empty():
            try:
                ligne, image, nom = self.file.get(timeout=.1)
            except queue.Empty:
                continue
            try:
                self._ecrire(ligne, image, nom)
            except Exception:
                self.erreurs += 1
            finally:
                if image is not None:
                    self._image_occupee.release()
                self.file.task_done()

    def fermer(self, delai=1.):
        self._fin.set()
        if self._thread.ident is not None:
            self._thread.join(timeout=delai)
