# DQIII8 bin package
import sys
from pathlib import Path

_bin = Path(__file__).parent
for _d in [_bin] + [_bin / s for s in ["core", "agents", "monitoring", "tools", "ui"]]:
    _d_str = str(_d)
    if _d_str not in sys.path:
        sys.path.insert(0, _d_str)
