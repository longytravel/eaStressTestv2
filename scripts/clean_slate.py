from __future__ import annotations

import argparse
import shutil
from datetime import datetime
from pathlib import Path


def _rm(path: Path) -> None:
    if not path.exists():
        return
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()


def main() -> int:
    ap = argparse.ArgumentParser(description="Clean old runs/reports to start from a fresh slate.")
    ap.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[1]))
    ap.add_argument("--archive", action="store_true", help="Move to archive/ instead of deleting")
    ap.add_argument("--yes", action="store_true", help="Actually perform deletions/moves")
    args = ap.parse_args()

    repo_root = Path(args.repo_root).resolve()
    runs_dir = repo_root / "runs"
    archive_root = repo_root / "archive"
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    if not runs_dir.exists():
        print(f"Runs dir does not exist: {runs_dir}")
        return 0

    children = sorted(runs_dir.iterdir())
    print("Planned cleanup (everything under runs/):")
    for p in children:
        print(f" - {p}")

    if not args.yes:
        print("\nDry-run only. Re-run with --yes to perform.")
        return 0

    if args.archive:
        dest = archive_root / f"runs_{stamp}"
        dest.mkdir(parents=True, exist_ok=True)
        for p in children:
            try:
                shutil.move(str(p), str(dest / p.name))
            except Exception:
                pass
        print(f"Archived to: {dest}")
        return 0

    for p in children:
        _rm(p)

    print("Clean slate complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
