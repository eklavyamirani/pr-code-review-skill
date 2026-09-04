---
name: pr-code-review
description: Reviews a pull request in a container and renders an interactive review page with semantic zoom, syntax glosses, executed value tapes and predict-then-reveal probes. Use when the user wants to review a PR, compare branches, or explore code changes interactively.
compatibility: Requires docker and bash on the host; everything else runs in the container
metadata:
  version: "3.1"
---

# PR Code Review Skill

Two halves. The **worktree half** gives you both versions of the code side by
side so you can actually run things. The **render half** turns the diff into a
keyboard-driven review page designed to keep a reader in flow.

The page exists because reading a diff is four simultaneous jobs — decode
syntax, simulate execution, infer intent, place it in the system — and the cost
is holding all four at once. Each gets its own channel, on demand, in place.

## Workflow

Everything below runs inside the container. The host only runs `docker`.

```bash
# 1. workspace: clone (read-only source), two worktrees, diff, files.json
PR_REVIEW_NETWORK=bridge pr-review <repo> --pr <N> -o <out>
#    or, fully offline:
pr-review <repo> <base-ref> <head-ref> -o <out>

# 2. explore and RUN things; the whole point of the container is that the PR's
#    code may execute. Drop into a shell in the same image:
pr-review <repo> <base> <head> -o <out> -- bash
#    /work/base and /work/pr are the two versions; /out is shared with the host.

# 3. build tapes from real execution rather than reasoning:
pr-review <repo> <base> <head> -o <out> -- \
  trace-review.py --cmd 'zsh -lc true' --watch PATH,MANPATH --out /out/trace.json

# 4. write <out>/review.json   (protocol below)

# 5. render
python3 scripts/render-review.py <out>/review.json -o <out>/review.html
```

The worktrees live at `<out>/.work` on the host and are bind-mounted to `/work`,
so they survive between runs: step 1 builds them, and every later `-- cmd`
invocation finds the same `/work/base` and `/work/pr`. Re-running step 1
rebuilds them from scratch.

The container is `--rm` and the host repo was mounted read-only, so the only
thing a review leaves behind is that output directory. `cleanup-review.sh <out>`
drops the worktrees and keeps the page; `--all` removes both.

`--pr N` defaults its base to the remote's **default branch**, not to the head's
first parent. Passing a base explicitly is still the safest option when the PR
targets anything else — `pr-review <repo> --pr <N> <base-ref>`. A wrong base
does not error; it produces a smaller review that looks entirely normal, so
check the file count in step 1's output against the PR before annotating.

Step 4 is the whole job. Everything else is mechanical.

**Never hand-write the HTML.** `templates/review.template.html` is generic and
stays untouched; you author data only. `render-review.py` validates first and
refuses on missing answers, unknown verdicts, or a gloss that matches no diff
line.

## Using trace-review.py

`trace-review.py` runs one command in `/work/base` and again in `/work/pr` with
`xtrace` on, then reports what differed. Output has three useful parts:

- `new_steps` — commands that execute only in the PR version, with `file:line`.
  Keyed on the expanded command, not the line number, so an insertion near the
  top does not report the whole tail as new.
- `vars` — each watched variable before and after. Anything ending in `PATH`
  additionally gets `delta` with `added`, `removed`, `reordered` and the first
  entry on each side, which is usually the thing you actually care about.
- `stdout` / `stderr` per side.

`$HOME` is redirected to a scratch directory per run and normalized back to the
literal `$HOME` in the output, so tapes stay readable and a traced script that
writes to the home directory does not touch anything real.

Turn its output into tape rows more or less verbatim — that is the point. If a
command cannot be run at all, say so in the tape's `disc`; see below.

## Annotation protocol

### Order hunks by execution, never by filename

Alphabetical file order forces the reader to hold half-built context across
jumps. Order by *when the machine runs the code*: install step, then config
read, then the shell/request path that consumes it. Put the stage in `stage`
(`"1 · brew bundle"`, `"3 · every login shell"`) so ordering is visible, and
write later hunks so they can lean on context established in earlier ones.

### Split by concern, not by file

One file usually yields two or three hunks. Six to ten hunks is a good page;
past twelve, the PR should have been split.

### A PR too large to annotate whole

Machine-authored PRs routinely land at 100+ files. The page does not scale to
that and should not try: annotating forty hunks produces something nobody
finishes. Select instead, and say in the subtitle what you selected.

Triage from `files.json` — it already carries per-file churn and a `docs` flag:

```bash
python3 -c 'import json;f=json.load(open("<out>/files.json"));
print(sum(not x["docs"] for x in f),"non-doc");
[print(x["changed"],x["file"]) for x in sorted(f,key=lambda x:-x["changed"])[:40] if not x["docs"]]'
```

Then follow the trust and data path rather than the churn ranking: what runs
first, what it trusts, where secrets and credentials enter, what executes
untrusted input, what deletes things. A 350-line test file is high churn and
low review value; a 9-line change to a permission check is the opposite.
Everything you leave out is fine — it is a review, not an audit — but the
subtitle has to say so, or the page implies a completeness it does not have.

### Skip pure documentation

Docs are a separate low-energy pass. Only annotate hunks where behaviour changes.

### Write all three zoom levels as faithful renderings

The reader switches altitude with `1` / `2` / `3` and must be able to trust
that a lower altitude *omits nothing that matters* — otherwise dropping down is
skimming, which is what this whole thing exists to avoid.

- `prose` — one paragraph, what this change does and why. Serif; reads as prose.
  Use `<em>` on the single load-bearing idea.
- `annotated` — array of strings, one per mechanical fact. Every deletion,
  addition and rename accounted for. `<code>` for identifiers.
- `diff` — array of `{"k": "add"|"del"|"ctx", "t": "<raw line>"}`. Verbatim from
  `git diff`, including the leading `+`/`-`. Do not re-type from memory; splice
  from the actual diff. Elide long comment blocks with `# ...` rather than
  paraphrasing code.

### Gloss syntax, not semantics

`glosses` is `[{"m": "<literal substring>", "t": "<3-4 word title>", "b": "<what the construct does>"}]`,
matched against diff lines at render time. Keep these strictly **language-level** —
what `whence -p` is, why an unquoted RHS inside `[[ ]]` is a pattern. The moment
a gloss mentions this repo it belongs in `prose` instead. Two to four per hunk;
gloss what is genuinely obscure, not what is merely present.

### Tapes must be executed, not imagined

`tape` is the highest-value element and the easiest to fake. Offloading
simulation only works if the values are real.

```json
"tape": {"label":"verified against upstream release tags — run 2026-09-04",
         "disc":"optional italic note",
         "rows":[["fzf 0.74.3","<ins>exists</ins> — matches latest tag"],
                 ["tmux 3.7c","<del>no such tag</del> — latest is 3.7b"]]}
```

**The two columns are not the same.** The left one is escaped and renders as
plain text — a `<code>` there appears on the page as the literal characters
`<code>`. The right one is inserted as HTML, which is what `<ins>` and `<del>`
need. `render-review.py` rejects markup in the left column, because this is
invisible in the JSON and obvious only once you look at the page.

Get values by actually running something: `set -x` traces mapped back to source
lines, `--dry-run`, a probe in the `pr/` worktree, an upstream API for a pinned
version. `<ins>` / `<del>` mark the before/after within a value.

**If you could not execute it, say so in `disc`** — "illustrative shape, not
captured on this machine". A tape presented as observed but actually guessed is
worse than no tape, because it launders a guess as evidence.

Every version string, hash, URL and external identifier in a machine-authored
PR gets checked against its source. These are the defects careful reading
cannot catch — `3.7c` looks exactly as plausible as `3.7b` — and the ones a
single command catches instantly.

### Probe before you tell

Each hunk ends with a question the reader answers *before* pressing `r`.

```json
"probe": {"q":"...","verdict":"bug|ok|think","label":"real bug","answer":"<html>"}
```

- `q` — answerable from the hunk plus earlier hunks. Not rhetorical, not a quiz
  on trivia. The best ones make the reader re-read one specific line. Plain
  text: it is escaped, so backticks and tags render literally. Only `answer`
  takes HTML.
- `verdict` — `bug` (defect), `think` (design question or misleading comment,
  no defect), `ok` (holds up; the claim checks out).
- `answer` — say what is true, why, and the smallest fix. Include the fix as a
  one-line `<code>` where one exists.

Do not front-load findings in the page header. The predict-then-check loop is
the mechanism; a summary at the top destroys it. Findings go in the chat
message *after* handing over the page.

Include `ok` hunks. A page where every probe is a bug trains the reader to stop
predicting and just press `r`.

## Verifying before handover

- `make validate JSON=<json>` exits non-zero on structural problems: a gloss
  matching no diff line, a probe without an answer, markup in a tape's left
  column, a bad verdict.
- Open the page and step through with `space` once. Validation cannot see
  layout: check that glosses land on the right tokens, that no diff line
  renders with a stray `<span>`, and that nothing in a tape wraps into
  nonsense. Driving it headless works and is worth it — click each rail entry,
  press `1`/`2`/`3`, and assert on the DOM.
- Sanity-check the hunk order by reading only the `stage` chips top to bottom.
- Check the file paths in the card headers against the tree. A wrong path
  renders perfectly and is wrong on every level of the page at once.

## Reading it

`space`/`j` next · `k` back · `1`/`2`/`3` zoom · `r` reveal · `?` park a question ·
hover a dotted token for syntax. Progress and parked questions persist in
`localStorage`, keyed per repo+PR, so a session can be abandoned and resumed.

Parked questions are the ADHD-specific affordance: capture the tangent, keep
reading, and answer the list afterwards. When the reader hands the parked list
back, answer them as a batch.

## Limitations

- Built for 6–12 annotated hunks. A PR needing more should be split.
- Tapes require being able to run the code; a PR in an unfamiliar stack gets
  weaker tapes, and `disc` must say so.
- `localStorage` is per-browser. Moving machines loses progress.
- The page pulls IBM Plex from Google Fonts. Offline it falls back to the
  system stacks, which is a downgrade, not a failure.
