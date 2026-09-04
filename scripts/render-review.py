#!/usr/bin/env python3
"""Render a review.json annotation file into a standalone review page.

    render-review.py <review.json> [-o out.html]

The template is generic and never edited per-PR. Only review.json changes.
Stdlib only; no network, no build step. Output is a single self-contained
HTML file that opens with file:// or publishes as an artifact unchanged.
"""
import json, sys, pathlib, argparse

TPL = pathlib.Path(__file__).resolve().parent.parent / "templates" / "review.template.html"

REQUIRED_HUNK = ("file", "title", "prose", "annotated", "diff")
VERDICTS = {"bug", "ok", "think"}


def validate(d):
    errs = []
    for k in ("repo", "pr", "title", "hunks"):
        if k not in d:
            errs.append(f"top-level: missing {k!r}")
    for i, h in enumerate(d.get("hunks", [])):
        at = f"hunks[{i}] ({h.get('file', '?')})"
        for k in REQUIRED_HUNK:
            if not h.get(k):
                errs.append(f"{at}: missing {k!r}")
        for g in h.get("glosses", []):
            if not any(g.get("m", "\0") in l.get("t", "") for l in h.get("diff", [])):
                errs.append(f"{at}: gloss {g.get('m')!r} matches no diff line")
        p = h.get("probe")
        if p:
            if not p.get("answer"):
                errs.append(f"{at}: probe has no answer")
            if p.get("verdict") not in VERDICTS:
                errs.append(f"{at}: verdict must be one of {sorted(VERDICTS)}")
    return errs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("data")
    ap.add_argument("-o", "--out", default=None)
    ap.add_argument("--force", action="store_true", help="render despite validation errors")
    a = ap.parse_args()

    d = json.loads(pathlib.Path(a.data).read_text())
    errs = validate(d)
    for e in errs:
        print("!!", e, file=sys.stderr)
    if errs and not a.force:
        sys.exit(f"\n{len(errs)} problem(s); fix them or pass --force")

    # </script> inside annotation prose would close the data block early
    blob = json.dumps(d, ensure_ascii=False).replace("</", "<\\/")
    html = TPL.read_text().replace("/*__DATA__*/", blob)

    out = pathlib.Path(a.out or (pathlib.Path(a.data).with_suffix(".html")))
    out.write_text(html)
    n = len(d["hunks"])
    bugs = sum(1 for h in d["hunks"] if (h.get("probe") or {}).get("verdict") == "bug")
    print(f"{out}  ({n} hunks, {bugs} flagged, {len(html)//1024}KB)")


if __name__ == "__main__":
    main()
