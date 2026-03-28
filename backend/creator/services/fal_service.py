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

from creator.assets import list_product_reference_files, list_ugc_creator_reference_files
from creator.catalog import PRODUCTS_BY_ID, UGC_CREATORS_BY_ID
from creator.prompting import (
    build_generation_prompt,
    build_negative_prompt,
    build_video_starter_frame_prompt,
)


TEXT_IMAGE_MODEL = "fal-ai/nano-banana-pro"
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


@dataclass
class ReferenceAssets:
    combined: list[str]
    uploaded: list[str]
    product: list[str]
    creator: list[str]


def _sync_video_starter_frames_enabled() -> bool:
    return os.getenv("ENABLE_SYNC_VIDEO_STARTER_FRAME", "").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


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


def _select_model(
    *,
    content_type: str,
    reference_count: int,
    video_style: str,
    use_sync_starter_frame: bool,
) -> tuple[str, str]:
    if content_type == "image":
        if reference_count:
            return REFERENCE_IMAGE_MODEL, "Nano Banana Pro Edit"
        return TEXT_IMAGE_MODEL, "Nano Banana Pro"

    if use_sync_starter_frame:
        return IMAGE_TO_VIDEO_MODEL, "Veo 3.1 Fast Image-to-Video"
    if reference_count:
        return IMAGE_TO_VIDEO_MODEL, "Veo 3.1 Fast Image-to-Video"
    return TEXT_VIDEO_MODEL, "Veo 3.1 Fast Text-to-Video"


def _model_label_for_id(model_id: str) -> str:
    return {
        TEXT_IMAGE_MODEL: "Nano Banana Pro",
        REFERENCE_IMAGE_MODEL: "Nano Banana Pro Edit",
        TEXT_VIDEO_MODEL: "Veo 3.1 Fast Text-to-Video",
        IMAGE_TO_VIDEO_MODEL: "Veo 3.1 Fast Image-to-Video",
        REFERENCE_VIDEO_MODEL: "Veo 3.1 Reference-to-Video",
    }[model_id]


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


def _choose_video_anchor_image_url(
    *,
    video_style: str,
    reference_assets: ReferenceAssets,
) -> str:
    ordered = _starter_frame_reference_uris(
        video_style=video_style,
        reference_assets=reference_assets,
    )
    return ordered[0] if ordered else ""


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


def _request_video_starter_frame(
    *,
    prompt_text: str,
    video_orientation: str,
    reference_uris: list[str],
) -> str:
    arguments: dict[str, Any] = {
        "prompt": prompt_text,
        "aspect_ratio": "16:9" if video_orientation == "landscape" else "9:16",
        "resolution": "2K",
        "num_images": 1,
    }
    model_id = TEXT_IMAGE_MODEL
    if reference_uris:
        model_id = REFERENCE_IMAGE_MODEL
        arguments["image_urls"] = reference_uris
        arguments["limit_generations"] = True

    try:
        result = fal_client.subscribe(model_id, arguments)
    except Exception as exc:  # pragma: no cover - network/provider failure
        raise FalSubmissionError(
            "Unable to prepare the opening frame for the video."
        ) from exc

    image_url = _extract_first_image_url(result)
    if not image_url:
        raise FalSubmissionError(
            "fal.ai did not return a usable starter frame for the video."
        )
    return image_url


def _generate_video_starter_frame_url(
    *,
    product_ids: list[str],
    prompt: str,
    language: str,
    video_style: str,
    video_orientation: str,
    ugc_creator_id: str,
    include_audio: bool,
    reference_assets: ReferenceAssets,
) -> str:
    products = [PRODUCTS_BY_ID[product_id] for product_id in product_ids]
    ugc_creator = UGC_CREATORS_BY_ID.get(ugc_creator_id or "")
    primary_reference_uris = _starter_frame_reference_uris(
        video_style=video_style,
        reference_assets=reference_assets,
    )
    prompt_text = build_video_starter_frame_prompt(
        products=products,
        user_prompt=prompt,
        language=language,
        video_style=video_style,
        video_orientation=video_orientation,
        ugc_creator=ugc_creator,
        has_reference_images=bool(primary_reference_uris),
        include_audio=include_audio,
    )
    attempt_reference_sets = [primary_reference_uris]
    if reference_assets.product:
        attempt_reference_sets.append(reference_assets.product[:MAX_REFERENCE_IMAGES])
    attempt_reference_sets.append([])

    seen_reference_sets: set[tuple[str, ...]] = set()
    last_error: FalSubmissionError | None = None
    for reference_uris in attempt_reference_sets:
        reference_key = tuple(reference_uris)
        if reference_key in seen_reference_sets:
            continue
        seen_reference_sets.add(reference_key)
        try:
            return _request_video_starter_frame(
                prompt_text=prompt_text,
                video_orientation=video_orientation,
                reference_uris=reference_uris,
            )
        except FalSubmissionError as exc:
            last_error = exc

    if last_error:
        raise last_error
    raise FalSubmissionError("Unable to prepare the opening frame for the video.")


def _build_arguments(
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
) -> tuple[str, dict[str, Any], bool, bool]:
    products = [PRODUCTS_BY_ID[product_id] for product_id in product_ids]
    ugc_creator = UGC_CREATORS_BY_ID.get(ugc_creator_id or "")
    reference_assets = _collect_reference_assets(
        product_ids=product_ids,
        ugc_creator_id=ugc_creator_id,
        reference_images=reference_images,
    )
    reference_data_uris = reference_assets.combined
    use_sync_starter_frame = (
        content_type == "video" and _sync_video_starter_frames_enabled()
    )
    model_id, _ = _select_model(
        content_type=content_type,
        reference_count=len(reference_data_uris),
        video_style=video_style or "ad",
        use_sync_starter_frame=use_sync_starter_frame,
    )
    has_reference_images = bool(reference_data_uris)
    used_generated_starter_frame = False

    full_prompt = build_generation_prompt(
        products=products,
        content_type=content_type,
        user_prompt=prompt,
        language=language,
        video_style=video_style,
        video_orientation=video_orientation,
        ugc_creator=ugc_creator,
        has_reference_images=has_reference_images,
        include_audio=include_audio,
    )

    if content_type == "image":
        arguments: dict[str, Any] = {
            "prompt": full_prompt,
            "aspect_ratio": aspect_ratio,
            "resolution": "2K",
            "num_images": 1,
            "output_format": "webp",
        }
        if has_reference_images:
            arguments["image_urls"] = reference_data_uris
            arguments["limit_generations"] = True
        return model_id, arguments, has_reference_images, used_generated_starter_frame

    arguments = {
        "prompt": full_prompt,
        "aspect_ratio": aspect_ratio,
        "duration": _video_duration(
            video_style=video_style or "ad",
            include_audio=include_audio,
        ),
        "resolution": "720p",
        "generate_audio": include_audio,
        "negative_prompt": build_negative_prompt(video_style),
        "auto_fix": True,
    }

    if use_sync_starter_frame:
        starter_frame_url = _generate_video_starter_frame_url(
            product_ids=product_ids,
            prompt=prompt,
            language=language,
            video_style=video_style or "ad",
            video_orientation=video_orientation or "portrait",
            ugc_creator_id=ugc_creator_id,
            include_audio=include_audio,
            reference_assets=reference_assets,
        )
        used_generated_starter_frame = True
        arguments["image_url"] = starter_frame_url
        return model_id, arguments, has_reference_images, used_generated_starter_frame

    if model_id == IMAGE_TO_VIDEO_MODEL:
        anchor_image_url = _choose_video_anchor_image_url(
            video_style=video_style or "ad",
            reference_assets=reference_assets,
        )
        if anchor_image_url:
            arguments["image_url"] = anchor_image_url
    return model_id, arguments, has_reference_images, used_generated_starter_frame


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
    video_duration = _video_duration(
        video_style=video_style or "ad",
        include_audio=include_audio,
    )
    try:
        model_id, arguments, used_reference_images, used_generated_starter_frame = (
            _build_arguments(
                product_ids=product_ids,
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
        )
    except FalSubmissionError:
        raise
    except Exception as exc:
        raise FalSubmissionError(
            "Unable to prepare the generation request. Try shortening the prompt or removing the creator reference photo and try again."
        ) from exc
    model_label = _model_label_for_id(model_id)

    try:
        handle = fal_client.submit(model_id, arguments)
    except Exception as exc:  # pragma: no cover - network/provider failure
        raise FalSubmissionError(str(exc)) from exc

    guidance_chunks = []
    if content_type == "video":
        if used_generated_starter_frame:
            guidance_chunks.append(
                f"Video generation now builds a custom starter frame first and then animates it with Veo 3.1 Fast for a stronger opening shot. Clip length is set to {video_duration} for faster turnaround."
            )
        else:
            guidance_chunks.append(
                f"Video generation uses the faster direct Veo 3.1 Fast submission flow so the hosted app can return a job immediately and avoid request timeouts. Clip length is set to {video_duration} for faster turnaround."
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
    if used_generated_starter_frame:
        guidance_chunks.append(
            "The video should open on a generated scene frame instead of the untouched uploaded packshot."
        )
    if content_type == "video" and video_style == "ugc":
        guidance_chunks.append(
            "UGC audio is locked on and the prompt keeps the creator speaking in the selected language."
        )
    elif content_type == "video" and include_audio:
        guidance_chunks.append(
            "Audio generation is enabled, but the cleanest ad voiceovers still usually come from a separate dedicated voice tool."
        )

    return SubmissionResult(
        model_id=model_id,
        model_label=model_label,
        request_id=handle.request_id,
        content_type=content_type,
        used_reference_images=used_reference_images,
        guidance_note=" ".join(guidance_chunks),
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
