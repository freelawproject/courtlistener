import pytest

from cl.ai.models import (
    LLMProvider,
    LLMRequest,
    LLMTask,
    LLMTaskChoices,
    LLMTaskStatusChoices,
    Prompt,
    PromptTypes,
)
from cl.search.factories import CourtFactory, DocketFactory
from cl.tests.cases import TestCase


@pytest.mark.django_db
class AiModelsTest(TestCase):
    def setUp(self):
        self.court = CourtFactory()
        self.docket = DocketFactory(court=self.court)

    def test_create_llm_task(self):
        """Test that we can create an LLMTask and its related models."""
        prompt = Prompt.objects.create(
            name="Test System Prompt",
            prompt_type=PromptTypes.SYSTEM,
            text="You are a helpful assistant.",
        )
        self.assertEqual(Prompt.objects.count(), 1)

        llm_request = LLMRequest.objects.create(
            name="Test Batch Request",
            is_batch=True,
            provider=LLMProvider.GEMINI,
            api_model_name="gemini-2.5-pro",
            status=LLMTaskStatusChoices.UNPROCESSED,
        )
        llm_request.prompts.add(prompt)
        self.assertEqual(LLMRequest.objects.count(), 1)
        self.assertEqual(llm_request.prompts.count(), 1)

        llm_task = LLMTask.objects.create(
            request=llm_request,
            task=LLMTaskChoices.CASENAME,
            content_object=self.docket,
            llm_key="test-key-1",
        )
        self.assertEqual(LLMTask.objects.count(), 1)
        self.assertEqual(llm_task.request, llm_request)
        self.assertEqual(llm_task.content_object, self.docket)
        self.assertEqual(llm_task.status, LLMTaskStatusChoices.UNPROCESSED)
