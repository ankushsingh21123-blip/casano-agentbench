import os
import sys
from pathlib import Path

# Ensure `app` package is importable when pytest runs from backend/.
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
