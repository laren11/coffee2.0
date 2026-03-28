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

LANGUAGE_LABELS = {
    "en": "English",
    "sl": "Slovenian",
    "hr": "Croatian",
    "de": "German",
    "it": "Italian",
}

VIDEO_ORIENTATION_GUIDANCE = {
    "portrait": (
        "Compose for a vertical 9:16 social-first frame. Keep the subject large in frame, "
        "front-load the hook, and make the visuals feel premium on mobile."
    ),
    "landscape": (
        "Compose for a widescreen 16:9 frame. Use cinematic lateral movement, polished "
        "product staging, and balanced compositions that look premium on desktop and TV."
    ),
}

VIDEO_SEQUENCE_GUIDANCE = {
    "ugc": (
        "Structure the video with a fast hook in the first 2 seconds, a relatable proof or "
        "demo moment, a clear product interaction, and a satisfying closing payoff shot."
    ),
    "ad": (
        "Structure the video like a premium ad: strong hero opener, dynamic benefit cutaways, "
        "tasteful motion, persuasive product proof, and a clean final hero packshot."
    ),
}


def build_generation_prompt(
    *,
    product: dict[str, Any],
    content_type: str,
    user_prompt: str,
    language: str,
    video_style: str | None,
    video_orientation: str | None,
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
    language_block = (
        f"All spoken dialogue, captions, voiceover, and any on-screen CTA text must be in "
        f"{LANGUAGE_LABELS.get(language, 'English')} only. If text appears, keep it short, "
        "legible, premium, and conversion-focused."
    )
    user_brief_block = (
        "Treat the user's custom brief as the highest-priority creative instruction and follow "
        "it precisely unless it conflicts with packaging fidelity or safety constraints."
    )

    if content_type == "image":
        style_block = (
            "Output a high-converting branded still image. Use product-ad photography, "
            "editorial composition, strong focal hierarchy, and social-ready framing."
        )
        orientation_block = ""
        sequence_block = ""
    else:
        style_block = VIDEO_STYLE_GUIDANCE[video_style or "ad"]
        orientation_block = VIDEO_ORIENTATION_GUIDANCE[video_orientation or "portrait"]
        sequence_block = VIDEO_SEQUENCE_GUIDANCE[video_style or "ad"]

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
            orientation_block,
            sequence_block,
            creator_block,
            language_block,
            user_brief_block,
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
