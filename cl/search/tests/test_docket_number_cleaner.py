from dataclasses import dataclass

from cl.search.docket_number_cleaner import (
    clean_docket_number_raw,
    is_generic,
    prelim_clean_F,
    regex_clean_F,
)
from cl.tests.cases import TestCase


@dataclass
class CleanDocketNumberTestCase:
    docket_id: str
    docket_number_raw: str
    court: str
    expected: tuple


class TestCleanDocketNumberRaw(TestCase):
    def test_is_generic(self):
        test_cases = [
            ("12-1234-ag", "F", True),
            ("12-1234P", "F", True),
            ("12A1234", "F", True),
            ("A-1234", "F", True),
            ("12-1234", "F", True),
            ("1234", "F", True),
            ("notadocket", "F", False),
            ("12-1234, 1234", "F", False),
            ("12-1234", "not_a_court", False),
        ]
        for input_str, court_map, expected in test_cases:
            assert is_generic(input_str, court_map) == expected, (
                f"Failed for input_str: {input_str}"
            )

    def test_prelim_clean_F(self):
        test_cases = [
            ("No. 12-1234-ag", "12-1234-ag"),
            ("Case No. 12 ‒ 1234", "12-1234"),
            ("Docket NO. 12-1234P", "12-1234P"),
            ("Case 12a1234", "12a1234"),
            (" 12——1234 ", "12-1234"),
            ("12-1234.", "12-1234"),
            ("12‐1234_1", "12-1234"),
            ("-12―1234-", "12-1234"),
            ("No.   12 -- 1234   ", "12-1234"),
            ("1234_1", "1234"),
        ]
        for input_str, expected in test_cases:
            assert prelim_clean_F(input_str) == expected, (
                f"Failed for input_str: {input_str}, {prelim_clean_F(input_str)}"
            )

    def test_regex_clean_F(self):
        test_cases = [
            ("12-1234-ag", "12-1234-AG"),
            ("12-1234P", "12-1234P"),
            ("12m1234", "12M1234"),
            ("a-1234", "A-1234"),
            ("12-1234", "12-1234"),
            ("1234", "1234"),
            ("No dockets here", ""),
        ]
        for input_str, expected in test_cases:
            assert regex_clean_F(input_str) == expected, (
                f"Failed for input_str: {input_str}"
            )

    def test_clean_docket_number_raw(self):
        test_cases: list[CleanDocketNumberTestCase] = [
            CleanDocketNumberTestCase(
                docket_id="d1",
                docket_number_raw="No. 12-1234-ag",
                court="ca1",
                expected=("12-1234-AG", None),
            ),
            CleanDocketNumberTestCase(
                docket_id="d2",
                docket_number_raw="Docket Nos. 12-1234-ag and 13-5678-pr",
                court="ca1",
                expected=("Docket Nos. 12-1234-ag and 13-5678-pr", "d2"),
            ),
            CleanDocketNumberTestCase(
                docket_id="d3",
                docket_number_raw="Docket No. 12-1234-ag",
                court="unknowncourt",
                expected=None,
            ),
            CleanDocketNumberTestCase(
                docket_id="d4",
                docket_number_raw="",
                court="scotus",
                expected=None,
            ),
        ]

        for test_case in test_cases:
            with self.subTest(test_case=test_case):
                result = clean_docket_number_raw(
                    test_case.docket_id,
                    test_case.docket_number_raw,
                    test_case.court,
                )
                self.assertEqual(
                    result, test_case.expected, f"Failed for case: {test_case}"
                )
