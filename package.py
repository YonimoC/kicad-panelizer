"""Build a KiCad PCM-installable ZIP and repository metadata."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path


PLUGIN_ID = "kicad-panelizer"
ROOT_FILES = ("metadata.json",)
PACK_DIRS = ("plugins", "resources")
SKIP_DIRS = {"__pycache__", ".git", "_dev", "tests"}


def load_metadata(root: Path) -> dict:
    return json.loads((root / "metadata.json").read_text(encoding="utf-8-sig"))


def iter_entries(root: Path):
    for name in ROOT_FILES:
        path = root / name
        if path.is_file():
            yield name, path

    for directory in PACK_DIRS:
        base = root / directory
        if not base.is_dir():
            continue
        for current, subdirs, files in os.walk(base):
            subdirs[:] = sorted(
                name for name in subdirs if name not in SKIP_DIRS and name != "__pycache__"
            )
            for name in sorted(files):
                if name.endswith((".pyc", ".bak", ".zip")):
                    continue
                path = Path(current) / name
                yield path.relative_to(root).as_posix(), path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def install_size(entries: list[tuple[str, Path]]) -> int:
    return sum(path.stat().st_size for _, path in entries)


def build_zip(root: Path, output: Path) -> tuple[str, int, int]:
    entries = list(iter_entries(root))
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, path in entries:
            archive.write(path, name)
    return sha256_file(output), output.stat().st_size, install_size(entries)


def package_record(metadata: dict, sha256: str, size: int, extracted_size: int) -> dict:
    data = json.loads(json.dumps(metadata))
    version = data["versions"][0]
    version["download_url"] = (
        "https://github.com/YonimoC/kicad-panelizer/releases/download/"
        f"v{version['version']}/{PLUGIN_ID}.zip"
    )
    version["download_sha256"] = sha256
    version["download_size"] = size
    version["install_size"] = extracted_size
    return {"packages": [data]}


def write_repository_files(root: Path, packages: dict) -> None:
    docs = root / "docs"
    docs.mkdir(exist_ok=True)
    packages_path = docs / "packages.json"
    packages_path.write_text(
        json.dumps(packages, ensure_ascii=False, indent=4) + "\n", encoding="utf-8"
    )

    timestamp = int(time.time())
    utc = datetime.fromtimestamp(timestamp, timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    repository = {
        "$schema": "https://go.kicad.org/pcm/schemas/v2",
        "name": "YonimoC KiCad Addons",
        "maintainer": {
            "name": "LWH",
            "contact": {"web": "https://github.com/YonimoC"},
        },
        "schema_version": 2,
        "packages": {
            "url": "https://raw.githubusercontent.com/YonimoC/kicad-panelizer/main/docs/packages.json",
            "sha256": sha256_file(packages_path),
            "update_timestamp": timestamp,
            "update_time_utc": utc,
        },
    }
    (root / "repository.json").write_text(
        json.dumps(repository, ensure_ascii=False, indent=4) + "\n", encoding="utf-8"
    )


def install_to_cache(zip_path: Path) -> None:
    for version in ("8.0", "9.0", "10.0", "11.0"):
        if sys.platform == "win32":
            cache = Path.home() / "AppData" / "Local" / "KiCad" / version / "pcm_cache"
        elif sys.platform == "darwin":
            cache = Path.home() / "Library" / "Caches" / "KiCad" / version / "pcm_cache"
        else:
            cache = Path.home() / ".cache" / "kicad" / version / "pcm_cache"
        if cache.parent.parent.exists():
            cache.mkdir(parents=True, exist_ok=True)
            shutil.copy2(zip_path, cache / zip_path.name)
            print(f"  copied to {cache / zip_path.name}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the KiCad Panelizer PCM package")
    parser.add_argument("--install", action="store_true", help="copy ZIP into local PCM cache")
    args = parser.parse_args()

    root = Path(__file__).resolve().parent
    metadata = load_metadata(root)
    version = metadata["versions"][0]["version"]
    output = root / "dist" / f"{PLUGIN_ID}-{version}.zip"
    release_copy = root / "dist" / f"{PLUGIN_ID}.zip"

    sha256, size, extracted_size = build_zip(root, output)
    shutil.copy2(output, release_copy)
    packages = package_record(metadata, sha256, size, extracted_size)
    write_repository_files(root, packages)

    print(f"built: {output}")
    print(f"release asset: {release_copy}")
    print(f"sha256: {sha256}")
    print(f"download size: {size:,} bytes")
    print(f"install size: {extracted_size:,} bytes")

    if args.install:
        install_to_cache(release_copy)


if __name__ == "__main__":
    main()

