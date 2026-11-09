from pathlib import Path
import json
import sys
import unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from content import load, validate
from routes import main_page_url

class SiteTest(unittest.TestCase):
    def test_authored_content(self):
        validate(ROOT)

    def test_redirects_cover_changed_urls_from_the_lwt_inventory(self):
        inventory = json.loads((ROOT / 'migration.json').read_text())['url_mappings']
        required = {'/team/': 'people/'}
        for old, target in inventory.items():
            current = main_page_url(target).lstrip('/')
            if old.lstrip('/') != current:
                required[old] = current
        redirects = load(ROOT / 'redirects.yml')
        _, data = validate(ROOT)
        people = {person['id'] for person in data['people']}
        for old, target in required.items():
            with self.subTest(old=old):
                self.assertEqual(redirects.get(old), target)
                if old.startswith('/members/'):
                    self.assertIn(Path(target).stem, people)
