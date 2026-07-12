import os
import sys

# Repo root (for `api.*` / `datapipeline.*` imports) and the gdelt pipeline
# dir (its stages are standalone scripts, not a package).
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "datapipeline", "gdelt_and_gkg"))
