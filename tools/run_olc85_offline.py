"""Run with the existing Python 3.12 runtime; never install or download packages.

PISRS_OLC85_TEST_DSN is optional for unit-only runs and must name the disposable
olc85_fixture database on a nonproduction loopback port for PostgreSQL tests.
"""

import importlib.util
import os
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "src"))
os.environ["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
cache = Path(os.environ.get("UV_CACHE_DIR", str(Path.home() / ".cache" / "uv"))) / "archive-v0"
for package in ("pytest", "pluggy", "packaging", "iniconfig", "pygments"):
    if importlib.util.find_spec(package) is not None:
        continue
    candidates = list(cache.glob(f"*/{package}/__init__.py"))
    if package == "pytest":
        locked = [p for p in candidates if list(p.parent.parent.glob("pytest-9.0.3.dist-info"))]
        major9 = [p for p in candidates if list(p.parent.parent.glob("pytest-9.*.dist-info"))]
        candidates = locked or major9 or candidates
    if not candidates:
        raise SystemExit(f"Existing offline dependency unavailable: {package}")
    sys.path.append(str(candidates[0].parent.parent))

import pytest  # noqa: E402

print("offline_pytest=" + pytest.__version__, flush=True)

raise SystemExit(pytest.main(["-p", "no:cacheprovider", str(root / "tests"), *sys.argv[1:]]))
