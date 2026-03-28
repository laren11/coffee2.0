from django.urls import path

from .views import (
    AuthLoginView,
    AuthMeView,
    GenerationStatusView,
    GenerateContentView,
    HealthView,
    ProductCatalogView,
)


urlpatterns = [
    path("health/", HealthView.as_view(), name="health"),
    path("auth/login/", AuthLoginView.as_view(), name="auth-login"),
    path("auth/me/", AuthMeView.as_view(), name="auth-me"),
    path("products/", ProductCatalogView.as_view(), name="products"),
    path("generate/", GenerateContentView.as_view(), name="generate"),
    path("generate/status/", GenerationStatusView.as_view(), name="generate-status"),
]
