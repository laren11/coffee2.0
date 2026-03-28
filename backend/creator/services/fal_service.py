from __future__ import annotations

import base64
import binascii
import mimetypes
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import fal_client
from fal_client.client import Completed, InProgress, Queued

from creator.assets import list_product_reference_files, list_ugc_creator_reference_files
from creator.catalog import PRODUCTS_BY_ID, UGC_CREATORS_BY_ID
from creator.prompting import (
    build_generation_prompt,
    build_negative_prompt,
    build_video_starter_frame_prompt,
)


TEXT_IMAGE_MODEL = "fal-ai/nano-banana-pro"
REFERENCE_IMAGE_MODEL = "fal-ai/nano-banana-pro/edit"
TEXT_VIDEO_MODEL = "fal-ai/veo3.1"
IMAGE_TO_VIDEO_MODEL = "fal-ai/veo3.1/image-to-video"
REFERENCE_VIDEO_MODEL = "fal-ai/veo3.1/reference-to-video"
MAX_REFERENCE_IMAGES = 6
MAX_REFERENCE_IMAGE_SIZE_BYTES = 8 * 1024 * 1024

MODEL_LABELS = {
    TEXT_IMAGE_MODEL: "Nano Banana Pro",
    REFERENCE_IMAGE_MODEL: "Nano Banana Pro Edit",
    TEXT_VIDEO_MODEL: "Veo 3.1 Text-to-Video",
    IMAGE_TO_VIDEO_MODEL: "Veo 3.1 Image-to-Video",
    REFERENCE_VIDEO_MODEL: "Veo 3.1 Reference-to-Video",
    "fal-ai/veo3.1/fast": "Veo 3.1 Fast Text-to-Video",
    "fal-ai/veo3.1/fast/image-to-video": "Veo 3.1 Fast Image-to-Video",
}


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
    pipeline_stage: str = "provider"
    pipeline_payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class ReferenceAssets:
    combined: list[str]
    uploaded: list[str]
    product: list[str]
    creator: list[str]


def _ensure_fal_key() -> None:
    if not os.getenv("FAL_KEY"):
        raise FalConfigurationError(
            "FAL_KEY is missing. Add it to backend/.env before generating content."
        )


def _video_duration(*, video_style: str, include_audio: bool) -> str:
    if video_style == "ugc":
        return "4s"
    if include_audio:
        return "4s"
    return "6s"


def _video_resolution(*, video_style: str, include_audio: bool) -> str:
    if video_style == "ugc" or include_audio:
        return "720p"
    return "1080p"


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


def _collect_reference_assets(
    *,
    product_ids: list[str],
    ugc_creator_id: str,
    reference_images: list,
) -> ReferenceAssets:
    uploaded_reference_uris = [
        _file_to_data_uri(upload) for upload in reference_images[:MAX_REFERENCE_IMAGES]
    ]
    product_reference_groups = [list_product_reference_files(product_id) for product_id in product_ids]
    local_product_reference_uris: list[str] = []
    while (
        len(local_product_reference_uris) < MAX_REFERENCE_IMAGES
        and any(product_reference_groups)
    ):
        for group in product_reference_groups:
            if not group:
                continue
            local_product_reference_uris.append(_path_to_data_uri(group.pop(0)))
            if len(local_product_reference_uris) >= MAX_REFERENCE_IMAGES:
                break
    local_creator_reference_uris = (
        [_path_to_data_uri(path) for path in list_ugc_creator_reference_files(ugc_creator_id)]
        if ugc_creator_id
        else []
    )
    return ReferenceAssets(
        combined=(
            uploaded_reference_uris
            + local_product_reference_uris
            + local_creator_reference_uris
        )[:MAX_REFERENCE_IMAGES],
        uploaded=uploaded_reference_uris,
        product=local_product_reference_uris,
        creator=local_creator_reference_uris,
    )


def _model_label_for_id(model_id: str) -> str:
    return MODEL_LABELS.get(model_id, model_id)


def _starter_frame_reference_uris(
    *,
    video_style: str,
    reference_assets: ReferenceAssets,
) -> list[str]:
    ordered = list(reference_assets.uploaded)
    if video_style == "ugc":
        ordered.extend(reference_assets.creator)
        ordered.extend(reference_assets.product)
    else:
        ordered.extend(reference_assets.product)
        ordered.extend(reference_assets.creator)
    return ordered[:MAX_REFERENCE_IMAGES]


def _extract_first_image_url(result: Any) -> str:
    images: Any = []
    if isinstance(result, dict):
        images = result.get("images", [])
    else:
        images = getattr(result, "images", None)
        if images is None:
            data = getattr(result, "data", None)
            if isinstance(data, dict):
                images = data.get("images", [])
            else:
                images = getattr(data, "images", [])
    if not images:
        return ""

    first_image = images[0]
    if isinstance(first_image, dict):
        return first_image.get("url", "") or ""
    return getattr(first_image, "url", "") or ""


def _submit_provider_request(model_id: str, arguments: dict[str, Any]) -> str:
    try:
        handle = fal_client.submit(model_id, arguments)
    except Exception as exc:  # pragma: no cover - network/provider failure
        raise FalSubmissionError(str(exc)) from exc
    return handle.request_id


def _build_image_arguments(
    *,
    product_ids: list[str],
    prompt: str,
    language: str,
    aspect_ratio: str,
    video_style: str,
    video_orientation: str,
    ugc_creator_id: str,
    include_audio: bool,
    reference_images: list,
) -> tuple[str, dict[str, Any], bool]:
    products = [PRODUCTS_BY_ID[product_id] for product_id in product_ids]
    ugc_creator = UGC_CREATORS_BY_ID.get(ugc_creator_id or "")
    reference_assets = _collect_reference_assets(
        product_ids=product_ids,
        ugc_creator_id=ugc_creator_id,
        reference_images=reference_images,
    )
    reference_data_uris = reference_assets.combined
    has_reference_images = bool(reference_data_uris)

    full_prompt = build_generation_prompt(
        products=products,
        content_type="image",
        user_prompt=prompt,
        language=language,
        video_style=video_style,
        video_orientation=video_orientation,
        ugc_creator=ugc_creator,
        has_reference_images=has_reference_images,
        include_audio=include_audio,
    )

    arguments: dict[str, Any] = {
        "prompt": full_prompt,
        "aspect_ratio": aspect_ratio,
        "resolution": "2K",
        "num_images": 1,
        "output_format": "webp",
    }
    model_id = TEXT_IMAGE_MODEL
    if has_reference_images:
        model_id = REFERENCE_IMAGE_MODEL
        arguments["image_urls"] = reference_data_uris
        arguments["limit_generations"] = True

    return model_id, arguments, has_reference_images


def _build_video_pipeline(
    *,
    product_ids: list[str],
    prompt: str,
    language: str,
    aspect_ratio: str,
    video_style: str,
    video_orientation: str,
    ugc_creator_id: str,
    include_audio: bool,
    reference_images: list,
) -> tuple[str, dict[str, Any], bool, dict[str, Any], str]:
    products = [PRODUCTS_BY_ID[product_id] for product_id in product_ids]
    ugc_creator = UGC_CREATORS_BY_ID.get(ugc_creator_id or "")
    reference_assets = _collect_reference_assets(
        product_ids=product_ids,
        ugc_creator_id=ugc_creator_id,
        reference_images=reference_images,
    )
    starter_reference_uris = _starter_frame_reference_uris(
        video_style=video_style,
        reference_assets=reference_assets,
    )
    has_reference_images = bool(reference_assets.combined)

    starter_prompt = build_video_starter_frame_prompt(
        products=products,
        user_prompt=prompt,
        language=language,
        video_style=video_style,
        video_orientation=video_orientation,
        ugc_creator=ugc_creator,
        has_reference_images=bool(starter_reference_uris),
        include_audio=include_audio,
    )
    starter_arguments: dict[str, Any] = {
        "prompt": starter_prompt,
        "aspect_ratio": aspect_ratio,
        "resolution": "2K",
        "num_images": 1,
        "output_format": "webp",
    }
    starter_model_id = TEXT_IMAGE_MODEL
    starter_model_label = "Nano Banana Pro Starter Frame"
    if starter_reference_uris:
        starter_model_id = REFERENCE_IMAGE_MODEL
        starter_model_label = "Nano Banana Pro Edit Starter Frame"
        starter_arguments["image_urls"] = starter_reference_uris
        starter_arguments["limit_generations"] = True

    final_model_id = IMAGE_TO_VIDEO_MODEL
    final_arguments = {
        "prompt": build_generation_prompt(
            products=products,
            content_type="video",
            user_prompt=prompt,
            language=language,
            video_style=video_style,
            video_orientation=video_orientation,
            ugc_creator=ugc_creator,
            has_reference_images=has_reference_images,
            include_audio=include_audio,
        ),
        "aspect_ratio": aspect_ratio,
        "duration": _video_duration(
            video_style=video_style,
            include_audio=include_audio,
        ),
        "resolution": _video_resolution(
            video_style=video_style,
            include_audio=include_audio,
        ),
        "generate_audio": include_audio,
        "negative_prompt": build_negative_prompt(video_style),
        "auto_fix": True,
    }
    pipeline_payload = {
        "final_model_id": final_model_id,
        "final_model_label": _model_label_for_id(final_model_id),
        "final_arguments": final_arguments,
        "used_reference_images": has_reference_images,
    }
    return (
        starter_model_id,
        starter_arguments,
        has_reference_images,
        pipeline_payload,
        starter_model_label,
    )


def submit_generation(
    *,
    product_ids: list[str],
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
    resolved_video_style = video_style or "ad"
    resolved_video_orientation = video_orientation or "portrait"
    video_duration = _video_duration(
        video_style=resolved_video_style,
        include_audio=include_audio,
    )
    video_resolution = _video_resolution(
        video_style=resolved_video_style,
        include_audio=include_audio,
    )

    try:
        if content_type == "image":
            model_id, arguments, used_reference_images = _build_image_arguments(
                product_ids=product_ids,
                prompt=prompt,
                language=language,
                aspect_ratio=aspect_ratio,
                video_style=resolved_video_style,
                video_orientation=resolved_video_orientation,
                ugc_creator_id=ugc_creator_id,
                include_audio=include_audio,
                reference_images=reference_images,
            )
            model_label = _model_label_for_id(model_id)
            request_id = _submit_provider_request(model_id, arguments)
            pipeline_stage = "provider"
            pipeline_payload: dict[str, Any] = {}
        else:
            (
                model_id,
                arguments,
                used_reference_images,
                pipeline_payload,
                model_label,
            ) = _build_video_pipeline(
                product_ids=product_ids,
                prompt=prompt,
                language=language,
                aspect_ratio=aspect_ratio,
                video_style=resolved_video_style,
                video_orientation=resolved_video_orientation,
                ugc_creator_id=ugc_creator_id,
                include_audio=include_audio,
                reference_images=reference_images,
            )
            request_id = _submit_provider_request(model_id, arguments)
            pipeline_stage = "starter_frame"
    except FalSubmissionError:
        raise
    except Exception as exc:
        raise FalSubmissionError(
            "Unable to prepare the generation request. Try shortening the prompt or removing the creator reference photo and try again."
        ) from exc

    guidance_chunks = []
    if content_type == "video":
        guidance_chunks.append(
            f"Video generation now runs in two steps: first a premium starter frame is created with {model_label}, then it is animated with Veo 3.1 Image-to-Video for better product fidelity, more realistic motion, and a stronger opening shot. The final render targets {video_resolution} at {video_duration}."
        )
    if len(product_ids) > 1:
        guidance_chunks.append(
            "Multiple selected products were blended into one combined campaign prompt and shared visual setup."
        )
    if used_reference_images:
        guidance_chunks.append(
            "Reference photos were used to keep the product and creator closer to the real packaging and look."
        )
    else:
        guidance_chunks.append(
            "No reference photos were available, so the result may drift from the exact real-world packaging."
        )
    if content_type == "video":
        guidance_chunks.append(
            "The video should open from a generated in-scene shot, not from the untouched uploaded packshot."
        )
    if content_type == "video" and resolved_video_style == "ugc":
        guidance_chunks.append(
            "UGC audio is locked on and the prompt keeps the creator speaking clearly in the selected language."
        )
    elif content_type == "video" and include_audio:
        guidance_chunks.append(
            "Audio generation is enabled, but the cleanest ad voiceovers still usually come from a dedicated voice tool."
        )

    return SubmissionResult(
        model_id=model_id,
        model_label=model_label,
        request_id=request_id,
        content_type=content_type,
        used_reference_images=used_reference_images,
        guidance_note=" ".join(guidance_chunks),
        pipeline_stage=pipeline_stage,
        pipeline_payload=pipeline_payload,
    )


def submit_staged_video_render(
    *,
    pipeline_payload: dict[str, Any],
    starter_frame_url: str,
) -> SubmissionResult:
    _ensure_fal_key()
    final_model_id = str(pipeline_payload.get("final_model_id") or "")
    if not final_model_id:
        raise FalSubmissionError("Video pipeline is missing its final Veo model.")

    arguments = dict(pipeline_payload.get("final_arguments") or {})
    if not arguments:
        raise FalSubmissionError("Video pipeline is missing its final render arguments.")

    arguments["image_url"] = starter_frame_url
    request_id = _submit_provider_request(final_model_id, arguments)

    return SubmissionResult(
        model_id=final_model_id,
        model_label=str(
            pipeline_payload.get("final_model_label")
            or _model_label_for_id(final_model_id)
        ),
        request_id=request_id,
        content_type="video",
        used_reference_images=bool(pipeline_payload.get("used_reference_images")),
        guidance_note="",
        pipeline_stage="video_render",
        pipeline_payload={},
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
