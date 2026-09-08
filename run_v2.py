from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path


def load_v2_main():
    package_root = Path(__file__).resolve().parent
    specification = importlib.util.spec_from_file_location(
        "v2",
        package_root / "__init__.py",
        submodule_search_locations=[str(package_root)],
    )
    if specification is None or specification.loader is None:
        raise RuntimeError("无法加载 V2 程序")
    package = importlib.util.module_from_spec(specification)
    sys.modules["v2"] = package
    specification.loader.exec_module(package)
    return importlib.import_module("v2.__main__").main


if __name__ == "__main__":
    raise SystemExit(load_v2_main()())
