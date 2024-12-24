from unittest.mock import MagicMock, patch

from cl.api.utils import invert_user_logs
from cl.tests.cases import SimpleTestCase

USER_1_ID = 1
USER_2_ID = 2
USER_3_ID = 3


class TestApiUsage(SimpleTestCase):

    @patch("cl.api.utils.get_redis_interface")
    def test_invert_user_logs_shows_v4_logs_one_date(
        self, mock_get_redis_interface
    ):
        mock_redis = MagicMock()
        mock_pipeline = MagicMock()
        mock_get_redis_interface.return_value = mock_redis
        mock_redis.pipeline.return_value = mock_pipeline

        mock_pipeline.execute.return_value = [
            # v3
            [(USER_1_ID, 10), (USER_2_ID, 20), (USER_3_ID, 30)],
            # v4
            [(USER_1_ID, 15), (USER_2_ID, 25), (USER_3_ID, 35)],
        ]

        results = invert_user_logs(
            "2023-01-01", "2023-01-01", add_usernames=False
        )

        for date in ["2023-01-01"]:
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
        self.assertEqual(results[USER_3_ID]["2023-01-01"], 65)
        self.assertEqual(results[USER_3_ID]["total"], 65)

    @patch("cl.api.utils.get_redis_interface")
    def test_invert_user_logs_shows_v4_logs_two_dates(
        self, mock_get_redis_interface
    ):
        mock_redis = MagicMock()
        mock_pipeline = MagicMock()
        mock_get_redis_interface.return_value = mock_redis
        mock_redis.pipeline.return_value = mock_pipeline

        mock_pipeline.execute.return_value = [
            # v3
            [(USER_2_ID, 20), (USER_3_ID, 30)],
            [(USER_1_ID, 15), (USER_2_ID, 25), (USER_3_ID, 35)],
            # v4
            [(USER_1_ID, 20), (USER_2_ID, 30)],
            [(USER_1_ID, 25), (USER_2_ID, 35), (USER_3_ID, 45)],
        ]

        results = invert_user_logs(
            "2023-01-01", "2023-01-02", add_usernames=False
        )

        for date in ["2023-01-01", "2023-01-02"]:
            mock_pipeline.zrange.assert_any_call(
                f"api:v3.user.d:{date}.counts", 0, -1, withscores=True
            )
            mock_pipeline.zrange.assert_any_call(
                f"api:v4.user.d:{date}.counts", 0, -1, withscores=True
            )

        self.assertIn(USER_1_ID, results)
        self.assertIn(USER_2_ID, results)

        self.assertEqual(results[USER_1_ID]["2023-01-01"], 20)
        self.assertEqual(results[USER_1_ID]["2023-01-02"], 40)
        self.assertEqual(results[USER_1_ID]["total"], 60)

        self.assertEqual(results[USER_2_ID]["2023-01-01"], 50)
        self.assertEqual(results[USER_2_ID]["2023-01-02"], 60)
        self.assertEqual(results[USER_2_ID]["total"], 110)

        self.assertEqual(results[USER_3_ID]["2023-01-01"], 30)
        self.assertEqual(results[USER_3_ID]["2023-01-02"], 80)
        self.assertEqual(results[USER_3_ID]["total"], 110)
