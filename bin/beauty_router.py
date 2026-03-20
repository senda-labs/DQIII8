"""
Beauty Competitive Dashboard — FastAPI router.
Mounted by dashboard.py via app.include_router(beauty_router).
Endpoints are public (read-only analytical data).
"""
from datetime import datetime
from statistics import mean
from typing import Any

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, JSONResponse

from beauty_scraper import BrandData, get_all_brands, calculate_competitive_index

beauty_router = APIRouter()


def _brand_summary(brand: BrandData, all_brands: list, rank: int) -> dict:
    products = brand.products
    return {
        "rank": rank,
        "brand": brand.name,
        "score": calculate_competitive_index(brand, all_brands),
        "avg_price_eur": round(mean(p.price_eur for p in products), 2),
        "avg_rating": round(mean(p.rating for p in products), 2),
        "avg_availability_pct": round(mean(p.availability_pct for p in products) * 100, 1),
        "total_sku_count": sum(p.sku_count for p in products),
        "total_reviews": sum(p.num_reviews for p in products),
    }


def _ranked_brands() -> list:
    brands = get_all_brands()
    scored = sorted(brands, key=lambda b: calculate_competitive_index(b, brands), reverse=True)
    return [_brand_summary(b, brands, i + 1) for i, b in enumerate(scored)]


def _category_matrix(brands: list) -> dict:
    """Returns {category: {brand_name: '€XX.XX' or 'N/A'}}."""
    categories = ["Foundation", "Eyes", "Lips", "Skincare"]
    matrix: dict[str, dict[str, str]] = {}
    for cat in categories:
        matrix[cat] = {}
        for brand in brands:
            prods = [p for p in brand.products if p.category == cat]
            if prods:
                avg = sum(p.price_eur for p in prods) / len(prods)
                matrix[cat][brand.name] = f"€{avg:.2f}"
            else:
                matrix[cat][brand.name] = "N/A"
    return matrix


def _row_color(rank: int, total: int) -> str:
    if rank <= 2:
        return "#14532d"
    if rank <= total - 2:
        return "#713f12"
    return "#7f1d1d"


def _build_html(ranked: list, matrix: dict, brands: list, timestamp: str) -> str:
    brand_names = [b.name for b in brands]
    categories = ["Foundation", "Eyes", "Lips", "Skincare"]
    total = len(ranked)

    table_rows = ""
    for item in ranked:
        color = _row_color(item["rank"], total)
        table_rows += (
            f'<tr style="background:{color}">'
            f'<td>{item["rank"]}</td>'
            f'<td><strong>{item["brand"]}</strong></td>'
            f'<td>{item["score"]}</td>'
            f'<td>€{item["avg_price_eur"]}</td>'
            f'<td>{item["avg_rating"]}</td>'
            f'<td>{item["avg_availability_pct"]}%</td>'
            f'<td>{item["total_sku_count"]}</td>'
            f'<td>{item["total_reviews"]:,}</td>'
            f'</tr>\n'
        )

    chart_labels = str([item["brand"] for item in ranked])
    chart_scores = str([item["score"] for item in ranked])
    chart_colors = str([
        "#22c55e" if item["rank"] <= 2
        else "#f59e0b" if item["rank"] <= total - 2
        else "#ef4444"
        for item in ranked
    ])

    cat_headers = "".join(f"<th>{name}</th>" for name in brand_names)
    cat_rows = ""
    for cat in categories:
        cells = "".join(f'<td>{matrix[cat].get(name, "N/A")}</td>' for name in brand_names)
        cat_rows += f"<tr><td><strong>{cat}</strong></td>{cells}</tr>\n"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Beauty Competitive Analysis</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ background: #0a0a0f; color: #e5e7eb; font-family: monospace; padding: 2rem; }}
    h1 {{ color: #f472b6; font-size: 1.8rem; margin-bottom: .25rem; }}
    .subtitle {{ color: #6b7280; font-size: .85rem; margin-bottom: 2rem; }}
    h2 {{ color: #a78bfa; font-size: 1.1rem; margin: 2rem 0 .75rem; border-bottom: 1px solid #1f2937; padding-bottom: .5rem; }}
    table {{ width: 100%; border-collapse: collapse; font-size: .85rem; margin-bottom: 1rem; }}
    th {{ background: #1f2937; color: #9ca3af; padding: .5rem .75rem; text-align: left; }}
    td {{ padding: .5rem .75rem; border-bottom: 1px solid #1f2937; }}
    .chart-wrap {{ max-width: 900px; background: #111827; border-radius: 8px; padding: 1.5rem; margin-bottom: 1rem; }}
    .legend {{ display: flex; gap: 1.5rem; font-size: .8rem; margin: .75rem 0 2rem; }}
    .dot {{ width: 12px; height: 12px; border-radius: 50%; display: inline-block; margin-right: 4px; vertical-align: middle; }}
    .nav {{ margin-bottom: 2rem; }}
    .nav a {{ color: #60a5fa; text-decoration: none; margin-right: 1rem; font-size: .85rem; }}
    .nav a:hover {{ text-decoration: underline; }}
  </style>
</head>
<body>
  <h1>Beauty Competitive Analysis</h1>
  <p class="subtitle">Data as of: {timestamp} &nbsp;|&nbsp; 6 brands &nbsp;|&nbsp; 4 categories &nbsp;|&nbsp; mock data (Phase 1)</p>

  <div class="nav">
    <a href="/beauty/api/analysis">JSON: Analysis</a>
    <a href="/beauty/api/brands">JSON: All Brands</a>
    <a href="/">Back to Dashboard</a>
  </div>

  <h2>Brand Ranking — Competitive Index</h2>
  <table>
    <thead><tr>
      <th>Rank</th><th>Brand</th><th>Score (0–100)</th>
      <th>Avg Price</th><th>Avg Rating</th><th>Availability</th>
      <th>Total SKUs</th><th>Total Reviews</th>
    </tr></thead>
    <tbody>{table_rows}</tbody>
  </table>

  <div class="legend">
    <span><span class="dot" style="background:#22c55e"></span>Top tier (rank 1–2)</span>
    <span><span class="dot" style="background:#f59e0b"></span>Mid tier (rank 3–4)</span>
    <span><span class="dot" style="background:#ef4444"></span>Bottom tier (rank 5–6)</span>
  </div>

  <h2>Competitive Index by Brand</h2>
  <div class="chart-wrap">
    <canvas id="chart" height="80"></canvas>
  </div>

  <h2>Average Price by Category (€)</h2>
  <table>
    <thead><tr><th>Category</th>{cat_headers}</tr></thead>
    <tbody>{cat_rows}</tbody>
  </table>

  <script>
    new Chart(document.getElementById('chart'), {{
      type: 'bar',
      data: {{
        labels: {chart_labels},
        datasets: [{{
          label: 'Competitive Index',
          data: {chart_scores},
          backgroundColor: {chart_colors},
          borderRadius: 4,
        }}]
      }},
      options: {{
        plugins: {{ legend: {{ display: false }} }},
        scales: {{
          y: {{ min: 0, max: 100, grid: {{ color: '#1f2937' }}, ticks: {{ color: '#9ca3af' }} }},
          x: {{ grid: {{ display: false }}, ticks: {{ color: '#9ca3af', maxRotation: 30 }} }}
        }}
      }}
    }});
  </script>
</body>
</html>"""


# ── Endpoints ──────────────────────────────────────────────────────────────

@beauty_router.get("/beauty", response_class=HTMLResponse)
async def get_dashboard():
    try:
        brands = get_all_brands()
        ranked = _ranked_brands()
        matrix = _category_matrix(brands)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return HTMLResponse(_build_html(ranked, matrix, brands, timestamp))
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@beauty_router.get("/beauty/api/brands")
async def get_brands():
    try:
        brands = get_all_brands()
        return JSONResponse([
            {
                "brand": b.name,
                "products": [
                    {
                        "name": p.name,
                        "category": p.category,
                        "price_eur": p.price_eur,
                        "rating": p.rating,
                        "num_reviews": p.num_reviews,
                        "sku_count": p.sku_count,
                        "availability_pct": p.availability_pct,
                    }
                    for p in b.products
                ],
            }
            for b in brands
        ])
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@beauty_router.get("/beauty/api/analysis")
async def get_analysis():
    try:
        return JSONResponse(_ranked_brands())
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)
