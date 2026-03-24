# Technical SEO

## Core Web Vitals (Google ranking signals since 2021)
| Metric | Good | Needs Improvement | Poor |
|--------|------|------------------|------|
| LCP (Largest Contentful Paint) | <2.5s | 2.5–4.0s | >4.0s |
| INP (Interaction to Next Paint) | <200ms | 200–500ms | >500ms |
| CLS (Cumulative Layout Shift) | <0.1 | 0.1–0.25 | >0.25 |

- LCP: main content load speed (hero image, H1, above-fold block)
- INP: responsiveness to all user interactions (replaced FID in March 2024)
- CLS: visual stability (images without dimensions, injected ads, web fonts)

## Crawlability

### robots.txt
```
User-agent: *
Disallow: /admin/
Disallow: /checkout/
Allow: /
Sitemap: https://example.com/sitemap.xml
```
- Located at domain root: `/robots.txt`
- Googlebot respects Disallow but can still index disallowed URLs if linked

### Sitemap.xml
- XML format, max 50,000 URLs or 50MB per sitemap
- Include: `<loc>`, `<lastmod>`, `<changefreq>`, `<priority>`
- Submit in Google Search Console → Sitemaps

### Crawl Budget
```
Crawl budget = crawl rate limit × crawl demand
```
- Wasted on: duplicate URLs, infinite scroll, session IDs in URLs, broken links
- Critical for large sites (>10,000 pages): use canonical tags, noindex, pagination

## Indexing Controls
- `<meta name="robots" content="noindex,nofollow">`: prevent indexing of page
- `rel="canonical"`: consolidate duplicate content to preferred URL
- Hreflang: `<link rel="alternate" hreflang="es" href="...">` for multilingual
- `X-Robots-Tag`: HTTP header equivalent for non-HTML resources

## Schema Markup (Structured Data)
```json
{
  "@context": "https://schema.org",
  "@type": "Article",
  "headline": "...",
  "datePublished": "2025-01-01",
  "author": {"@type": "Person", "name": "..."}
}
```
Types: Article, Product, FAQ, HowTo, LocalBusiness, BreadcrumbList, Review
Rich results eligibility requires valid schema + content match.

## Authority Metrics (Moz methodology)
```
Domain Authority (DA): 0–100 logarithmic scale
  Input: linking root domains, MozRank, MozTrust
  Not a Google metric — proxy for ranking potential

Page Authority (PA): same algorithm at page level
  PA ≈ f(inbound links, link quality, anchor text diversity)
```
- DA 1–20: new/weak domain
- DA 40–60: established, competitive for mid-tail
- DA 60+: authoritative, competitive for head terms

## Technical Checklist
- HTTPS on all pages (HTTP → 301 redirect)
- Mobile-first indexing (Google uses mobile version for ranking)
- Page speed: compress images (WebP), minify CSS/JS, lazy loading
- Broken links (4xx): fix or 301-redirect
- Redirect chains: max 1 hop (A→B→C = bad; A→C = good)
