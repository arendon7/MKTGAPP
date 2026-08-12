import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

class WorkflowHygieneTests(unittest.TestCase):
    def test_only_canonical_product_workflows_are_tracked(self):
        names={p.name for p in (ROOT/'.github/workflows').glob('*.yml')}
        self.assertEqual(names,{'ci.yml','full-mac-app.yml','persistent-release.yml'})

if __name__=='__main__':unittest.main()
