from app.services.translit import has_devanagari, romanize, romanize_word


def test_matches_creator_captions_from_real_reel():
    # Lines whose Hinglish spelling we can see burned into the creator's own reel
    assert romanize("लेकिन इसे बनाना इतना आसान नहीं था") == "lekin ise banana itna aasan nahi tha"
    assert romanize("सुरज के साथ") == "suraj ke saath"
    assert romanize("सब कुछ एक ही") == "sab kuch ek hi"


def test_schwa_deletion():
    assert romanize_word("करना") == "karna"      # medial
    assert romanize_word("समझना") == "samajhna"  # medial, right-to-left
    assert romanize_word("कमल") == "kamal"       # final only
    assert romanize_word("मदद") == "madad"


def test_vowel_length_style():
    assert romanize_word("नीचे") == "neeche"     # first syllable keeps long vowel
    assert romanize_word("ली") == "li"           # word-final short
    assert romanize_word("दुनिया") == "duniya"
    assert romanize_word("आ") == "aa"


def test_nukta_nasal_conjunct_digits():
    assert romanize_word("ज़िंदगी") == "zindgi"
    assert romanize_word("हिंदी") == "hindi"
    assert romanize("१४ भाषाएं") .startswith("14 ")


def test_common_words_and_loanwords():
    assert romanize("मैंने वीडियो में कमेंट किया") == "maine video mein comment kiya"
    assert romanize("ट्राइ करने के लिए") == "try karne ke liye"


def test_latin_and_punctuation_untouched():
    assert romanize("free speech to text, यार!") == "free speech to text, yaar!"
    assert romanize("English only.") == "English only."
    assert romanize("हो गया।") == "ho gaya."
    assert has_devanagari("abc हो") and not has_devanagari("abc")
