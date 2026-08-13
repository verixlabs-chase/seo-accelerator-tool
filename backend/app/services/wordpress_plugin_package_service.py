from __future__ import annotations

import hashlib
import io
import re
from dataclasses import dataclass
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


WORDPRESS_PLUGIN_DIRECTORY = "lsos-execution-plugin"
WORDPRESS_PLUGIN_ENTRYPOINT = "lsos-execution-plugin.php"
_PACKAGE_TIMESTAMP = (2020, 1, 1, 0, 0, 0)
_ALLOWED_SUFFIXES = {
    ".css",
    ".gif",
    ".jpeg",
    ".jpg",
    ".js",
    ".json",
    ".md",
    ".mo",
    ".php",
    ".png",
    ".po",
    ".pot",
    ".svg",
    ".txt",
    ".webp",
}
_BLOCKED_NAMES = {
    ".env",
    "wp-config.php",
    "credentials.json",
    "secrets.json",
}


class WordPressPluginPackageError(RuntimeError):
    pass


@dataclass(frozen=True)
class WordPressPluginPackage:
    content: bytes
    filename: str
    version: str
    sha256: str
    size_bytes: int
    file_count: int

    def metadata(self) -> dict[str, str | int]:
        return {
            "filename": self.filename,
            "version": self.version,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
            "file_count": self.file_count,
        }


def build_wordpress_plugin_package() -> WordPressPluginPackage:
    plugin_root = _plugin_root()
    files = _package_files(plugin_root)
    version = _plugin_version(plugin_root / WORDPRESS_PLUGIN_ENTRYPOINT)
    buffer = io.BytesIO()

    with ZipFile(buffer, mode="w", compression=ZIP_DEFLATED, compresslevel=9) as archive:
        for source_path in files:
            relative_path = source_path.relative_to(plugin_root).as_posix()
            archive_path = f"{WORDPRESS_PLUGIN_DIRECTORY}/{relative_path}"
            info = ZipInfo(archive_path, date_time=_PACKAGE_TIMESTAMP)
            info.compress_type = ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = (0o100644 & 0xFFFF) << 16
            archive.writestr(info, source_path.read_bytes(), compress_type=ZIP_DEFLATED, compresslevel=9)

    content = buffer.getvalue()
    return WordPressPluginPackage(
        content=content,
        filename=f"insightos-wordpress-{version}.zip",
        version=version,
        sha256=hashlib.sha256(content).hexdigest(),
        size_bytes=len(content),
        file_count=len(files),
    )


def get_wordpress_plugin_package_metadata() -> dict[str, str | int]:
    return build_wordpress_plugin_package().metadata()


def _plugin_root() -> Path:
    root = (
        Path(__file__).resolve().parents[2]
        / "wordpress_execution_plugin"
        / WORDPRESS_PLUGIN_DIRECTORY
    )
    if not root.is_dir():
        raise WordPressPluginPackageError("The WordPress plugin release files are unavailable.")
    return root


def _package_files(plugin_root: Path) -> list[Path]:
    files: list[Path] = []
    for path in sorted(plugin_root.rglob("*"), key=lambda item: item.as_posix().lower()):
        if not path.is_file() or path.is_symlink():
            continue
        relative_parts = path.relative_to(plugin_root).parts
        if any(part.startswith(".") for part in relative_parts):
            continue
        if path.name.lower() in _BLOCKED_NAMES:
            raise WordPressPluginPackageError(
                f"Blocked file found in the WordPress plugin release: {path.name}"
            )
        if path.suffix.lower() not in _ALLOWED_SUFFIXES:
            raise WordPressPluginPackageError(
                f"Unsupported file found in the WordPress plugin release: {path.name}"
            )
        files.append(path)

    entrypoint = plugin_root / WORDPRESS_PLUGIN_ENTRYPOINT
    if entrypoint not in files:
        raise WordPressPluginPackageError("The WordPress plugin entry point is missing.")
    return files


def _plugin_version(entrypoint: Path) -> str:
    source = entrypoint.read_text(encoding="utf-8")
    header_match = re.search(r"^\s*\*\s*Version:\s*([0-9]+(?:\.[0-9]+){2})\s*$", source, re.MULTILINE)
    constant_match = re.search(
        r"define\(['\"]LSOS_EXECUTION_PLUGIN_VERSION['\"],\s*['\"]([^'\"]+)['\"]\)",
        source,
    )
    if not header_match or not constant_match:
        raise WordPressPluginPackageError("The WordPress plugin version is missing.")
    if header_match.group(1) != constant_match.group(1):
        raise WordPressPluginPackageError("The WordPress plugin version declarations do not match.")
    return header_match.group(1)
