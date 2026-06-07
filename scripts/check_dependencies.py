#!/usr/bin/env python3
"""
Dependency version checker.

Verifies that critical package versions are compatible for fastapi==0.111.0.
Exits with code 1 if any check fails.
"""
import sys


def get_version(package):
    """Get installed version of a package, or 'NOT INSTALLED'."""
    try:
        mod = __import__(package)
        return getattr(mod, "__version__", "unknown")
    except ImportError:
        return "NOT INSTALLED"


def check_starlette_compat():
    """Check starlette version is >=0.37.2 and <0.38.0 for fastapi==0.111.0."""
    starlette_ver = get_version("starlette")
    if starlette_ver == "NOT INSTALLED":
        return False, f"starlette NOT INSTALLED (required: >=0.37.2,<0.38.0 for fastapi==0.111.0)"

    try:
        parts = starlette_ver.split(".")
        major, minor = int(parts[0]), int(parts[1])
        patch = int(parts[2]) if len(parts) > 2 else 0
        version_tuple = (major, minor, patch)
        min_ver = (0, 37, 2)
        max_ver = (0, 38, 0)

        if version_tuple >= min_ver and version_tuple < max_ver:
            return True, starlette_ver
        else:
            return False, f"{starlette_ver} (required: >=0.37.2,<0.38.0)"
    except (ValueError, IndexError):
        return False, f"{starlette_ver} (unparseable, required: >=0.37.2,<0.38.0)"


def main():
    print("=" * 50)
    print("Dependency Version Check")
    print("=" * 50)

    packages = ["fastapi", "starlette", "jinja2", "httpx"]
    all_ok = True

    for pkg in packages:
        ver = get_version(pkg)
        print(f"[OK] {pkg}={ver}")

    ok, msg = check_starlette_compat()
    if ok:
        print(f"[OK] starlette={msg} (compatible)")
        print("[OK] dependency compatibility passed")
    else:
        print(f"[FAIL] starlette version incompatible: {msg}")
        print("Expected: >=0.37.2,<0.38.0 for fastapi==0.111.0")
        print("Please reinstall dependencies:")
        print("  pip install -r requirements.txt --upgrade --force-reinstall")
        print("=" * 50)
        sys.exit(1)

    print("=" * 50)
    return 0


if __name__ == "__main__":
    sys.exit(main())
