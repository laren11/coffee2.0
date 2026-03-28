from __future__ import annotations

import base64
import binascii
import mimetypes
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import fal_client
from fal_client.client import Completed, InProgress, Queued

from creator.assets import (
    list_product_reference_files,
    list_ugc_creator_reference_files,
)
from creator.catalog import PRODUCTS_BY_ID, UGC_CREATORS_BY_ID
from creator.prompting import build_generation_prompt, build_negative_prompt


TEXT_IMAGE_MODEL = "fal-ai/nano-banana"
REFERENCE_IMAGE_MODEL = "fal-ai/nano-banana-pro/edit"
TEXT_VIDEO_MODEL = "fal-ai/veo3.1/fast"
IMAGE_TO_VIDEO_MODEL = "fal-ai/veo3.1/fast/image-to-video"
REFERENCE_VIDEO_MODEL = "fal-ai/veo3.1/reference-to-video"
MAX_REFERENCE_IMAGES = 6
MAX_REFERENCE_IMAGE_SIZE_BYTES = 8 * 1024 * 1024


class FalConfigurationError(RuntimeError):
    pass


class FalSubmissionError(RuntimeError):
    pass


@dataclass
class SubmissionResult:
    model_id: str
    model_label: str
    request_id: str
    content_type: str
    used_reference_images: bool
    guidance_note: str


def _ensure_fal_key() -> None:
    if not os.getenv("FAL_KEY"):
        raise FalConfigurationError(
            "FAL_KEY is missing. Add it to backend/.env before generating content."
        )


def _file_to_data_uri(upload) -> str:
    if upload.size > MAX_REFERENCE_IMAGE_SIZE_BYTES:
        raise FalSubmissionError(
            f"{upload.name} is larger than 8 MB. Compress it and try again."
        )

    mime_type = upload.content_type or mimetypes.guess_type(upload.name)[0] or "image/png"
    try:
        encoded = base64.b64encode(upload.read()).decode("utf-8")
    except (binascii.Error, ValueError) as exc:
        raise FalSubmissionError(
            f"Unable to read the uploaded file {upload.name}."
        ) from exc
    finally:
        upload.seek(0)

    return f"data:{mime_type};base64,{encoded}"


def _path_to_data_uri(path: Path) -> str:
    if path.stat().st_size > MAX_REFERENCE_IMAGE_SIZE_BYTES:
        raise FalSubmissionError(f"{path.name} is larger than 8 MB. Compress it and try again.")

    mime_type = mimetypes.guess_type(path.name)[0] or "image/png"
    encoded = base64.b64encode(path.read_bytes()).decode("utf-8")
    return f"data:{mime_type};base64,{encoded}"


def _serialize_logs(logs: list[Any]) -> list[dict[str, Any]]:
    serialized = []
    for log in logs:
        if isinstance(log, dict):
            serialized.append(log)
            continue

        message = getattr(log, "message", None) or str(log)
        timestamp = getattr(log, "timestamp", None)
        serialized.append({"message": message, "timestamp": timestamp})
    return serialized


def _select_model(content_type: str, reference_count: int) -> tuple[str, str]:
    if content_type == "image":
        if reference_count:
            return REFERENCE_IMAGE_MODEL, "Nano Banana Pro Edit"
        return TEXT_IMAGE_MODEL, "Nano Banana"

    if reference_count >= 2:
        return REFERENCE_VIDEO_MODEL, "Veo 3.1 Reference-to-Video"
    if reference_count == 1:
        return IMAGE_TO_VIDEO_MODEL, "Veo 3.1 Fast Image-to-Video"
    return TEXT_VIDEO_MODEL, "Veo 3.1 Fast Text-to-Video"


def _model_label_for_id(model_id: str) -> str:
    return {
        TEXT_IMAGE_MODEL: "Nano Banana",
        REFERENCE_IMAGE_MODEL: "Nano Banana Pro Edit",
        TEXT_VIDEO_MODEL: "Veo 3.1 Fast Text-to-Video",
        IMAGE_TO_VIDEO_MODEL: "Veo 3.1 Fast Image-to-Video",
        REFERENCE_VIDEO_MODEL: "Veo 3.1 Reference-to-Video",
    }[model_id]


def _build_arguments(
    *,
    product_id: str,
    content_type: str,
    prompt: str,
    language: str,
    aspect_ratio: str,
    video_style: str,
    video_orientation: str,
    ugc_creator_id: str,
    include_audio: bool,
    reference_images: list,
) -> tuple[str, dict[str, Any], bool]:
    product = PRODUCTS_BY_ID[product_id]
    ugc_creator = UGC_CREATORS_BY_ID.get(ugc_creator_id or "")
    uploaded_reference_uris = [
        _file_to_data_uri(upload) for upload in reference_images[:MAX_REFERENCE_IMAGES]
    ]
    local_product_reference_uris = [
        _path_to_data_uri(path)
        for path in list_product_reference_files(product_id)
    ]
    local_creator_reference_uris = (
        [_path_to_data_uri(path) for path in list_ugc_creator_reference_files(ugc_creator_id)]
        if ugc_creator_id
        else []
    )
    reference_data_uris = (
        uploaded_reference_uris
        + local_product_reference_uris
        + local_creator_reference_uris
    )[:MAX_REFERENCE_IMAGES]
    model_id, _ = _select_model(content_type, len(reference_data_uris))
    has_reference_images = bool(reference_data_uris)

    full_prompt = build_generation_prompt(
        product=product,
        content_type=content_type,
        user_prompt=prompt,
        language=language,
        video_style=video_style,
        video_orientation=video_orientation,
        ugc_creator=ugc_creator,
        has_reference_images=has_reference_images,
    )

    if content_type == "image":
        arguments: dict[str, Any] = {
            "prompt": full_prompt,
            "aspect_ratio": aspect_ratio,
            "resolution": "1K",
        }
        if has_reference_images:
            arguments["image_urls"] = reference_data_uris
            arguments["limit_generations"] = True
        return model_id, arguments, has_reference_images

    arguments = {
        "prompt": full_prompt,
        "aspect_ratio": aspect_ratio,
        "duration": "8s",
        "resolution": "720p",
        "generate_audio": include_audio,
        "auto_fix": True,
    }

    if model_id == TEXT_VIDEO_MODEL:
        arguments["negative_prompt"] = build_negative_prompt(video_style)
    elif model_id == IMAGE_TO_VIDEO_MODEL:
        arguments["negative_prompt"] = build_negative_prompt(video_style)
        arguments["image_url"] = reference_data_uris[0]
    elif model_id == REFERENCE_VIDEO_MODEL:
        arguments["image_urls"] = reference_data_uris

    return model_id, arguments, has_reference_images


def submit_generation(
    *,
    product_id: str,
    content_type: str,
    prompt: str,
    language: str,
    aspect_ratio: str,
    video_style: str,
    video_orientation: str,
    ugc_creator_id: str,
    include_audio: bool,
    reference_images: list,
) -> SubmissionResult:
    _ensure_fal_key()
    model_id, arguments, used_reference_images = _build_arguments(
        product_id=product_id,
        content_type=content_type,
        prompt=prompt,
        language=language,
        aspect_ratio=aspect_ratio,
        video_style=video_style,
        video_orientation=video_orientation,
        ugc_creator_id=ugc_creator_id,
        include_audio=include_audio,
        reference_images=reference_images,
    )
    model_label = _model_label_for_id(model_id)

    try:
        handle = fal_client.submit(model_id, arguments)
    except Exception as exc:  # pragma: no cover - network/provider failure
        raise FalSubmissionError(str(exc)) from exc

    guidance_note = (
        "Reference photos were used to keep the product closer to the real packaging."
        if used_reference_images
        else "No reference photos were uploaded, so the result may drift from the exact real-world packaging."
    )
    return SubmissionResult(
        model_id=model_id,
        model_label=model_label,
        request_id=handle.request_id,
        content_type=content_type,
        used_reference_images=used_reference_images,
        guidance_note=guidance_note,
    )


def fetch_generation_status(*, model_id: str, request_id: str) -> dict[str, Any]:
    _ensure_fal_key()

    try:
        status = fal_client.status(model_id, request_id, with_logs=True)
    except Exception as exc:  # pragma: no cover - network/provider failure
        raise FalSubmissionError(str(exc)) from exc

    if isinstance(status, Queued):
        return {
            "state": "queued",
            "queue_position": status.position,
            "logs": [],
        }

    if isinstance(status, InProgress):
        return {
            "state": "processing",
            "logs": _serialize_logs(status.logs),
        }

    if isinstance(status, Completed):
        if status.error:
            return {
                "state": "failed",
                "error": status.error,
                "error_type": status.error_type,
                "logs": _serialize_logs(status.logs),
            }

        try:
            result = fal_client.result(model_id, request_id)
        except Exception as exc:  # pragma: no cover - network/provider failure
            raise FalSubmissionError(str(exc)) from exc

        payload = {
            "state": "completed",
            "logs": _serialize_logs(status.logs),
        }
        if "images" in result:
            payload["assets"] = [
                {
                    "url": image.get("url"),
                    "file_name": image.get("file_name"),
                    "content_type": image.get("content_type"),
                }
                for image in result["images"]
            ]
            payload["content_type"] = "image"
            payload["description"] = result.get("description", "")
        elif "video" in result:
            payload["assets"] = [result["video"]]
            payload["content_type"] = "video"
        else:
            payload["raw_result"] = result
        return payload

    raise FalSubmissionError("Received an unknown job state from fal.ai.")
