"""Devanagari -> Roman Hinglish, the way Indian creators type it ("itna aasan nahi tha").

Deterministic and word-for-word, so caption timing stays exact and no words are added or
changed by a model. Latin words in mixed Hinglish transcripts pass through untouched.

Rules (in order):
  1. common-word dictionary (function words have fixed popular spellings: में->mein, है->hai)
  2. akshara parsing: consonant (+nukta) + matra / virama / inherent 'a'
  3. schwa deletion: drop word-final inherent 'a'; drop medial 'a' in V C(a) C V (right to left)
  4. Hinglish vowel style: long aa/ee/oo medially, short a/i/u at word end (करना -> karna, ही -> hi)
"""
from __future__ import annotations

import re

_DEV = re.compile(r"[ऀ-ॿ]")
_WORD = re.compile(r"[ऀ-ॿ]+")

VOWELS = {"अ": "a", "आ": "aa", "इ": "i", "ई": "ee", "उ": "u", "ऊ": "oo", "ऋ": "ri", "ए": "e", "ऐ": "ai",
          "ओ": "o", "औ": "au", "ऑ": "o", "ऍ": "e"}
MATRAS = {"ा": "aa", "ि": "i", "ी": "ee", "ु": "u", "ू": "oo", "ृ": "ri", "े": "e", "ै": "ai",
          "ो": "o", "ौ": "au", "ॉ": "o", "ॅ": "e"}
CONS = {"क": "k", "ख": "kh", "ग": "g", "घ": "gh", "ङ": "n", "च": "ch", "छ": "chh", "ज": "j", "झ": "jh",
        "ञ": "n", "ट": "t", "ठ": "th", "ड": "d", "ढ": "dh", "ण": "n", "त": "t", "थ": "th", "द": "d",
        "ध": "dh", "न": "n", "प": "p", "फ": "ph", "ब": "b", "भ": "bh", "म": "m", "य": "y", "र": "r",
        "ल": "l", "व": "v", "श": "sh", "ष": "sh", "स": "s", "ह": "h", "ळ": "l"}
NUKTA = {"क": "q", "ख": "kh", "ग": "g", "ज": "z", "ड": "d", "ढ": "rh", "फ": "f", "य": "y"}
PRECOMPOSED = {"क़": "क़", "ख़": "ख़", "ग़": "ग़", "ज़": "ज़", "ड़": "ड़", "ढ़": "ढ़", "फ़": "फ़", "य़": "य़"}
NASAL = {"ं", "ँ"}
VIRAMA, NUKTA_SIGN, VISARGA = "्", "़", "ः"
DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")

# Popular spellings that rules can't derive (Hinglish convention, not phonetics).
COMMON = {
    "है": "hai", "हैं": "hain", "में": "mein", "मैं": "main", "नहीं": "nahi", "नही": "nahi", "यह": "yeh",
    "वह": "woh", "ये": "ye", "वो": "wo", "क्यों": "kyun", "क्यूं": "kyun", "हूँ": "hoon", "हूं": "hoon",
    "हाँ": "haan", "हां": "haan", "तो": "to", "कि": "ki", "की": "ki", "के": "ke", "का": "ka", "को": "ko",
    "से": "se", "ने": "ne", "पर": "par", "भी": "bhi", "ही": "hi", "एक": "ek", "और": "aur", "लिए": "liye",
    "लिये": "liye", "कर": "kar", "क्या": "kya", "कैसे": "kaise", "कोई": "koi", "कुछ": "kuch", "सब": "sab",
    "बहुत": "bahut", "अब": "ab", "फिर": "phir", "जब": "jab", "तब": "tab", "था": "tha", "थे": "the",
    "थी": "thi", "आप": "aap", "हम": "hum", "तुम": "tum", "मुझे": "mujhe", "मेरा": "mera", "मेरी": "meri",
    "मेरे": "mere", "अपना": "apna", "अपने": "apne", "अपनी": "apni", "इसका": "iska", "इसके": "iske",
    "इसकी": "iski", "इसको": "isko", "इसे": "ise", "उसका": "uska", "उसके": "uske", "उसे": "use",
    "इस": "is", "उस": "us", "जो": "jo", "जहां": "jahan", "जहाँ": "jahan", "वहां": "wahan", "यहां": "yahan",
    "यहाँ": "yahan", "लेकिन": "lekin", "सिर्फ": "sirf", "ज़रूर": "zaroor", "जरूर": "zaroor", "दोनों": "dono",
    "वीडियो": "video", "ऐसा": "aisa", "ऐसे": "aise", "वाला": "wala", "वाले": "wale", "वाली": "wali",
    "रहा": "raha", "रहे": "rahe", "रही": "rahi", "गया": "gaya", "गए": "gaye", "दिया": "diya", "लिया": "liya",
    "हुआ": "hua", "हुए": "hue", "होगा": "hoga", "होता": "hota", "होती": "hoti", "होते": "hote", "हो": "ho",
    "दिन": "din", "साथ": "saath", "बाद": "baad", "पहले": "pehle", "सबसे": "sabse", "आज": "aaj", "कल": "kal",
    "मैंने": "maine", "क्योंकि": "kyunki", "इसमें": "isme", "उसमें": "usme", "चाहिए": "chahiye",
    "चाहिये": "chahiye", "उन्हें": "unhe", "इन्हें": "inhe", "हमें": "hume", "तुम्हें": "tumhe", "आपको": "aapko",
    "आपके": "aapke", "आपकी": "aapki", "आपका": "aapka", "बोले": "bole", "बोलो": "bolo", "देखो": "dekho",
    "करो": "karo", "करें": "karein", "रहें": "rahein", "जाएगा": "jayega", "आएगा": "aayega", "आएगी": "aayegi",
    "सकते": "sakte", "सकता": "sakta", "सकती": "sakti", "चलो": "chalo", "यार": "yaar", "भाई": "bhai",
}

# English words that Whisper sometimes writes in Devanagari; Hinglish writers keep the English spelling.
LOANWORDS = {
    "ट्राई": "try", "ट्राइ": "try", "आइडिया": "idea", "एक्सपोर्ट": "export", "इम्पोर्ट": "import",
    "कमेंट": "comment", "कमेंट्स": "comments", "डिसाइड": "decide", "डेली": "daily", "लाइफ": "life",
    "प्रोब्लम": "problem", "प्रॉब्लम": "problem", "प्रोब्लेम": "problem", "लिंक": "link", "फॉलो": "follow",
    "लाइक": "like", "शेयर": "share", "सब्सक्राइब": "subscribe", "चैनल": "channel", "रील": "reel",
    "रील्स": "reels", "कंटेंट": "content", "क्रिएटर": "creator", "क्रिएटर्स": "creators", "टूल": "tool",
    "टूल्स": "tools", "ऐप": "app", "एप": "app", "वेबसाइट": "website", "फ्री": "free", "एआई": "AI",
    "वॉटरमार्क": "watermark", "वाटरमार्क": "watermark", "बेस्ट": "best", "पार्ट": "part", "फोन": "phone",
    "मोबाइल": "mobile", "कैमरा": "camera", "एडिट": "edit", "एडिटिंग": "editing", "एडिटर": "editor",
    "कैप्शन": "caption", "कैप्शंस": "captions", "सबटाइटल": "subtitle", "फॉन्ट": "font", "स्टाइल": "style",
    "कलर": "color", "एनिमेशन": "animation", "टेम्पलेट": "template", "डाउनलोड": "download",
    "अपलोड": "upload", "इंस्टाग्राम": "Instagram", "यूट्यूब": "YouTube", "गूगल": "Google",
    "प्रोजेक्ट": "project", "कोडिंग": "coding", "टेस्टिंग": "testing", "मॉडल": "model", "मॉडल्स": "models",
    "सोर्स": "source", "ओपन": "open", "लैपटॉप": "laptop", "कंप्यूटर": "computer", "सॉफ्टवेयर": "software",
    "एनॉइंग": "annoying", "एक्चुअली": "actually", "बेसिकली": "basically", "ओके": "okay", "सो": "so",
    "रेडी": "ready", "स्टार्ट": "start", "फिनिश": "finish", "टाइम": "time", "मनी": "money", "बिज़नेस": "business",
    "बिजनेस": "business", "मार्केटिंग": "marketing", "ब्रांड": "brand", "प्रोडक्ट": "product", "यूज़": "use",
    "यूज": "use", "सीक्रेट": "secret", "टिप": "tip", "टिप्स": "tips", "हैक": "hack", "ट्रिक": "trick",
}


def _aksharas(word: str) -> list[list[str]]:
    """Parse into [consonant_or_vowel_roman, vowel_roman | '' (virama) | None (inherent a), nasal]."""
    for k, v in PRECOMPOSED.items():
        word = word.replace(k, v)
    out: list[list] = []
    i = 0
    while i < len(word):
        ch = word[i]
        nxt = word[i + 1] if i + 1 < len(word) else ""
        if ch in CONS:
            roman = CONS[ch]
            if nxt == NUKTA_SIGN:
                roman = NUKTA.get(ch, roman)
                i += 1
                nxt = word[i + 1] if i + 1 < len(word) else ""
            vowel = None
            if nxt in MATRAS:
                vowel = MATRAS[nxt]
                i += 1
            elif nxt == VIRAMA:
                vowel = ""
                i += 1
            out.append([roman, vowel, False])
        elif ch in VOWELS:
            out.append(["", VOWELS[ch], False])
        elif ch in NASAL and out:
            out[-1][2] = True
        elif ch == VISARGA and out:
            out[-1][0] += "h" if out[-1][1] == "" else ""
        elif ch.isdigit():
            out.append([ch.translate(DIGITS), "", False])
        i += 1
    return out


def _delete_schwas(ak: list[list]) -> None:
    """None (inherent 'a') -> 'a' or '' following Hindi schwa deletion."""
    n = len(ak)
    has_vowel = lambda j: ak[j][1] not in ("",)  # None counts as vowel until deleted

    if n > 1 and ak[-1][1] is None and ak[-1][0]:
        ak[-1][1] = ""                     # word-final: कर -> kar
    for j in range(n - 2, 0, -1):          # medial, right to left: करना -> karna
        if ak[j][1] is None and ak[j][0] and has_vowel(j - 1) and ak[j + 1][0] and ak[j + 1][1] not in ("",):
            ak[j][1] = ""
    for a in ak:
        if a[1] is None:
            a[1] = "a"


def romanize_word(word: str) -> str:
    if word in COMMON:
        return COMMON[word]
    if word in LOANWORDS:
        return LOANWORDS[word]
    ak = _aksharas(word)
    if not ak:
        return word
    _delete_schwas(ak)
    parts = []
    for j, (c, v, nasal) in enumerate(ak):
        # Hinglish spells long vowels out only in the first syllable: aasan, banana, karna, neeche, sabhi
        # ...and always short at the end of a word (ली -> li, सी -> si), except a bare vowel (आ -> aa)
        if j > 0 or (j == len(ak) - 1 and c):
            v = {"aa": "a", "ee": "i", "oo": "u"}.get(v, v)
        parts.append(c + v + ("n" if nasal else ""))
    return "".join(parts)


def romanize(text: str) -> str:
    """Romanize every Devanagari run inside `text`; everything else is left as it is."""
    if not _DEV.search(text):
        return text
    text = text.replace("।", ".").translate(DIGITS)
    return _WORD.sub(lambda m: romanize_word(m.group(0)), text)


def has_devanagari(text: str) -> bool:
    return bool(_DEV.search(text))
