"""Minimal UI translations for English/French/German.

Deliberately not a full i18n framework (no .po files, no pluralization
rules) -- this is a small local tool with a handful of fixed strings, and a
plain dict keeps that easy to scan and edit by hand.

Scope note: the fallback-rate warning text built in fx_rate.py (RateResult
.warning) is left untranslated everywhere -- it's a technical diagnostic
message that embeds a raw exception string, which can't be meaningfully
translated anyway.
"""

TRANSLATIONS = {
    "en": {
        "page_title": "IKYUM Price List Generator",
        "heading": "IKYUM Price List Generator",
        "subtitle": "Upload the client's price-list workbook to generate the finished A5 PDF.",
        "currency_label": "Currency",
        "currency_both": "CHF + EUR",
        "currency_chf": "CHF only",
        "currency_eur": "EUR only",
        "buffer_label": "Exchange rate buffer",
        "buffer_checkbox_text": "Apply +{percent}% buffer on top of the live rate",
        "buffer_none": "None (disabled)",
        "generate_button": "Generate PDF",
        "error_no_file": "Please choose an .xlsx file first.",
        "error_not_xlsx": "File must be a .xlsx workbook.",
        "error_invalid_currency": "Invalid currency option: {value!r}",
        "error_missing_cover": "Missing cover template file: {exc}. Run make_placeholder_covers.py "
                                "first, or check config.json's cover paths.",
        "error_generation_failed": "Generation failed: {exc}",
        "result_heading": "Price list ready",
        "label_currency": "Currency",
        "label_rate_source": "Rate source",
        "rate_source_live": "Live (Frankfurter API)",
        "rate_source_fallback": "Fallback (config.json)",
        "label_mid_market_rate": "Mid-market rate",
        "label_buffer_applied": "Buffer applied",
        "label_rate_used": "Rate used for EUR prices",
        "label_sections": "Sections",
        "label_items": "Items",
        "download_button": "Download PDF",
        "generate_another": "Generate another",
    },
    "fr": {
        "page_title": "Générateur de liste de prix IKYUM",
        "heading": "Générateur de liste de prix IKYUM",
        "subtitle": "Importez le classeur de tarifs du client pour générer le PDF A5 final.",
        "currency_label": "Devise",
        "currency_both": "CHF + EUR",
        "currency_chf": "CHF uniquement",
        "currency_eur": "EUR uniquement",
        "buffer_label": "Marge sur le taux de change",
        "buffer_checkbox_text": "Appliquer une marge de +{percent}% sur le taux en direct",
        "buffer_none": "Aucune (désactivée)",
        "generate_button": "Générer le PDF",
        "error_no_file": "Veuillez d'abord choisir un fichier .xlsx.",
        "error_not_xlsx": "Le fichier doit être un classeur .xlsx.",
        "error_invalid_currency": "Option de devise invalide : {value!r}",
        "error_missing_cover": "Fichier modèle de couverture manquant : {exc}. Exécutez d'abord "
                                "make_placeholder_covers.py, ou vérifiez les chemins dans config.json.",
        "error_generation_failed": "Échec de la génération : {exc}",
        "result_heading": "Liste de prix prête",
        "label_currency": "Devise",
        "label_rate_source": "Source du taux",
        "rate_source_live": "En direct (API Frankfurter)",
        "rate_source_fallback": "Secours (config.json)",
        "label_mid_market_rate": "Taux interbancaire",
        "label_buffer_applied": "Marge appliquée",
        "label_rate_used": "Taux utilisé pour les prix EUR",
        "label_sections": "Sections",
        "label_items": "Articles",
        "download_button": "Télécharger le PDF",
        "generate_another": "Générer une autre liste",
    },
    "de": {
        "page_title": "IKYUM Preislisten-Generator",
        "heading": "IKYUM Preislisten-Generator",
        "subtitle": "Laden Sie die Preisliste des Kunden hoch, um das fertige A5-PDF zu erstellen.",
        "currency_label": "Währung",
        "currency_both": "CHF + EUR",
        "currency_chf": "Nur CHF",
        "currency_eur": "Nur EUR",
        "buffer_label": "Wechselkurspuffer",
        "buffer_checkbox_text": "Puffer von +{percent}% auf den Live-Kurs anwenden",
        "buffer_none": "Keiner (deaktiviert)",
        "generate_button": "PDF erstellen",
        "error_no_file": "Bitte wählen Sie zuerst eine .xlsx-Datei aus.",
        "error_not_xlsx": "Die Datei muss eine .xlsx-Arbeitsmappe sein.",
        "error_invalid_currency": "Ungültige Währungsoption: {value!r}",
        "error_missing_cover": "Cover-Vorlagendatei fehlt: {exc}. Führen Sie zuerst "
                                "make_placeholder_covers.py aus, oder prüfen Sie die Pfade in config.json.",
        "error_generation_failed": "Erstellung fehlgeschlagen: {exc}",
        "result_heading": "Preisliste bereit",
        "label_currency": "Währung",
        "label_rate_source": "Kursquelle",
        "rate_source_live": "Live (Frankfurter API)",
        "rate_source_fallback": "Ausweichwert (config.json)",
        "label_mid_market_rate": "Mittelkurs",
        "label_buffer_applied": "Angewendeter Puffer",
        "label_rate_used": "Für EUR-Preise verwendeter Kurs",
        "label_sections": "Abschnitte",
        "label_items": "Artikel",
        "download_button": "PDF herunterladen",
        "generate_another": "Weitere erstellen",
    },
}

SUPPORTED_LANGS = tuple(TRANSLATIONS.keys())  # ("en", "fr", "de")
DEFAULT_LANG = "en"

LANGUAGE_NAMES = {"en": "EN", "fr": "FR", "de": "DE"}


def resolve_lang(candidate: str | None) -> str:
    """Returns candidate if it's a supported language code, else the default."""
    return candidate if candidate in SUPPORTED_LANGS else DEFAULT_LANG


def get_translator(lang: str):
    """Returns a t(key, **kwargs) function for the given language, falling
    back to English for any key missing in that language's dict, and to the
    raw key itself if it's missing from English too (so a typo shows up as
    visibly wrong text instead of crashing the page).
    """
    strings = TRANSLATIONS.get(lang, TRANSLATIONS[DEFAULT_LANG])
    fallback = TRANSLATIONS[DEFAULT_LANG]

    def t(key: str, **kwargs) -> str:
        text = strings.get(key, fallback.get(key, key))
        return text.format(**kwargs) if kwargs else text

    return t
