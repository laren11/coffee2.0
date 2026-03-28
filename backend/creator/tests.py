from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from rest_framework.authtoken.models import Token

from creator.models import GenerationRecord
from creator.prompting import build_generation_prompt


class PromptingTests(SimpleTestCase):
    def test_prompt_mentions_reference_fidelity_when_images_exist(self):
        prompt = build_generation_prompt(
            product={
                "name": "Coffee 2.0",
                "tagline": "Focus and clean energy.",
                "description": "Premium functional coffee.",
                "benefits": ["adaptogens", "mushrooms"],
                "creative_angles": ["desk focus"],
                "base_prompt": "Make the product the hero.",
            },
            content_type="video",
            user_prompt="A quick creator testimonial in a bright kitchen.",
            language="sl",
            video_style="ugc",
            video_orientation="portrait",
            ugc_creator={
                "name": "Founder",
                "description": "Confident creator persona.",
                "persona_prompt": "Speak directly and confidently.",
            },
            has_reference_images=True,
            include_audio=True,
        )

        self.assertIn("Preserve the exact packaging", prompt)
        self.assertIn("creator-made UGC", prompt)
        self.assertIn("Founder", prompt)
        self.assertIn("Slovenian", prompt)
        self.assertIn("clear native Slovenian speech", prompt)


class ApiTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="coffee",
            password="coffe20",
        )
        self.token = Token.objects.create(user=self.user)
        self.auth_headers = {"HTTP_AUTHORIZATION": f"Token {self.token.key}"}

    def test_login_endpoint_returns_token(self):
        response = self.client.post(
            "/api/auth/login/",
            {"username": "coffee", "password": "coffe20"},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("token", response.json())

    @patch("creator.views.submit_generation")
    def test_generate_endpoint_returns_job_token(self, submit_generation_mock):
        submit_generation_mock.return_value.model_id = "fal-ai/nano-banana"
        submit_generation_mock.return_value.model_label = "Nano Banana"
        submit_generation_mock.return_value.request_id = "req-123"
        submit_generation_mock.return_value.content_type = "image"
        submit_generation_mock.return_value.used_reference_images = False
        submit_generation_mock.return_value.guidance_note = "No reference photos."

        response = self.client.post(
            "/api/generate/",
            {
                "product_id": "coffee-2-0",
                "content_type": "image",
                "prompt": "Premium coffee hero ad.",
                "language": "en",
                "aspect_ratio": "1:1",
            },
            **self.auth_headers,
        )

        self.assertEqual(response.status_code, 202)
        self.assertIn("job_token", response.json())

    @patch("creator.views.submit_generation")
    def test_generate_endpoint_accepts_legacy_founder_alias(self, submit_generation_mock):
        submit_generation_mock.return_value.model_id = "fal-ai/veo3.1/fast"
        submit_generation_mock.return_value.model_label = "Veo 3.1 Fast Text-to-Video"
        submit_generation_mock.return_value.request_id = "req-legacy-founder"
        submit_generation_mock.return_value.content_type = "video"
        submit_generation_mock.return_value.used_reference_images = False
        submit_generation_mock.return_value.guidance_note = "Fast pipeline."

        response = self.client.post(
            "/api/generate/",
            {
                "product_id": "coffee-2-0",
                "content_type": "video",
                "prompt": "Founder testimonial.",
                "language": "en",
                "video_style": "ugc",
                "video_orientation": "portrait",
                "ugc_creator_id": "assertive-founder",
            },
            **self.auth_headers,
        )

        self.assertEqual(response.status_code, 202)
        self.assertEqual(
            submit_generation_mock.call_args.kwargs["ugc_creator_id"], "founder"
        )

    @patch("creator.views.fetch_generation_status")
    def test_status_endpoint_returns_completed_payload(self, status_mock):
        status_mock.return_value = {
            "state": "completed",
            "content_type": "image",
            "assets": [{"url": "https://example.com/image.png"}],
            "logs": [],
        }

        response = self.client.get(
            "/api/generate/status/",
            {"token": "ZmFsLWFpL25hbm8tYmFuYW5hfHJlcS0xMjM"},
            **self.auth_headers,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["state"], "completed")

    def test_catalog_exposes_languages_and_video_orientations(self):
        response = self.client.get("/api/products/", **self.auth_headers)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("languages", payload["generation_options"])
        self.assertIn("videoOrientations", payload["generation_options"])

    def test_history_endpoint_returns_user_generations(self):
        GenerationRecord.objects.create(
            user=self.user,
            job_token="job-123",
            model_id="fal-ai/nano-banana-pro",
            model_label="Nano Banana Pro",
            product_id="coffee-2-0",
            product_name="Coffee 2.0",
            content_type="image",
            language="en",
            prompt="A bright premium coffee ad.",
            status="completed",
            assets=[{"url": "https://example.com/image.webp"}],
        )

        response = self.client.get("/api/history/", **self.auth_headers)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload["items"]), 1)
        self.assertEqual(payload["items"][0]["product_name"], "Coffee 2.0")
