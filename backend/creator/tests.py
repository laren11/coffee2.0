from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from rest_framework.authtoken.models import Token

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
            video_style="ugc",
            ugc_creator={
                "name": "High-Energy Founder",
                "description": "Confident creator persona.",
                "persona_prompt": "Speak directly and confidently.",
            },
            has_reference_images=True,
        )

        self.assertIn("Preserve the exact packaging", prompt)
        self.assertIn("creator-made UGC", prompt)
        self.assertIn("High-Energy Founder", prompt)


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
                "aspect_ratio": "1:1",
            },
            **self.auth_headers,
        )

        self.assertEqual(response.status_code, 202)
        self.assertIn("job_token", response.json())

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
