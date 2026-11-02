"""Parse amounts spoken in English, Hindi or Hinglish into integer paise.

The LLM may extract the phrase ("do lakh", "dedh sau", "1.5 lakh"); this code
computes the value."""
import re
from decimal import Decimal, InvalidOperation

UNITS: dict[str, Decimal] = {}


def _add(words: str, value: float | int) -> None:
    for w in words.split():
        UNITS[w] = Decimal(str(value))


_add("zero shunya", 0)
_add("one ek एक", 1)
_add("two do दो", 2)
_add("three teen tin तीन", 3)
_add("four char chaar चार", 4)
_add("five paanch panch paach पांच पाँच", 5)
_add("six chhe chhah che chah छह छः", 6)
_add("seven saat सात", 7)
_add("eight aath ath आठ", 8)
_add("nine nau नौ", 9)
_add("ten das दस", 10)
_add("eleven gyarah gyara ग्यारह", 11)
_add("twelve barah bara बारह", 12)
_add("thirteen terah तेरह", 13)
_add("fourteen chaudah चौदह", 14)
_add("fifteen pandrah pandra पंद्रह", 15)
_add("sixteen solah सोलह", 16)
_add("seventeen satrah सत्रह", 17)
_add("eighteen atharah athara अठारह", 18)
_add("nineteen unnis उन्नीस", 19)
_add("twenty bees bis बीस", 20)
_add("twentyfive pachees pachchis pachis पच्चीस", 25)
_add("thirty tees tis तीस", 30)
_add("forty chalees chalis चालीस", 40)
_add("fifty pachaas pachas पचास", 50)
_add("sixty saath साठ", 60)
_add("seventy sattar सत्तर", 70)
_add("eighty assi अस्सी", 80)
_add("ninety nabbe नब्बे", 90)

FRACTIONS = {"dedh": Decimal("1.5"), "derh": Decimal("1.5"), "डेढ़": Decimal("1.5"), "डेढ": Decimal("1.5"),
             "dhai": Decimal("2.5"), "dhaai": Decimal("2.5"), "ढाई": Decimal("2.5"),
             "half": Decimal("0.5"), "aadha": Decimal("0.5"), "adha": Decimal("0.5")}
PREFIX_MODS = {"saade": Decimal("0.5"), "sadhe": Decimal("0.5"), "saadhe": Decimal("0.5"),
               "साढ़े": Decimal("0.5"), "paune": Decimal("-0.25"), "पौने": Decimal("-0.25"),
               "sava": Decimal("0.25"), "sawa": Decimal("0.25"), "सवा": Decimal("0.25")}
MULTIPLIERS = {"hundred": 100, "sau": 100, "so": 100, "सौ": 100,
               "thousand": 1000, "hazaar": 1000, "hazar": 1000, "hajar": 1000, "hajaar": 1000,
               "हज़ार": 1000, "हजार": 1000, "k": 1000,
               "lakh": 100000, "lakhs": 100000, "lac": 100000, "lacs": 100000, "लाख": 100000,
               "million": 1000000,
               "crore": 10000000, "crores": 10000000, "karod": 10000000, "करोड़": 10000000, "cr": 10000000}
CURRENCY = {"rs", "rs.", "inr", "₹", "rupees", "rupee", "rupaye", "rupaiye", "rupay", "rupiya", "रुपये",
            "रुपए", "रुपया", "paise"}
FILLER = {"and", "aur", "only"}
TIME_WORDS = {"baje", "bje", "bajkar", "am", "pm", "o'clock", "oclock", "बजे", "tarikh", "tareekh", "तारीख",
              "din", "days", "day", "hafte", "week", "weeks", "mahine", "month", "months", "minute",
              "minutes", "ghante", "hours", "hour"}

_NUM_RE = re.compile(r"^\d+(?:\.\d+)?$")


def _tokens(text: str) -> list[str]:
    text = text.lower().replace("₹", " ₹ ")
    text = re.sub(r"(?<=\d),(?=\d)", "", text)          # 1,50,000 -> 150000
    text = re.sub(r"(\d+(?:\.\d+)?)\s*k\b", r"\1 k", text)  # 5k -> 5 k
    return [t.strip(".,!?;:'\"()") for t in text.split() if t.strip(".,!?;:'\"()")]


def _is_number_token(t: str) -> bool:
    return bool(_NUM_RE.match(t)) or t in UNITS or t in FRACTIONS or t in PREFIX_MODS or t in MULTIPLIERS


def parse_amount_to_paise(phrase: str | int | float | None) -> int | None:
    if phrase is None:
        return None
    if isinstance(phrase, int | float):
        return int(round(Decimal(str(phrase)) * 100)) if phrase > 0 else None
    total = Decimal(0)
    current = Decimal(0)
    pending_mod: Decimal | None = None
    seen = False
    for t in _tokens(phrase):
        if t in CURRENCY or t in FILLER:
            continue
        value: Decimal | None = None
        if _NUM_RE.match(t):
            try:
                value = Decimal(t)
            except InvalidOperation:
                return None
        elif t in UNITS:
            value = UNITS[t]
        elif t in FRACTIONS:
            value = FRACTIONS[t]
        elif t in PREFIX_MODS:
            pending_mod = PREFIX_MODS[t]
            continue
        elif t in MULTIPLIERS:
            mult = Decimal(MULTIPLIERS[t])
            if current == 0:
                current = Decimal(1) + (pending_mod or 0)
                pending_mod = None
            if mult == 100:
                current *= mult
            else:
                total += current * mult
                current = Decimal(0)
            seen = True
            continue
        else:
            continue
        if pending_mod is not None:
            value = value + pending_mod
            pending_mod = None
        current += value
        seen = True
    if not seen:
        return None
    amount = total + current
    if amount <= 0:
        return None
    return int((amount * 100).quantize(Decimal(1)))


def find_amount_phrase(text: str) -> str | None:
    """Find the most likely amount phrase in free text (used by the mock LLM)."""
    toks = _tokens(text)
    best: list[str] = []
    i = 0
    while i < len(toks):
        if _is_number_token(toks[i]) or toks[i] in CURRENCY:
            j = i
            run: list[str] = []
            while j < len(toks) and (_is_number_token(toks[j]) or toks[j] in CURRENCY or toks[j] in FILLER):
                run.append(toks[j])
                j += 1
            nxt = toks[j] if j < len(toks) else ""
            while run and run[-1] in FILLER:
                run.pop()
            has_strong = any(_NUM_RE.match(t) or t in MULTIPLIERS or t in FRACTIONS for t in run)
            has_currency = any(t in CURRENCY for t in run)
            is_time = nxt in TIME_WORDS or (i > 0 and toks[i - 1] in {"at", "by"} and not has_currency)
            if not is_time and (has_currency or any(t in MULTIPLIERS for t in run)
                                or (has_strong and any(_NUM_RE.match(t) for t in run))):
                if len(run) > len(best):
                    best = run
            i = j + 1
        else:
            i += 1
    phrase = " ".join(t for t in best if t not in CURRENCY)
    return phrase or None
