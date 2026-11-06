import unittest
from tools.acceptance import summarize_cases


class AcceptanceReportTests(unittest.TestCase):
    def test_only_ui_deferred_can_be_backend_complete(self):
        value=summarize_cases([{"id":"T01","status":"PASS"},{"id":"E08-UI","status":"SKIP"}],True)
        self.assertEqual(value["status"],"PASS_WITH_UI_DEFERRED")
        self.assertTrue(value["backend_passed"])

    def test_skipped_live_fault_is_partial_not_pass(self):
        value=summarize_cases([{"id":"T01","status":"PASS"},{"id":"E02","status":"SKIP"}],True)
        self.assertEqual(value["status"],"PARTIAL")
        self.assertFalse(value["backend_passed"])

    def test_failed_precheck_or_any_failed_case_is_failure(self):
        for ready,cases in [(False,[]),(True,[{"id":"T03","status":"FAIL"}])]:
            self.assertEqual(summarize_cases(cases,ready)["status"],"FAIL")


if __name__=="__main__":
    unittest.main()
