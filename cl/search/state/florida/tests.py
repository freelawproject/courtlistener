from cl.search.state.florida.models import (
    AltchaChallenge,
    AltchaChallengeParameters,
    AltchaData,
)
from cl.tests.cases import TestCase


class DocumentDownloadTest(TestCase):
    def test_generate_altcha_token(self):
        challenge = AltchaChallenge(
            parameters=AltchaChallengeParameters(
                algorithm="PBKDF2/SHA-256",
                cost=10_000,
                data=AltchaData(
                    resource="/courts/68f021c4-6a44-4735-9a76-5360b2e8af13/cms/case/4b5eafaf-a6c7-4556-9a60-cf173c204883/docketentrydocuments/7b6b41bf-3eb6-4704-8f9b-093367be9d69"
                ),
                expiresAt=1789424228,
                keyLength=32,
                keyPrefix="d003cf8e29159842a4dd2abb90a6d68a",
                keySignature="1912061753893c495c19080c40d90eb9029919d47b17b8c6cfb97d1af86a997a",
                nonce="ee760148b810f7fd855b75fb728bc54b",
                salt="8a4d1d31f3e89688791f46e1941a6cd7",
            ),
            signature="bfe8968a0b09e59072225361880098d663323e1245ce129f55e44a4a8f372aec",
        )

        solution = challenge.solve()

        self.assertIsNotNone(solution)
        self.assertEqual(solution.counter, 229)
        self.assertEqual(
            solution.derived_key,
            "d003cf8e29159842a4dd2abb90a6d68ad21e5bbb1b09ede19320c43a152d0c87",
        )
