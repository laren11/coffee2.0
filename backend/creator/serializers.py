from rest_framework import serializers

from .catalog import PRODUCTS, UGC_CREATORS, get_catalog_payload


PRODUCT_IDS = [product["id"] for product in PRODUCTS]
UGC_CREATOR_IDS = [creator["id"] for creator in UGC_CREATORS]
GENERATION_OPTIONS = get_catalog_payload()["generation_options"]
IMAGE_ASPECT_RATIOS = set(GENERATION_OPTIONS["imageAspectRatios"])
VIDEO_ASPECT_RATIOS = set(GENERATION_OPTIONS["videoAspectRatios"])


class GenerationRequestSerializer(serializers.Serializer):
    product_id = serializers.ChoiceField(choices=PRODUCT_IDS)
    content_type = serializers.ChoiceField(choices=["image", "video"])
    prompt = serializers.CharField(max_length=1200, trim_whitespace=True)
    aspect_ratio = serializers.CharField(max_length=10, required=False, allow_blank=True)
    video_style = serializers.ChoiceField(
        choices=["ugc", "ad"],
        required=False,
        allow_blank=True,
    )
    ugc_creator_id = serializers.ChoiceField(
        choices=UGC_CREATOR_IDS,
        required=False,
        allow_blank=True,
    )
    include_audio = serializers.BooleanField(required=False, default=False)

    def validate(self, attrs):
        content_type = attrs["content_type"]
        aspect_ratio = attrs.get("aspect_ratio") or (
            "1:1" if content_type == "image" else "9:16"
        )
        video_style = attrs.get("video_style") or ""
        ugc_creator_id = attrs.get("ugc_creator_id") or ""

        if content_type == "image" and aspect_ratio not in IMAGE_ASPECT_RATIOS:
            raise serializers.ValidationError(
                {"aspect_ratio": "Choose a valid image aspect ratio."}
            )

        if content_type == "video":
            if aspect_ratio not in VIDEO_ASPECT_RATIOS:
                raise serializers.ValidationError(
                    {"aspect_ratio": "Choose a valid video aspect ratio."}
                )
            if not video_style:
                raise serializers.ValidationError(
                    {"video_style": "Select either UGC or Ad video."}
                )
            if video_style == "ugc" and not ugc_creator_id:
                attrs["ugc_creator_id"] = UGC_CREATOR_IDS[0]
        else:
            attrs["ugc_creator_id"] = ""

        attrs["aspect_ratio"] = aspect_ratio
        attrs["video_style"] = video_style
        return attrs
