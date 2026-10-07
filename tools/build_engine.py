"""Adds the in-browser Python the Refresh button runs to a built site.

    python tools/build_engine.py site

Writes site/engine/pyodide/ (Python compiled for the browser, from the
pyodide npm package) and site/engine/lib.zip (jinja2, markupsafe and tzdata,
the only libraries the analysis needs beyond Python itself). The advisor
package, its morning data and refresh.js are written by advisor.bundle.
"""

import io
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path

PYODIDE = "0.29.5"
PYODIDE_FILES = ("pyodide.js", "pyodide.asm.js", "pyodide.asm.wasm", "python_stdlib.zip", "pyodide-lock.json")
# markupsafe ships as source so it runs without its C speedups.
LIBS = ("jinja2==3.1.4", "markupsafe==2.1.5", "tzdata")


def main(site):
    engine = Path(site) / "engine"
    (engine / "pyodide").mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        subprocess.run(["npm", "pack", f"pyodide@{PYODIDE}", "--silent", "--pack-destination", str(tmp)],
                       check=True, stdout=subprocess.DEVNULL)
        with tarfile.open(next(tmp.glob("pyodide-*.tgz"))) as tar:
            for name in PYODIDE_FILES:
                (engine / "pyodide" / name).write_bytes(tar.extractfile(f"package/{name}").read())

        subprocess.run([sys.executable, "-m", "pip", "download", "--quiet", "--no-deps", "--no-binary", "markupsafe",
                        "-d", str(tmp / "dl"), *LIBS], check=True)
        with zipfile.ZipFile(engine / "lib.zip", "w", zipfile.ZIP_DEFLATED) as out:
            for wheel in (tmp / "dl").glob("*.whl"):
                with zipfile.ZipFile(wheel) as z:
                    for name in z.namelist():
                        if ".dist-info/" not in name:
                            out.writestr(name, z.read(name))
            sdist = next((tmp / "dl").glob("[Mm]arkup[Ss]afe-*.tar.gz"))
            with tarfile.open(sdist) as tar:
                for m in tar.getmembers():
                    parts = Path(m.name).parts
                    if m.isfile() and "markupsafe" in parts and m.name.endswith((".py", ".typed")):
                        out.writestr("/".join(parts[parts.index("markupsafe"):]), tar.extractfile(m).read())
    size = sum(f.stat().st_size for f in engine.rglob("*") if f.is_file())
    print(f"engine: {size / 1e6:.1f} MB in {engine}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "site")
