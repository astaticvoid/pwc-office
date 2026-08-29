"""
corrections_lib.py — shared segment walking for office_text corrections.

Imported by validate_corrections.py and apply_corrections.py. They must agree
exactly: the whole safety property of the manifest is that validate sees the
same matches apply will act on, so "validated" means "will apply cleanly". Two
copies of this walk would be two chances to disagree.

An `office_text` correction comes in two shapes, chosen by the type of `old`:

  substring  — `old` and `new` are strings. Every occurrence of `old` in every
               text-bearing segment of the field is replaced. `count` states how
               many occurrences are expected and defaults to 1; a mismatch is an
               error rather than a silent partial apply. This is the shape
               almost everything wants: the errata fix a word or a mark inside a
               canticle, and the whole-field form would mean restating the
               canticle to change "hid" to "hidden".

  whole      — `old` and `new` are anything else (list/dict). The field must
               equal `old` and is replaced by `new`. For structural edits that
               are not expressible as a text substitution — deleting segments,
               reordering, changing a segment's type.
"""


def iter_text_segments(node):
    """Yield each segment dict in an office field that carries a `text` string.

    Descends `alternatives` into its groups. Deliberately does NOT follow
    `{"type": "shared"}` references: a shared block is reachable from many
    forms, so correcting one through a form would silently rewrite the others.
    Corrections to shared text address the `_shared` office directly.
    """
    if isinstance(node, list):
        for item in node:
            yield from iter_text_segments(item)
        return
    if not isinstance(node, dict):
        return
    if node.get("type") == "shared":
        return
    if node.get("type") == "alternatives":
        for group in node.get("groups", []):
            yield from iter_text_segments(group.get("segments", []))
        return
    if isinstance(node.get("text"), str):
        yield node
        return
    # A named-field block — the `_penitential` confession/absolution dicts,
    # with string fields beside a plain list-of-lists `alternatives` — is not
    # itself a segment, so its segments are reached by walking its values.
    # String leaves inside a block stay unreachable: a plain-string FIELD
    # takes the narrow route in count_occurrences and the applier, and no
    # dict block carries a corrected string today.
    for value in node.values():
        yield from iter_text_segments(value)


def is_shared_reference(field) -> bool:
    """True if the field is nothing but a pointer into `_shared`."""
    return isinstance(field, dict) and field.get("type") == "shared"


def count_occurrences(field, old: str) -> int:
    """Total occurrences of `old` in `field`.

    A field is either a plain string — every office `title` is one — or a
    structure of segments. Both are correctable by substring; the string case
    is not reachable through `iter_text_segments`, which walks segments only.
    """
    if isinstance(field, str):
        return field.count(old)
    return sum(seg["text"].count(old) for seg in iter_text_segments(field))


def replace_occurrences(field, old: str, new: str) -> int:
    """Replace every occurrence of `old` with `new` in place. Returns the count."""
    replaced = 0
    for seg in iter_text_segments(field):
        found = seg["text"].count(old)
        if found:
            seg["text"] = seg["text"].replace(old, new)
            replaced += found
    return replaced


ALL_OFFICES = "*"


def resolve_offices(data: dict, correction: dict) -> list[tuple[str, dict]]:
    """The (key, office) pairs a correction addresses, in file order.

    `office: "*"` addresses every office carrying the field. It exists for the
    text the book prints identically in all 30 forms — the Psalm and Reading
    introductions, the section hand-offs — where the alternative is 30 manifest
    entries differing only in a key, which is a worse record, not a stricter
    one: nobody reads 30 copies to check they still agree.

    `count` stays a corpus-wide total rather than becoming per-office (see
    check_office_text_across), so the entry says in one line how far the text
    reaches and fails when the corpus stops matching it.

    That is a slightly weaker guarantee than the N entries it replaces, and the
    gap is worth knowing: a *redistribution* leaving the total unchanged — one
    form losing an occurrence while another gains one — fails two of 28
    per-office entries but passes a single wildcard entry, which then applies to
    a spread nobody authorized. Both catch text changing; only per-office
    entries catch it moving between forms. For the rubrics this exists for, the
    same sentence printed in all 30 forms, the distribution is uniform and a
    redistribution would be a defect the conservation check (#94) is the right
    thing to catch. Use a named office where the spread itself is the point.

    Offices without the field are skipped rather than reported: a wildcard is a
    statement about the text, not about which forms happen to have the section.
    An entry matching nothing anywhere still fails on the count.
    """
    key = correction["office"]
    if key != ALL_OFFICES:
        office = data.get(key)
        return [(key, office)] if office is not None else []
    return [(k, o) for k, o in data.items()
            if not k.startswith("_") and isinstance(o, dict)
            and correction["field"] in o]


def check_office_text(correction: dict, field) -> str | None:
    """Return an error string if `correction` does not apply cleanly to `field`.

    Shared by the validator (which stops here) and the applier (which calls
    this first, then mutates), so a correction can never apply on a state the
    validator would have rejected.

    One caveat, deliberately not papered over: the validator checks every
    correction against the pristine artifact independently, while the applier
    mutates as it goes. Two corrections on the same office+field are therefore
    checked against different states, and the second can fail at apply time
    having passed validation — if the first one's `new` text creates or destroys
    a match for the second's `old`. Validation is a guarantee per correction,
    not across a set of them touching one field.
    """
    return check_office_text_across(correction, [field])


def check_office_text_across(correction: dict, fields: list) -> str | None:
    """check_office_text over every field the correction resolves to.

    The entry point for the validator and the applier, so both judge a wildcard
    the same way. `count` is the total across the whole set, not per office:
    one entry reading "28 occurrences" is checked as a single statement about
    the book, and moves the moment the corpus does.
    """
    if not fields:
        return "matches no office"

    old = correction.get("old")
    if not isinstance(old, str):
        # Keyed on the wildcard, not on how many offices it happens to resolve
        # to today: a wildcard whole-field entry that matches one form now would
        # pass, then start failing the moment a second form grows the field.
        if correction.get("office") == ALL_OFFICES or len(fields) > 1:
            return ("whole-field replacement addresses one office only — across "
                    "a set it would write the same structure over each")
        return None if fields[0] == old else "field does not equal 'old'"

    for field in fields:
        if is_shared_reference(field):
            key = field.get("key")
            return (
                f"field is only a reference to the shared block '{key}' — correct "
                f"_shared.{key} instead, which corrects every form that uses it"
            )

    expected = correction.get("count", 1)
    actual = sum(count_occurrences(f, old) for f in fields)
    if actual == expected:
        return None
    if actual == 0 and sum(count_occurrences(f, old.replace(" ", "\xa0")) for f in fields):
        return (
            "'old' not found, but matches with a non-breaking space — "
            "use the literal \\u00a0 character in 'old'"
        )
    return f"expected {expected} occurrence(s) of 'old', found {actual}"
