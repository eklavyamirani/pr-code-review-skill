#!/usr/bin/env python3
"""Worked example: how selfhost-v2-pr21.json was assembled.

    selfhost-v2-pr21.build.py <outdir>/.work review.json

Kept because of one thing the protocol asks for and gives no mechanism for:
diff bodies are read out of the worktrees by line range, never retyped. The
line numbers are pinned to that PR's head, so this is a pattern to copy, not a
script to re-run. `_t` exists for the same reason — a tape's left column is
escaped by the template, so markup there would render literally."""
import json, pathlib, re, sys

W = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else ".")
def lines(side, path, a, b, kind="add"):
    text = (W / side / path).read_text().splitlines()
    p = {"add": "+", "del": "-", "ctx": " "}[kind]
    return [{"k": kind, "t": p + l} for l in text[a-1:b]]

H = []

def _t(tape):
    """The template escapes a tape's left column and trusts its right one, so
    markup on the left would render as literal <code> text. Strip it here."""
    tape["rows"] = [[re.sub(r"</?[a-zA-Z][^>]*>", "", a), b] for a, b in tape["rows"]]
    return tape


H.append({
 "file": ".github/workflows/deploy-homelab.yml",
 "stage": "1 · what GitHub may still do",
 "title": "Deployment removed from CI entirely",
 "prose": "Three workflows are deleted outright — <code>deploy-homelab.yml</code>, <code>deploy-public.yml</code>, <code>backup-restore.yml</code> — and with them every path by which a GitHub Actions run could reach the VMs. The deleted file is the one that mattered: it held <code>id-token: write</code> and traded a GitHub OIDC token for an Azure federated credential, then drove the box through <code>az vm run-command</code>. <em>After this PR the repository holds no credential that reaches production</em>; the only surviving workflow is static validation with <code>permissions: contents: read</code>. Everything downstream in this review exists because the VM now has to fetch its own work.",
 "annotated": [
   "<code>.github/workflows/deploy-homelab.yml</code> deleted (167 lines) — OIDC → Azure federated credential → <code>az vm run-command</code>.",
   "<code>.github/workflows/deploy-public.yml</code> and <code>.github/workflows/backup-restore.yml</code> deleted alongside it.",
   "<code>validate-homelab.yml</code> survives; it gains the reconciler unit tests and two <code>reconcile.py validate</code> calls, and keeps <code>permissions: contents: read</code>.",
   "No workflow left in the tree requests <code>id-token</code>, uses <code>azure/login</code>, or references a repository secret."
 ],
 "diff": lines("base", ".github/workflows/deploy-homelab.yml", 1, 12, "del")
       + [{"k":"del","t":"-# ..."}]
       + lines("base", ".github/workflows/deploy-homelab.yml", 28, 34, "del"),
 "glosses": [
   {"m": "id-token: write", "t": "OIDC token permission", "b": "Lets the job mint a short-lived OIDC JWT from GitHub's issuer. Without it the workflow cannot obtain a federated cloud credential at all — it is the switch that turns a run into an identity."},
   {"m": "federated-credential", "t": "Trust without a shared secret", "b": "A cloud-side record saying \"accept tokens from this issuer whose subject claim equals X\". No secret is stored on either side; the subject string is the whole access control."},
   {"m": "subject", "t": "The claim being matched", "b": "The OIDC subject identifies exactly which repo, branch or environment produced the token, e.g. repo:owner/name:environment:prod."}
 ],
 "tape": _t({
   "label": "grep over .github/workflows in both worktrees — executed 2026-09-04",
   "rows": [
     ["workflow files", "<del>backup-restore, deploy-homelab, deploy-public, validate-homelab</del> → <ins>validate-homelab</ins>"],
     ["<code>secrets.*</code> refs", "<del>13 distinct: AZURE_CLIENT_ID, DEPLOY_SSH_KEY, GH_PAT, PROD_VM_IP, …</del> → <ins>secrets.example only</ins>"],
     ["<code>id-token</code>", "<del>2 workflows</del> → <ins>0</ins>"],
     ["<code>azure/login@v2</code>", "<del>present</del> → <ins>absent</ins>"]
   ]
 }),
 "probe": {
   "q": "The tape still shows one match for secrets. in the PR tree — is a credential left behind?",
   "verdict": "ok", "label": "holds up",
   "answer": "No. The surviving match is the literal path <code>home-lab/secrets.example</code> in a shell line inside <code>validate-homelab.yml</code>, not a <code>${{ secrets.NAME }}</code> expression — the grep pattern <code>secrets\\.[A-Za-z_]+</code> cannot tell the two apart. The claim in the PR description holds: no Azure identity, no SSH key, no PAT reachable from Actions."
 }})

H.append({
 "file": "public/scripts/reconcile.sh",
 "stage": "2 · public VM, every 60s",
 "title": "Which tag the box decides to run",
 "prose": "The timer wakes, fetches, and picks its own release. Selection is deliberately narrow: enumerate <code>refs/tags/public-v*</code>, keep only strict <code>MAJOR.MINOR.PATCH</code>, sort, take the highest. The state file records the tag <em>and the commit it pointed at</em>, which is what makes the two refusals below possible — a downgrade, and a tag that has been moved to a different commit. Note there is no signature check anywhere in this path: whoever can push a tag to the repository decides what the public VM runs.",
 "annotated": [
   "<code>flock -n 9</code> on <code>${state_dir}/reconcile.lock</code>, exiting 0 rather than 1 when another run holds it — a skipped tick is not a failure.",
   "<code>for-each-ref</code> lists candidate tags; the <code>grep -E</code> drops anything that is not three bare numeric components (so <code>v1.0.0-rc1</code> and <code>v01.0.0</code> are excluded).",
   "<code>sort -V | tail -n 1</code> picks the highest surviving tag.",
   "<code>mapfile -t last_release</code> reads the two-line state file; a third line means corrupt and aborts.",
   "Downgrade guard: re-sorts <code>last_tag</code> against <code>source_ref</code> and refuses unless the candidate sorts highest.",
   "Moved-tag guard: same tag name, different commit → refuse.",
   "Same tag, same commit → <code>exit 0</code>, the no-op path taken on almost every tick."
 ],
 "diff": lines("pr", "public/scripts/reconcile.sh", 9, 10)
       + [{"k":"ctx","t":" ..."}]
       + lines("pr", "public/scripts/reconcile.sh", 16, 52),
 "glosses": [
   {"m": "flock -n 9", "t": "Non-blocking lock on fd 9", "b": "Takes an advisory lock on whatever file descriptor 9 was opened to. -n means fail immediately instead of waiting; the lock is released when the process exits and the fd closes."},
   {"m": "%(refname:strip=2)", "t": "Drop two path components", "b": "for-each-ref format directive: turns refs/tags/public-v1.2.3 into public-v1.2.3 by stripping the first two slash-separated parts."},
   {"m": "sort -V", "t": "Version sort, not lexical", "b": "Compares embedded digit runs numerically rather than character by character, so 1.10.0 sorts above 1.9.0. GNU coreutils only — not in POSIX sort."},
   {"m": "mapfile -t", "t": "Read lines into an array", "b": "Bash builtin filling an array with one element per input line; -t strips the trailing newline from each."},
   {"m": "^{commit}", "t": "Peel to a commit", "b": "Git revision suffix that dereferences an annotated tag object through to the commit it points at. Without it rev-parse on an annotated tag returns the tag object's own SHA."}
 ],
 "tape": _t({
   "label": "the selection pipeline, run verbatim in the container — 2026-09-04",
   "rows": [
     ["candidates <code>1.9.0 1.10.0 1.2.0 2.0.0</code>", "<code>sort -V | tail -1</code> → <ins>homelab-v2.0.0</ins>"],
     ["<code>rc1</code>, <code>v01.0.0</code>, <code>v1.0</code>, <code>v1.0.0</code>", "grep keeps <ins>homelab-v1.0.0</ins> only"],
     ["last=<code>v1.10.0</code> cand=<code>v1.9.0</code>", "highest → <ins>v1.10.0</ins> ≠ candidate, so <del>refused</del>"]
   ]
 }),
 "probe": {
   "q": "The downgrade guard compares two strings by sorting them. Does public-v1.10.0 beat public-v1.9.0, or does the box happily roll itself back one minor version?",
   "verdict": "ok", "label": "holds up",
   "answer": "It holds. <code>sort -V</code> compares digit runs numerically, so <code>v1.10.0</code> sorts above <code>v1.9.0</code> and the guard refuses the downgrade — confirmed in the tape. This would be a real bug with plain <code>sort</code>, and it is worth naming the dependency: <code>-V</code> is a GNU coreutils extension, so the script is not portable to a BusyBox or BSD userland. On the Ubuntu image it targets, it is correct."
 }})

H.append({
 "file": "public/scripts/reconcile.sh",
 "stage": "2 · public VM, every 60s",
 "title": "What happens when the new release will not start",
 "prose": "The deploy is a detached checkout followed by <code>compose up --wait</code>, and the failure path restores the previous commit and brings the old stack back. The recovery itself is sound. What is missing is any record that the attempt happened: <em>the state file is only written on success</em>, so a tag that cannot start is re-selected, re-checked-out and re-deployed on every subsequent tick, with a full teardown and rollback of the live stack each time.",
 "annotated": [
   "<code>previous_revision</code> captured from <code>HEAD</code> before the checkout, so rollback targets a commit rather than a branch name.",
   "The deploy subshell chains <code>config --quiet</code>, <code>pull --quiet</code>, then <code>up -d --remove-orphans --wait --wait-timeout 300</code>.",
   "On failure: checkout back to <code>previous_revision</code> and <code>compose up</code> the old tree again, then <code>exit 1</code>.",
   "On success only: write the two-line state file via a temp file plus <code>mv</code> (atomic rename).",
   "There is no failure counter, no backoff, and no record of the tag that failed."
 ],
 "diff": lines("pr", "public/scripts/reconcile.sh", 58, 78),
 "glosses": [
   {"m": "--wait-timeout 300", "t": "Bound the readiness wait", "b": "With --wait, compose blocks until every service is running-and-healthy; --wait-timeout caps that at N seconds and exits non-zero if the deadline passes."},
   {"m": "--remove-orphans", "t": "Delete unlisted containers", "b": "Removes containers carrying this project's label that the current compose file no longer declares — how a service that was deleted from the manifest actually goes away."},
   {"m": "checkout --detach", "t": "Check out without a branch", "b": "Moves HEAD directly to a commit rather than to a branch pointing at it, so nothing later fast-forwards the working tree behind you."}
 ],
 "tape": _t({
   "label": "systemd timer settings read from the units in the PR tree",
   "disc": "The loop below is the arithmetic those two settings imply; it was not reproduced against a live VM.",
   "rows": [
     ["public timer", "<code>OnUnitInactiveSec=60s</code>, <code>OnBootSec=2min</code> (public/terraform/cloud-init.yml)"],
     ["one failing tick", "checkout → pull → <code>up --wait</code> up to <ins>300s</ins> → rollback <code>up --wait</code> up to <ins>300s</ins>"],
     ["state after failure", "<del>unchanged</del> — same tag selected again 60s later"],
     ["net effect", "the healthy stack is torn down and restarted <ins>every ~1–10 min, indefinitely</ins>"]
   ]
 }),
 "probe": {
   "q": "A tag ships that crashes on start. The rollback works perfectly. What does the box do sixty seconds later?",
   "verdict": "bug", "label": "real bug",
   "answer": "It tries the identical tag again, and keeps trying forever. <code>${release_file}</code> is written only on the success path, so the next tick re-selects the same highest tag, passes both guards (it is not a downgrade, and the tag has not moved), checks out, fails, and rolls back again — bouncing the last known-good stack on every attempt. Rollback that leaves no trace is a restart loop with extra steps. The smallest fix is to record the failure and refuse to retry it: write a losing marker next to the state file and skip when it matches, e.g. <code>printf '%s\\n' \"${source_ref}\" > \"${state_dir}/failed-release\"</code> before <code>exit 1</code>, checked right after the tag is selected. A backoff or a failure counter would do as well; the requirement is that a failing tag stops being re-attempted at full rate."
 }})

H.append({
 "file": "home-lab/reconciler/selfhost_reconciler/manifest.py",
 "stage": "3 · reconciler starts · manifests",
 "title": "Immutable artifacts, enforced per kind",
 "prose": "Manifests are validated in three passes: JSON Schema for shape, then policy checks in Python for things a schema cannot express, then cross-manifest checks for collisions. The artifact rule is the load-bearing one. A production component must name an image by <code>sha256</code> digest; a preview component may instead name a repository plus the two workflows that must have built and signed it. <em>The <code>else</code> branch is what makes it airtight</em> — anything that is not a preview image, including a fixed image inside a preview manifest, falls through to the digest requirement.",
 "annotated": [
   "<code>OCI_DIGEST_RE</code> requires a registry host, a path, and <code>@sha256:</code> plus exactly 64 hex characters — a tag alone cannot match.",
   "<code>preview and \"previewImage\" in artifact</code> is the only route around the digest rule.",
   "In that branch the repository must match <code>OCI_REPOSITORY_RE</code> and both <code>buildWorkflow</code> and <code>signerWorkflow</code> must look like <code>owner/repo/.github/workflows/x.yml</code>.",
   "<code>_validate_policy</code> later re-checks that both workflow repositories equal the repository in <code>source.pullRequest</code>, lower-cased on both sides.",
   "Secret-shaped environment names are rejected unless they end in <code>_FILE</code>; the schema separately forces env names to <code>^[A-Z_][A-Z0-9_]*$</code>, so the case-sensitive regex cannot be dodged with lowercase."
 ],
 "diff": lines("pr", "home-lab/reconciler/selfhost_reconciler/manifest.py", 106, 129),
 "glosses": [
   {"m": "fullmatch", "t": "Anchor both ends", "b": "Unlike re.search, requires the pattern to consume the entire string — no prefix or suffix can be smuggled past it. The equivalent of wrapping the pattern in ^...$."},
   {"m": "artifact.get(\"image\")", "t": "Absent, not empty", "b": "dict.get returns None for a missing key rather than raising, so the None check below covers both \"no image key\" and \"image that is not a digest\" in one branch."}
 ],
 "tape": _t({
   "label": "OCI_DIGEST_RE evaluated against candidate references — executed in the container",
   "rows": [
     ["<code>ghcr.io/o/app:v1.2.3</code>", "<del>no match</del> — tags are not digests"],
     ["<code>ghcr.io/o/app@sha256:</code>+64 hex", "<ins>match</ins>"],
     ["<code>ghcr.io/o/app@sha256:</code>+63 hex", "<del>no match</del> — length is exact"],
     ["<code>app@sha256:</code>+64 hex", "<del>no match</del> — a registry host is required"]
   ]
 }),
 "probe": {
   "q": "A preview manifest declares a component with a plain image: field set to ghcr.io/owner/app:latest. Which branch does it take?",
   "verdict": "ok", "label": "holds up",
   "answer": "The <code>else</code> branch, and it is rejected. The condition is <code>preview and \"previewImage\" in artifact</code> — being a preview is necessary but not sufficient, so a preview component that supplies <code>image</code> instead is held to the same digest rule as production. Worth noticing because the natural way to write this check (<code>if preview: … else: …</code>) would have made <code>latest</code> deployable on every preview box."
 }})

H.append({
 "file": "home-lab/reconciler/selfhost_reconciler/github.py",
 "stage": "4 · preview · resolve the image",
 "title": "Tag → digest, and the platform assertion",
 "prose": "A preview binds to a PR head by tag (<code>pr-&lt;n&gt;-&lt;sha&gt;</code>), resolves that tag to a digest, and from there on refers to the image only by digest. The resolution is right. The assertion bolted onto the end is not: it demands that the set of platforms in the image index be <em>exactly</em> <code>{linux/amd64, linux/arm64}</code>, and every image that carries the provenance attestation this very PR requires also carries index entries with the platform <code>unknown/unknown</code>.",
 "annotated": [
   "First <code>imagetools inspect --format '{{json .Manifest}}'</code> on <code>repo:tag</code> yields the index digest; <code>DIGEST_RE</code> checks it is <code>sha256:</code> + 64 hex.",
   "<code>resolved_reference</code> is rebuilt as <code>repo@digest</code>, and the second inspect uses that — so nothing after this point depends on the mutable tag.",
   "<code>platforms</code> is built from every index entry that has a <code>platform</code> key, with no filtering.",
   "<code>if platforms != required</code> is set equality, so any extra entry fails, not just a missing one.",
   "<code>_run_registry_command</code> retries 4 times with 1s/2s/4s backoff before raising."
 ],
 "diff": lines("pr", "home-lab/reconciler/selfhost_reconciler/github.py", 105, 120),
 "glosses": [
   {"m": "frozenset", "t": "Hashable immutable set", "b": "A set that cannot be mutated after construction, so it can be stored in a frozen dataclass or used as a dict key. Compares by contents like a normal set."},
   {"m": "--raw", "t": "Unparsed manifest bytes", "b": "imagetools flag that prints the registry's manifest document as-is, rather than buildx's human summary — the only way to see the index's per-entry platform blocks."},
   {"m": "raw.get(\"manifests\", [])", "t": "Index, or single image", "b": "Only a multi-platform index has a manifests array; a single-architecture image has none, and this default quietly turns that case into an empty platform set."}
 ],
 "tape": _t({
   "label": "docker buildx imagetools inspect --raw against three public multi-arch images — executed 2026-09-04",
   "rows": [
     ["<code>ghcr.io/goauthentik/server:2024.10.5</code>", "linux/amd64, linux/arm64, <del>unknown/unknown ×2</del>"],
     ["<code>ghcr.io/immich-app/immich-server:v1.119.0</code>", "linux/amd64, linux/arm64, <del>unknown/unknown ×2</del>"],
     ["<code>docker.io/traefik:v3.2</code>", "6 real platforms, <del>unknown/unknown ×6</del>"],
     ["computed <code>platforms</code>", "<del>{linux/amd64, linux/arm64, unknown/unknown}</del> ≠ required"]
   ]
 }),
 "probe": {
   "q": "The image is built for exactly linux/amd64 and linux/arm64, as required. Does resolve_oci_image accept it?",
   "verdict": "bug", "label": "real bug",
   "answer": "No — it raises, and every preview deploy fails on the first component. Buildx records provenance and SBOM attestations as extra manifests inside the same index, each carrying <code>platform: {os: unknown, architecture: unknown}</code>. Those entries have a <code>platform</code> key, so the comprehension keeps them, and set equality against <code>{linux/amd64, linux/arm64}</code> fails. The tape shows three unrelated registries all shaped this way, and it is not incidental here: this PR mandates <code>gh attestation verify</code> with a SLSA provenance predicate, so a conforming image is <em>guaranteed</em> to carry the attestation manifests that break the check. Filter them out before comparing: <code>if item.get(\"platform\", {}).get(\"architecture\") not in (None, \"unknown\")</code>."
 }})

H.append({
 "file": "home-lab/reconciler/selfhost_reconciler/reconcile.py",
 "stage": "4 · preview · verify the image",
 "title": "Three attestations, none bound to the commit",
 "prose": "Each preview image is put through <code>gh attestation verify</code> three times — build-workflow provenance, signer-workflow provenance, and an SPDX SBOM — and then through an OCI label check. <code>verify_github_attestation</code> takes a <code>source_sha</code> parameter and forwards it as <code>--source-digest</code>, which is exactly the flag that would tie an attestation to the commit under review. <em>All three call sites pass <code>None</code></em>, so the flag is never sent, and the only thing tying the image to the PR head is a label the build wrote into the image.",
 "annotated": [
   "The fourth positional argument of all three <code>verify_github_attestation</code> calls is the literal <code>None</code> — the <code>source_sha</code> slot.",
   "In <code>github.py</code>, <code>--source-digest</code> is appended only <code>if source_sha is not None</code>, so it is never appended.",
   "<code>pull_request.head_sha</code> <em>is</em> available at all three call sites — it is passed to <code>verify_oci_labels</code> on the next line.",
   "<code>verify_oci_labels</code> pulls the image and requires <code>org.opencontainers.image.revision</code> to equal the head SHA.",
   "Calls two and three both use <code>signerWorkflow</code>, differing only in predicate type: SLSA provenance, then SPDX."
 ],
 "diff": lines("pr", "home-lab/reconciler/selfhost_reconciler/reconcile.py", 152, 180),
 "glosses": [
   {"m": "https://slsa.dev/provenance/v1", "t": "Provenance predicate type", "b": "The in-toto predicate identifying a SLSA build-provenance statement — who built the artifact, from what source, on what runner. Passing it makes verify reject attestations of any other kind."},
   {"m": "https://spdx.dev/Document", "t": "SBOM predicate type", "b": "Marks the attestation as carrying an SPDX software bill of materials rather than build provenance — a different claim about the same image digest."}
 ],
 "tape": _t({
   "label": "flag checked against the gh CLI manual; call sites from grep over the PR tree",
   "rows": [
     ["<code>gh attestation verify --source-digest</code>", "<ins>exists</ins> — \"Enforce that the digest associated with the source repository matches the provided value\""],
     ["<code>--signer-workflow</code>, <code>--deny-self-hosted-runners</code>", "<ins>exist</ins> — both are passed"],
     ["call sites passing <code>source_sha</code>", "<del>0 of 3</del> (reconcile.py:152, :160, :168 all pass None)"],
     ["commit binding actually enforced by", "<code>verify_oci_labels</code> → <code>org.opencontainers.image.revision</code>"]
   ]
 }),
 "probe": {
   "q": "With --source-digest never sent, what stops an image built by the right workflow from a different commit in the same repo from being deployed as this PR's preview?",
   "verdict": "think", "label": "control built, left off",
   "answer": "In practice, two weaker things. The tag is <code>pr-&lt;n&gt;-&lt;head_sha&gt;</code>, so the wrong commit's image is not normally at that tag; and <code>verify_oci_labels</code> requires <code>org.opencontainers.image.revision</code> to equal the head SHA, which is inside the image config and therefore covered by the digest. So the binding exists — it just rests on a label the build workflow chose to write, rather than on the signed provenance statement, which is the artifact specifically designed to carry it. This is not exploitable as written, and it is not a defect in behaviour; it is a security control that was plumbed all the way through and then not switched on. Pass the SHA that is already in scope: <code>verify_github_attestation(resolved, pull_request.repository, …, pull_request.head_sha, …)</code>."
 }})

H.append({
 "file": "home-lab/reconciler/selfhost_reconciler/secrets.py",
 "stage": "5 · resolve secrets",
 "title": "The fail-closed placeholder check",
 "prose": "<code>DirectorySecretProvider</code> is the local-deploy secret source, and it is written to fail closed: too-broad directory permissions, an unexpected owner, a group- or world-writable file, an empty value, or a placeholder all raise before the value is used. Four of those five work. <em>The placeholder check compares raw bytes against <code>b\"REPLACE_ME\"</code></em>, and every placeholder file this repository ships is <code>REPLACE_ME</code> followed by a newline — so the one check aimed at the repo's own committed placeholders is the one that never fires.",
 "annotated": [
   "Constructor rejects the directory if <code>st_mode & 0o077</code> — any group or other bit at all.",
   "Constructor rejects the directory if <code>st_uid != os.geteuid()</code>.",
   "<code>get</code> maps <code>some-secret</code> to <code>some_secret.txt</code> via <code>name.replace('-', '_')</code>.",
   "Per-file check is <code>st_mode & 0o022</code> — group/other <em>write</em> only; a world-readable file passes, which the 0o077 directory check is what actually covers.",
   "<code>value = path.read_bytes()</code> — no decode, no strip.",
   "The guard is <code>not value or value == b\"REPLACE_ME\"</code>; a trailing newline defeats the second half.",
   "<code>version</code> is <code>mtime_ns:size</code>, so touching a file rotates the secret volume even if the bytes are identical.",
   "<code>github_token_environment</code>, further down the same file, does <code>.strip()</code> before its identical comparison."
 ],
 "diff": lines("pr", "home-lab/reconciler/selfhost_reconciler/secrets.py", 23, 42),
 "glosses": [
   {"m": "st_mode & 0o022", "t": "Group/other write bits", "b": "Masks the mode against the two write bits outside the owner. 0o077 would be the stricter test, catching read and execute for group and other as well."},
   {"m": "os.geteuid()", "t": "Effective, not real, uid", "b": "The uid used for permission checks, which differs from the real uid under setuid. For an ordinary systemd unit the two are the same."},
   {"m": "read_bytes", "t": "Raw bytes, no decoding", "b": "Returns the file's exact contents with no text decoding and no newline handling — b'x\\n' is a different object from b'x'."},
   {"m": "st_mtime_ns", "t": "Nanosecond mtime", "b": "Modification time as an integer nanosecond count. Used here as a change token: any rewrite changes it, so it identifies a version without touching the value."}
 ],
 "tape": _t({
   "label": "DirectorySecretProvider.get run against the repo's own placeholder files — executed in the container, 2026-09-04",
   "rows": [
     ["<code>secrets.example/github_api_token.txt</code>", "on disk: <code>b'REPLACE_ME\\n'</code>"],
     ["<code>get(\"github-api-token\")</code>", "<del>ACCEPTED</del> — returned <code>b'REPLACE_ME\\n'</code> as the secret"],
     ["same file without the newline", "<ins>REJECTED</ins> — ValueError: secret is empty or a placeholder"],
     ["placeholders this PR adds", "<del>github_api_token</del>, <del>grafana_oauth_client_secret</del>, <del>uptime_kuma_admin_password</del> — all <code>REPLACE_ME\\n</code>"]
   ]
 }),
 "probe": {
   "q": "An operator copies secrets.example/ to secrets/, fills in three of the twelve files, and starts the reconciler. Does it stop them?",
   "verdict": "bug", "label": "real bug",
   "answer": "No. <code>b\"REPLACE_ME\\n\" != b\"REPLACE_ME\"</code>, so every unfilled placeholder sails through and is written into a read-only secret volume as if it were real — the failure surfaces later as an application that will not authenticate, with no mention of a placeholder anywhere. The tape shows the same file rejected the moment the trailing newline is removed, so the check is correct in intent and wrong by one byte. The author knew: <code>github_token_environment</code>, ninety lines further down this same file, strips before comparing. Match it — <code>if not value.strip() or value.strip() == b\"REPLACE_ME\":</code> — and consider rejecting anything that starts with <code>#</code>, since the other nine shipped placeholders are comment blocks that would also be accepted as secrets."
 }})

H.append({
 "file": "home-lab/reconciler/selfhost_reconciler/runtime.py",
 "stage": "6 · write the secret volume",
 "title": "Writing files without ever passing them as arguments",
 "prose": "Secret material reaches its volume through a throwaway BusyBox container: content on stdin, written to a temp file, chowned, chmoded, renamed into place. The shape is right — <em>the value is never an argv element, never an environment variable, and never appears in a log line</em>, which is precisely the leak this design set out to prevent. The names around it are a different matter: <code>filename</code>, <code>uid</code>, <code>gid</code> and <code>mode</code> are interpolated into a shell string with no quoting and no escaping.",
 "annotated": [
   "<code>umask 077</code> first, so the temp file is never briefly readable.",
   "Content arrives via <code>input_bytes=content</code> on the container's stdin (<code>-i</code>), not on the command line.",
   "Write is temp-then-<code>mv</code>, so a reader never sees a partial file.",
   "The container gets <code>--network none</code>, <code>--cap-drop ALL</code>, then re-adds only <code>CHOWN</code>, <code>FOWNER</code>, <code>DAC_OVERRIDE</code>.",
   "BusyBox is pinned by digest at the top of the file, so this helper is not itself a supply-chain hole.",
   "<code>{filename}</code>, <code>{uid}</code>, <code>{gid}</code> and <code>{mode}</code> land inside <code>sh -c</code> unquoted."
 ],
 "diff": lines("pr", "home-lab/reconciler/selfhost_reconciler/runtime.py", 387, 405)
       + [{"k":"add","t":"+                # ..."}]
       + lines("pr", "home-lab/reconciler/selfhost_reconciler/runtime.py", 413, 431),
 "glosses": [
   {"m": "umask 077", "t": "Default-deny new files", "b": "Clears group and other bits from the permissions of anything created afterwards, so a file is never momentarily readable between creation and chmod."},
   {"m": "DAC_OVERRIDE", "t": "Bypass file permission checks", "b": "The capability that lets a process ignore read/write/execute bits entirely. Needed here to rewrite a 0400 file it does not own; also the one that makes the other two nearly redundant."},
   {"m": "-eu", "t": "Abort on error or unset", "b": "sh flags: -e exits on the first failing command, -u treats an unset variable as an error. Together they stop the mv from running after a failed chmod."}
 ],
 "tape": _t({
   "label": "what constrains the interpolated names — schema patterns read from the PR tree",
   "disc": "No injection was executed: on the schemas as written, no reachable input escapes the shell string.",
   "rows": [
     ["config file names", "<code>propertyNames: ^[A-Za-z0-9_.-]+$</code> — no space, quote, <code>;</code>, <code>$</code> or <code>/</code>"],
     ["secret targets", "<code>^/run/secrets/[A-Za-z0-9_.-]+$</code>, then <code>Path(target).name</code>"],
     ["<code>user</code> → uid/gid", "<code>^[1-9][0-9]*:[1-9][0-9]*$</code> — digits only"],
     ["<code>mode</code>", "not from the manifest — literal <code>\"0400\"</code> / <code>\"0444\"</code> at both call sites"]
   ]
 }),
 "probe": {
   "q": "A manifest declares a config file named  x; rm -rf /dest;  — what happens?",
   "verdict": "think", "label": "no defect, thin margin",
   "answer": "The manifest is rejected before this code runs: the schema's <code>propertyNames</code> pattern for <code>files</code> allows only <code>[A-Za-z0-9_.-]</code>, so the semicolon never gets here. Nothing to fix today. What is worth naming is where the safety lives — one regex, in a JSON Schema file, two modules away from the <code>sh -c</code> string that depends on it, with nothing at the injection site recording the dependency. Widening that pattern later (a config file with a space in the name is a plausible request) silently turns this into command execution inside the writer container. It is cheap to not rely on it: pass the names as positional arguments and quote them — <code>sh -eu -c 'umask 077; cat &gt; \"/dest/.$1.tmp\"; chown \"$2\" \"/dest/.$1.tmp\"; …' writer \"$filename\" \"$uid:$gid\"</code> — which removes the coupling entirely. Note the blast radius is already small: <code>--network none</code>, all capabilities dropped but three, and only the target volume mounted."
 }})

H.append({
 "file": "home-lab/reconciler/selfhost_reconciler/runtime.py",
 "stage": "7 · converge · remove what is no longer wanted",
 "title": "Deleting volumes without deleting data",
 "prose": "The last step of a successful reconcile sweeps managed volumes that nothing wants any more. A sweep that deletes by label is the kind of code that turns a config change into data loss, so the interesting question is what keeps it away from application data. The answer is a two-label scheme: derived volumes carry <code>selfhost.managed=true</code>, persistent data carries <code>selfhost.managed-data=true</code>, and <em>this filter only ever names the first</em>.",
 "annotated": [
   "<code>docker volume ls --quiet</code> filtered on <em>both</em> <code>selfhost.managed=true</code> and <code>selfhost.project=&lt;project&gt;</code>.",
   "<code>existing - desired</code> is a set difference over volume names; everything left is removed.",
   "<code>desired</code> is assembled by the caller from the secret volumes and config volumes of the manifests that survived this run.",
   "Persistent volumes are created in <code>ensure_persistent_volumes</code> with <code>selfhost.managed-data=true</code> — a different key, so they never appear in this listing.",
   "Application data is removed only by <code>cleanup_application(..., remove_data_volumes=True)</code>, which the caller passes only in preview mode.",
   "Both secret and config volume names embed a content or version hash, so a change produces a new name and the old one becomes sweepable."
 ],
 "diff": lines("pr", "home-lab/reconciler/selfhost_reconciler/runtime.py", 511, 532),
 "glosses": [
   {"m": "--filter", "t": "Repeatable, AND-ed", "b": "Docker CLI filters of the same type combine with AND, so two label filters require both labels. Different filter types combine with OR in some subcommands — a docker-specific trap worth knowing."},
   {"m": "existing - desired", "t": "Set difference", "b": "Python set operator yielding elements of the left set absent from the right. sorted() around it only fixes the deletion order for reproducible logs."}
 ],
 "tape": _t({
   "label": "label scheme as written in the PR tree",
   "disc": "Read from the source rather than run against a live Docker daemon.",
   "rows": [
     ["secret volume", "<code>selfhost.managed=true</code> + <code>type=secret</code> → <del>swept when unreferenced</del>"],
     ["config volume", "<code>selfhost.managed=true</code> + <code>type=config</code> → <del>swept when unreferenced</del>"],
     ["persistent volume", "<code>selfhost.managed-data=true</code> + <code>owner=uid:gid</code> → <ins>never matched by this filter</ins>"],
     ["preview teardown", "<code>cleanup_application(remove_data_volumes=True)</code>, re-checking all three labels first"]
   ]
 }),
 "probe": {
   "q": "An application is deleted from home-lab/apps/ and the production reconciler runs. Its database volume is now unreferenced — does this sweep delete it?",
   "verdict": "ok", "label": "holds up",
   "answer": "No, and it takes two independent guards to get there. The listing filters on <code>selfhost.managed=true</code>, which persistent volumes do not carry — they are labelled <code>selfhost.managed-data=true</code>, a distinct key rather than a distinct value, so no filter can confuse them. Separately, a removed application goes onto <code>pendingCleanup</code> and is torn down by <code>cleanup_application</code>, which deletes data volumes only when <code>remove_data_volumes</code> is true, and the caller sets that from <code>mode == \"preview\"</code>. In production the volume is orphaned and kept, which is the right default for the direction whose mistakes are unrecoverable."
 }})

data = {
 "repo": "eklavyamirani/selfhost-v2",
 "pr": 21,
 "name": "Pull-based deployments",
 "title": "Deployments stop being pushed and start being pulled",
 "subtitle": "108 files, +6,493/−1,038. GitHub Actions loses every credential that reached a VM; in exchange each box now decides for itself what to run, from immutable semantic tags. Nine hunks, ordered by when the machine runs the code — not one of them is a documentation change.",
 "hunks": H,
}
out = pathlib.Path(sys.argv[2] if len(sys.argv) > 2 else "review.json")
out.write_text(json.dumps(data, indent=2, ensure_ascii=False))
print(f"wrote {out} — {len(H)} hunks")
