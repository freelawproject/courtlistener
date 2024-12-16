from unittest.mock import MagicMock, patch

from cl.api.utils import invert_user_logs
from cl.tests.cases import SimpleTestCase

USER_1_ID = 1
USER_2_ID = 2


class TestApiUsage(SimpleTestCase):
    def setUp(self):
        self.start_date = "2023-01-01"
        self.end_date = "2023-01-01"
        self.expected_dates = ["2023-01-01"]
        self.v3_results = [(USER_1_ID, 10), (USER_2_ID, 20)]
        self.v4_results = [(USER_1_ID, 15), (USER_2_ID, 25)]

    @patch("cl.api.utils.get_redis_interface")
    def test_invert_user_logs_shows_v4_logs(self, mock_get_redis_interface):
        mock_redis = MagicMock()
        mock_pipeline = MagicMock()
        mock_get_redis_interface.return_value = mock_redis
        mock_redis.pipeline.return_value = mock_pipeline

        mock_pipeline.execute.return_value = [
            self.v3_results,
            self.v4_results,
        ]

        results = invert_user_logs(
            self.start_date, self.end_date, add_usernames=False
        )

        for date in self.expected_dates:
            mock_pipeline.zrange.assert_any_call(
                f"api:v3.user.d:{date}.counts", 0, -1, withscores=True
            )
            mock_pipeline.zrange.assert_any_call(
                f"api:v4.user.d:{date}.counts", 0, -1, withscores=True
            )

        self.assertIn(USER_1_ID, results)
        self.assertIn(USER_2_ID, results)

        self.assertEqual(results[USER_1_ID]["2023-01-01"], 25)
        self.assertEqual(results[USER_1_ID]["total"], 25)
        self.assertEqual(results[USER_2_ID]["2023-01-01"], 45)
        self.assertEqual(results[USER_2_ID]["total"], 45)
