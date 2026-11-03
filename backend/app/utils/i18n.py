"""Fixed-phrase templates in en, hi (Devanagari) and hi-Latn (Hinglish).

Confirmations, errors and clarifications always come from here; the LLM only
writes free-form answers."""
import re

from app.utils.text import is_devanagari

LANGS = ("en", "hi", "hi-Latn")

_HINGLISH_MARKERS = {
    "hai", "hain", "ka", "ki", "ke", "ko", "kitna", "kitne", "kitni", "kya", "kal", "baje", "dila", "do",
    "karo", "kar", "baaki", "baki", "bakaya", "udhaar", "udhar", "yaad", "mein", "se", "ne", "diya", "diye",
    "dega", "denge", "dene", "aaj", "parso", "agle", "agla", "wala", "wale", "batao", "bata", "dikhao",
    "bhai", "ji", "nahi", "haan", "paisa", "paise", "rupaye", "hazaar", "lakh", "sau", "mila", "mile",
    "kaun", "kab", "konsa", "kaunsa", "abhi", "jama", "lena", "dena", "hisaab", "pehla", "doosra", "dusra",
}


def detect_language(text: str) -> str:
    if is_devanagari(text):
        return "hi"
    words = set(re.findall(r"[a-z]+", text.lower()))
    hits = len(words & _HINGLISH_MARKERS)
    if hits >= 2 or (hits == 1 and len(words) <= 3):
        return "hi-Latn"
    return "en"


def normalize_lang(lang: str | None) -> str:
    if not lang:
        return "en"
    lang = lang.strip()
    low = lang.lower()
    if low in ("hi-latn", "hinglish", "hi_latn"):
        return "hi-Latn"
    if low.startswith("hi"):
        return "hi"
    return "en"


T: dict[str, dict[str, str]] = {
    "clarify_customer": {
        "en": "I found more than one customer matching \"{query}\". Which one do you mean?\n{options}",
        "hi": "\"{query}\" नाम के एक से ज़्यादा ग्राहक मिले। आप किसकी बात कर रहे हैं?\n{options}",
        "hi-Latn": "\"{query}\" naam ke ek se zyada customer mile. Aap kiski baat kar rahe hain?\n{options}",
    },
    "clarify_invoice": {
        "en": "{customer} has more than one open invoice. Which one?\n{options}",
        "hi": "{customer} के एक से ज़्यादा खुले बिल हैं। कौन सा?\n{options}",
        "hi-Latn": "{customer} ke ek se zyada open invoice hain. Kaun sa?\n{options}",
    },
    "ask_customer": {
        "en": "Which customer is this for?",
        "hi": "यह किस ग्राहक के लिए है?",
        "hi-Latn": "Yeh kis customer ke liye hai?",
    },
    "ask_date": {
        "en": "When should I set it for? Please tell me the day and time.",
        "hi": "कब के लिए रखूँ? दिन और समय बताइए।",
        "hi-Latn": "Kab ke liye rakhun? Din aur time bataiye.",
    },
    "ask_amount": {
        "en": "What is the amount?",
        "hi": "रकम कितनी है?",
        "hi-Latn": "Amount kitna hai?",
    },
    "ask_invoice": {
        "en": "Which invoice number?",
        "hi": "कौन सा बिल नंबर?",
        "hi-Latn": "Kaun sa invoice number?",
    },
    "preview_create_customer": {
        "en": "I will create customer '{customer}'{phone}. Please confirm.",
        "hi": "मैं नया ग्राहक '{customer}'{phone} जोड़ूँगा। पुष्टि करें।",
        "hi-Latn": "Main naya customer '{customer}'{phone} add karunga. Confirm karein.",
    },
    "preview_schedule_reminder": {
        "en": "I will schedule a {channel} reminder for {customer} on {when}{invoice}. Please confirm.",
        "hi": "मैं {customer} के लिए {when} को {channel} रिमाइंडर सेट करूँगा{invoice}। कृपया पुष्टि करें।",
        "hi-Latn": "Main {customer} ke liye {when} ko {channel} reminder set karunga{invoice}. Confirm karein.",
    },
    "preview_record_payment_commitment": {
        "en": "I will record that {customer} promised to pay {amount} on {when}. Please confirm.",
        "hi": "मैं दर्ज करूँगा कि {customer} ने {when} को {amount} देने का वादा किया है। कृपया पुष्टि करें।",
        "hi-Latn": "Main record karunga ki {customer} ne {when} ko {amount} dene ka vaada kiya hai. Confirm karein.",
    },
    "preview_record_payment": {
        "en": "I will record a payment of {amount} from {customer} against invoice {invoice} on {when}. Please confirm.",
        "hi": "मैं {customer} से {amount} का भुगतान बिल {invoice} पर {when} को दर्ज करूँगा। कृपया पुष्टि करें।",
        "hi-Latn": "Main {customer} se {amount} ka payment invoice {invoice} par {when} ko record karunga. Confirm karein.",
    },
    "confirmed": {
        "en": "Done. {summary}",
        "hi": "हो गया। {summary}",
        "hi-Latn": "Ho gaya. {summary}",
    },
    "cancelled": {
        "en": "Okay, I cancelled that.",
        "hi": "ठीक है, मैंने इसे रद्द कर दिया।",
        "hi-Latn": "Theek hai, maine cancel kar diya.",
    },
    "expired": {
        "en": "That request expired. Please ask again.",
        "hi": "यह अनुरोध समाप्त हो गया। कृपया फिर से कहें।",
        "hi-Latn": "Yeh request expire ho gayi. Please dobara boliye.",
    },
    "not_found_customer": {
        "en": "I could not find a customer named \"{query}\".",
        "hi": "\"{query}\" नाम का कोई ग्राहक नहीं मिला।",
        "hi-Latn": "\"{query}\" naam ka koi customer nahi mila.",
    },
    "not_found_invoice": {
        "en": "I could not find invoice {query}.",
        "hi": "बिल {query} नहीं मिला।",
        "hi-Latn": "Invoice {query} nahi mila.",
    },
    "permission_denied": {
        "en": "Sorry, you are not allowed to do that here.",
        "hi": "माफ़ कीजिए, आपको यह करने की अनुमति नहीं है।",
        "hi-Latn": "Sorry, aapko yeh karne ki permission nahi hai.",
    },
    "provider_unavailable": {
        "en": "The assistant is temporarily unavailable. Please try again shortly.",
        "hi": "सहायक अभी उपलब्ध नहीं है। थोड़ी देर बाद कोशिश करें।",
        "hi-Latn": "Assistant abhi available nahi hai. Thodi der baad try karein.",
    },
    "unsupported": {
        "en": "Sorry, I can't help with that. I can check balances, overdue invoices, and set reminders.",
        "hi": "माफ़ कीजिए, मैं इसमें मदद नहीं कर सकता। मैं बकाया, ओवरड्यू बिल और रिमाइंडर में मदद कर सकता हूँ।",
        "hi-Latn": "Sorry, main isme madad nahi kar sakta. Main baaki, overdue invoice aur reminder mein madad kar sakta hoon.",
    },
    "smalltalk": {
        "en": "Hello! How can I help with your business today?",
        "hi": "नमस्ते! आज मैं आपके कारोबार में कैसे मदद करूँ?",
        "hi-Latn": "Namaste! Aaj main aapke business mein kaise madad karun?",
    },
    "date_in_past": {
        "en": "That time is already in the past. Please choose a future time.",
        "hi": "वह समय बीत चुका है। कृपया आगे का समय चुनें।",
        "hi-Latn": "Woh time nikal chuka hai. Please aage ka time chuniye.",
    },
    "invalid_input": {
        "en": "I could not understand that value: {detail}",
        "hi": "मैं यह मान समझ नहीं पाया: {detail}",
        "hi-Latn": "Main yeh value samajh nahi paya: {detail}",
    },
    "empty_input": {
        "en": "I didn't catch that. Could you say it again?",
        "hi": "मैं समझ नहीं पाया। कृपया फिर से कहें।",
        "hi-Latn": "Main samajh nahi paya. Please dobara boliye.",
    },
    "overdue_count": {
        "en": "{count} invoices are overdue, totalling {amount}.",
        "hi": "{count} बिल ओवरड्यू हैं, कुल {amount}।",
        "hi-Latn": "{count} invoice overdue hain, total {amount}.",
    },
    "overdue_none": {
        "en": "No invoices are overdue.",
        "hi": "कोई बिल ओवरड्यू नहीं है।",
        "hi-Latn": "Koi invoice overdue nahi hai.",
    },
    "balance": {
        "en": "{customer} owes {amount} across {count} open invoice(s).",
        "hi": "{customer} का {amount} बाकी है ({count} खुले बिल)।",
        "hi-Latn": "{customer} ka {amount} baaki hai ({count} open invoice).",
    },
    "no_open_invoices_for_payment": {
        "en": "{customer} has no open bills with pending balance to record a payment.",
        "hi": "{customer} का कोई बकाया बिल नहीं मिला जिसमें भुगतान दर्ज किया जा सके।",
        "hi-Latn": "{customer} ka koi open bill nahi mila jisme payment darj ki ja sake.",
    },
    "balance_zero": {
        "en": "{customer} has no outstanding balance.",
        "hi": "{customer} का कुछ भी बाकी नहीं है।",
        "hi-Latn": "{customer} ka kuch bhi baaki nahi hai.",
    },
    "invoice_details": {
        "en": "Invoice {number} for {customer}: total {total}, paid {paid}, balance {balance}, due {due_on} ({status}).",
        "hi": "बिल {number} ({customer}): कुल {total}, भुगतान {paid}, बाकी {balance}, देय तिथि {due_on} ({status})।",
        "hi-Latn": "Invoice {number} ({customer}): total {total}, paid {paid}, baaki {balance}, due {due_on} ({status}).",
    },
    "customers_found": {
        "en": "Found {count} customer(s): {names}",
        "hi": "{count} ग्राहक मिले: {names}",
        "hi-Latn": "{count} customer mile: {names}",
    },
    "reminders_list": {
        "en": "{customer} has {count} upcoming reminder(s){details}.",
        "hi": "{customer} के {count} आने वाले रिमाइंडर हैं{details}।",
        "hi-Latn": "{customer} ke {count} upcoming reminder hain{details}.",
    },
    "dashboard": {
        "en": "Outstanding {outstanding}; {overdue} overdue invoice(s); {reminders} upcoming reminder(s); collected this month {collected}.",
        "hi": "कुल बकाया {outstanding}; {overdue} ओवरड्यू बिल; {reminders} आने वाले रिमाइंडर; इस महीने वसूली {collected}।",
        "hi-Latn": "Total baaki {outstanding}; {overdue} overdue invoice; {reminders} upcoming reminder; is mahine collection {collected}.",
    },
    "dry_run": {
        "en": "(Test mode: nothing was saved.) {text}",
        "hi": "(टेस्ट मोड: कुछ भी सेव नहीं हुआ।) {text}",
        "hi-Latn": "(Test mode: kuch save nahi hua.) {text}",
    },
}


def t(key: str, lang: str | None, **kwargs: object) -> str:
    lang = normalize_lang(lang)
    template = T[key].get(lang) or T[key]["en"]
    return template.format(**kwargs)
