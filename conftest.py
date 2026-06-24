from __future__ import annotations

import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT_STR = str(PROJECT_ROOT)

if PROJECT_ROOT_STR not in sys.path:
    sys.path.insert(0, PROJECT_ROOT_STR)

existing_pythonpath = os.environ.get("PYTHONPATH")
if existing_pythonpath:
    paths = existing_pythonpath.split(os.pathsep)
    if PROJECT_ROOT_STR not in paths:
        os.environ["PYTHONPATH"] = os.pathsep.join([PROJECT_ROOT_STR, *paths])
else:
    os.environ["PYTHONPATH"] = PROJECT_ROOT_STR
