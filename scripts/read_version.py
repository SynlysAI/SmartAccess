"""输出 SmartAccess 当前版本号。"""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    """从源码目录读取版本号并打印。"""

    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "src"))
    from smartaccess import __version__

    print(__version__)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
