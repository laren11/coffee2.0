from __future__ import annotations

from typing import Any


VIDEO_STYLE_GUIDANCE = {
    "ugc": (
        "Style the output like authentic creator-made UGC. Use a believable human "
        "presence, handheld or lightly stabilized phone-camera framing, natural light, "
        "relatable locations, and conversational pacing. It should feel native to "
        "TikTok, Reels, and paid social while still looking premium enough to run as an ad."
    ),
    "ad": (
        "Style the output like a polished direct-response commercial. Use premium product "
        "hero shots, crisp lighting, confident camera movement, clean compositions, "
        "strong visual hierarchy, and a high-end wellness advertising aesthetic."
    ),
}


def build_generation_prompt(
    *,
    product: dict[str, Any],
    content_type: str,
    user_prompt: str,
    video_style: str | None,
    ugc_creator: dict[str, Any] | None,
    has_reference_images: bool,
) -> str:
    product_context = (
        f"Product: {product['name']}. "
        f"Positioning: {product['tagline']} "
        f"{product['description']} "
        f"Key benefits: {', '.join(product['benefits'])}. "
        f"Creative angles that fit the brand: {', '.join(product['creative_angles'])}. "
        f"{product['base_prompt']}"
    )

    if has_reference_images:
        fidelity_instruction = (
            "Preserve the exact packaging, logo placement, product silhouette, material "
            "finish, color relationships, and label structure from the reference images. "
            "Do not invent a different product design."
        )
    else:
        fidelity_instruction = (
            "No reference photos were provided. Create a premium visual inspired by the "
            "Coffee 2.0 brand direction, but keep the packaging believable, minimal, and "
            "high-end. Do not include unrelated brands or illegible text-heavy labels."
        )

    shared_quality_bar = (
        "Prioritize realistic materials, premium lighting, clean composition, sharp product "
        "focus, natural skin when people are present, and conversion-oriented ad quality. "
        "Avoid low-quality CGI, warped packaging, duplicate items, floating objects, random "
        "text overlays, subtitles, watermarks, or off-brand clutter."
    )

    if content_type == "image":
        style_block = (
            "Output a high-converting branded still image. Use product-ad photography, "
            "editorial composition, strong focal hierarchy, and social-ready framing."
        )
    else:
        style_block = VIDEO_STYLE_GUIDANCE[video_style or "ad"]

    creator_block = ""
    if video_style == "ugc" and ugc_creator:
        creator_block = (
            f"UGC creator profile: {ugc_creator['name']}. "
            f"{ugc_creator['description']} "
            f"{ugc_creator['persona_prompt']} "
            "If reference photos of the creator are provided, keep the subject consistent "
            "with those photos."
        )

    return " ".join(
        [
            product_context,
            fidelity_instruction,
            style_block,
            creator_block,
            shared_quality_bar,
            f"Creative brief from the user: {user_prompt.strip()}",
        ]
    )


def build_negative_prompt(video_style: str | None) -> str:
    generic = [
        "warped packaging",
        "duplicate product units",
        "unreadable label",
        "extra fingers",
        "deformed face",
        "watermark",
        "subtitles",
        "cheap CGI",
        "unrelated brands",
        "blurry hero product",
    ]
    if video_style == "ugc":
        generic.extend(["overly cinematic studio look", "unnatural influencer pose"])
    return ", ".join(generic)
