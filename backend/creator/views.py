from __future__ import annotations

import base64
from typing import Any

from django.contrib.auth import authenticate
from rest_framework import permissions, serializers, status
from rest_framework.authtoken.models import Token
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from .catalog import get_catalog_payload
from .serializers import GenerationRequestSerializer
from .services.fal_service import (
    FalConfigurationError,
    FalSubmissionError,
    fetch_generation_status,
    submit_generation,
)


def _encode_job_token(model_id: str, request_id: str) -> str:
    raw = f"{model_id}|{request_id}".encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")


def _decode_job_token(token: str) -> tuple[str, str]:
    try:
        padding = "=" * (-len(token) % 4)
        raw = base64.urlsafe_b64decode((token + padding).encode("utf-8")).decode("utf-8")
        model_id, request_id = raw.split("|", maxsplit=1)
        return model_id, request_id
    except Exception as exc:  # pragma: no cover - malformed token
        raise ValueError("Invalid job token.") from exc


class HealthView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        return Response({"status": "ok", "provider": "fal.ai"})


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150, trim_whitespace=True)
    password = serializers.CharField(max_length=128, trim_whitespace=False)


class AuthLoginView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = authenticate(
            request,
            username=serializer.validated_data["username"],
            password=serializer.validated_data["password"],
        )
        if not user:
            return Response(
                {"detail": "Invalid username or password."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        token, _ = Token.objects.get_or_create(user=user)
        return Response(
            {
                "token": token.key,
                "user": {
                    "username": user.username,
                },
            }
        )


class AuthMeView(APIView):
    def get(self, request):
        return Response(
            {
                "user": {
                    "username": request.user.username,
                }
            }
        )


class ProductCatalogView(APIView):
    def get(self, request):
        return Response(get_catalog_payload())


class GenerateContentView(APIView):
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def post(self, request):
        serializer = GenerationRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reference_images = request.FILES.getlist("reference_images")

        try:
            submission = submit_generation(
                product_id=serializer.validated_data["product_id"],
                content_type=serializer.validated_data["content_type"],
                prompt=serializer.validated_data["prompt"],
                aspect_ratio=serializer.validated_data["aspect_ratio"],
                video_style=serializer.validated_data["video_style"],
                ugc_creator_id=serializer.validated_data["ugc_creator_id"],
                include_audio=serializer.validated_data["include_audio"],
                reference_images=reference_images,
            )
        except FalConfigurationError as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        except FalSubmissionError as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            {
                "job_token": _encode_job_token(submission.model_id, submission.request_id),
                "request_id": submission.request_id,
                "model_id": submission.model_id,
                "model_label": submission.model_label,
                "content_type": submission.content_type,
                "used_reference_images": submission.used_reference_images,
                "guidance_note": submission.guidance_note,
            },
            status=status.HTTP_202_ACCEPTED,
        )


class GenerationStatusView(APIView):
    def get(self, request):
        token = request.query_params.get("token", "")
        if not token:
            return Response(
                {"detail": "Missing job token."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            model_id, request_id = _decode_job_token(token)
            payload: dict[str, Any] = fetch_generation_status(
                model_id=model_id,
                request_id=request_id,
            )
        except ValueError:
            return Response(
                {"detail": "Invalid job token."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except FalConfigurationError as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        except FalSubmissionError as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        payload["model_id"] = model_id
        payload["request_id"] = request_id
        return Response(payload)
