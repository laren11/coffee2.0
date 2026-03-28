from rest_framework import serializers

from .catalog import LANGUAGES, PRODUCTS, UGC_CREATORS, VIDEO_ORIENTATIONS, get_catalog_payload


PRODUCT_IDS = [product["id"] for product in PRODUCTS]
UGC_CREATOR_IDS = [creator["id"] for creator in UGC_CREATORS]
UGC_CREATOR_ID_ALIASES = {
    "assertive-founder": "founder",
    "high-energy-founder": "founder",
}
UGC_CREATOR_CHOICES = list(dict.fromkeys(UGC_CREATOR_IDS + list(UGC_CREATOR_ID_ALIASES)))
LANGUAGE_IDS = [language["id"] for language in LANGUAGES]
VIDEO_ORIENTATION_IDS = [orientation["id"] for orientation in VIDEO_ORIENTATIONS]
VIDEO_ORIENTATION_TO_RATIO = {
    orientation["id"]: orientation["aspect_ratio"] for orientation in VIDEO_ORIENTATIONS
}
RATIO_TO_VIDEO_ORIENTATION = {
    orientation["aspect_ratio"]: orientation["id"] for orientation in VIDEO_ORIENTATIONS
}
GENERATION_OPTIONS = get_catalog_payload()["generation_options"]
IMAGE_ASPECT_RATIOS = set(GENERATION_OPTIONS["imageAspectRatios"])
VIDEO_ASPECT_RATIOS = set(GENERATION_OPTIONS["videoAspectRatios"])


class GenerationRequestSerializer(serializers.Serializer):
    product_id = serializers.ChoiceField(choices=PRODUCT_IDS)
    content_type = serializers.ChoiceField(choices=["image", "video"])
    prompt = serializers.CharField(max_length=1200, trim_whitespace=True)
    aspect_ratio = serializers.CharField(max_length=10, required=False, allow_blank=True)
    language = serializers.ChoiceField(choices=LANGUAGE_IDS, required=False, allow_blank=True)
    video_style = serializers.ChoiceField(
        choices=["ugc", "ad"],
        required=False,
        allow_blank=True,
    )
    video_orientation = serializers.ChoiceField(
        choices=VIDEO_ORIENTATION_IDS,
        required=False,
        allow_blank=True,
    )
    ugc_creator_id = serializers.ChoiceField(
        choices=UGC_CREATOR_CHOICES,
        required=False,
        allow_blank=True,
    )
    include_audio = serializers.BooleanField(required=False, default=False)

    def validate(self, attrs):
        content_type = attrs["content_type"]
        aspect_ratio = attrs.get("aspect_ratio") or ""
        language = attrs.get("language") or "en"
        video_style = attrs.get("video_style") or ""
        video_orientation = attrs.get("video_orientation") or ""
        ugc_creator_id = attrs.get("ugc_creator_id") or ""
        ugc_creator_id = UGC_CREATOR_ID_ALIASES.get(ugc_creator_id, ugc_creator_id)

        if content_type == "image":
            aspect_ratio = aspect_ratio or "1:1"
            if aspect_ratio not in IMAGE_ASPECT_RATIOS:
                raise serializers.ValidationError(
                    {"aspect_ratio": "Choose a valid image aspect ratio."}
                )
            video_orientation = ""

        if content_type == "video":
            if video_orientation:
                aspect_ratio = VIDEO_ORIENTATION_TO_RATIO[video_orientation]
            else:
                aspect_ratio = aspect_ratio or "9:16"
                video_orientation = RATIO_TO_VIDEO_ORIENTATION.get(aspect_ratio, "")

            if aspect_ratio not in VIDEO_ASPECT_RATIOS:
                raise serializers.ValidationError(
                    {"aspect_ratio": "Choose a valid video aspect ratio."}
                )
            if not video_orientation:
                raise serializers.ValidationError(
                    {"video_orientation": "Select portrait or landscape."}
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
        attrs["language"] = language
        attrs["video_style"] = video_style
        attrs["video_orientation"] = video_orientation
        attrs["ugc_creator_id"] = ugc_creator_id
        return attrs
