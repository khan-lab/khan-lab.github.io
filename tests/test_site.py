from pathlib import Path
import sys
import unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from content import validate

class SiteTest(unittest.TestCase):
    def test_authored_content(self):
        validate(ROOT)
