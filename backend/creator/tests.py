from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from rest_framework.authtoken.models import Token

from creator.models import GenerationRecord
from creator.prompting import build_generation_prompt, build_video_starter_frame_prompt
from creator.services.fal_service import (
    IMAGE_TO_VIDEO_MODEL,
    REFERENCE_IMAGE_MODEL,
    TEXT_IMAGE_MODEL,
    submit_generation,
    submit_staged_video_render,
)


class PromptingTests(SimpleTestCase):
    def test_prompt_mentions_reference_fidelity_when_images_exist(self):
        prompt = build_generation_prompt(
            products=[
                {
                    "name": "Coffee 2.0",
                    "tagline": "Focus and clean energy.",
                    "description": "Premium functional coffee.",
                    "benefits": ["adaptogens", "mushrooms"],
                    "creative_angles": ["desk focus"],
                    "base_prompt": "Make the product the hero.",
                }
            ],
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

    def test_starter_frame_prompt_matches_ugc_language_and_tone(self):
        prompt = build_video_starter_frame_prompt(
            products=[
                {
                    "name": "Coffee 2.0",
                    "tagline": "Focus and clean energy.",
                    "description": "Premium functional coffee.",
                    "benefits": ["adaptogens", "mushrooms"],
                    "creative_angles": ["desk focus"],
                    "base_prompt": "Make the product the hero.",
                }
            ],
            user_prompt="Founder-style direct-to-camera hook in a modern office.",
            language="de",
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

        self.assertIn("creator-made UGC ad", prompt)
        self.assertIn("Founder", prompt)
        self.assertIn("German", prompt)
        self.assertIn("before the creator starts speaking", prompt)

    def test_multi_product_prompt_mentions_lineup(self):
        prompt = build_generation_prompt(
            products=[
                {
                    "name": "Coffee 2.0",
                    "tagline": "Focus and clean energy.",
                    "description": "Premium functional coffee.",
                    "benefits": ["adaptogens"],
                    "creative_angles": ["desk focus"],
                    "base_prompt": "Make the product the hero.",
                },
                {
                    "name": "Matcha 2.0",
                    "tagline": "Calm energy and clarity.",
                    "description": "Premium functional matcha.",
                    "benefits": ["calm energy"],
                    "creative_angles": ["morning ritual"],
                    "base_prompt": "Position it as a premium ritual drink.",
                },
            ],
            content_type="image",
            user_prompt="Show the products as a premium pair.",
            language="en",
            video_style="ad",
            video_orientation="portrait",
            ugc_creator=None,
            has_reference_images=True,
            include_audio=False,
        )

        self.assertIn("Products featured together: Coffee 2.0, Matcha 2.0.", prompt)
        self.assertIn("bundle", prompt)


class FalServiceTests(SimpleTestCase):
    @patch("creator.services.fal_service._submit_provider_request", return_value="starter-req")
    def test_video_submission_queues_starter_frame_then_quality_video(
        self, submit_provider_request_mock
    ):
        submission = submit_generation(
            product_ids=["coffee-2-0"],
            content_type="video",
            prompt="Create a cinematic performance ad.",
            language="en",
            aspect_ratio="16:9",
            video_style="ad",
            video_orientation="landscape",
            ugc_creator_id="",
            include_audio=False,
            reference_images=[],
        )

        self.assertEqual(submission.pipeline_stage, "starter_frame")
        self.assertEqual(submission.request_id, "starter-req")
        self.assertEqual(submission.model_id, REFERENCE_IMAGE_MODEL)
        self.assertEqual(
            submission.pipeline_payload["final_model_id"], IMAGE_TO_VIDEO_MODEL
        )
        self.assertEqual(
            submission.pipeline_payload["final_arguments"]["duration"], "6s"
        )
        self.assertEqual(
            submission.pipeline_payload["final_arguments"]["resolution"], "1080p"
        )
        self.assertIn("two steps", submission.guidance_note)
        submit_provider_request_mock.assert_called_once()

    @patch("creator.services.fal_service._submit_provider_request", return_value="starter-req")
    def test_ugc_video_defaults_to_shorter_duration_and_audio(
        self, submit_provider_request_mock
    ):
        submission = submit_generation(
            product_ids=["coffee-2-0"],
            content_type="video",
            prompt="Create a founder testimonial.",
            language="en",
            aspect_ratio="9:16",
            video_style="ugc",
            video_orientation="portrait",
            ugc_creator_id="founder",
            include_audio=True,
            reference_images=[],
        )

        self.assertEqual(submission.pipeline_stage, "starter_frame")
        self.assertEqual(
            submission.pipeline_payload["final_arguments"]["duration"], "4s"
        )
        self.assertEqual(
            submission.pipeline_payload["final_arguments"]["resolution"], "720p"
        )
        self.assertTrue(
            submission.pipeline_payload["final_arguments"]["generate_audio"]
        )
        submit_provider_request_mock.assert_called_once()

    @patch("creator.services.fal_service._submit_provider_request", return_value="video-req")
    def test_staged_video_render_uses_generated_starter_frame(
        self, submit_provider_request_mock
    ):
        submission = submit_staged_video_render(
            pipeline_payload={
                "final_model_id": IMAGE_TO_VIDEO_MODEL,
                "final_model_label": "Veo 3.1 Image-to-Video",
                "final_arguments": {
                    "prompt": "Create a premium ad.",
                    "aspect_ratio": "16:9",
                    "duration": "6s",
                    "resolution": "1080p",
                    "generate_audio": False,
                },
                "used_reference_images": True,
            },
            starter_frame_url="https://example.com/starter-frame.webp",
        )

        self.assertEqual(submission.pipeline_stage, "video_render")
        self.assertEqual(submission.model_id, IMAGE_TO_VIDEO_MODEL)
        self.assertEqual(submission.request_id, "video-req")
        self.assertEqual(
            submit_provider_request_mock.call_args.args[1]["image_url"],
            "https://example.com/starter-frame.webp",
        )


class ApiTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="coffee",
            password="coffe20",
        )
        self.token = Token.objects.create(user=self.user)
        self.auth_headers = {"HTTP_AUTHORIZATION": f"Token {self.token.key}"}

    def _mock_submission(
        self,
        *,
        model_id: str,
        model_label: str,
        request_id: str,
        content_type: str,
        used_reference_images: bool,
        guidance_note: str,
        pipeline_stage: str = "provider",
        pipeline_payload: dict | None = None,
    ):
        return SimpleNamespace(
            model_id=model_id,
            model_label=model_label,
            request_id=request_id,
            content_type=content_type,
            used_reference_images=used_reference_images,
            guidance_note=guidance_note,
            pipeline_stage=pipeline_stage,
            pipeline_payload=pipeline_payload or {},
        )

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
        submit_generation_mock.return_value = self._mock_submission(
            model_id="fal-ai/nano-banana",
            model_label="Nano Banana",
            request_id="req-123",
            content_type="image",
            used_reference_images=False,
            guidance_note="No reference photos.",
        )

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
        self.assertEqual(
            submit_generation_mock.call_args.kwargs["product_ids"], ["coffee-2-0"]
        )

    @patch("creator.views.submit_generation")
    def test_generate_endpoint_accepts_multiple_products(self, submit_generation_mock):
        submit_generation_mock.return_value = self._mock_submission(
            model_id="fal-ai/nano-banana",
            model_label="Nano Banana",
            request_id="req-multi",
            content_type="image",
            used_reference_images=True,
            guidance_note="Multi-product prompt.",
        )

        response = self.client.post(
            "/api/generate/",
            {
                "product_ids": ["coffee-2-0", "matcha-2-0"],
                "content_type": "image",
                "prompt": "Bundle ad.",
                "language": "en",
                "aspect_ratio": "1:1",
            },
            **self.auth_headers,
        )

        self.assertEqual(response.status_code, 202)
        self.assertEqual(
            submit_generation_mock.call_args.kwargs["product_ids"],
            ["coffee-2-0", "matcha-2-0"],
        )

    @patch("creator.views.submit_generation")
    def test_generate_endpoint_accepts_legacy_founder_alias(self, submit_generation_mock):
        submit_generation_mock.return_value = self._mock_submission(
            model_id=REFERENCE_IMAGE_MODEL,
            model_label="Nano Banana Pro Edit Starter Frame",
            request_id="req-legacy-founder",
            content_type="video",
            used_reference_images=False,
            guidance_note="Starter-frame pipeline.",
            pipeline_stage="starter_frame",
            pipeline_payload={
                "final_model_id": IMAGE_TO_VIDEO_MODEL,
                "final_model_label": "Veo 3.1 Image-to-Video",
                "final_arguments": {"prompt": "Founder testimonial."},
            },
        )

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
        self.assertTrue(submit_generation_mock.call_args.kwargs["include_audio"])

    @patch("creator.views.submit_generation")
    def test_generate_endpoint_returns_debug_id_for_unexpected_errors(
        self, submit_generation_mock
    ):
        submit_generation_mock.side_effect = ValueError("boom")

        response = self.client.post(
            "/api/generate/",
            {
                "product_id": "coffee-2-0",
                "content_type": "video",
                "prompt": "Founder testimonial.",
                "language": "en",
                "video_style": "ugc",
                "video_orientation": "portrait",
                "ugc_creator_id": "founder",
            },
            **self.auth_headers,
        )

        self.assertEqual(response.status_code, 500)
        self.assertIn("Debug ID:", response.json()["detail"])

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

    @patch("creator.views.submit_staged_video_render")
    @patch("creator.views.fetch_generation_status")
    def test_status_endpoint_advances_starter_frame_pipeline(
        self,
        status_mock,
        submit_staged_video_render_mock,
    ):
        GenerationRecord.objects.create(
            user=self.user,
            job_token="job-starter",
            provider_request_id="starter-req",
            model_id=REFERENCE_IMAGE_MODEL,
            model_label="Nano Banana Pro Edit Starter Frame",
            pipeline_stage="starter_frame",
            pipeline_payload={
                "final_model_id": IMAGE_TO_VIDEO_MODEL,
                "final_model_label": "Veo 3.1 Image-to-Video",
                "final_arguments": {
                    "prompt": "Create a premium founder video.",
                    "aspect_ratio": "9:16",
                    "duration": "4s",
                    "resolution": "720p",
                    "generate_audio": True,
                },
            },
            product_id="coffee-2-0",
            product_name="Coffee 2.0",
            content_type="video",
            language="en",
            video_style="ugc",
            video_orientation="portrait",
            aspect_ratio="9:16",
            prompt="Founder video.",
            status="processing",
            used_reference_images=True,
        )
        status_mock.return_value = {
            "state": "completed",
            "content_type": "image",
            "assets": [{"url": "https://example.com/starter.png"}],
            "logs": [],
        }
        submit_staged_video_render_mock.return_value = self._mock_submission(
            model_id=IMAGE_TO_VIDEO_MODEL,
            model_label="Veo 3.1 Image-to-Video",
            request_id="video-req",
            content_type="video",
            used_reference_images=True,
            guidance_note="",
            pipeline_stage="video_render",
        )

        response = self.client.get(
            "/api/generate/status/",
            {"token": "job-starter"},
            **self.auth_headers,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["state"], "processing")
        self.assertEqual(response.json()["pipeline_stage"], "video_render")
        self.assertEqual(response.json()["request_id"], "video-req")

        record = GenerationRecord.objects.get(job_token="job-starter")
        self.assertEqual(record.pipeline_stage, "video_render")
        self.assertEqual(record.provider_request_id, "video-req")

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
            product_id="coffee-2-0,matcha-2-0",
            product_name="Coffee 2.0, Matcha 2.0",
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
        self.assertEqual(payload["items"][0]["product_name"], "Coffee 2.0, Matcha 2.0")
        self.assertEqual(
            payload["items"][0]["product_ids"], ["coffee-2-0", "matcha-2-0"]
        )
