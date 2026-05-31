# cleanup_files.py
import os
from pathlib import Path
import argparse
from datetime import datetime

"""
Find and delete experiment artifacts:
- .png, .json, .csv, .tex
- optionally snapshots
- optionally database
"""

TARGET_EXTENSIONS = {".png", ".json", ".csv", ".tex"}
SKIP_DIRS = {".venv", ".git", "__pycache__", "dashboard"}


# ----------------------------
# INPUT HANDLING
# ----------------------------
def get_yes_no(prompt):
    while True:
        response = input(prompt).strip().lower()
        if response == "y":
            return True
        elif response == "n":
            return False
        else:
            print("Invalid input, please answer y/n")


def resolve_option(flag_value, prompt_text):
    if flag_value is None:
        return get_yes_no(prompt_text)
    return flag_value


# ----------------------------
# FIND TARGET FILES
# ----------------------------
# def find_targets_with_rules(root_dir, skip_dirs, delete_tex):
#     root = Path(root_dir).resolve()
#     matches = []

#     for path in root.rglob("*"):

#         # IMPORTANT: skip directories themselves
#         if path.is_dir():
#             continue

#         # skip anything inside forbidden directories
#         if any(part in skip_dirs for part in path.parts):
#             continue

#         # skip tex if flag is off
#         if not delete_tex and path.suffix.lower() == ".tex":
#             continue

#         # collect target extensions
#         if path.suffix.lower() in TARGET_EXTENSIONS:
#             matches.append(path)

#     return matches

def find_targets_with_rules(root_dir, skip_dirs, delete_tex):
    root = Path(root_dir).resolve()
    matches = []

    for path in root.rglob("*"):

        # match test semantics (substring-based skip)
        if any(skip in str(path) for skip in skip_dirs):
            continue

        if not path.is_file():
            continue

        if not delete_tex and path.suffix.lower() == ".tex":
            continue

        if path.suffix.lower() in TARGET_EXTENSIONS:
            matches.append(path)

    return matches


# ----------------------------
# DELETE FILES
# ----------------------------
def delete_files(files, log_file):
    deleted = []

    log_file = Path(log_file).resolve()
    log_file.parent.mkdir(parents=True, exist_ok=True)

    with open(log_file, "w") as f:
        f.write(f"Deletion log - {datetime.now()}\n\n")

        for file in files:
            try:
                file.unlink()
                deleted.append(file)
                f.write(f"DELETED: {file}\n")
            except Exception as e:
                f.write(f"FAILED: {file} -> {e}\n")

    return deleted


# ----------------------------
# SNAPSHOT CLEANUP
# ----------------------------
def cleanup_snapshots(snapshot_dir: Path):
    if not snapshot_dir.exists():
        return 0

    count = 0

    for folder in snapshot_dir.iterdir():
        if folder.is_dir():
            try:
                import shutil
                shutil.rmtree(folder)
                count += 1
            except Exception as e:
                print(f"[ERROR] Failed to delete snapshot {folder}: {e}")

    return count


# ----------------------------
# MAIN
# ----------------------------
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("folder", help="Root folder to scan")
    parser.add_argument("--confirm", action="store_true")

    parser.add_argument("--delete-tex", dest="delete_tex", action="store_true")
    parser.add_argument("--keep-tex", dest="delete_tex", action="store_false")

    parser.add_argument("--delete-db", dest="delete_db", action="store_true")
    parser.add_argument("--keep-db", dest="delete_db", action="store_false")

    parser.add_argument("--delete-snapshots", dest="delete_snapshots", action="store_true")
    parser.add_argument("--keep-snapshots", dest="delete_snapshots", action="store_false")

    parser.set_defaults(
        delete_tex=None,
        delete_db=None,
        delete_snapshots=None
    )

    args = parser.parse_args()
    root = Path(args.folder).resolve()

    skip_dirs = set(SKIP_DIRS)

    # ----------------------------
    # SNAPSHOTS
    # ----------------------------
    snapshot_dir = root / "snapshots"

    if snapshot_dir.exists():
        delete_snapshots = resolve_option(
            args.delete_snapshots,
            "\n[QUESTION] Delete ALL snapshots? (y/n): "
        )

        if delete_snapshots:
            print("[INFO] Deleting snapshots")
            deleted_snapshots = cleanup_snapshots(snapshot_dir)
            print(f"[INFO] Deleted {deleted_snapshots} snapshot folders")
        else:
            print("[INFO] Preserving snapshots")
            skip_dirs.add("snapshots")

    # ----------------------------
    # TEX FILES
    # ----------------------------
    delete_tex = resolve_option(
        args.delete_tex,
        "\n[QUESTION] Delete .tex files? (y/n): "
    )

    # ----------------------------
    # DATABASE
    # ----------------------------
    db_path = root / "databases" / "jitter.db"

    if db_path.exists():
        delete_db = resolve_option(
            args.delete_db,
            "\n[QUESTION] Delete database file? (y/n): "
        )

        if delete_db:
            try:
                db_path.unlink()
                print("[INFO] Deleted database")
            except Exception as e:
                print(f"[ERROR] Failed to delete database: {e}")

    # ----------------------------
    # FIND TARGET FILES
    # ----------------------------
    targets = find_targets_with_rules(root, skip_dirs, delete_tex)

    print("\n==============================")
    print(f"Scanning: {root}")
    print(f"Found {len(targets)} target files")
    print("==============================\n")

    for t in targets[:20]:
        print(t)

    if len(targets) > 20:
        print(f"... and {len(targets) - 20} more")

    if not args.confirm:
        print("\n[DRY RUN] No files deleted.")
        return

    log_file = root / "deletion_log.txt"
    deleted = delete_files(targets, log_file)

    print("\n==============================")
    print(f"Deleted {len(deleted)} files")
    print(f"Log saved to: {log_file}")
    print("==============================")


if __name__ == "__main__":
    main()