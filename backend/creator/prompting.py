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


def _unique_items(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _build_product_context(products: list[dict[str, Any]]) -> str:
    product_names = [product["name"] for product in products]
    taglines = [product["tagline"] for product in products]
    benefits = _unique_items(
        [benefit for product in products for benefit in product["benefits"]]
    )
    creative_angles = _unique_items(
        [angle for product in products for angle in product["creative_angles"]]
    )
    base_prompts = [product["base_prompt"] for product in products]

    if len(products) == 1:
        product = products[0]
        return (
            f"Product: {product['name']}. "
            f"Positioning: {product['tagline']} "
            f"{product['description']} "
            f"Key benefits: {', '.join(product['benefits'])}. "
            f"Creative angles that fit the brand: {', '.join(product['creative_angles'])}. "
            f"{product['base_prompt']}"
        )

    return (
        f"Products featured together: {', '.join(product_names)}. "
        f"Blend these product positionings into one coherent Coffee 2.0 campaign: "
        f"{' '.join(taglines)} "
        f"Show the products as a believable lineup or bundle rather than unrelated isolated items. "
        f"Key benefits across the lineup: {', '.join(benefits)}. "
        f"Creative angles that fit the brand: {', '.join(creative_angles)}. "
        f"{' '.join(base_prompts)}"
    )


def build_generation_prompt(
    *,
    products: list[dict[str, Any]],
    content_type: str,
    user_prompt: str,
    language: str,
    video_style: str | None,
    video_orientation: str | None,
    ugc_creator: dict[str, Any] | None,
    has_reference_images: bool,
    include_audio: bool,
) -> str:
    product_context = _build_product_context(products)

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
                    f"Audio is required. Generate clear native {_language_label(language)} "
                    "speech only from one speaker with clean diction, believable pacing, "
                    "short punchy lines, low background noise, and fully intelligible words. "
                    "Do not switch to English or mix languages unless English was selected. "
                    "The talking should feel like a real creator speaking naturally to camera "
                    "with accurate lip sync and confident delivery."
                )
            else:
                audio_block = (
                    f"If speech is present, use clear native {_language_label(language)} "
                    "voiceover or on-camera dialogue with clean studio-like intelligibility, "
                    "subtle ambient sound, premium ad polish, and no accidental language drift."
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


def build_video_starter_frame_prompt(
    *,
    products: list[dict[str, Any]],
    user_prompt: str,
    language: str,
    video_style: str,
    video_orientation: str | None,
    ugc_creator: dict[str, Any] | None,
    has_reference_images: bool,
    include_audio: bool,
) -> str:
    primary_product = products[0]
    product_names = [product["name"] for product in products]
    lineup_block = ""
    if len(products) > 1:
        lineup_block = (
            f"Feature the selected product lineup together: {', '.join(product_names)}. "
            "Make each selected product readable in the scene and compose them like a purposeful bundle."
        )
    reference_block = (
        "Use the reference images only to preserve the exact real packaging, product identity, "
        "and any creator likeness the user has rights to use."
        if has_reference_images
        else "Keep the product premium and believable within the Coffee 2.0 brand world."
    )
    if video_style == "ugc":
        creator_block = ""
        if ugc_creator:
            creator_block = (
                f"Creator preset: {ugc_creator['name']}. "
                f"{ugc_creator['description']} "
                f"{ugc_creator['persona_prompt']} "
                "If creator reference photos are present, keep the subject consistent with them."
            )
        speech_block = (
            f"Design the frame as the believable split-second before the creator starts "
            f"speaking in {_language_label(language)} with direct eye contact, relaxed mouth, "
            "natural posture, and room for the video to open into clear dialogue."
            if include_audio
            else "Design the frame as a believable creator moment with natural eye line and "
            "social-native body language."
        )
        style_block = (
            "Create a single ultra-realistic opening frame for a creator-made UGC ad. "
            "Use smartphone-native framing, natural light, a believable home, office, gym, "
            "kitchen, or lifestyle environment, and subtle handheld realism without looking messy."
        )
        product_block = (
            "The product should be present naturally in-hand, on a counter, on a desk, or being "
            "introduced into the scene, not as a flat centered packshot."
        )
    else:
        creator_block = ""
        speech_block = (
            f"If speech or voiceover is implied later, the visual setup should still feel native "
            f"to {_language_label(language)}."
        )
        campaign_subject = (
            primary_product["name"]
            if len(products) == 1
            else f"{primary_product['name']} lineup"
        )
        style_block = (
            f"Create a single ultra-realistic opening frame for a premium {campaign_subject} ad. "
            "Use cinematic composition, premium lighting, depth, foreground layering, and "
            "in-scene storytelling that feels photographed rather than rendered."
        )
        product_block = (
            "The product should be integrated into the environment or motion setup naturally, "
            "not staged as a plain background catalog packshot."
        )

    return " ".join(
        [
            style_block,
            lineup_block,
            reference_block,
            product_block,
            VIDEO_ORIENTATION_GUIDANCE.get(video_orientation or "portrait", ""),
            speech_block,
            creator_block,
            "Avoid a flat centered packshot, plain background, generic AI glamor shot, or any "
            "frame that feels like the untouched uploaded reference image.",
            "The frame should feel premium, believable, ad-ready, and strong enough to serve as "
            "the first moment before camera motion begins.",
            f"Creative brief from the user: {user_prompt.strip()}",
        ]
    )


def build_cinematic_keyframe_prompt(
    *,
    products: list[dict[str, Any]],
    user_prompt: str,
    language: str,
    video_orientation: str | None,
    has_reference_images: bool,
) -> str:
    return build_video_starter_frame_prompt(
        products=products,
        user_prompt=user_prompt,
        language=language,
        video_style="ad",
        video_orientation=video_orientation,
        ugc_creator=None,
        has_reference_images=has_reference_images,
        include_audio=False,
    )
