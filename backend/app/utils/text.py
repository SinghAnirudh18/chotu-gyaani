"""Name normalization with basic Devanagari -> Latin transliteration so
"रमेश", "Ramesh" and "Ramesh" spoken by STT all match the same customer."""
import re
import unicodedata

_CONSONANTS = {
    "क": "k", "ख": "kh", "ग": "g", "घ": "gh", "ङ": "n", "च": "ch", "छ": "chh", "ज": "j", "झ": "jh",
    "ञ": "n", "ट": "t", "ठ": "th", "ड": "d", "ढ": "dh", "ण": "n", "त": "t", "थ": "th", "द": "d",
    "ध": "dh", "न": "n", "प": "p", "फ": "ph", "ब": "b", "भ": "bh", "म": "m", "य": "y", "र": "r",
    "ल": "l", "व": "v", "श": "sh", "ष": "sh", "स": "s", "ह": "h", "क़": "q", "ख़": "kh", "ग़": "g",
    "ज़": "z", "ड़": "r", "ढ़": "rh", "फ़": "f", "य़": "y",
}
_VOWELS = {"अ": "a", "आ": "aa", "इ": "i", "ई": "ee", "उ": "u", "ऊ": "oo", "ऋ": "ri", "ए": "e",
           "ऐ": "ai", "ओ": "o", "औ": "au"}
_MATRAS = {"ा": "aa", "ि": "i", "ी": "ee", "ु": "u", "ू": "oo", "ृ": "ri", "े": "e", "ै": "ai",
           "ो": "o", "ौ": "au", "ॅ": "e", "ॉ": "o"}
_VIRAMA = "्"
_MARKS = {"ं": "n", "ँ": "n", "ः": "h", "़": ""}
_DIGITS = {chr(0x0966 + i): str(i) for i in range(10)}


def is_devanagari(text: str) -> bool:
    return any("ऀ" <= ch <= "ॿ" for ch in text)


def transliterate(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    out: list[str] = []
    chars = list(text)
    i = 0
    while i < len(chars):
        ch = chars[i]
        nxt = chars[i + 1] if i + 1 < len(chars) else ""
        if ch in _CONSONANTS:
            out.append(_CONSONANTS[ch])
            if nxt == "़":
                i += 1
                nxt = chars[i + 1] if i + 1 < len(chars) else ""
            if nxt in _MATRAS:
                out.append(_MATRAS[nxt])
                i += 1
            elif nxt == _VIRAMA:
                i += 1
            else:
                # inherent 'a'; dropped at word end (schwa deletion)
                end_of_word = not nxt or not ("ऀ" <= nxt <= "ॿ") or nxt in _MARKS
                if not end_of_word:
                    out.append("a")
        elif ch in _VOWELS:
            out.append(_VOWELS[ch])
        elif ch in _MATRAS:
            out.append(_MATRAS[ch])
        elif ch in _MARKS:
            out.append(_MARKS[ch])
        elif ch in _DIGITS:
            out.append(_DIGITS[ch])
        elif ch == _VIRAMA:
            pass
        else:
            out.append(ch)
        i += 1
    return "".join(out)


def normalize_name(name: str) -> str:
    s = transliterate(name).lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    s = s.replace("w", "v").replace("ph", "f").replace("z", "j")
    s = re.sub(r"aa+", "a", s)
    s = re.sub(r"(ee|ii)+", "i", s)
    s = re.sub(r"(oo|uu)+", "u", s)
    s = re.sub(r"(.)\1+", r"\1", s)  # collapse doubled letters: "guptaa"/"gupta"
    s = re.sub(r"\s+", " ", s).strip()
    return s
