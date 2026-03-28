from __future__ import annotations

from typing import Any


VIDEO_STYLE_GUIDANCE = {
    "ugc": (
        "Style the output like high-performing creator-made UGC. Use a believable human "
        "presence, lightly handheld or gently stabilized phone-camera framing, natural "
        "light, lived-in locations, authentic product interaction, and conversational "
        "social-native pacing."
    ),
    "ad": (
        "Style the output like a premium direct-response commercial. Use cinematic camera "
        "language, realistic lens behavior, premium lighting, elegant motion, tactile "
        "product detail, and a polished wellness-advertising finish."
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
        "Compose for a vertical 9:16 social-first frame. Keep the hook readable on mobile, "
        "fill the frame with clear subject focus, and avoid tiny distant subjects."
    ),
    "landscape": (
        "Compose for a cinematic 16:9 frame. Use lateral movement, layered foreground and "
        "background depth, and premium widescreen compositions."
    ),
}

VIDEO_SEQUENCE_GUIDANCE = {
    "ugc": (
        "Structure the video with a fast hook in the first 2 seconds, one believable proof "
        "or demo moment, a clear product interaction, and a satisfying closing takeaway."
    ),
    "ad": (
        "Structure the video like a premium ad: an in-scene cinematic hook, dynamic benefit "
        "cutaways, persuasive product proof, tasteful pacing changes, and a clean closing "
        "hero moment."
    ),
}


def _language_label(language: str) -> str:
    return LANGUAGE_LABELS.get(language, "English")


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
    include_audio: bool,
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
            "Keep the real product recognizable and avoid inventing a different design."
        )
    else:
        fidelity_instruction = (
            "No reference photos were provided. Create a premium Coffee 2.0-style product "
            "visual with believable packaging, elegant branding, and no unrelated brands."
        )

    shared_quality_bar = (
        "Prioritize realistic lighting, accurate physics, premium materials, natural skin, "
        "clean motion, believable environments, and a high-trust commercial finish. Avoid "
        "cheap CGI, floating objects, warped packaging, broken anatomy, random text overlays, "
        "subtitles, watermarks, clutter, or generic AI aesthetics."
    )
    language_block = (
        f"All spoken dialogue, captions, voiceover, and any CTA text must be in "
        f"{_language_label(language)} only. If text appears, keep it minimal, legible, "
        "premium, and conversion-focused."
    )
    user_brief_block = (
        "Treat the user's custom brief as the highest-priority creative instruction and follow "
        "it precisely unless it conflicts with packaging fidelity or safety constraints."
    )

    if content_type == "image":
        style_block = (
            "Output a high-converting branded still image with editorial product-ad "
            "composition, premium depth, natural reflections, and a clear focal hierarchy."
        )
        orientation_block = ""
        sequence_block = ""
        realism_block = (
            "Make the image feel photographed, not rendered. Use realistic shadows, material "
            "texture, and premium but believable staging."
        )
        opening_guardrail = ""
        audio_block = ""
    else:
        resolved_video_style = video_style or "ad"
        resolved_orientation = video_orientation or "portrait"
        style_block = VIDEO_STYLE_GUIDANCE[resolved_video_style]
        orientation_block = VIDEO_ORIENTATION_GUIDANCE[resolved_orientation]
        sequence_block = VIDEO_SEQUENCE_GUIDANCE[resolved_video_style]
        realism_block = (
            "Make every shot feel captured by a real camera with natural exposure, coherent "
            "depth of field, realistic motion blur, believable body movement, and polished "
            "commercial pacing."
        )
        opening_guardrail = (
            "Do not open on a flat static centered packshot or directly on the untouched "
            "reference image. Start inside a cinematic real-world moment or natural creator "
            "setup, then reveal the product organically."
        )
        if include_audio:
            if resolved_video_style == "ugc":
                audio_block = (
                    f"Generate clear native {_language_label(language)} speech from one "
                    "speaker with clean diction, believable pacing, short punchy lines, low "
                    "background noise, and intelligible words. The talking should feel like a "
                    "real creator speaking naturally to camera."
                )
            else:
                audio_block = (
                    f"If speech is present, use clear native {_language_label(language)} "
                    "voiceover or on-camera dialogue with clean studio-like intelligibility, "
                    "subtle ambient sound, and premium ad polish."
                )
        else:
            audio_block = (
                "No generated dialogue is required. Let the visuals feel strong enough to work "
                "even without native audio."
            )

    creator_block = ""
    if video_style == "ugc" and ugc_creator:
        creator_block = (
            f"UGC creator profile: {ugc_creator['name']}. "
            f"{ugc_creator['description']} "
            f"{ugc_creator['persona_prompt']} "
            "If creator reference photos are provided, keep the subject consistent with those "
            "photos. Without creator photos, use the preset only as a tone and delivery guide, "
            "not as a specific real person."
        )

    return " ".join(
        block
        for block in [
            product_context,
            fidelity_instruction,
            style_block,
            orientation_block,
            sequence_block,
            realism_block,
            opening_guardrail,
            creator_block,
            audio_block,
            language_block,
            user_brief_block,
            shared_quality_bar,
            f"Creative brief from the user: {user_prompt.strip()}",
        ]
        if block
    )


def build_negative_prompt(video_style: str | None) -> str:
    generic = [
        "warped packaging",
        "duplicate product units",
        "unreadable label",
        "floating product",
        "deformed face",
        "extra fingers",
        "cheap CGI",
        "glitchy motion",
        "rubbery facial expressions",
        "unrelated brands",
        "watermark",
        "subtitles",
        "cartoon look",
        "plastic skin",
        "blurry hero product",
    ]
    if video_style == "ugc":
        generic.extend(["overly cinematic studio lighting", "stiff influencer posing"])
    else:
        generic.extend(["amateur phone footage", "flat lighting", "awkward handheld shake"])
    return ", ".join(generic)


def build_cinematic_keyframe_prompt(
    *,
    product: dict[str, Any],
    user_prompt: str,
    language: str,
    video_orientation: str | None,
    has_reference_images: bool,
) -> str:
    reference_block = (
        "Use the reference images only to preserve packaging fidelity and product identity."
        if has_reference_images
        else "Keep the product premium and believable within the Coffee 2.0 brand world."
    )
    return " ".join(
        [
            f"Create a single cinematic opening frame for a premium {product['name']} ad.",
            reference_block,
            "Do not create a centered static packshot on a plain background.",
            "Show the product inside a realistic in-scene moment with premium lighting, depth, "
            "foreground interest, and strong cinematic composition.",
            VIDEO_ORIENTATION_GUIDANCE.get(video_orientation or "portrait", ""),
            f"Any visible text or spoken context implied by the scene should align with {_language_label(language)}.",
            "The frame should feel expensive, realistic, ad-ready, and suitable as the first "
            "shot of a high-converting commercial.",
            f"Creative brief from the user: {user_prompt.strip()}",
        ]
    )
