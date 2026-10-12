import cv2, time, traceback, numpy as np
import fm_live as f
out = open("diag_out.txt", "w", encoding="utf-8")
def P(*a):
    out.write(" ".join(str(x) for x in a) + "\n"); out.flush()
try:
    import rapidocr_onnxruntime as r
    P("version", getattr(r, "__version__", "?"))
    eng = r.RapidOCR()
    im = cv2.imread("fm_lecture_debug.png")
    rows = f.trouver_lignes(im)
    P("rows", len(rows), rows[:2], im.shape)
    def up(z, H=48):
        k = H / z.shape[0]
        return cv2.resize(z, None, fx=k, fy=k, interpolation=cv2.INTER_CUBIC)
    for (x, y, w, h) in rows:
        strip = im[y+2:y+h-2, x+int(.02*w):x+int(.63*w)]
        t = time.time(); a = eng(up(strip), use_det=False, use_cls=False, use_rec=True); ta = time.time()-t
        t = time.time(); b = eng(up(strip, 64), use_cls=False); tb = time.time()-t
        bb = [(int(i[0][0][0]), i[1], round(float(i[2]), 2)) for i in (b[0] or [])]
        mn = im[y+int(.12*h):y+int(.88*h), x+int(.02*w):x+int(.11*w)]
        c = eng(up(mn), use_det=False, use_cls=False, use_rec=True)
        c2 = eng(cv2.copyMakeBorder(up(mn), 8, 8, 60, 60, cv2.BORDER_REPLICATE), use_det=False, use_cls=False, use_rec=True)
        P("ROW", "A:", a[0], round(ta, 3), "| B:", bb, round(tb, 3), "| min:", c[0], c2[0])
    x, y, w, h = rows[0]; x2, y2, w2, h2 = rows[-1]
    tab = im[y-4:y2+h2+4, x:x+w]
    t = time.time(); d = eng(tab, use_cls=False); P("TABLE", round(time.time()-t, 3), [(int(i[0][0][0]), int(i[0][0][1]), i[1]) for i in (d[0] or [])])
    pas = rows[1][1]-rows[0][1]
    z = im[max(0, int(y-3.0*pas)):int(y-1.9*pas), x:x+int(.30*w)]
    cv2.imwrite("diag_rel.png", z)
    P("REL rec", eng(up(z), use_det=False, use_cls=False, use_rec=True)[0], "det", [(i[1]) for i in (eng(up(z, 96), use_cls=False)[0] or [])])
except Exception:
    P(traceback.format_exc())
P("FIN")
