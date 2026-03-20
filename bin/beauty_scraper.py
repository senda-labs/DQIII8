"""
Beauty Competitive Scraper — Phase 1: structured mock data.
Phase 2: replace get_all_brands() with real HTTP scrapers.
"""
from dataclasses import dataclass
from statistics import mean
from typing import List


@dataclass(frozen=True)
class Product:
    name: str
    category: str          # Foundation | Eyes | Lips | Skincare
    price_eur: float
    rating: float          # 1.0–5.0
    num_reviews: int
    sku_count: int
    availability_pct: float  # [0.0, 1.0]


@dataclass(frozen=True)
class BrandData:
    name: str
    products: tuple


def get_all_brands() -> List[BrandData]:
    """Return mock beauty brand data. Replace body for Phase 2 real scraping."""
    return [
        BrandData("Sephora Collection", (
            Product("Best Skin Ever Foundation", "Foundation", 32.0, 4.5, 12400, 18, 0.95),
            Product("Colorful Eyeshadow Palette", "Eyes", 28.0, 4.3, 8900, 12, 0.90),
            Product("Cream Lip Stain", "Lips", 22.0, 4.6, 15200, 24, 0.92),
            Product("Triple Firming Neck Cream", "Skincare", 55.0, 4.1, 4300, 6, 0.88),
        )),
        BrandData("MAC Cosmetics", (
            Product("Studio Fix Fluid SPF15", "Foundation", 45.0, 4.4, 22100, 22, 0.91),
            Product("Eye Shadow x9", "Eyes", 38.0, 4.5, 11300, 9, 0.85),
            Product("Lipstick Matte", "Lips", 26.0, 4.7, 31000, 30, 0.93),
            Product("Strobe Cream", "Skincare", 40.0, 4.2, 9800, 8, 0.80),
        )),
        BrandData("L'Oréal Paris", (
            Product("Infallible 24H Fresh Wear", "Foundation", 18.0, 4.2, 31000, 20, 0.97),
            Product("Color Riche Mono Eyeshadow", "Eyes", 9.0, 4.0, 7600, 14, 0.89),
            Product("Color Riche Lipstick", "Lips", 12.0, 4.3, 28400, 28, 0.96),
            Product("Age Perfect Serum", "Skincare", 28.0, 4.1, 12100, 10, 0.93),
        )),
        BrandData("Maybelline", (
            Product("Fit Me Matte+Poreless", "Foundation", 14.0, 4.3, 45200, 24, 0.98),
            Product("Eye Studio Color Tattoo", "Eyes", 8.0, 4.1, 13400, 16, 0.91),
            Product("SuperStay Matte Ink", "Lips", 11.0, 4.5, 52000, 32, 0.97),
            Product("Dream Pure BB", "Skincare", 12.0, 3.9, 8700, 8, 0.90),
        )),
        BrandData("NYX Professional", (
            Product("Can't Stop Won't Stop Foundation", "Foundation", 16.0, 4.1, 18900, 16, 0.88),
            Product("Lid Lingerie Eyeshadow Palette", "Eyes", 15.0, 4.4, 9200, 10, 0.82),
            Product("Soft Matte Lip Cream", "Lips", 9.0, 4.6, 38700, 26, 0.94),
            Product("Bare With Me Serum", "Skincare", 20.0, 4.0, 5100, 7, 0.79),
        )),
        BrandData("Rimmel London", (
            Product("Lasting Finish Foundation", "Foundation", 11.0, 3.9, 14300, 14, 0.84),
            Product("Scandaleyes Eyeshadow Palette", "Eyes", 10.0, 3.8, 6800, 8, 0.76),
            Product("Lasting Finish Lipstick", "Lips", 8.0, 4.0, 19600, 20, 0.82),
            Product("Kind & Free Moisturiser", "Skincare", 15.0, 3.7, 3200, 5, 0.72),
        )),
    ]


def _normalize(values: List[float]) -> List[float]:
    """Min-max normalize. If min == max, return 0.5 for all (neutral)."""
    lo, hi = min(values), max(values)
    if hi == lo:
        return [0.5] * len(values)
    return [(v - lo) / (hi - lo) for v in values]


def calculate_competitive_index(brand: BrandData, all_brands: List[BrandData]) -> float:
    """
    Compute competitive index in [0, 100] for a brand relative to all_brands.

    Weights:
      rating       40%  — quality signal
      price (inv)  30%  — lower price = better
      reviews      20%  — popularity proxy
      sku_count     5%  — product breadth
      availability  5%  — stock health
    """
    def brand_avg(b: BrandData, field: str) -> float:
        return mean(getattr(p, field) for p in b.products)

    ratings        = [brand_avg(b, "rating")           for b in all_brands]
    prices         = [brand_avg(b, "price_eur")         for b in all_brands]
    reviews        = [brand_avg(b, "num_reviews")       for b in all_brands]
    skus           = [brand_avg(b, "sku_count")         for b in all_brands]
    availabilities = [brand_avg(b, "availability_pct") for b in all_brands]

    idx = next(i for i, b in enumerate(all_brands) if b.name == brand.name)

    rating_norm  = _normalize(ratings)[idx]
    price_norm   = _normalize(prices)[idx]
    reviews_norm = _normalize(reviews)[idx]
    sku_norm     = _normalize(skus)[idx]
    avail_norm   = availabilities[idx]       # already [0.0, 1.0]

    score = (
        rating_norm            * 100 * 0.40
        + (1 - price_norm)     * 100 * 0.30
        + reviews_norm         * 100 * 0.20
        + sku_norm             * 100 * 0.05
        + avail_norm           * 100 * 0.05
    )
    return round(score, 2)
