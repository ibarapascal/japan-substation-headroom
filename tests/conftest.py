"""Test setup: make the repository root importable and expose the fixture directory."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
FIXTURES = os.path.join(ROOT, "tests", "fixtures")
