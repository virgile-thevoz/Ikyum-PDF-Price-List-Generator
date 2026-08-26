"""Minimal UI translations for English/French/German.

Deliberately not a full i18n framework (no .po files, no pluralization
rules) -- this is a small local tool with a handful of fixed strings, and a
plain dict keeps that easy to scan and edit by hand.

Scope note: the fallback-rate warning text built in fx_rate.py (RateResult
.warning) is left untranslated everywhere -- it's a technical diagnostic
message that embeds a raw exception string, which can't be meaningfully
translated anyway.

Most of these strings are web-UI-only (see app.py's render()). Five are
the exception, all resolved by build_pricelist.py rather than app.py
directly: "pdf_footer_role" (the one word/phrase in generate_pricelist.py's
per-page footer that varies by language), "pdf_index_label" (the table of
contents' own title, and the matching word in the "back to top" link on
every other page), "pdf_option_column_label" (each item's price sub-table
column header, above its option names -- always plural, since an item
usually lists more than one option), "pdf_sale_prices_label" (stamped on
the front cover only, right-aligned next to the date stamp, on every
generated PDF regardless of whether a resale multiplier was used -- see
cover_stamp.assemble_final_pdf's price_type_text), and the "Rates from
..." cover date stamp, which is fully localized (label and date format
both) by date_stamp.py -- see that module's LABELS/MONTH_NAMES rather than
this file for the date stamp's own strings.
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
        "rate_mode_label": "Exchange rate",
        "rate_mode_daily": "Daily rate",
        "rate_mode_custom": "Custom rate",
        "custom_rate_placeholder": "e.g. 0.97",
        "buffer_label": "Exchange rate buffer",
        "buffer_checkbox_text": "Apply +{percent}% buffer on top of the live rate",
        "buffer_daily_only_hint": "Applies to the daily rate only",
        "buffer_none": "None (disabled)",
        "resale_label": "Suggested sale prices (multiplier)",
        "resale_msrp_label": "MSRP",
        "resale_none_label": "None (default MSRP)",
        "editable_prices_label": "Editable prices",
        "editable_prices_checkbox_text": "Make price cells editable in the PDF",
        "editable_prices_hint": "Edit prices individually once the PDF is exported. Item names, descriptions, and everything else stay fixed.",
        "pdf_type_label": "PDF type",
        "pdf_type_web": "Web (interactive)",
        "pdf_type_print": "Print (crop marks)",
        "filename_label": "File name (optional)",
        "filename_placeholder": "Leave blank for an automatic name",
        "generate_button": "Generate PDF",
        "error_no_file": "Please choose an .xlsx file first.",
        "error_not_xlsx": "File must be a .xlsx workbook.",
        "error_invalid_currency": "Invalid currency option: {value!r}",
        "error_invalid_pdf_type": "Invalid PDF type option: {value!r}",
        "error_invalid_resale_multiplier": "Invalid resale multiplier: {value!r}",
        "error_invalid_rate_mode": "Invalid exchange rate option: {value!r}",
        "error_invalid_custom_rate": "Invalid custom rate: {value!r}. Enter a positive number, e.g. 0.97.",
        "error_missing_cover": "Missing cover template file: {exc}. Run make_placeholder_covers.py "
                                "first, or check config.json's cover paths.",
        "error_generation_failed": "Generation failed: {exc}",
        "result_heading": "Price list ready",
        "label_filename": "File name",
        "label_currency": "Currency",
        "label_pdf_type": "PDF type",
        "label_rate_source": "Rate source",
        "rate_source_live": "Live (Frankfurter API)",
        "rate_source_fallback": "Fallback (config.json)",
        "rate_source_custom": "Custom (entered manually)",
        "label_mid_market_rate": "Mid-market rate",
        "label_buffer_applied": "Buffer applied",
        "label_rate_used": "Rate used for EUR prices",
        "label_sections": "Sections",
        "label_items": "Items",
        "download_button": "Download PDF",
        "generate_another": "Generate another",
        "label_resale_multiplier": "Resale multiplier",
        "label_editable_prices": "Editable prices",
        "editable_prices_yes": "Yes -- price cells are fillable form fields",
        "editable_prices_no": "No",
        "pdf_footer_role": "Authorized Representative",
        "pdf_index_label": "Index",
        "pdf_option_column_label": "Options",
        "pdf_sale_prices_label": "Sale prices",
    },
    "fr": {
        "page_title": "Générateur de liste de prix IKYUM",
        "heading": "Générateur de liste de prix IKYUM",
        "subtitle": "Importez le classeur de tarifs du client pour générer le PDF A5 final.",
        "currency_label": "Devise",
        "currency_both": "CHF + EUR",
        "currency_chf": "CHF uniquement",
        "currency_eur": "EUR uniquement",
        "rate_mode_label": "Taux de change",
        "rate_mode_daily": "Taux du jour",
        "rate_mode_custom": "Taux personnalisé",
        "custom_rate_placeholder": "p. ex. 0,97",
        "buffer_label": "Marge sur le taux de change",
        "buffer_checkbox_text": "Appliquer une marge de +{percent}% sur le taux en direct",
        "buffer_daily_only_hint": "S'applique uniquement au taux du jour",
        "buffer_none": "Aucune (désactivée)",
        "resale_label": "Prix de vente suggérés (coefficient)",
        "resale_msrp_label": "PVC",
        "resale_none_label": "Aucun (PVC par défaut)",
        "editable_prices_label": "Prix modifiables",
        "editable_prices_checkbox_text": "Rendre les cellules de prix modifiables dans le PDF",
        "editable_prices_hint": "Modifiez les prix individuellement une fois le PDF exporté. Les noms d'articles, descriptions et tout le reste restent fixes.",
        "pdf_type_label": "Type de PDF",
        "pdf_type_web": "Web (interactif)",
        "pdf_type_print": "Impression (traits de coupe)",
        "filename_label": "Nom du fichier (facultatif)",
        "filename_placeholder": "Laisser vide pour un nom automatique",
        "generate_button": "Générer le PDF",
        "error_no_file": "Veuillez d'abord choisir un fichier .xlsx.",
        "error_not_xlsx": "Le fichier doit être un classeur .xlsx.",
        "error_invalid_currency": "Option de devise invalide : {value!r}",
        "error_invalid_pdf_type": "Option de type de PDF invalide : {value!r}",
        "error_invalid_resale_multiplier": "Multiplicateur de revente invalide : {value!r}",
        "error_invalid_rate_mode": "Option de taux de change invalide : {value!r}",
        "error_invalid_custom_rate": "Taux personnalisé invalide : {value!r}. Saisissez un nombre positif, p. ex. 0,97.",
        "error_missing_cover": "Fichier modèle de couverture manquant : {exc}. Exécutez d'abord "
                                "make_placeholder_covers.py, ou vérifiez les chemins dans config.json.",
        "error_generation_failed": "Échec de la génération : {exc}",
        "result_heading": "Liste de prix prête",
        "label_filename": "Nom du fichier",
        "label_currency": "Devise",
        "label_pdf_type": "Type de PDF",
        "label_rate_source": "Source du taux",
        "rate_source_live": "En direct (API Frankfurter)",
        "rate_source_fallback": "Secours (config.json)",
        "rate_source_custom": "Personnalisé (saisi manuellement)",
        "label_mid_market_rate": "Taux interbancaire",
        "label_buffer_applied": "Marge appliquée",
        "label_rate_used": "Taux utilisé pour les prix EUR",
        "label_sections": "Sections",
        "label_items": "Articles",
        "download_button": "Télécharger le PDF",
        "generate_another": "Générer une autre liste",
        "label_resale_multiplier": "Multiplicateur de revente",
        "label_editable_prices": "Prix modifiables",
        "editable_prices_yes": "Oui -- les cellules de prix sont des champs de formulaire modifiables",
        "editable_prices_no": "Non",
        "pdf_footer_role": "Mandataire autorisé",
        "pdf_index_label": "Index",
        "pdf_option_column_label": "Options",
        "pdf_sale_prices_label": "Prix de vente",
    },
    "de": {
        "page_title": "IKYUM Preislisten-Generator",
        "heading": "IKYUM Preislisten-Generator",
        "subtitle": "Laden Sie die Preisliste des Kunden hoch, um das fertige A5-PDF zu erstellen.",
        "currency_label": "Währung",
        "currency_both": "CHF + EUR",
        "currency_chf": "Nur CHF",
        "currency_eur": "Nur EUR",
        "rate_mode_label": "Wechselkurs",
        "rate_mode_daily": "Tageskurs",
        "rate_mode_custom": "Eigener Kurs",
        "custom_rate_placeholder": "z. B. 0,97",
        "buffer_label": "Wechselkurspuffer",
        "buffer_checkbox_text": "Puffer von +{percent}% auf den Live-Kurs anwenden",
        "buffer_daily_only_hint": "Gilt nur für den Tageskurs",
        "buffer_none": "Keiner (deaktiviert)",
        "resale_label": "Empfohlene Verkaufspreise (Faktor)",
        "resale_msrp_label": "UVP",
        "resale_none_label": "Keiner (Standard-UVP)",
        "editable_prices_label": "Bearbeitbare Preise",
        "editable_prices_checkbox_text": "Preiszellen im PDF bearbeitbar machen",
        "editable_prices_hint": "Bearbeiten Sie die Preise einzeln, nachdem das PDF exportiert wurde. Artikelnamen, Beschreibungen und alles andere bleiben fest.",
        "pdf_type_label": "PDF-Typ",
        "pdf_type_web": "Web (interaktiv)",
        "pdf_type_print": "Druck (Schnittmarken)",
        "filename_label": "Dateiname (optional)",
        "filename_placeholder": "Leer lassen für einen automatischen Namen",
        "generate_button": "PDF erstellen",
        "error_no_file": "Bitte wählen Sie zuerst eine .xlsx-Datei aus.",
        "error_not_xlsx": "Die Datei muss eine .xlsx-Arbeitsmappe sein.",
        "error_invalid_currency": "Ungültige Währungsoption: {value!r}",
        "error_invalid_pdf_type": "Ungültige PDF-Typ-Option: {value!r}",
        "error_invalid_resale_multiplier": "Ungültiger Wiederverkaufsfaktor: {value!r}",
        "error_invalid_rate_mode": "Ungültige Wechselkurs-Option: {value!r}",
        "error_invalid_custom_rate": "Ungültiger eigener Kurs: {value!r}. Geben Sie eine positive Zahl ein, z. B. 0,97.",
        "error_missing_cover": "Cover-Vorlagendatei fehlt: {exc}. Führen Sie zuerst "
                                "make_placeholder_covers.py aus, oder prüfen Sie die Pfade in config.json.",
        "error_generation_failed": "Erstellung fehlgeschlagen: {exc}",
        "result_heading": "Preisliste bereit",
        "label_filename": "Dateiname",
        "label_currency": "Währung",
        "label_pdf_type": "PDF-Typ",
        "label_rate_source": "Kursquelle",
        "rate_source_live": "Live (Frankfurter API)",
        "rate_source_fallback": "Ausweichwert (config.json)",
        "rate_source_custom": "Benutzerdefiniert (manuell eingegeben)",
        "label_mid_market_rate": "Mittelkurs",
        "label_buffer_applied": "Angewendeter Puffer",
        "label_rate_used": "Für EUR-Preise verwendeter Kurs",
        "label_sections": "Abschnitte",
        "label_items": "Artikel",
        "download_button": "PDF herunterladen",
        "generate_another": "Weitere erstellen",
        "label_resale_multiplier": "Wiederverkaufsfaktor",
        "label_editable_prices": "Bearbeitbare Preise",
        "editable_prices_yes": "Ja -- Preiszellen sind ausfüllbare Formularfelder",
        "editable_prices_no": "Nein",
        "pdf_footer_role": "Bevollmächtigter",
        "pdf_index_label": "Verzeichnis",
        "pdf_option_column_label": "Optionen",
        "pdf_sale_prices_label": "Verkaufspreise",
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
