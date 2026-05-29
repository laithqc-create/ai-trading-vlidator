#!/usr/bin/env python3
"""
scripts/build_extension.py
Package the browser extension into a distributable zip file.

Usage:
    python scripts/build_extension.py
    python scripts/build_extension.py --out dist/extension_v2.0.0.zip
"""
import argparse
import json
import os
import shutil
import sys
import zipfile
from pathlib import Path

REPO_ROOT  = Path(__file__).parent.parent
EXT_DIR    = REPO_ROOT / "extension"
DIST_DIR   = REPO_ROOT / "dist"
STATIC_DIR = REPO_ROOT / "miniapp" / "static"  # served by /api/download/

# Files to include from extension/
INCLUDE_FILES = [
    "manifest.json",
    "background.js",
    "content.js",
    "sidepanel.html",
    "sidepanel.js",
]
INCLUDE_DIRS = [
    "icons",
]


def build(out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Read version from manifest
    with open(EXT_DIR / "manifest.json") as f:
        manifest = json.load(f)
    version = manifest.get("version", "0.0.0")
    print(f"Building extension v{version} → {out_path}")

    with zipfile.ZipFile(out_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for filename in INCLUDE_FILES:
            src = EXT_DIR / filename
            if src.exists():
                zf.write(src, filename)
                print(f"  + {filename}")
            else:
                print(f"  ! MISSING: {filename}", file=sys.stderr)

        for dirname in INCLUDE_DIRS:
            src_dir = EXT_DIR / dirname
            if src_dir.is_dir():
                for fpath in sorted(src_dir.rglob("*")):
                    if fpath.is_file():
                        arc_name = fpath.relative_to(EXT_DIR)
                        zf.write(fpath, arc_name)
                        print(f"  + {arc_name}")
            else:
                print(f"  ! MISSING dir: {dirname}", file=sys.stderr)

    size_kb = out_path.stat().st_size / 1024
    print(f"\n✓ Built {out_path.name} ({size_kb:.1f} KB)")

    # Copy to miniapp/static/ so the download endpoint can serve it
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    dest = STATIC_DIR / "extension.zip"
    shutil.copy2(out_path, dest)
    print(f"✓ Copied to {dest.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build the ATV browser extension zip.")
    parser.add_argument("--out", default=str(DIST_DIR / "extension.zip"), help="Output path")
    args = parser.parse_args()
    build(Path(args.out))
