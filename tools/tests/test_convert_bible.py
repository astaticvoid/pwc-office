"""Tests for tools/convert_bible.py book normalization and versification.

Ensures that:
- Sirach's Prologue is separated from Chapter 1.
- Sirach Chapter 1 begins at verse 1 ("All wisdom is from the Lord...").
- Subsequent verses in Sirach are indexed by their true superscript numbers.
- James 1:7-8 combined verses are properly mapped.
"""

import importlib.util
import pathlib

TOOLS = pathlib.Path(__file__).resolve().parent.parent

_SPEC = importlib.util.spec_from_file_location(
    "convert_bible", TOOLS / "convert_bible.py"
)
cb = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(cb)


def test_sirach_prologue_separation():
    # Synthetic raw Sirach chapter 1 with prologue conflated
    raw_ch1 = {
        "1": "¹ Many great teachings have been given to us\n",
        "2": "² and the others that followed them,\n",
        "34": "³⁶ to live according to the law.\n\nAll wisdom is from the Lord,\n    and with him it remains forever.\n",
        "35": "² The sand of the sea,\n",
        "36": "³ The height of heaven,\n",
        "37": "⁴ Wisdom was created before all things\n",
        "38": "⁶ The root of wisdom—to whom has it been revealed?\n",
    }
    raw_ch3 = {
        "18": "¹⁸ The greater you are\n",
        "19": "²⁰ For great is the might\n",
        "30": "³¹ Those who repay favors\n",
    }
    raw_sirach = {"1": raw_ch1, "3": raw_ch3}

    normalized = cb.normalize_book("Sirach", raw_sirach)

    assert "Prologue" in normalized
    assert "1" in normalized
    assert normalized["Prologue"]["1"] == "Many great teachings have been given to us"
    assert normalized["Prologue"]["34"] == "to live according to the law."

    # Chapter 1 starts with verse 1
    assert normalized["1"]["1"] == "All wisdom is from the Lord,\n    and with him it remains forever."
    assert normalized["1"]["2"] == "The sand of the sea,"
    assert normalized["1"]["3"] == "The height of heaven,"
    assert normalized["1"]["4"] == "Wisdom was created before all things"
    assert "5" not in normalized["1"]
    assert normalized["1"]["6"] == "The root of wisdom—to whom has it been revealed?"

    # Chapter 3 handles omitted verse 19 by re-keying to true superscript
    assert normalized["3"]["18"] == "The greater you are"
    assert "19" not in normalized["3"]
    assert normalized["3"]["20"] == "For great is the might"
    assert normalized["3"]["31"] == "Those who repay favors"


def test_james_combined_verses():
    # Case A: raw input where 7 has combined 7,8 and next verse is 9 keyed as 8
    raw_james_1 = {
        "6": "⁶ But ask in faith\n",
        "7": "⁷,⁸ For the doubter\n",
        "8": "⁹ Let the brother\n",
        "26": "²⁷ Religion that is pure\n",
    }
    raw_james = {"1": raw_james_1}

    normalized = cb.normalize_book("James", raw_james)

    assert normalized["1"]["7"] == "For the doubter"
    assert normalized["1"]["8"] == "For the doubter"
    assert normalized["1"]["9"] == "Let the brother"
    assert normalized["1"]["27"] == "Religion that is pure"

    # Case B: input where both 7 and 8 have combined 7,8 (idempotent / pre-updated)
    raw_james_1_dup = {
        "6": "⁶ But ask in faith\n",
        "7": "⁷,⁸ For the doubter\n",
        "8": "⁷,⁸ For the doubter\n",
        "9": "⁹ Let the brother\n",
    }
    normalized_dup = cb.normalize_book("James", {"1": raw_james_1_dup})
    assert normalized_dup["1"]["7"] == "For the doubter"
    assert normalized_dup["1"]["8"] == "For the doubter"
    assert normalized_dup["1"]["9"] == "Let the brother"


def test_sirach_already_separated():
    raw_sirach = {
        "Prologue": {
            "1": "¹ Many great teachings\n",
            "21": "²¹–²² For what was originally expressed in Hebrew\n",
        },
        "1": {
            "1": "¹ All wisdom is from the Lord\n",
            "2": "² The sand of the sea\n",
        },
    }
    normalized = cb.normalize_book("Sirach", raw_sirach)
    assert normalized["Prologue"]["1"] == "Many great teachings"
    assert normalized["Prologue"]["21"] == "For what was originally expressed in Hebrew"
    assert normalized["1"]["1"] == "All wisdom is from the Lord"
    assert normalized["1"]["2"] == "The sand of the sea"


def test_strip_verse_num_ranges():
    assert cb.strip_verse_num("¹ Single verse") == "Single verse"
    assert cb.strip_verse_num("⁷,⁸ Comma separated") == "Comma separated"
    assert cb.strip_verse_num("²¹–²² En-dash range") == "En-dash range"
    assert cb.strip_verse_num("³¹-³² Hyphen range") == "Hyphen range"
    assert cb.strip_verse_num("No superscript") == "No superscript"

