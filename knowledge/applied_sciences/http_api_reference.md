---
domain: applied_sciences
agent: web-specialist
keywords_es: [HTTP, estado, REST, API, endpoint, autenticación, JWT, OAuth, WebSocket, código estado, CORS, CSP, seguridad, cabecera]
keywords_en: [HTTP, status, REST, API, endpoint, authentication, JWT, OAuth, WebSocket, status code, CORS, CSP, security, header]
---

# HTTP & API Reference

## HTTP Status Codes (Complete)

### 1xx — Informational
| Code | Name | Use |
|------|------|-----|
| 100 | Continue | client should continue sending request body |
| 101 | Switching Protocols | upgrading to WebSocket |
| 103 | Early Hints | preload hints before final response |

### 2xx — Success
| Code | Name | Use |
|------|------|-----|
| 200 | OK | standard success; has body |
| 201 | Created | resource created; include Location header |
| 202 | Accepted | async processing; not yet complete |
| 204 | No Content | success; no body (DELETE, PATCH with no return) |
| 206 | Partial Content | range request (video streaming) |

### 3xx — Redirection
| Code | Name | Use |
|------|------|-----|
| 301 | Moved Permanently | SEO-safe redirect; browser caches |
| 302 | Found | temporary redirect; POST → GET (browser rewrites method) |
| 304 | Not Modified | conditional GET; use cache |
| 307 | Temporary Redirect | keeps HTTP method (POST stays POST) |
| 308 | Permanent Redirect | like 301 but keeps method |

### 4xx — Client Errors
| Code | Name | Use |
|------|------|-----|
| 400 | Bad Request | malformed syntax, invalid params |
| 401 | Unauthorized | authentication required / failed ("not logged in") |
| 403 | Forbidden | authenticated but no permission ("logged in but can't access") |
| 404 | Not Found | resource doesn't exist |
| 405 | Method Not Allowed | endpoint exists but not that HTTP method |
| 409 | Conflict | state conflict (duplicate, optimistic lock) |
| 410 | Gone | resource permanently deleted (vs 404 = maybe exists) |
| 415 | Unsupported Media Type | wrong Content-Type |
| 422 | Unprocessable Entity | semantic error; valid syntax but invalid data |
| 429 | Too Many Requests | rate limit exceeded; include Retry-After |

**401 vs 403 rule:** 401 = "I don't know who you are"; 403 = "I know who you are, but NO"

### 5xx — Server Errors
| Code | Name | Use |
|------|------|-----|
| 500 | Internal Server Error | catch-all; unexpected server error |
| 501 | Not Implemented | method not supported by server |
| 502 | Bad Gateway | upstream server returned invalid response |
| 503 | Service Unavailable | server down/overloaded; include Retry-After |
| 504 | Gateway Timeout | upstream server timeout |

## REST vs GraphQL Decision Matrix

| Criterion | REST | GraphQL |
|-----------|------|---------|
| Data fetching | Fixed endpoints; over/under-fetching possible | Precise queries; client specifies exact fields |
| Caching | HTTP caching (ETags, Cache-Control) — excellent | Harder; all POST to /graphql; need persisted queries |
| Performance (mobile) | Multiple roundtrips for related data | Single query; bandwidth-efficient |
| Schema | OpenAPI/Swagger optional | Strongly typed schema mandatory |
| File uploads | Multipart form — easy | Complex; multipart spec unofficial |
| Realtime | SSE, webhooks, WebSocket | Subscriptions built-in |
| Versioning | URL versioning (/v1/, /v2/) or headers | Schema evolution with deprecation |

**Use REST when:** CRUD APIs, public/third-party APIs, CDN caching critical, simple client needs
**Use GraphQL when:** mobile + web with different data needs, BFF (backend for frontend), avoiding multiple roundtrips

## JWT Structure & Claims

```
Header.Payload.Signature
  Header: {"alg":"RS256","typ":"JWT"}    base64url encoded
  Payload: claims                         base64url encoded (NOT encrypted!)
  Signature: HMACSHA256/RS256(header+payload, secret)

Standard Claims (IANA registered):
  iss: issuer (who created the token)
  sub: subject (who the token is about; user ID)
  aud: audience (who should accept it)
  exp: expiration time (NumericDate; UNIX timestamp)
  nbf: not before (invalid before this time)
  iat: issued at
  jti: JWT ID (unique identifier; prevent replay)

Security rules:
  - NEVER store sensitive data in payload (base64url is trivially decodable)
  - Verify signature BEFORE reading claims
  - Check exp BEFORE trusting claims
  - Use RS256 (asymmetric) for public APIs; HS256 (symmetric) for internal only
  - Short expiry (15min) + refresh token pattern for security
```

## OAuth 2.0 — Grant Types

| Grant Type | Use Case | Security |
|------------|---------|---------|
| Authorization Code + PKCE | Web apps, SPAs, mobile | Most secure; recommended default |
| Client Credentials | Server-to-server (M2M) | Service account authentication |
| Device Authorization | Smart TV, IoT, CLI tools | Device with no browser |
| Refresh Token | Obtain new access tokens | Long-lived sessions |
| Implicit | SPA (OBSOLETE) | Removed in OAuth 2.1 — do not use |
| Resource Owner Password | Migration only (legacy) | Deprecated; never for new systems |

PKCE (Proof Key for Code Exchange): code_verifier → SHA256 → base64url → code_challenge; prevents auth code interception

## Security Headers (Mandatory)

| Header | Value | Purpose |
|--------|-------|---------|
| Content-Security-Policy | `default-src 'self'; script-src 'self'` | XSS prevention; whitelist content sources |
| Strict-Transport-Security | `max-age=31536000; includeSubDomains; preload` | HTTPS only; prevent downgrade attacks |
| X-Content-Type-Options | `nosniff` | Prevent MIME sniffing attacks |
| X-Frame-Options | `DENY` or `SAMEORIGIN` | Clickjacking prevention |
| Referrer-Policy | `strict-origin-when-cross-origin` | Limit referrer data leakage |
| Permissions-Policy | `camera=(), microphone=(), geolocation=()` | Restrict browser API access |

CORS essential headers:
- `Access-Control-Allow-Origin`: specify, never `*` for credentialed requests
- `Access-Control-Allow-Methods`: list allowed methods
- `Access-Control-Allow-Headers`: list allowed request headers
- `Access-Control-Max-Age`: seconds to cache preflight (max 86400)

**Source:** RFC 9110 HTTP Semantics (2022) + RFC 7519 JWT + RFC 6749 OAuth 2.0 + RFC 7636 PKCE + MDN Web Docs (developer.mozilla.org) + OWASP Security Headers Project
