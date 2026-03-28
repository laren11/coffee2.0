from __future__ import annotations

from django.conf import settings
from django.db import models


class GenerationRecord(models.Model):
    STATUS_CHOICES = [
        ("queued", "Queued"),
        ("processing", "Processing"),
        ("completed", "Completed"),
        ("failed", "Failed"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="generation_records",
    )
    job_token = models.CharField(max_length=255, unique=True)
    model_id = models.CharField(max_length=255)
    model_label = models.CharField(max_length=255)
    product_id = models.CharField(max_length=100)
    product_name = models.CharField(max_length=255)
    content_type = models.CharField(max_length=20)
    language = models.CharField(max_length=20, default="en")
    video_style = models.CharField(max_length=20, blank=True)
    video_orientation = models.CharField(max_length=20, blank=True)
    aspect_ratio = models.CharField(max_length=20, blank=True)
    prompt = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="queued")
    used_reference_images = models.BooleanField(default=False)
    guidance_note = models.TextField(blank=True)
    error_message = models.TextField(blank=True)
    result_description = models.TextField(blank=True)
    assets = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.product_name} {self.content_type} ({self.status})"
