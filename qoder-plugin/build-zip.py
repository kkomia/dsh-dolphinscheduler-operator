#!/usr/bin/env python3
"""把 Qoder 插件打成 zip。

用法：
    python qoder-plugin/build-zip.py

产物：qoder-plugin/dolphinscheduler-operator-<version>.zip
zip 根层直接是 .qoder-plugin/plugin.json，这是 Qoder 的打包约定（拖进聊天窗口即可安装）。
"""
from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLUGIN_DIR = HERE / "dolphinscheduler-operator"

SKIP_DIRS = {"__MACOSX", ".git", "node_modules", "__pycache__"}
SKIP_NAMES = {".DS_Store", "Thumbs.db", "settings.local.json", "desktop.ini"}


def should_skip(rel: Path) -> bool:
    return any(part in SKIP_DIRS for part in rel.parts) or rel.name in SKIP_NAMES


def main() -> int:
    manifest = PLUGIN_DIR / ".qoder-plugin" / "plugin.json"
    if not manifest.is_file():
        print(f"找不到插件清单：{manifest}", file=sys.stderr)
        return 1

    meta = json.loads(manifest.read_text(encoding="utf-8"))
    name = str(meta.get("name", ""))
    version = str(meta.get("version", "0.0.0"))
    if name and name != PLUGIN_DIR.name:
        print(f"警告：manifest name={name!r} 与目录名 {PLUGIN_DIR.name!r} 不一致", file=sys.stderr)

    files = sorted(
        path
        for path in PLUGIN_DIR.rglob("*")
        if path.is_file() and not should_skip(path.relative_to(PLUGIN_DIR))
    )
    if not files:
        print("插件目录是空的", file=sys.stderr)
        return 1

    out = HERE / f"dolphinscheduler-operator-{version}.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in files:
            zf.write(path, path.relative_to(PLUGIN_DIR).as_posix())

    print(f"{out.name}  {out.stat().st_size:,} bytes  {len(files)} files")
    for path in files:
        print("  " + path.relative_to(PLUGIN_DIR).as_posix())
    return 0


if __name__ == "__main__":
    sys.exit(main())
