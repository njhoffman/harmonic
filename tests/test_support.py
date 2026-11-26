import os
import unittest
from unittest.mock import patch

from support import REQUIRE_ENV, requires


class RequiresTests(unittest.TestCase):
    def run_case(self, case):
        result = unittest.TestResult()
        unittest.defaultTestLoader.loadTestsFromTestCase(case).run(result)
        return result

    def make(self, decorate_class):
        decorator = requires(False, "tool X is missing")
        if decorate_class:
            @decorator
            class Case(unittest.TestCase):
                def test_it(self):
                    pass
            return Case

        class Case(unittest.TestCase):
            @decorator
            def test_it(self):
                pass
        return Case

    def test_missing_integration_skips_by_default(self):
        with patch.dict(os.environ, {REQUIRE_ENV: "0"}):
            for decorate_class in (False, True):
                result = self.run_case(self.make(decorate_class))
                self.assertEqual(len(result.skipped), 1)
                self.assertTrue(result.wasSuccessful())

    def test_missing_integration_fails_when_required(self):
        with patch.dict(os.environ, {REQUIRE_ENV: "1"}):
            for decorate_class in (False, True):
                result = self.run_case(self.make(decorate_class))
                self.assertFalse(result.wasSuccessful())
                self.assertFalse(result.skipped)
                problems = result.failures + result.errors
                self.assertIn("tool X is missing", problems[0][1])

    def test_present_integration_runs_when_required(self):
        with patch.dict(os.environ, {REQUIRE_ENV: "1"}):
            @requires(True, "unused")
            class Case(unittest.TestCase):
                def test_it(self):
                    pass
            result = self.run_case(Case)
            self.assertEqual((result.testsRun, len(result.skipped)), (1, 0))
            self.assertTrue(result.wasSuccessful())


if __name__ == "__main__":
    unittest.main()
