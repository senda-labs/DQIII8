"""Tests for beauty competitive dashboard."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "bin"))

from beauty_scraper import get_all_brands, calculate_competitive_index

CATEGORIES = {"Foundation", "Eyes", "Lips", "Skincare"}


def test_get_all_brands_returns_data():
    brands = get_all_brands()
    assert len(brands) > 0
    for brand in brands:
        cat_names = {p.category for p in brand.products}
        assert cat_names == CATEGORIES, f"{brand.name} missing categories: {CATEGORIES - cat_names}"


def test_competitive_index_range():
    brands = get_all_brands()
    for brand in brands:
        score = calculate_competitive_index(brand, brands)
        assert 0.0 <= score <= 100.0, f"{brand.name} score {score} out of [0, 100]"
