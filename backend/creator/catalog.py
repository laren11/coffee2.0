from __future__ import annotations

from .assets import (
    list_product_reference_files,
    list_ugc_creator_reference_files,
    product_asset_folder_slug,
    ugc_creator_asset_folder_slug,
)


PRODUCTS = [
    {
        "id": "coffee-2-0",
        "name": "Coffee 2.0",
        "tagline": "The flagship mushroom coffee for focus and clean energy.",
        "description": (
            "A premium functional coffee built around focus, clean energy, digestive "
            "support, and everyday performance."
        ),
        "benefits": [
            "12 g of functional mushrooms per serving",
            "7 adaptogens plus collagen",
            "Built for focus, clean energy, digestion, and immunity",
        ],
        "creative_angles": [
            "morning ritual",
            "desk focus",
            "premium coffee ad",
            "wellness lifestyle content",
        ],
        "palette": ["#6D4A38", "#F5E6D6", "#B97A5B"],
        "base_prompt": (
            "Feature Coffee 2.0 as the hero product in a premium, high-converting "
            "wellness campaign."
        ),
    },
    {
        "id": "refresh-2-0",
        "name": "Refresh 2.0",
        "tagline": "Hydration, cognition, and strength in one daily mix.",
        "description": (
            "A hydration and performance formula designed to support strength, mental "
            "clarity, and all-day performance."
        ),
        "benefits": [
            "5 g of pure creatine monohydrate",
            "4 electrolytes plus vitamins and nootropics",
            "Made for strength, clarity, and performance",
        ],
        "creative_angles": [
            "gym recovery",
            "summer hydration",
            "performance supplement ad",
            "before and after workout content",
        ],
        "palette": ["#177E89", "#D7F3F5", "#74C2C9"],
        "base_prompt": (
            "Present Refresh 2.0 as a modern hydration and performance essential with "
            "a bright, athletic, premium feel."
        ),
    },
    {
        "id": "matcha-2-0",
        "name": "Matcha 2.0",
        "tagline": "Calm energy and mental clarity from premium matcha.",
        "description": (
            "A premium organic matcha blend with mushrooms and adaptogens for calm "
            "energy, focus, and a smoother daily ritual."
        ),
        "benefits": [
            "Organic Japanese matcha",
            "5 medicinal mushrooms and 7 adaptogens",
            "Focus, calm energy, and mental clarity without a hard crash",
        ],
        "creative_angles": [
            "calm morning ritual",
            "minimal matcha cafe aesthetic",
            "creator lifestyle reel",
            "premium wellness flatlay",
        ],
        "palette": ["#738B45", "#EEF5D8", "#ADC178"],
        "base_prompt": (
            "Position Matcha 2.0 as a premium ritual drink for calm, sustained energy "
            "and wellness-forward routines."
        ),
    },
    {
        "id": "collagen-2-0",
        "name": "Collagen 2.0",
        "tagline": "A premium collagen formula for beauty and recovery.",
        "description": (
            "An advanced collagen formula centered on skin, recovery, and total-body "
            "support with a premium wellness identity."
        ),
        "benefits": [
            "20 g of collagen per serving",
            "Positioned for skin, regeneration, and body support",
            "Premium beauty and wellness product storytelling",
        ],
        "creative_angles": [
            "beauty routine",
            "clean bathroom counter ad",
            "soft lifestyle UGC",
            "premium supplement packshot",
        ],
        "palette": ["#C68B7B", "#F9E5DE", "#E7B5A6"],
        "base_prompt": (
            "Show Collagen 2.0 as a premium beauty-and-recovery supplement with a "
            "clean, aspirational, high-trust visual style."
        ),
    },
]

UGC_CREATORS = [
    {
        "id": "founder",
        "name": "Founder",
        "description": (
            "Confident, masculine entrepreneur-style UGC with direct eye contact, "
            "clear speech, and assertive delivery."
        ),
        "persona_prompt": (
            "The speaker should feel like a sharp, high-agency founder talking directly "
            "to camera in a confident but believable way, without imitating any specific "
            "real public figure."
        ),
    },
    {
        "id": "wellness-mentor",
        "name": "Wellness Mentor",
        "description": (
            "Calm, premium lifestyle creator suited for beauty, ritual, and wellness "
            "product storytelling."
        ),
        "persona_prompt": (
            "The speaker should feel warm, grounded, trustworthy, and premium, like a "
            "wellness creator filming an honest recommendation."
        ),
    },
    {
        "id": "performance-creator",
        "name": "Performance Creator",
        "description": (
            "Fitness and performance-focused creator with practical, direct-response "
            "UGC energy."
        ),
        "persona_prompt": (
            "The speaker should feel athletic, credible, energetic, and social-native, "
            "with a performance and routine-focused delivery."
        ),
    },
]

LANGUAGES = [
    {"id": "en", "label": "English", "native_label": "English"},
    {"id": "sl", "label": "Slovenian", "native_label": "Slovenscina"},
    {"id": "hr", "label": "Croatian", "native_label": "Hrvatski"},
    {"id": "de", "label": "German", "native_label": "Deutsch"},
    {"id": "it", "label": "Italian", "native_label": "Italiano"},
]

VIDEO_ORIENTATIONS = [
    {
        "id": "portrait",
        "label": "Portrait",
        "aspect_ratio": "9:16",
        "description": "Best for Reels, TikTok, Stories, and paid social.",
    },
    {
        "id": "landscape",
        "label": "Landscape",
        "aspect_ratio": "16:9",
        "description": "Best for widescreen ads, YouTube, and landing pages.",
    },
]

PRODUCTS_BY_ID = {product["id"]: product for product in PRODUCTS}
UGC_CREATORS_BY_ID = {creator["id"]: creator for creator in UGC_CREATORS}


def _serialize_product(product: dict) -> dict:
    return {
        **product,
        "asset_folder": product_asset_folder_slug(product["id"]),
        "local_reference_count": len(list_product_reference_files(product["id"])),
    }


def _serialize_ugc_creator(creator: dict) -> dict:
    return {
        **creator,
        "asset_folder": ugc_creator_asset_folder_slug(creator["id"]),
        "local_reference_count": len(list_ugc_creator_reference_files(creator["id"])),
    }


def get_catalog_payload() -> dict:
    return {
        "products": [_serialize_product(product) for product in PRODUCTS],
        "generation_options": {
            "imageAspectRatios": ["1:1", "4:5", "16:9", "9:16"],
            "videoAspectRatios": ["9:16", "16:9"],
            "videoStyles": [
                {
                    "id": "ugc",
                    "label": "UGC Video",
                    "description": "Creator-style, handheld, social-first content.",
                },
                {
                    "id": "ad",
                    "label": "Ad Video",
                    "description": "Polished, commercial-style branded content.",
                },
            ],
            "languages": LANGUAGES,
            "videoOrientations": VIDEO_ORIENTATIONS,
            "ugcCreators": [_serialize_ugc_creator(creator) for creator in UGC_CREATORS],
        },
    }
