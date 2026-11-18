"""Parse every Mermaid diagram in the repository's Markdown with Mermaid's own CLI.

`mkdocs build --strict` checks links and anchors but never parses a diagram, so a syntax
slip only shows up as a broken figure on the docs site. This renders each file's diagrams
in headless Chromium and fails, naming the file, on the first one Mermaid rejects.

Run with `uv run poe docs-check` (needs Node.js 20+); CI runs it in the Docs build job.
"""

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# Mermaid 11: the major version the docs site (MkDocs Material) renders with.
CLI = "@mermaid-js/mermaid-cli@11.17.1"
ROOT = Path(__file__).resolve().parents[1]
# CI runners (Ubuntu 24.04) refuse Chromium's sandbox to unprivileged users; the input is
# this repository's own Markdown, so running without it is acceptable here.
PUPPETEER_CONFIG = Path(__file__).with_name("puppeteer.json")
_FENCE = "```mermaid"


def files_with_diagrams() -> list[Path]:
    candidates = [*ROOT.glob("*.md"), *(ROOT / "docs").rglob("*.md")]
    return sorted(p for p in candidates if _FENCE in p.read_text(encoding="utf-8"))


def main() -> int:
    npx = shutil.which("npx")
    if npx is None:
        print("npx not found: install Node.js 20 or newer", file=sys.stderr)
        return 2
    files = files_with_diagrams()
    failed: list[str] = []
    with tempfile.TemporaryDirectory() as out:
        for index, path in enumerate(files):
            diagrams = path.read_text(encoding="utf-8").count(_FENCE)
            result = subprocess.run(  # noqa: S603 — fixed command; the input is our own docs
                [
                    npx,
                    "--yes",
                    CLI,
                    "--input",
                    str(path),
                    "--output",
                    str(Path(out) / f"{index}.md"),
                    "--puppeteerConfigFile",
                    str(PUPPETEER_CONFIG),
                    "--quiet",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            name = path.relative_to(ROOT).as_posix()
            if result.returncode == 0:
                print(f"ok    {name} ({diagrams})")
            else:
                failed.append(name)
                print(f"FAIL  {name}\n{result.stderr.strip() or result.stdout.strip()}")
    total = sum(p.read_text(encoding="utf-8").count(_FENCE) for p in files)
    print(f"{len(files) - len(failed)} of {len(files)} files parse ({total} diagrams)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
