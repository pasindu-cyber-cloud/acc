"""One-shot build helper for ProcAI Windows packaging.

Runs PyInstaller against ``procai.spec`` and (optionally) compiles the Inno
Setup installer if ISCC is available on PATH. Run from the repository root or
the installer directory:

    python installer/build.py            # build the exe only
    python installer/build.py --installer  # also build the setup installer

This script deliberately does NOT sign binaries (signing requires your own
certificate and is documented in INSTALLER.md) and never disables any security
control.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INSTALLER_DIR = ROOT / "installer"
SPEC = INSTALLER_DIR / "procai.spec"


def run(cmd: list[str], cwd: Path) -> None:
    print(f"\n>>> {' '.join(cmd)}  (cwd={cwd})")
    subprocess.run(cmd, cwd=str(cwd), check=True)


def build_exe() -> None:
    if shutil.which("pyinstaller") is None:
        raise SystemExit("PyInstaller not found. Install dev requirements: "
                         "pip install -r requirements-dev.txt")
    run(["pyinstaller", str(SPEC), "--noconfirm", "--clean"], cwd=ROOT)
    print(f"\nBuilt: {ROOT / 'dist' / 'ProcAI' / 'ProcAI.exe'}")


def build_installer() -> None:
    iscc = shutil.which("ISCC") or shutil.which("iscc")
    if iscc is None:
        print("Inno Setup (ISCC) not found on PATH; skipping installer build.")
        print("Install from https://jrsoftware.org/isinfo.php and re-run with --installer.")
        return
    run([iscc, str(INSTALLER_DIR / "procai_installer.iss")], cwd=INSTALLER_DIR)
    print("\nInstaller written to installer/Output/ (see Inno Setup output).")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build ProcAI for Windows.")
    parser.add_argument("--installer", action="store_true",
                        help="Also compile the Inno Setup installer.")
    args = parser.parse_args()

    if not sys.platform.startswith("win"):
        print("WARNING: ProcAI targets Windows. Building on a non-Windows OS will "
              "produce a non-Windows binary.")
    build_exe()
    if args.installer:
        build_installer()
    return 0


if __name__ == "__main__":
    sys.exit(main())
