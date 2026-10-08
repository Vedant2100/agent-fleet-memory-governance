#!/usr/bin/env python3
"""Publish a completed local evidence snapshot through the handoff PR.

The experiment checkout is read-only. A publication receipt prevents repeat comments.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path


REPOSITORY = "Vedant2100/agent-fleet-memory-governance"
BRANCH = "handoff/aamas-2027-evidence"
PR = "https://github.com/Vedant2100/agent-fleet-memory-governance/pull/1"
MAX_GIT_BLOB = 95_000_000


def run(*args: str, cwd: Path, input_text: str | None = None) -> str:
    result = subprocess.run(args, cwd=cwd, input=input_text, text=True,
                            capture_output=True, check=False, timeout=600)
    if result.returncode:
        raise RuntimeError(f"{' '.join(args[:3])} failed: {result.stderr[-1000:]}")
    return result.stdout.strip()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def latest_version(root: Path) -> Path:
    versions = [path for path in (root / "versions").iterdir()
                if path.is_dir() and (path / "evidence-manifest.json").is_file()]
    if not versions:
        raise RuntimeError("no collected evidence snapshot")
    return max(versions, key=lambda path: int(path.name.split("-", 1)[0][1:]))


def previous_comments(repo: Path) -> list[dict]:
    raw = run("gh", "api", f"repos/{REPOSITORY}/issues/1/comments?per_page=100", cwd=repo)
    return json.loads(raw)


def comment_once(repo: Path, body: str, evidence_commit: str) -> str:
    comments = previous_comments(repo)
    existing = [item for item in comments if evidence_commit in item.get("body", "")]
    if existing:
        return existing[0]["html_url"]
    run("gh", "pr", "comment", PR, "--body", body, cwd=repo)
    comments = previous_comments(repo)
    posted = [item for item in comments if evidence_commit in item.get("body", "")]
    if not posted:
        raise RuntimeError("PR comment could not be verified")
    return posted[-1]["html_url"]


def publication_notice(repo: Path, manifest: dict, commit: str, url: str) -> tuple[str, str]:
    prior_round_zero = any(item.get("body", "").startswith("PAPER_WRITER round=0")
                           for item in previous_comments(repo))
    is_ready = manifest["status"] == "COLLECTED_COMPLETE"
    marker = "PAPER_WRITER round=0" if is_ready and not prior_round_zero else "PAPER_EVIDENCE_UPDATE"
    body = (f"{marker}\n\nEvidence commit: `{commit}`\n"
            f"Experiment code commit: `{manifest['experiment_commit']}`\n"
            f"Bundle URL: {url}\nBundle SHA-256: `{manifest['archive']['sha256']}`\n"
            f"Bundle size: {manifest['archive']['size_bytes']} bytes\n"
            f"Affected experiments: Luna A–F core comparison; Slurm job {manifest['slurm_job_id']}.\n"
            f"Status: {manifest['status']}. G_LLM_WRITE is unrun and outside the amended core.\n")
    return marker, comment_once(repo, body, commit)


def write_receipt(version: Path, manifest: dict, commit: str, url: str,
                  marker: str, comment_url: str) -> None:
    data = {"evidence_commit": commit, "experiment_commit": manifest["experiment_commit"],
            "bundle_url": url, "bundle_sha256": manifest["archive"]["sha256"],
            "comment_marker": marker, "comment_url": comment_url,
            "published_at_utc": datetime.now(timezone.utc).isoformat()}
    (version / "github-publication.json").write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    print(json.dumps(data))


def render_status(manifest: dict, snapshot: dict, url: str) -> str:
    counts = manifest["arm_counts"]
    lines = [
        "# Fleet-Mem AAMAS 2027 evidence status", "",
        f"**{'PROVISIONAL — ' if manifest.get('provisional') else ''}{manifest['status']}**, collected {snapshot['collected_at_utc']}.", "",
        f"Experiment code commit: `{manifest['experiment_commit']}`.",
        f"Evidence bundle: [{manifest['archive']['filename']}]({url}).",
        f"Bundle SHA-256: `{manifest['archive']['sha256']}`; size: {manifest['archive']['size_bytes']} bytes.",
        f"Slurm job {manifest['slurm_job_id']}: `{manifest['slurm_state']}`.", "",
        "| Arm | Canonical grades | Applied | Resolved |", "| --- | ---: | ---: | ---: |",
        "| A_NO_MEMORY | 10 | 10 | 2 |",
    ]
    for arm in ("B_SHARE_ALL", "C_RANDOM_MATCHED", "D_JEV_WRITE", "E_JEV_WRITE_READ"):
        item = counts[arm]
        lines.append(f"| {arm} | {item['graded']} | {item['applied']} | {item['resolved']} |")
    lines.extend(("| F_ORACLE_RELATED_CEILING | 10 | 10 | 1 |",
                  "| G_LLM_WRITE | 0 | 0 | 0; outside amended A–F core |", "",
                  "This is a development pilot, not a confirmatory effect estimate. The frozen A/F signal gate has 3/10 executable discordances. Original failed attempts and the supplemental test-file-filtered regrade are retained in the bundle. G was listed in the earlier protocol and remains unrun.", ""))
    if manifest["issues"]:
        lines += ["## Validation issues", ""] + [f"- {item}" for item in manifest["issues"]] + [""]
    return "\n".join(lines)


def publish(version: Path, repo: Path) -> None:
    receipt = version / "github-publication.json"
    if receipt.is_file():
        print(receipt.read_text())
        return
    manifest = json.loads((version / "evidence-manifest.json").read_text())
    snapshot = json.loads((version / "snapshot.json").read_text())
    archive = version / manifest["archive"]["filename"]
    if archive.stat().st_size > MAX_GIT_BLOB:
        raise RuntimeError("archive exceeds conservative GitHub git blob limit; keep local ZIP for Drive upload")
    if sha256(archive) != manifest["archive"]["sha256"]:
        raise RuntimeError("local ZIP checksum mismatch")
    if run("git", "branch", "--show-current", cwd=repo) != BRANCH:
        raise RuntimeError("handoff worktree is on the wrong branch")
    if run("git", "status", "--porcelain", cwd=repo):
        raise RuntimeError("handoff worktree has uncommitted changes")
    existing_manifest = json.loads((repo / "handoff/evidence-manifest.json").read_text())
    if (existing_manifest.get("archive", {}).get("sha256") == manifest["archive"]["sha256"]
            and existing_manifest.get("publication_status") == "GITHUB_FALLBACK_VERIFIED"):
        commit = run("git", "rev-parse", "HEAD", cwd=repo)
        url = existing_manifest["archive"]["github_url"]
        matching = [item for item in previous_comments(repo)
                    if manifest["archive"]["sha256"] in item.get("body", "")]
        if matching:
            body = matching[-1]["body"]
            marker = body.splitlines()[0]
            write_receipt(version, manifest, commit, url, marker, matching[-1]["html_url"])
        else:
            marker, comment_url = publication_notice(repo, manifest, commit, url)
            write_receipt(version, manifest, commit, url, marker, comment_url)
        return

    target = repo / "handoff/bundles" / archive.name
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and sha256(target) != manifest["archive"]["sha256"]:
        raise RuntimeError("bundle filename collision")
    if not target.exists():
        shutil.copyfile(archive, target)
    url = ("https://github.com/" + REPOSITORY + "/raw/refs/heads/" + BRANCH
           + "/handoff/bundles/" + archive.name)
    manifest["archive"]["github_url"] = url
    manifest["archive"]["publication_route"] = "GITHUB_HANDOFF_BRANCH_FALLBACK"
    manifest["publication_status"] = "GITHUB_FALLBACK_PENDING_VERIFICATION"
    manifest.pop("ready_comment_posted", None)
    manifest["snapshot_utc"] = datetime.now(timezone.utc).isoformat()
    manifest["branch"] = BRANCH
    manifest["repository"] = REPOSITORY
    manifest["pull_request"] = PR
    prior_manifest = json.loads((repo / "handoff/evidence-manifest.json").read_text())
    manifest["artifacts"] = prior_manifest.get("artifacts", [])
    manifest_path = repo / "handoff/evidence-manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    (repo / "handoff/experiment-status.md").write_text(render_status(manifest, snapshot, url))
    run("git", "add", "handoff/evidence-manifest.json", "handoff/experiment-status.md",
        f"handoff/bundles/{archive.name}", cwd=repo)
    run("git", "commit", "-m", f"Publish Fleet-Mem evidence {version.name}", cwd=repo)
    evidence_commit = run("git", "rev-parse", "HEAD", cwd=repo)
    run("git", "push", "origin", BRANCH, cwd=repo)

    metadata = json.loads(run("gh", "api", f"repos/{REPOSITORY}/contents/handoff/bundles/{archive.name}?ref={BRANCH}", cwd=repo))
    expected_blob = run("git", "hash-object", str(target), cwd=repo)
    if metadata.get("size") != archive.stat().st_size or metadata.get("sha") != expected_blob:
        raise RuntimeError("GitHub bundle metadata did not match local size and git blob checksum")
    manifest["publication_status"] = "GITHUB_FALLBACK_VERIFIED"
    manifest["bundle_commit"] = evidence_commit
    manifest["archive"]["github_blob_sha1"] = expected_blob
    url = metadata["download_url"]
    manifest["archive"]["github_url"] = url
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    (repo / "handoff/experiment-status.md").write_text(render_status(manifest, snapshot, url))
    run("git", "add", "handoff/evidence-manifest.json", "handoff/experiment-status.md", cwd=repo)
    run("git", "commit", "-m", f"Verify Fleet-Mem evidence {version.name}", cwd=repo)
    run("git", "push", "origin", BRANCH, cwd=repo)
    final_commit = run("git", "rev-parse", "HEAD", cwd=repo)

    pr_body = ("Fleet-Mem AAMAS 2027 evidence handoff.\n\n"
               f"Status: {manifest['status']}. Experiment code commit: `{manifest['experiment_commit']}`.\n"
               f"Evidence commit: `{final_commit}`. Bundle: {url}.\n"
               f"SHA-256: `{manifest['archive']['sha256']}`. G_LLM_WRITE remains unrun outside the amended A–F core.\n")
    run("gh", "pr", "edit", PR, "--body", pr_body, cwd=repo)
    marker, comment_url = publication_notice(repo, manifest, final_commit, url)
    write_receipt(version, manifest, final_commit, url, marker, comment_url)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--handoff-repo", type=Path, required=True)
    args = parser.parse_args()
    publish(latest_version(args.output_root), args.handoff_repo)


if __name__ == "__main__":
    main()
