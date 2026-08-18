"""Local-only Flask app: upload the client's price-list .xlsx, generate the
finished A5 PDF (cover + price tables + back cover), download it.

No auth, no database, never exposed beyond localhost -- run with
`python app.py` and open http://127.0.0.1:5000.
"""

import os
import uuid
from datetime import datetime

from flask import Flask, make_response, render_template, request, send_from_directory, url_for
from werkzeug.utils import secure_filename

from build_pricelist import build
from fx_rate import load_config
from generate_pricelist import CURRENCY_MODES
from i18n import LANGUAGE_NAMES, SUPPORTED_LANGS, get_translator, resolve_lang

app = Flask(__name__)

CONFIG = load_config()
UPLOAD_DIR = CONFIG["upload_dir"]
OUTPUT_DIR = CONFIG["output_dir"]
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

LANG_COOKIE_MAX_AGE = 60 * 60 * 24 * 365  # 1 year


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
    apply_buffer = "apply_buffer" in request.form
    buffer_percent = CONFIG["fx"]["buffer_percent"]

    uploaded = request.files.get("price_list")
    if uploaded is None or uploaded.filename == "":
        return render("index.html", 400, lang=lang, error=t("error_no_file"),
                       currency=currency_mode, apply_buffer=apply_buffer, buffer_percent=buffer_percent)
    if not uploaded.filename.lower().endswith(".xlsx"):
        return render("index.html", 400, lang=lang, error=t("error_not_xlsx"),
                       currency=currency_mode, apply_buffer=apply_buffer, buffer_percent=buffer_percent)
    if currency_mode not in CURRENCY_MODES:
        return render("index.html", 400, lang=lang, error=t("error_invalid_currency", value=currency_mode),
                       apply_buffer=apply_buffer, buffer_percent=buffer_percent)

    run_id = uuid.uuid4().hex[:8]
    safe_name = secure_filename(uploaded.filename)
    upload_path = os.path.join(UPLOAD_DIR, f"{run_id}_{safe_name}")
    uploaded.save(upload_path)

    try:
        result = build(upload_path, CONFIG, currency_mode, apply_buffer)
    except FileNotFoundError as exc:
        return render("index.html", 400, lang=lang, error=t("error_missing_cover", exc=exc),
                       currency=currency_mode, apply_buffer=apply_buffer, buffer_percent=buffer_percent)
    except Exception as exc:
        return render("index.html", 500, lang=lang, error=t("error_generation_failed", exc=exc),
                       currency=currency_mode, apply_buffer=apply_buffer, buffer_percent=buffer_percent)

    output_filename = f"pricelist_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{run_id}.pdf"
    output_path = os.path.join(OUTPUT_DIR, output_filename)
    with open(output_path, "wb") as f:
        f.write(result.pdf_bytes)

    return render(
        "result.html",
        lang=lang,
        download_url=url_for("download", filename=output_filename),
        date_stamp_text=result.date_stamp_text,
        rate=result.rate,
        section_count=result.section_count,
        item_count=result.item_count,
        currency_mode=result.currency_mode,
    )


@app.route("/download/<path:filename>", methods=["GET"])
def download(filename):
    return send_from_directory(OUTPUT_DIR, filename, as_attachment=True)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
