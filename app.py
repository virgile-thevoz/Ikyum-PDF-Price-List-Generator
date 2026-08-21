"""Local-only Flask app: upload the client's price-list .xlsx, generate the
finished A5 PDF (cover + price tables + back cover), download it.

No auth, no database, never exposed beyond localhost -- run with
`python app.py` and open http://127.0.0.1:5000.
"""

import os
import re
import uuid
from datetime import datetime

from flask import Flask, make_response, render_template, request, send_from_directory, url_for
from werkzeug.utils import secure_filename

from build_pricelist import build
from fx_rate import load_config
from generate_pricelist import CURRENCY_MODES, PDF_TYPES, RESALE_MULTIPLIERS
from i18n import LANGUAGE_NAMES, SUPPORTED_LANGS, get_translator, resolve_lang

app = Flask(__name__)

CONFIG = load_config()
UPLOAD_DIR = CONFIG["upload_dir"]
OUTPUT_DIR = CONFIG["output_dir"]
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

LANG_COOKIE_MAX_AGE = 60 * 60 * 24 * 365  # 1 year

# Characters invalid in filenames on Windows/macOS/most filesystems, plus
# ASCII control characters -- stripped from the user-chosen download name
# (see sanitize_pdf_filename). Deliberately not werkzeug's secure_filename:
# that's ASCII-only and would mangle accented names (e.g. "Liste d'été"),
# which is fine for the *stored* file (an opaque internal name, see
# output_filename in generate()) but not for a name the client picked to
# recognize their own file by.
_UNSAFE_FILENAME_CHARS = re.compile(r'[\x00-\x1f\x7f/\\:*?"<>|]')


def sanitize_pdf_filename(name: str, fallback: str) -> str:
    """Turns a user-supplied name into a safe *download* filename (the name
    the browser saves the file as -- see the "as" query param on the
    /download route): strips characters invalid on common filesystems,
    collapses whitespace, caps length, and ensures a single ".pdf"
    extension. Falls back to `fallback` (expected to already be a safe
    "*.pdf" name) if the result would be empty.
    """
    name = _UNSAFE_FILENAME_CHARS.sub("", name or "")
    name = re.sub(r"\s+", " ", name).strip()
    name = re.sub(r"\.pdf$", "", name, flags=re.IGNORECASE).strip()
    name = name[:150]
    return f"{name}.pdf" if name else fallback


def parse_resale_multiplier(raw: str) -> float | None:
    """Turns the resale_multiplier form field's raw string into a float, or
    None for the "None (disabled)" option (an empty string). Raises
    ValueError if it's non-empty but not one of RESALE_MULTIPLIERS.
    """
    raw = (raw or "").strip()
    if not raw:
        return None
    value = float(raw)
    if value not in RESALE_MULTIPLIERS:
        raise ValueError(f"resale_multiplier must be one of {RESALE_MULTIPLIERS} or empty, got {raw!r}")
    return value


def current_lang() -> str:
    """The language for this request: an explicit ?lang=/form field wins,
    then the cookie from a previous visit, then the default (English).
    """
    return resolve_lang(request.values.get("lang") or request.cookies.get("lang"))


def render(template_name: str, status: int = 200, lang: str | None = None, **context):
    """render_template plus: inject t()/lang/languages for the toggle, and
    persist the chosen language in a cookie so it carries over to the next
    request (e.g. from the upload page to the result page).
    """
    if lang is None:
        lang = current_lang()
    t = get_translator(lang)
    body = render_template(template_name, t=t, lang=lang, languages=SUPPORTED_LANGS, language_names=LANGUAGE_NAMES, **context)
    response = make_response(body, status)
    response.set_cookie("lang", lang, max_age=LANG_COOKIE_MAX_AGE)
    return response


@app.route("/", methods=["GET"])
def index():
    return render("index.html", buffer_percent=CONFIG["fx"]["buffer_percent"], apply_buffer=True)


@app.route("/generate", methods=["POST"])
def generate():
    lang = current_lang()
    t = get_translator(lang)
    currency_mode = request.form.get("currency", "both")
    pdf_type = request.form.get("pdf_type", "web")
    output_name = request.form.get("output_name", "")
    resale_multiplier_raw = request.form.get("resale_multiplier", "")
    apply_buffer = "apply_buffer" in request.form
    buffer_percent = CONFIG["fx"]["buffer_percent"]
    # Common re-render context shared by every validation-error/exception
    # branch below, so the client's other choices aren't lost on error.
    form_state = dict(currency=currency_mode, pdf_type=pdf_type, output_name=output_name,
                       resale_multiplier=resale_multiplier_raw, apply_buffer=apply_buffer, buffer_percent=buffer_percent)

    uploaded = request.files.get("price_list")
    if uploaded is None or uploaded.filename == "":
        return render("index.html", 400, lang=lang, error=t("error_no_file"), **form_state)
    if not uploaded.filename.lower().endswith(".xlsx"):
        return render("index.html", 400, lang=lang, error=t("error_not_xlsx"), **form_state)
    if currency_mode not in CURRENCY_MODES:
        return render("index.html", 400, lang=lang, error=t("error_invalid_currency", value=currency_mode), **form_state)
    if pdf_type not in PDF_TYPES:
        return render("index.html", 400, lang=lang, error=t("error_invalid_pdf_type", value=pdf_type), **form_state)
    try:
        resale_multiplier = parse_resale_multiplier(resale_multiplier_raw)
    except ValueError:
        return render("index.html", 400, lang=lang, error=t("error_invalid_resale_multiplier", value=resale_multiplier_raw), **form_state)

    run_id = uuid.uuid4().hex[:8]
    safe_name = secure_filename(uploaded.filename)
    upload_path = os.path.join(UPLOAD_DIR, f"{run_id}_{safe_name}")
    uploaded.save(upload_path)

    try:
        result = build(upload_path, CONFIG, currency_mode, apply_buffer, pdf_type, lang, resale_multiplier)
    except FileNotFoundError as exc:
        return render("index.html", 400, lang=lang, error=t("error_missing_cover", exc=exc), **form_state)
    except Exception as exc:
        return render("index.html", 500, lang=lang, error=t("error_generation_failed", exc=exc), **form_state)

    # output_filename is the *stored* name on disk -- an opaque, always-safe,
    # always-unique internal identifier (also embedded in the download URL).
    # It's separate from the *download* name (what the browser saves the
    # file as), which is whatever the client typed in output_name -- see
    # sanitize_pdf_filename and the /download route's "as" query param.
    output_filename = f"pricelist_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{run_id}.pdf"
    output_path = os.path.join(OUTPUT_DIR, output_filename)
    with open(output_path, "wb") as f:
        f.write(result.pdf_bytes)

    download_name = sanitize_pdf_filename(output_name, fallback=output_filename)

    return render(
        "result.html",
        lang=lang,
        download_url=url_for("download", filename=output_filename, **{"as": download_name}),
        date_stamp_text=result.date_stamp_text,
        rate=result.rate,
        section_count=result.section_count,
        item_count=result.item_count,
        currency_mode=result.currency_mode,
        pdf_type=result.pdf_type,
        download_name=download_name,
        resale_multiplier=result.resale_multiplier,
    )


@app.route("/download/<path:filename>", methods=["GET"])
def download(filename):
    download_name = sanitize_pdf_filename(request.args.get("as", ""), fallback=filename)
    return send_from_directory(OUTPUT_DIR, filename, as_attachment=True, download_name=download_name)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
