"""Fail unless every package an image installed is pinned by the constraints file.

    python scripts/check_constraints.py <image-freeze.txt> infra/constraints/python.txt

`pip install -c` only pins what the file lists. A package that reaches an image
without being listed resolves to whatever is newest at build time, which is the
exact failure the file exists to prevent: on 23 September 2026 an unchanged
commit built a different, broken voice image because torch was not pinned.

So this reads what an image *actually* installed (its `pip freeze`) and checks
each package against the file. It reports two kinds of drift:

- **unpinned**: installed, but not in the constraints file at all;
- **mismatched**: in the file, but installed at a different version.

Either fails the check. Names are compared the way pip compares them (PEP 503:
case, `-`, `_` and `.` are equivalent), so `typing_extensions` and
`typing-extensions` are the same package.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


def _canonical(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _pins(path: Path) -> dict[str, str]:
    """``name==version`` lines, ignoring comments and blank lines."""
    pins: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        name, sep, version = line.partition("==")
        if not sep:
            raise SystemExit(f"{path}: not an exact pin: {raw!r}")
        pins[_canonical(name)] = version.strip()
    return pins


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__)
        return 2
    installed = _pins(Path(argv[1]))
    constraints = _pins(Path(argv[2]))

    unpinned = sorted(name for name in installed if name not in constraints)
    mismatched = sorted(
        f"{name}: installed {installed[name]}, pinned {constraints[name]}"
        for name in installed
        if name in constraints and installed[name] != constraints[name]
    )

    for name in unpinned:
        print(f"unpinned: {name}=={installed[name]}")
    for line in mismatched:
        print(f"mismatched: {line}")
    if unpinned or mismatched:
        print(
            f"\n{len(unpinned)} unpinned and {len(mismatched)} mismatched of "
            f"{len(installed)} installed packages. Regenerate the constraints file "
            "from this image's pip freeze (see its header)."
        )
        return 1
    print(f"all {len(installed)} installed packages are pinned by {argv[2]}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
