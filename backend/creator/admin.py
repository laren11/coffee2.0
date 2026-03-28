from django.contrib import admin

from .models import GenerationRecord


@admin.register(GenerationRecord)
class GenerationRecordAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "product_name",
        "content_type",
        "status",
        "model_label",
        "created_at",
    )
    list_filter = ("status", "content_type", "language", "video_style")
    search_fields = ("user__username", "product_name", "prompt", "job_token")
