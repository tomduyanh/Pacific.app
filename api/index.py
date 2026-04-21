from pathlib import Path
import sys


# Ensure repository root is importable in Vercel serverless runtime.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.main import app
