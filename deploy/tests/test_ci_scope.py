"""Check which jobs run for each kind of repository change."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import release_scope


SCOPE_KEYS = ('backend', 'frontend', 'dependencies')
CASES = (
    # Single-file changes from EN-01.
    (('backend/tests/test_architecture.py',), (True, False, False)),
    (('backend/scripts/export_openapi.py',), (True, True, False)),
    (('backend/openapi.json',), (True, True, False)),
    (('frontend/src/api/generated/types.gen.ts',), (True, True, False)),
    (('backend/evals/retrieval_v3.json',), (True, False, False)),
    (('Makefile',), (True, True, False)),
    (('.github/workflows/delivery.yml',), (True, True, False)),
    (('frontend/src/app/App.tsx',), (False, True, False)),
    (('frontend/vite.config.ts',), (False, True, False)),
    (('backend/src/qunxue_api/main.py',), (True, False, False)),
    (('backend/src/qunxue_api/adapters/research_agent/prompts/memory_extraction.md',), (True, False, False)),
    (('backend/scripts/evaluate_retrieval.py',), (True, False, False)),
    (('backend/.python-version',), (True, False, False)),
    (('frontend/scripts/check-module-boundaries.mjs',), (True, True, False)),
    (('frontend/package.json',), (True, True, False)),
    (('frontend/package-lock.json',), (True, True, False)),
    (('backend/pyproject.toml',), (True, False, True)),
    (('backend/uv.lock',), (True, False, True)),
    (('deploy/release_scope.py',), (True, True, False)),
    (('tools/new-check.py',), (True, True, False)),
    (('frontend/new-tool.config.ts',), (True, True, False)),
    (('README.md', 'docs/ARCHITECTURE.md', 'backend/docs/frontier.md'), (False, False, False)),
    (('frontend/src/assets/classroom/README.md', 'frontend/vercel.json'), (False, False, False)),
    (('frontend/src/app/App.tsx', 'tools/new-check.py'), (True, True, False)),
    (('Makefile', 'backend/uv.lock'), (True, True, True)),
    ((), (False, False, False)),
)


class CiScopeTests(unittest.TestCase):
    def test_changed_paths_select_the_expected_jobs(self):
        for paths, expected in CASES:
            with self.subTest(paths=paths):
                self.assertEqual(release_scope.classify_ci(paths), dict(zip(SCOPE_KEYS, expected)))
