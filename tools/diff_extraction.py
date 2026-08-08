#!/usr/bin/env python3
"""
diff_extraction.py — semantic before/after diff for extraction output.

Answers "what did my change to the extractor actually do?" — the question every
extractor change has to answer before it can be trusted.

Usage:
    diff_extraction.py BEFORE.json AFTER.json [--expect N] [--quiet]

    --expect N   assert exactly N text nodes changed; exit 1 otherwise.
                 The normal target for a refactor is --expect 0.
    --quiet      summary only, no per-node listing.

Exit status is 0 when the diff matches expectations (no differences, or exactly
--expect of them) and 1 otherwise, so it can gate a commit.

Why not a plain JSON diff: identity has to survive movement. A segment's position
is not stable — inserting one renumbers every sibling after it, and hoisting a
block into `_shared` relocates it wholesale. Keying on JSON paths reports both as
mass change; one such comparison once reported 649 differences for a change that
altered nothing. So text is compared as a set keyed by (form, section, type),
and position is reported separately, where it is informative rather than noisy.
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

# Keys holding a section's segment list are everything except these.
_NON_SECTION_KEYS = {"title", "subtitle"}


def _walk_segments(node, out, section):
    """Collect (type, text) for every segment beneath `node`."""
    if isinstance(node, dict):
        text = node.get("text")
        if isinstance(text, str):
            out.append((node.get("type", "?"), text))
        for key, value in node.items():
            if key != "text" and isinstance(value, (dict, list)):
                _walk_segments(value, out, section)
    elif isinstance(node, list):
        for item in node:
            _walk_segments(item, out, section)


def sections_of(doc):
    """{(form, section): [(type, text), ...]} for an offices-shaped document.

    Falls back to treating the whole document as one pseudo-section, so the tool
    still works on psalter.json, collects.json and the lectionary months.
    """
    result = {}
    looks_like_offices = any(
        isinstance(v, dict) and any(isinstance(x, list) for x in v.values())
        for k, v in doc.items()
    ) if isinstance(doc, dict) else False

    if not looks_like_offices:
        segs = []
        _walk_segments(doc, segs, "")
        return {("<document>", "<all>"): segs}

    for form, body in doc.items():
        if not isinstance(body, dict):
            continue
        for section, value in body.items():
            if section in _NON_SECTION_KEYS or not isinstance(value, (list, dict)):
                continue
            segs = []
            _walk_segments(value, segs, section)
            result[(form, section)] = segs
    return result


def diff(before, after):
    """Structural and textual differences between two extraction artifacts."""
    sb, sa = sections_of(before), sections_of(after)

    report = {
        "forms_removed": sorted({f for f, _ in sb} - {f for f, _ in sa}),
        "forms_added": sorted({f for f, _ in sa} - {f for f, _ in sb}),
        "sections_removed": sorted(set(sb) - set(sa)),
        "sections_added": sorted(set(sa) - set(sb)),
        "count_changes": [],
        "modified": [],
        "text_removed": [],
        "text_added": [],
        "moved": [],
    }

    if isinstance(before, dict) and isinstance(after, dict):
        shb = sorted(before.get("_shared", {}) or {})
        sha = sorted(after.get("_shared", {}) or {})
        report["shared_removed"] = [k for k in shb if k not in sha]
        report["shared_added"] = [k for k in sha if k not in shb]
    else:
        report["shared_removed"] = report["shared_added"] = []

    for key in sorted(set(sb) & set(sa)):
        segs_b, segs_a = sb[key], sa[key]
        if len(segs_b) != len(segs_a):
            report["count_changes"].append((key, len(segs_b), len(segs_a)))

        # Text as a multiset: a node reports once, wherever it moved to.
        cb, ca = Counter(segs_b), Counter(segs_a)
        gone, came = [], []
        for item, n in (cb - ca).items():
            gone.extend([item] * n)
        for item, n in (ca - cb).items():
            came.extend([item] * n)
        # An edited segment shows up as both a removal and an addition. Pair them
        # so one edit counts once — reporting it as two is how a 14-node change
        # gets described as 28.
        gone.sort()
        came.sort()
        for old, new in zip(gone, came):
            report["modified"].append((key, old, new))
        for old in gone[len(came):]:
            report["text_removed"].append((key, *old))
        for new in came[len(gone):]:
            report["text_added"].append((key, *new))

        # Same contents, different order — invisible to the multiset view.
        if cb == ca and segs_b != segs_a:
            report["moved"].append(key)

    return report


def render(report, quiet=False):
    changed = (len(report["modified"]) + len(report["text_added"])
               + len(report["text_removed"]))
    structural = (report["forms_added"] or report["forms_removed"]
                  or report["sections_added"] or report["sections_removed"]
                  or report["shared_added"] or report["shared_removed"]
                  or report["count_changes"] or report["moved"])

    if not changed and not structural:
        print("No differences.")
        return changed

    for label, items in (("forms removed", report["forms_removed"]),
                         ("forms added", report["forms_added"]),
                         ("_shared removed", report["shared_removed"]),
                         ("_shared added", report["shared_added"])):
        if items:
            print(f"{label}: {', '.join(items)}")
    for label, items in (("sections removed", report["sections_removed"]),
                         ("sections added", report["sections_added"])):
        if items:
            print(f"{label}: " + ", ".join(f"{f}.{s}" for f, s in items))
    for (form, section), nb, na in report["count_changes"]:
        print(f"segment count  {form}.{section}: {nb} -> {na}")
    for form, section in report["moved"]:
        print(f"reordered      {form}.{section} (same segments, different order)")

    by_section = Counter(
        [f"{f}.{s}" for (f, s), _, _ in report["modified"]]
        + [f"{f}.{s}" for (f, s), _, _ in report["text_added"] + report["text_removed"]])
    parts = []
    for label, n in (("modified", len(report["modified"])),
                     ("added", len(report["text_added"])),
                     ("removed", len(report["text_removed"]))):
        if n:
            parts.append(f"{n} {label}")
    print(f"\n{changed} text node(s) changed ({', '.join(parts)})"
          + (f" across {len(by_section)} section(s)" if by_section else ""))
    for section, n in by_section.most_common():
        print(f"   {section}: {n}")

    if not quiet:
        for (form, section), (typ_o, old), (typ_n, new) in report["modified"]:
            print(f"\n~ [{form}.{section} {typ_o}]")
            print(f"    - {old[:150]!r}")
            print(f"    + {new[:150]!r}")
        for (form, section), typ, text in report["text_removed"]:
            print(f"\n- [{form}.{section} {typ}] {text[:160]!r}")
        for (form, section), typ, text in report["text_added"]:
            print(f"\n+ [{form}.{section} {typ}] {text[:160]!r}")
    return changed


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("before", type=Path)
    ap.add_argument("after", type=Path)
    ap.add_argument("--expect", type=int, default=None,
                    help="assert exactly N text nodes changed (0 for a refactor)")
    ap.add_argument("--quiet", action="store_true", help="summary only")
    args = ap.parse_args()

    for path in (args.before, args.after):
        if not path.exists():
            sys.exit(f"ERROR: {path} not found")

    report = diff(json.loads(args.before.read_text(encoding="utf-8")),
                  json.loads(args.after.read_text(encoding="utf-8")))
    changed = render(report, quiet=args.quiet)

    structural = (report["forms_added"] or report["forms_removed"]
                  or report["sections_added"] or report["sections_removed"]
                  or report["shared_added"] or report["shared_removed"]
                  or report["count_changes"] or report["moved"])

    if args.expect is not None:
        if changed != args.expect:
            print(f"\nFAIL: expected {args.expect} changed node(s), got {changed}")
            return 1
        if structural:
            print("\nFAIL: unexpected structural change (see above)")
            return 1
        print(f"\nOK: {changed} changed node(s), as expected")
        return 0
    return 1 if (changed or structural) else 0


if __name__ == "__main__":
    sys.exit(main())
