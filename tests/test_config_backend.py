"""Guard: the lite/pro deploy path must NOT eagerly import torch.

The 2c2g deploy target runs the lite tier with no torch in the venv. A red-team
measured that ``build_profile()`` -> ``get_backend()`` -> ``import torch`` balloons
RSS by ~458 MB when torch IS present, for a backend result lite/pro discard. These
tests pin that lite/pro determine their backend without importing torch, while the
chosen backend strings stay byte-identical to the legacy behaviour.
"""

from __future__ import annotations

import subprocess
import sys

from sylanne_core.config import build_profile


def test_backend_strings_unchanged() -> None:
    # Behaviour preserved: lite/pro -> numpy when numpy is available, max -> detected.
    assert build_profile("lite").backend in ("numpy", "python")
    assert build_profile("pro").backend in ("numpy", "python")
    # forced backend still honoured, and still normalised on lite/pro.
    assert build_profile("lite", force_backend="torch").backend == "numpy"
    assert build_profile("pro", force_backend="cupy").backend == "numpy"


def test_lite_pro_do_not_import_torch() -> None:
    # In a FRESH interpreter, building the lite/pro profiles must not pull torch into
    # sys.modules (the deploy-path RAM footgun). Run in a subprocess so a torch already
    # imported by the test session can't mask the regression.
    code = (
        "import sys;"
        "from sylanne_core.config import build_profile;"
        "build_profile('lite'); build_profile('pro');"
        "assert 'torch' not in sys.modules, 'lite/pro eagerly imported torch';"
        "print('OK')"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=120
    )
    assert proc.returncode == 0, (proc.stdout, proc.stderr)
    assert "OK" in proc.stdout
