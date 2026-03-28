from __future__ import annotations

import base64
import logging
from uuid import uuid4
from typing import Any

from django.contrib.auth import authenticate
from rest_framework import permissions, serializers, status
from rest_framework.authtoken.models import Token
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from .catalog import PRODUCTS_BY_ID, get_catalog_payload
from .models import GenerationRecord
from .serializers import GenerationRequestSerializer
from .services.fal_service import (
    FalConfigurationError,
    FalSubmissionError,
    fetch_generation_status,
    submit_generation,
    submit_staged_video_render,
)


logger = logging.getLogger(__name__)


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


def _serialize_generation_record(record: GenerationRecord) -> dict[str, Any]:
    product_ids = [product_id for product_id in record.product_id.split(",") if product_id]
    product_names = [
        product_name.strip()
        for product_name in record.product_name.split(",")
        if product_name.strip()
    ]
    return {
        "id": record.id,
        "job_token": record.job_token,
        "provider_request_id": record.provider_request_id,
        "model_id": record.model_id,
        "model_label": record.model_label,
        "pipeline_stage": record.pipeline_stage,
        "product_id": record.product_id,
        "product_name": record.product_name,
        "product_ids": product_ids,
        "product_names": product_names,
        "content_type": record.content_type,
        "language": record.language,
        "video_style": record.video_style,
        "video_orientation": record.video_orientation,
        "aspect_ratio": record.aspect_ratio,
        "prompt": record.prompt,
        "status": record.status,
        "used_reference_images": record.used_reference_images,
        "guidance_note": record.guidance_note,
        "error_message": record.error_message,
        "result_description": record.result_description,
        "assets": record.assets,
        "created_at": record.created_at.isoformat(),
        "updated_at": record.updated_at.isoformat(),
    }


def _update_generation_record(record: GenerationRecord, payload: dict[str, Any]) -> None:
    update_fields = ["updated_at"]
    next_state = payload.get("state")
    if next_state in {"queued", "processing", "completed", "failed"}:
        record.status = next_state
        update_fields.append("status")
    record.error_message = payload.get("error", "") or ""
    update_fields.append("error_message")
    if payload.get("description"):
        record.result_description = payload["description"]
        update_fields.append("result_description")
    if payload.get("assets"):
        record.assets = payload["assets"]
        update_fields.append("assets")
    if payload.get("pipeline_stage"):
        record.pipeline_stage = payload["pipeline_stage"]
        update_fields.append("pipeline_stage")
    if payload.get("pipeline_payload") is not None:
        record.pipeline_payload = payload["pipeline_payload"]
        update_fields.append("pipeline_payload")
    if payload.get("model_id"):
        record.model_id = payload["model_id"]
        update_fields.append("model_id")
    if payload.get("model_label"):
        record.model_label = payload["model_label"]
        update_fields.append("model_label")
    provider_request_id = payload.get("provider_request_id")
    if provider_request_id is not None:
        record.provider_request_id = provider_request_id
        update_fields.append("provider_request_id")
    record.save(update_fields=list(dict.fromkeys(update_fields)))


def _pipeline_stage_label(*, content_type: str, pipeline_stage: str) -> str:
    if pipeline_stage == "starter_frame":
        return "Creating starter frame"
    if pipeline_stage == "video_render":
        return "Rendering final video"
    if content_type == "image":
        return "Generating image"
    return "Rendering video"


def _build_response_payload(
    *,
    record: GenerationRecord | None,
    payload: dict[str, Any],
    model_id: str,
    request_id: str,
) -> dict[str, Any]:
    response_payload = dict(payload)
    pipeline_stage = (
        str(response_payload.get("pipeline_stage") or "")
        or (record.pipeline_stage if record else "provider")
    )
    content_type = (
        str(response_payload.get("content_type") or "")
        or (record.content_type if record else "")
    )
    response_payload["model_id"] = model_id
    response_payload["request_id"] = request_id
    response_payload["model_label"] = response_payload.get("model_label") or (
        record.model_label if record else ""
    )
    response_payload["pipeline_stage"] = pipeline_stage
    response_payload["stage_label"] = _pipeline_stage_label(
        content_type=content_type or "video",
        pipeline_stage=pipeline_stage or "provider",
    )
    return response_payload


def _record_provider_ids(record: GenerationRecord) -> tuple[str, str]:
    if record.provider_request_id:
        return record.model_id, record.provider_request_id
    return _decode_job_token(record.job_token)


def _starter_frame_to_video_payload(
    *,
    record: GenerationRecord,
    starter_payload: dict[str, Any],
    model_id: str,
    request_id: str,
) -> dict[str, Any]:
    assets = starter_payload.get("assets") or []
    starter_frame_url = ""
    if assets and isinstance(assets[0], dict):
        starter_frame_url = assets[0].get("url", "") or ""
    if not starter_frame_url:
        return {
            "state": "failed",
            "error": "fal.ai completed the starter frame job without returning an image.",
            "logs": starter_payload.get("logs", []),
            "pipeline_stage": "starter_frame",
            "model_id": model_id,
            "model_label": record.model_label,
            "provider_request_id": request_id,
        }

    try:
        video_submission = submit_staged_video_render(
            pipeline_payload=record.pipeline_payload,
            starter_frame_url=starter_frame_url,
        )
    except FalSubmissionError as exc:
        return {
            "state": "failed",
            "error": str(exc),
            "logs": starter_payload.get("logs", []),
            "pipeline_stage": "starter_frame",
            "model_id": model_id,
            "model_label": record.model_label,
            "provider_request_id": request_id,
        }

    kickoff_logs = list(starter_payload.get("logs", []))
    kickoff_logs.append(
        {
            "message": "Starter frame approved. Submitted the final Veo 3.1 render.",
            "timestamp": None,
        }
    )
    return {
        "state": "processing",
        "logs": kickoff_logs,
        "content_type": "video",
        "pipeline_stage": video_submission.pipeline_stage,
        "pipeline_payload": video_submission.pipeline_payload,
        "model_id": video_submission.model_id,
        "model_label": video_submission.model_label,
        "provider_request_id": video_submission.request_id,
    }


def _fetch_status_for_record(record: GenerationRecord) -> dict[str, Any]:
    model_id, request_id = _record_provider_ids(record)
    payload = fetch_generation_status(model_id=model_id, request_id=request_id)

    if record.pipeline_stage == "starter_frame" and payload.get("state") == "completed":
        payload = _starter_frame_to_video_payload(
            record=record,
            starter_payload=payload,
            model_id=model_id,
            request_id=request_id,
        )

    _update_generation_record(record, payload)
    return _build_response_payload(
        record=record,
        payload=payload,
        model_id=str(payload.get("model_id") or model_id),
        request_id=str(payload.get("provider_request_id") or request_id),
    )


def _unexpected_error_response(*, context: str, exc: Exception) -> Response:
    debug_id = uuid4().hex[:8]
    logger.exception("%s failed [%s]", context, debug_id)
    return Response(
        {
            "detail": (
                f"{context} failed unexpectedly. "
                f"Debug ID: {debug_id}. "
                f"Error type: {type(exc).__name__}. "
                "Check the Render API logs for this debug ID."
            )
        },
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )


def _normalize_generation_payload(data: Any) -> Any:
    payload = data.copy()
    product_ids = data.getlist("product_ids") if hasattr(data, "getlist") else []
    if not product_ids:
        single_product_id = data.get("product_id", "") if hasattr(data, "get") else ""
        if single_product_id:
            product_ids = [single_product_id]
    if hasattr(payload, "setlist"):
        payload.setlist("product_ids", product_ids)
    else:
        payload["product_ids"] = product_ids
    return payload


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


class GenerationHistoryView(APIView):
    def get(self, request):
        records = GenerationRecord.objects.filter(user=request.user)
        return Response(
            {"items": [_serialize_generation_record(record) for record in records]}
        )


class GenerateContentView(APIView):
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def post(self, request):
        serializer = GenerationRequestSerializer(data=_normalize_generation_payload(request.data))
        serializer.is_valid(raise_exception=True)
        reference_images = request.FILES.getlist("reference_images")

        try:
            submission = submit_generation(
                product_ids=serializer.validated_data["product_ids"],
                content_type=serializer.validated_data["content_type"],
                prompt=serializer.validated_data["prompt"],
                language=serializer.validated_data["language"],
                aspect_ratio=serializer.validated_data["aspect_ratio"],
                video_style=serializer.validated_data["video_style"],
                video_orientation=serializer.validated_data["video_orientation"],
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
        except Exception as exc:  # pragma: no cover - defensive logging path
            return _unexpected_error_response(
                context="Generate content",
                exc=exc,
            )

        job_token = _encode_job_token(submission.model_id, submission.request_id)
        selected_products = [
            PRODUCTS_BY_ID[product_id]
            for product_id in serializer.validated_data["product_ids"]
        ]
        GenerationRecord.objects.update_or_create(
            job_token=job_token,
            defaults={
                "user": request.user,
                "provider_request_id": submission.request_id,
                "model_id": submission.model_id,
                "model_label": submission.model_label,
                "pipeline_stage": submission.pipeline_stage,
                "pipeline_payload": submission.pipeline_payload,
                "product_id": ",".join(serializer.validated_data["product_ids"]),
                "product_name": ", ".join(
                    product["name"] for product in selected_products
                ),
                "content_type": submission.content_type,
                "language": serializer.validated_data["language"],
                "video_style": serializer.validated_data["video_style"],
                "video_orientation": serializer.validated_data["video_orientation"],
                "aspect_ratio": serializer.validated_data["aspect_ratio"],
                "prompt": serializer.validated_data["prompt"],
                "status": "queued",
                "used_reference_images": submission.used_reference_images,
                "guidance_note": submission.guidance_note,
                "error_message": "",
                "result_description": "",
                "assets": [],
            },
        )

        return Response(
            {
                "job_token": job_token,
                "request_id": submission.request_id,
                "model_id": submission.model_id,
                "model_label": submission.model_label,
                "pipeline_stage": submission.pipeline_stage,
                "stage_label": _pipeline_stage_label(
                    content_type=submission.content_type,
                    pipeline_stage=submission.pipeline_stage,
                ),
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
            record = GenerationRecord.objects.filter(
                user=request.user,
                job_token=token,
            ).first()
            if record:
                return Response(_fetch_status_for_record(record))

            model_id, request_id = _decode_job_token(token)
            payload = fetch_generation_status(
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
        except Exception as exc:  # pragma: no cover - defensive logging path
            return _unexpected_error_response(
                context="Fetch generation status",
                exc=exc,
            )

        return Response(
            _build_response_payload(
                record=None,
                payload=payload,
                model_id=model_id,
                request_id=request_id,
            )
        )
