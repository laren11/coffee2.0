from __future__ import annotations

from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
PRODUCT_ASSETS_ROOT = BASE_DIR / "assets" / "products"
UGC_CREATOR_ASSETS_ROOT = BASE_DIR / "assets" / "ugc-creators"


def _list_reference_files(folder: Path) -> list[Path]:
    if not folder.exists():
        return []
    return sorted(
        [
            path
            for path in folder.iterdir()
            if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
        ]
    )


def product_asset_folder_slug(product_id: str) -> str:
    return f"backend/assets/products/{product_id}"


def ugc_creator_asset_folder_slug(creator_id: str) -> str:
    return f"backend/assets/ugc-creators/{creator_id}"


def list_product_reference_files(product_id: str) -> list[Path]:
    return _list_reference_files(PRODUCT_ASSETS_ROOT / product_id)


def list_ugc_creator_reference_files(creator_id: str) -> list[Path]:
    return _list_reference_files(UGC_CREATOR_ASSETS_ROOT / creator_id)
