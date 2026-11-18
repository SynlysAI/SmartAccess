"""把打包目录压成带 SmartAccess 顶层目录的发布压缩包。"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path


def package_release(source: Path, output: Path) -> int:
    """将打包目录压缩为 SmartAccess-vX.Y.Z.zip。

    Args:
        source: Nuitka 输出目录，例如 run_desktop.dist。
        output: 目标 zip 路径。

    Returns:
        写入压缩包的文件数量。
    """

    files = [path for path in source.rglob("*") if path.is_file()]
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(
        output,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=6,
    ) as archive:
        for path in files:
            archive.write(path, Path("SmartAccess") / path.relative_to(source))
    return len(files)


def main() -> int:
    """从命令行读取源目录和输出路径并打包。"""

    if len(sys.argv) != 3:
        print("usage: package_release.py SOURCE OUTPUT", file=sys.stderr)
        return 1
    source = Path(sys.argv[1])
    output = Path(sys.argv[2])
    if not source.is_dir():
        print(f"source not found: {source}", file=sys.stderr)
        return 1
    count = package_release(source, output)
    print(f"{count} files -> {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
