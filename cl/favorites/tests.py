from django.test import Client, TestCase


class FavoriteTest(TestCase):
    fixtures = ['authtest_data.json', 'test_objects.json']

    def setUp(self):
        # Set up some handy variables
        self.client = Client()
        self.fave_cluster_params = {
            'cluster_id': 1,
            'name': 'foo',
            'notes': 'testing notes',
        }
        self.fave_audio_params = {
            'audio_id': 1,
            'name': 'foo',
            'notes': 'testing notes',
        }

    def test_create_fave(self):
        """Can we create a fave by sending a post?"""
        self.client.login(username='pandora', password='password')
        for params in [self.fave_cluster_params, self.fave_audio_params]:
            r = self.client.post(
                '/favorite/create-or-update/',
                params,
                follow=True,
                HTTP_X_REQUESTED_WITH='XMLHttpRequest',
            )
            self.assertEqual(r.status_code, 200)
            self.assertIn('It worked', r.content)

        # And can we delete them?
        for params in [self.fave_cluster_params, self.fave_audio_params]:
            r = self.client.post(
                '/favorite/delete/',
                params,
                follow=True,
                HTTP_X_REQUESTED_WITH='XMLHttpRequest',
            )
        self.assertEqual(r.status_code, 200)
        self.assertIn('It worked', r.content)
        self.client.logout()
