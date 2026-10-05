#!/usr/bin/env python3
"""Upload an annotator's traces/<Name>/ subdir to <hf-org>/<annotator-id>_annotation.

Files sit at repo root with `primary/` and `progress.json` directly under root
(no <Name>/ prefix). HF auto-creates .gitattributes on repo creation.

Idempotent: re-running uploads only changed files. Safe to invoke after filling
in additional post_task_form.json entries.
"""
import argparse
import sys
from pathlib import Path

from huggingface_hub import HfApi, create_repo

REPO_ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--annotator", required=True, help="e.g. P4")
    ap.add_argument("--repo-id", required=True, help="e.g. <hf-org>/<annotator-id>_annotation")
    ap.add_argument(
        "--path-in-repo",
        default="",
        help="prefix in HF repo, e.g. '' (root) or '<annotator-id>'",
    )
    ap.add_argument("--private", action="store_true", default=True)
    ap.add_argument("--public", dest="private", action="store_false")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    src = REPO_ROOT / "breakingweb" / "human" / "traces" / args.annotator
    if not src.is_dir():
        sys.exit(f"missing source dir: {src}")

    n_files = sum(1 for p in src.rglob("*") if p.is_file())
    privacy = "private" if args.private else "public"
    print(f"source: {src}")
    print(f"target: {args.repo_id} ({privacy} dataset)")
    print(f"path_in_repo: {args.path_in_repo or '<root>'}")
    print(f"local file count: {n_files}")

    if args.dry_run:
        print("[dry-run] no API calls made")
        return

    api = HfApi()
    print(f"creating dataset {args.repo_id} (exist_ok=True)...")
    create_repo(args.repo_id, repo_type="dataset", private=args.private, exist_ok=True)

    print(f"uploading {n_files} files...")
    commit_url = api.upload_folder(
        folder_path=str(src),
        path_in_repo=args.path_in_repo,
        repo_id=args.repo_id,
        repo_type="dataset",
        commit_message=f"upload {args.annotator} annotation traces ({n_files} files)",
    )
    print(f"commit: {commit_url}")

    remote = api.list_repo_files(args.repo_id, repo_type="dataset")
    print(f"remote file count: {len(remote)}")
    print(f"sample remote paths: {remote[:3]}")


if __name__ == "__main__":
    main()
