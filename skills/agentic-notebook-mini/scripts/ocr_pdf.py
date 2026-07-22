#!/usr/bin/env python3
"""
ocr_pdf.py — OCR scanned PDFs and images into indexable, page-markered text.

Standalone usage:
  python ocr_pdf.py <file.pdf> [-o out.txt] [--lang eng] [--dpi 300] [--pages 1-40]
  python ocr_pdf.py <scan.png> [-o out.txt] [--lang eng]
  python ocr_pdf.py <file.pdf> --engine easyocr        # force an engine

Output format is what build_index.py --from-text expects: plain text with
[[page N]] boundary markers, so page numbers survive into citations. When -o
is omitted, text goes to stdout (progress goes to stderr).

OCR engines (--engine auto|tesseract|easyocr, default auto):
  - tesseract: the `tesseract` CLI (apt-get install tesseract-ocr, or scoop on
    Windows — scoop's tessdata dir is auto-detected). Add language packs like
    tesseract-ocr-deu / tesseract-ocr-bul as needed.
  - easyocr: neural OCR (`pip install easyocr`), GPU-accelerated when torch
    sees CUDA; often better on difficult scans. In auto mode easyocr is
    preferred when installed, with per-page fallback to tesseract.

PDF rasterization tries, in order: PyMuPDF (fitz) → `pdftoppm` (poppler) →
pypdfium2. Images are OCR'd directly.

If a virtual environment exists at <skill>/.venv, the script re-execs inside
it automatically — create one there to hold optional dependencies (easyocr,
pymupdf) on machines where the system Python can't install packages.

build_index.py imports run_ocr()/have_tesseract() from this file to power
its --ocr flag; keep this script in the same directory.
"""

import os
import sys
from pathlib import Path

# --- Environment bootstrap: re-exec inside <skill>/.venv if present --------
_venv = Path(__file__).resolve().parent.parent / ".venv"
_venv_py = _venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
try:
    # sys.prefix equals the venv dir when running inside it — comparing
    # executables fails on Linux, where venv pythons are symlinks.
    _needs_venv = (_venv_py.exists()
                   and Path(sys.prefix).resolve() != _venv.resolve())
except OSError:
    _needs_venv = False
if _needs_venv:
    import subprocess as _sp
    raise SystemExit(_sp.call([str(_venv_py)] + sys.argv))
# ---------------------------------------------------------------------------

import argparse
import importlib.util
import re
import shutil
import subprocess
import tempfile

# Auto-configure Windows scoop paths for Tesseract languages if not set
if "TESSDATA_PREFIX" not in os.environ:
    for _cand in (r"%USERPROFILE%\scoop\apps\tesseract-languages\current",
                  r"%USERPROFILE%\scoop\apps\tesseract\current\tessdata"):
        _p = Path(os.path.expandvars(_cand))
        if _p.is_dir():
            os.environ["TESSDATA_PREFIX"] = str(_p)
            break

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff", ".tif"}


def have_tesseract() -> bool:
    return shutil.which("tesseract") is not None


def have_easyocr() -> bool:
    # find_spec avoids importing easyocr (and its torch dependency) just to
    # check availability — the real import happens only on first use.
    return importlib.util.find_spec("easyocr") is not None


_reader_cache = {}


def _easyocr(image_path: Path, lang: str) -> str:
    import easyocr  # heavy import, deferred to first use
    lang_map = {"eng": "en", "deu": "de", "fra": "fr", "spa": "es",
                "ita": "it", "por": "pt", "rus": "ru", "chi_sim": "ch_sim",
                "chi_tra": "ch_tra", "jpn": "ja", "kor": "ko", "bul": "bg"}
    langs = [lang_map.get(l.strip(), l.strip()) for l in lang.split("+") if l.strip()]
    langs = langs or ["en"]
    key = tuple(sorted(langs))
    if key not in _reader_cache:
        gpu = False
        try:
            import torch
            gpu = torch.cuda.is_available()
        except Exception:
            pass
        _reader_cache[key] = easyocr.Reader(list(langs), gpu=gpu)
    return "\n".join(_reader_cache[key].readtext(str(image_path), detail=0))


def _tesseract(image_path: Path, lang: str) -> str:
    out = subprocess.run(
        ["tesseract", str(image_path), "stdout", "-l", lang, "--psm", "3"],
        capture_output=True, timeout=600)
    if out.returncode != 0:
        err = out.stderr.decode("utf-8", errors="replace")[:300]
        raise RuntimeError(f"tesseract failed: {err}")
    return out.stdout.decode("utf-8", errors="replace")


_ENGINE_FN = {"easyocr": _easyocr, "tesseract": _tesseract}
_ENGINE_OK = {"easyocr": have_easyocr, "tesseract": have_tesseract}
_disabled_engines = set()  # engines that failed fatally (bad install) this run


def pick_engines(pref: str = "auto"):
    """Ordered list of usable engines. auto = easyocr first when installed."""
    order = {"auto": ["easyocr", "tesseract"],
             "easyocr": ["easyocr"],
             "tesseract": ["tesseract"]}[pref]
    avail = [e for e in order
             if e not in _disabled_engines and _ENGINE_OK[e]()]
    if not avail:
        raise RuntimeError(
            f"No OCR engine available for --engine {pref}. Install tesseract "
            "(`apt-get install tesseract-ocr` / scoop on Windows) or easyocr "
            "(`pip install easyocr`, optionally into <skill>/.venv), or "
            "extract this source another way.")
    return avail


def _ocr_image(png: Path, lang: str, engines, progress, page_label=""):
    for i, eng in enumerate(engines):
        if eng in _disabled_engines:
            continue
        try:
            return _ENGINE_FN[eng](png, lang)
        except Exception as e:
            # ImportError/OSError mean the engine itself is broken (missing
            # module, wrong-architecture DLL, vanished binary) — no page will
            # ever succeed, so disable it instead of re-failing every page.
            fatal = isinstance(e, (ImportError, OSError))
            if fatal:
                _disabled_engines.add(eng)
            nxt = next((x for x in engines[i + 1:]
                        if x not in _disabled_engines), None)
            progress(f"{eng} failed{page_label}: {e}"
                     + (" -- disabling it for the rest of this run" if fatal else "")
                     + (f" -- falling back to {nxt}" if nxt else ""))
    return ""


def _clean(text: str) -> str:
    """Light cleanup of common OCR noise without touching real content."""
    text = text.replace("\u00ad", "")
    text = re.sub(r"-\n(?=[a-z\u00e0-\u024f])", "", text)   # re-join hyphenated line breaks
    lines = [ln.rstrip() for ln in text.splitlines()]
    lines = [ln for ln in lines if re.search(r"[\w\u0080-\uffff]", ln) or not ln.strip()]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


# ------------------------------------------------------- PDF rasterization
# NamedTemporaryFile handles are closed before the renderer writes to the
# path: on Windows an open handle blocks other writers, which silently broke
# OCR before this fix.

def _pages_via_fitz(pdf: Path, dpi: int, page_range):
    import fitz  # type: ignore
    doc = fitz.open(str(pdf))
    total = doc.page_count
    for n in page_range or range(1, total + 1):
        if n > total:
            break
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
            tf.close()
            doc[n - 1].get_pixmap(dpi=dpi).save(tf.name)
            yield n, Path(tf.name), total
    doc.close()


def _pages_via_pdftoppm(pdf: Path, dpi: int, page_range):
    if not shutil.which("pdftoppm"):
        raise RuntimeError("pdftoppm not available")
    with tempfile.TemporaryDirectory() as td:
        cmd = ["pdftoppm", "-r", str(dpi), "-png", "-gray"]
        if page_range:
            cmd += ["-f", str(min(page_range)), "-l", str(max(page_range))]
        cmd += [str(pdf), str(Path(td) / "pg")]
        subprocess.run(cmd, check=True, capture_output=True, timeout=3600)
        pngs = sorted(Path(td).glob("pg-*.png"),
                      key=lambda p: int(re.search(r"(\d+)\.png$", p.name).group(1)))
        total = len(pngs) if not page_range else None
        for p in pngs:
            n = int(re.search(r"(\d+)\.png$", p.name).group(1))
            if page_range and n not in page_range:
                continue
            yield n, p, total


def _pages_via_pdfium(pdf: Path, dpi: int, page_range):
    import pypdfium2 as pdfium  # type: ignore
    doc = pdfium.PdfDocument(str(pdf))
    total = len(doc)
    for n in page_range or range(1, total + 1):
        if n > total:
            break
        bitmap = doc[n - 1].render(scale=dpi / 72)
        pil = bitmap.to_pil()
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
            tf.close()
            pil.save(tf.name)
            yield n, Path(tf.name), total


def run_ocr(path: Path, lang: str = "eng", dpi: int = 300, page_range=None,
            engine: str = "auto",
            progress=lambda msg: print(msg, file=sys.stderr)):
    """OCR a PDF or image. Returns list of (page_number, text). Raises when
    no OCR engine is available or rasterization fails entirely."""
    path = Path(path)
    engines = pick_engines(engine)
    if engines[0] == "easyocr":
        gpu = "?"
        try:
            import torch
            gpu = torch.cuda.is_available()
        except Exception:
            pass
        progress(f"OCR engine: easyocr (GPU={gpu})"
                 + (", fallback tesseract" if "tesseract" in engines else ""))

    if path.suffix.lower() in IMAGE_EXTS:
        progress(f"OCR {path.name} (image, lang={lang})")
        return [(1, _clean(_ocr_image(path, lang, engines, progress)))]

    last_err = None
    for name, fn in (("pymupdf", _pages_via_fitz),
                     ("pdftoppm", _pages_via_pdftoppm),
                     ("pypdfium2", _pages_via_pdfium)):
        try:
            results = []
            for n, png, total in fn(path, dpi, page_range):
                progress(f"OCR {path.name} p.{n}{f'/{total}' if total else ''} "
                         f"({name}, {dpi}dpi, lang={lang})")
                try:
                    text = _ocr_image(png, lang, engines, progress,
                                      page_label=f" on p.{n}")
                    results.append((n, _clean(text)))
                finally:
                    png.unlink(missing_ok=True)
            if results:
                return results
        except ImportError:
            continue
        except Exception as e:
            last_err = e
            continue
    raise RuntimeError(f"Could not rasterize {path.name}: no working backend "
                       f"(tried pymupdf, pdftoppm, pypdfium2). Last error: {last_err}")


def parse_page_arg(spec: str):
    """'1-40' or '3' or '1-10,50-60' → sorted set of ints."""
    pages = set()
    for part in spec.split(","):
        if "-" in part:
            a, b = part.split("-")
            pages.update(range(int(a), int(b) + 1))
        else:
            pages.add(int(part))
    return sorted(pages)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("file", help="PDF or image to OCR")
    ap.add_argument("-o", "--out", help="Write text here (default: stdout)")
    ap.add_argument("--lang", default="eng",
                    help="OCR language(s), tesseract codes, e.g. eng, deu, eng+bul")
    ap.add_argument("--dpi", type=int, default=300)
    ap.add_argument("--pages", help="Page selection, e.g. 1-40 or 1-10,50-60")
    ap.add_argument("--engine", default="auto",
                    choices=["auto", "tesseract", "easyocr"],
                    help="OCR engine (auto = easyocr when installed, else tesseract)")
    args = ap.parse_args()

    page_range = parse_page_arg(args.pages) if args.pages else None
    pages = run_ocr(Path(args.file), lang=args.lang, dpi=args.dpi,
                    page_range=page_range, engine=args.engine)
    chunks = [f"[[page {n}]]\n{text}" for n, text in pages if text.strip()]
    body = "\n\n".join(chunks) + "\n"
    if args.out:
        Path(args.out).write_text(body, encoding="utf-8")
        words = sum(len(t.split()) for _, t in pages)
        print(f"Wrote {len(chunks)} page(s), ~{words} words → {args.out}",
              file=sys.stderr)
    else:
        sys.stdout.write(body)


if __name__ == "__main__":
    try:
        main()
    except BrokenPipeError:
        try:
            sys.stdout.close()
        except Exception:
            pass
