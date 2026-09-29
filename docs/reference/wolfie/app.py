"""
PDF / dokumenty → Markdown
==========================
Lokální webová aplikace nad Microsoft MarkItDown.
Převede PDF (a další formáty) na Markdown, který se snadno vloží do AI.

Spuštění:  py app.py   (nebo dvojklik na run.bat)
Pak otevři: http://127.0.0.1:5000
"""

import io
import os
import re
import sys
import uuid
import socket
import zipfile
import tempfile
import threading
import webbrowser
from datetime import datetime


class _NullStream:
    """Náhrada za stdout/stderr v okenním .exe (--windowed je nemá -> jinak pád)."""

    def write(self, *a, **k):
        return 0

    def flush(self):
        pass


# V okenním režimu (PyInstaller --windowed) jsou stdout/stderr None; cokoli,
# co by chtělo psát na konzoli (banner Flasku, print) by jinak spadlo.
if sys.stdout is None:
    sys.stdout = _NullStream()
if sys.stderr is None:
    sys.stderr = _NullStream()

PORT = 5000


def pick_port(preferred: int = 5000) -> int:
    """Vrátí preferovaný port, a když je obsazený, najde jiný volný."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", preferred))
        return preferred
    except OSError:
        s2 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s2.bind(("127.0.0.1", 0))
        port = s2.getsockname()[1]
        s2.close()
        return port
    finally:
        s.close()


def app_dir() -> str:
    """Složka, kam ukládat výstupy – vedle .exe (nebo vedle app.py při běžném spuštění)."""
    if getattr(sys, "frozen", False):  # zabaleno PyInstallerem
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def resource_path(rel: str) -> str:
    """Cesta k zabaleným zdrojům (index.html). V onefile EXE je to dočasná složka _MEIPASS."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, rel)

from flask import (
    Flask,
    render_template,
    request,
    jsonify,
    send_file,
    abort,
)

try:
    from markitdown import MarkItDown
except ImportError:  # pragma: no cover
    raise SystemExit(
        "Chybí knihovna 'markitdown'. Nainstaluj ji:\n"
        '   py -m pip install "markitdown[all]" flask'
    )

# template_folder => index.html leží vedle app.py (resp. v _MEIPASS u .exe),
# takže ho lze i otevřít dvojklikem (file://), nejen načíst přes server.
app = Flask(__name__, template_folder=resource_path("."))
app.config["MAX_CONTENT_LENGTH"] = 200 * 1024 * 1024  # 200 MB na jeden request


@app.after_request
def _cors(resp):
    # Povolíme volání i když je stránka otevřená z jiného původu
    # (např. z náhledového panelu Claude Code), ne jen z 127.0.0.1:5000.
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return resp


@app.route("/convert", methods=["OPTIONS"])
@app.route("/convert_paths", methods=["OPTIONS"])
@app.route("/save_to_disk", methods=["OPTIONS"])
def _preflight():
    return ("", 204)

# MarkItDown je vláknově nezávislý na instanci – vytvoříme jednu sdílenou.
_md = MarkItDown()

# Jednoduché in-memory úložiště převedených výsledků (běží lokálně, jeden uživatel).
# id -> {"name": "soubor.md", "markdown": "...", "created": datetime}
_RESULTS: dict[str, dict] = {}
_LOCK = threading.Lock()

# Kam ukládat při „Uložit na disk“ (vedle app.py / .exe).
OUTPUT_DIR = os.path.join(app_dir(), "output")


# ── čištění výstupu (oprava typických artefaktů z PDF) ──────────────────────
_LIGATURES = {
    "ﬁ": "fi", "ﬂ": "fl", "ﬀ": "ff", "ﬃ": "ffi", "ﬄ": "ffl",
    "ﬅ": "ft", "ﬆ": "st",
}
# řádek, který nesmíme spojit s předchozím (nadpisy, odrážky, tabulky, kód…)
_BLOCK_RE = re.compile(r"^\s*(#{1,6}\s|[-*+]\s|\d+[.)]\s|>|\||```|=== )")


def _unwrap_lines(text: str) -> str:
    """Spojí natvrdo zalomené řádky uvnitř odstavce do jednoho řádku."""
    out: list[str] = []
    para: list[str] = []

    def flush():
        if para:
            out.append(" ".join(s.strip() for s in para))
            para.clear()

    for line in text.split("\n"):
        if line.strip() == "":
            flush()
            out.append("")
        elif _BLOCK_RE.match(line):
            flush()
            out.append(line)
        else:
            para.append(line)
    flush()
    return "\n".join(out)


def clean_markdown(text: str) -> str:
    """Opraví typické nečistoty z PDF: ligatury, (cid:NN), dělení slov,
    zalomené řádky, čísla stránek a přebytečné prázdné řádky."""
    if not text:
        return text
    for a, b in _LIGATURES.items():
        text = text.replace(a, b)
    text = re.sub(r"\(cid:\d+\)", "", text)          # zbytky nečitelných znaků
    text = text.replace("\f", "\n\n")                 # konce stránek
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)      # slovo roz-\ndělené koncem řádku
    text = re.sub(r"(?m)^[ \t]*\d{1,4}[ \t]*$\n?", "", text)  # osamocená čísla stránek
    text = _unwrap_lines(text)                          # spojení zalomených řádků
    text = re.sub(r"\n{3,}", "\n\n", text)            # max. jeden prázdný řádek
    return text.strip() + "\n"


def _to_markdown(file_storage, clean: bool = False) -> str:
    """Převede nahraný soubor na Markdown pomocí MarkItDown."""
    original = file_storage.filename or "soubor"
    suffix = os.path.splitext(original)[1] or ""
    # MarkItDown si rád bere cestu k souboru (lépe detekuje typ podle přípony),
    # tak nahrávku uložíme do dočasného souboru.
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        file_storage.save(tmp.name)
        tmp_path = tmp.name
    try:
        result = _md.convert(tmp_path)
        text = result.text_content or ""
        return clean_markdown(text) if clean else text
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def _to_markdown_path(path: str, clean: bool = False) -> str:
    """Převede soubor zadaný cestou (z nativního dialogu / drag&drop v okně)."""
    result = _md.convert(path)
    text = result.text_content or ""
    return clean_markdown(text) if clean else text


def _md_name(original: str) -> str:
    base = os.path.splitext(os.path.basename(original))[0] or "dokument"
    return f"{base}.md"


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/convert", methods=["POST"])
def convert():
    files = request.files.getlist("files")
    if not files:
        return jsonify({"error": "Žádné soubory."}), 400

    clean = request.form.get("clean", "false").lower() == "true"

    out = []
    for f in files:
        if not f or not f.filename:
            continue
        entry = {"name": f.filename}
        try:
            markdown = _to_markdown(f, clean=clean)
            file_id = uuid.uuid4().hex
            md_name = _md_name(f.filename)
            with _LOCK:
                _RESULTS[file_id] = {
                    "name": md_name,
                    "markdown": markdown,
                    "created": datetime.now(),
                }
            entry.update(
                {
                    "id": file_id,
                    "md_name": md_name,
                    "markdown": markdown,
                    "chars": len(markdown),
                    "ok": True,
                }
            )
        except Exception as exc:  # noqa: BLE001 – chceme chybu ukázat uživateli
            entry.update({"ok": False, "error": str(exc)})
        out.append(entry)

    return jsonify({"results": out})


@app.route("/convert_paths", methods=["POST"])
def convert_paths():
    """Převede soubory podle cest na disku – používá nativní výběr v okně
    (pywebview), kde je spolehlivější než HTML5 výběr/přetažení."""
    data = request.get_json(silent=True) or {}
    paths = data.get("paths") or []
    clean = bool(data.get("clean"))
    if not paths:
        return jsonify({"error": "Žádné soubory."}), 400

    out = []
    for p in paths:
        name = os.path.basename(p) or "soubor"
        entry = {"name": name}
        try:
            markdown = _to_markdown_path(p, clean=clean)
            file_id = uuid.uuid4().hex
            md_name = _md_name(name)
            with _LOCK:
                _RESULTS[file_id] = {
                    "name": md_name,
                    "markdown": markdown,
                    "created": datetime.now(),
                }
            entry.update(
                {
                    "id": file_id,
                    "md_name": md_name,
                    "markdown": markdown,
                    "chars": len(markdown),
                    "ok": True,
                }
            )
        except Exception as exc:  # noqa: BLE001 – chceme chybu ukázat uživateli
            entry.update({"ok": False, "error": str(exc)})
        out.append(entry)

    return jsonify({"results": out})


@app.route("/download/<file_id>")
def download(file_id):
    with _LOCK:
        item = _RESULTS.get(file_id)
    if not item:
        abort(404)
    buf = io.BytesIO(item["markdown"].encode("utf-8"))
    return send_file(
        buf,
        mimetype="text/markdown; charset=utf-8",
        as_attachment=True,
        download_name=item["name"],
    )


@app.route("/download_all")
def download_all():
    ids = request.args.get("ids", "")
    wanted = [i for i in ids.split(",") if i]
    buf = io.BytesIO()
    used = set()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        with _LOCK:
            items = [
                _RESULTS[i] for i in wanted if i in _RESULTS
            ] or list(_RESULTS.values())
        for item in items:
            name = item["name"]
            # zabráníme duplicitním názvům v zipu
            n = name
            k = 1
            while n in used:
                stem, ext = os.path.splitext(name)
                n = f"{stem}_{k}{ext}"
                k += 1
            used.add(n)
            zf.writestr(n, item["markdown"])
    buf.seek(0)
    return send_file(
        buf,
        mimetype="application/zip",
        as_attachment=True,
        download_name="markdown.zip",
    )


@app.route("/save_to_disk", methods=["POST"])
def save_to_disk():
    data = request.get_json(silent=True) or {}
    wanted = data.get("ids") or []
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    saved = []
    with _LOCK:
        items = [_RESULTS[i] for i in wanted if i in _RESULTS] or list(
            _RESULTS.values()
        )
    for item in items:
        path = os.path.join(OUTPUT_DIR, item["name"])
        # ať nepřepisujeme – přidáme číslo
        stem, ext = os.path.splitext(path)
        k = 1
        while os.path.exists(path):
            path = f"{stem}_{k}{ext}"
            k += 1
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(item["markdown"])
        saved.append(os.path.basename(path))
    return jsonify({"folder": OUTPUT_DIR, "saved": saved})


class Api:
    """Most mezi JavaScriptem v okně a Pythonem (pywebview).

    Otevře nativní systémový dialog pro výběr souborů. Uvnitř okna (WebView2)
    je to spolehlivější cesta, jak dostat soubory dovnitř, než HTML5 výběr nebo
    přetažení – a hlavně nikdy „neotevře soubor v prohlížeči“.
    """

    def __init__(self):
        self.window = None

    def pick_files(self):
        """Vrátí seznam absolutních cest k vybraným souborům (nebo prázdný)."""
        import webview

        if self.window is None:
            return []
        file_types = (
            "Dokumenty (*.pdf;*.docx;*.doc;*.pptx;*.ppt;*.xlsx;*.xls;"
            "*.html;*.htm;*.txt;*.md;*.csv;*.png;*.jpg;*.jpeg)",
            "Všechny soubory (*.*)",
        )
        paths = self.window.create_file_dialog(
            webview.OPEN_DIALOG, allow_multiple=True, file_types=file_types
        )
        return list(paths) if paths else []


def _run_server():
    app.run(host="127.0.0.1", port=PORT, debug=False, use_reloader=False, threaded=True)


def _wait_until_up(timeout: float = 15.0) -> bool:
    """Počká, než server začne přijímat spojení."""
    import time

    end = time.time() + timeout
    while time.time() < end:
        try:
            with socket.create_connection(("127.0.0.1", PORT), 0.5):
                return True
        except OSError:
            time.sleep(0.15)
    return False


def main():
    global PORT
    PORT = pick_port(PORT)

    # Jen server, bez okna/prohlížeče (pro testy a náhled).
    if "--server-only" in sys.argv:
        _run_server()
        return

    url = f"http://127.0.0.1:{PORT}"

    # Flask běží na pozadí; hlavní vlákno drží okno aplikace.
    threading.Thread(target=_run_server, daemon=True).start()
    _wait_until_up()

    # Výchozí je nativní okno (pywebview). S přepínačem --web (nebo když okno
    # nejde otevřít) se použije prohlížeč.
    if "--web" not in sys.argv:
        try:
            import webview

            api = Api()
            window = webview.create_window(
                "PDF → Markdown",
                url,
                width=1100,
                height=820,
                min_size=(760, 560),
                js_api=api,
            )
            api.window = window
            webview.start()
            return  # okno zavřeno -> konec
        except Exception as exc:  # noqa: BLE001
            print("Nativní okno nelze otevřít, používám prohlížeč:", exc)

    webbrowser.open(url)
    print(f"\n  PDF -> Markdown běží na  {url}\n  (okno/terminál zavři pro ukončení)\n")
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
