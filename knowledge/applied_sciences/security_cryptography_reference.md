---
domain: applied_sciences
type: reference_data
last_updated: 2026-03
keywords_en: [cryptography, TLS, AES, RSA, ECDSA, hash, SHA, bcrypt, key size, cipher, security, NIST, vulnerability, CVE, CVSS]
keywords_es: [criptografía, TLS, AES, RSA, ECDSA, hash, SHA, bcrypt, tamaño clave, cifrado, seguridad, NIST, vulnerabilidad]
---

## Symmetric Encryption — Key Sizes & Performance

| Algorithm | Key Size (bits) | Security Level (bits) | Throughput (AES-NI, 1 core) | Overhead vs AES-128 | Status |
|-----------|----------------|----------------------|----------------------------|---------------------|--------|
| AES-128-GCM | 128 | 128 | ~3.5 GB/s | 0% (baseline) | Recommended |
| AES-256-GCM | 256 | 256 | ~2.5 GB/s | ~29% slower | Recommended (high security) |
| AES-128-CBC | 128 | 128 | ~2.0 GB/s | ~43% slower | Legacy; avoid (padding oracle) |
| ChaCha20-Poly1305 | 256 | 256 | ~1.5 GB/s (no HW accel) | ~57% slower (no ASNI) | Recommended (mobile, no AES-NI) |
| 3DES | 168 | 112 | ~50 MB/s | ~98% slower | Deprecated (Sweet32 vuln) |
| RC4 | 40–2048 | <40 | ~300 MB/s | ~91% slower | Broken (do not use) |

AES-NI available on: Intel Westmere (2010)+, AMD Bulldozer (2011)+. ~10× faster than software AES.

## Asymmetric Encryption — Key Sizes & Equivalences

| Algorithm | Key Size | Security (bits) | Use Case | Performance (sign) |
|-----------|----------|-----------------|----------|--------------------|
| RSA | 2048 bit | 112 | TLS, PKI (minimum 2024) | ~1,200 ops/s |
| RSA | 3072 bit | 128 | TLS, PKI (post-2030 NIST) | ~600 ops/s |
| RSA | 4096 bit | 140+ | Long-term certs | ~300 ops/s |
| ECDSA P-256 | 256 bit | 128 | TLS, Code signing | ~10,000 ops/s |
| ECDSA P-384 | 384 bit | 192 | High-security TLS | ~5,000 ops/s |
| Ed25519 | 256 bit | 128 | SSH, JWT, modern TLS | ~50,000 ops/s |
| X25519 (ECDH) | 256 bit | 128 | Key exchange | ~100,000 ops/s |
| Post-Quantum ML-KEM-768 | 1184 bytes | 180 | NIST PQC standard 2024 | ~5,000 ops/s |

NIST recommendation: RSA-2048 acceptable through 2030; RSA-3072 for post-2030.

## Hash Functions — Properties & Performance

| Algorithm | Output (bits) | Collision resistance | Speed (1 core) | Relative speed (%) | Status |
|-----------|--------------|---------------------|----------------|---------------------|--------|
| MD5 | 128 | Broken (collisions found 2004) | ~800 MB/s | 286% of SHA-256 | DO NOT USE for security |
| SHA-1 | 160 | Broken (SHAttered 2017) | ~500 MB/s | 179% of SHA-256 | Deprecated in TLS 2017 |
| SHA-256 | 256 | 128-bit | ~280 MB/s | 100% (baseline) | Standard; TLS 1.3 |
| SHA-384 | 384 | 192-bit | ~200 MB/s | 71% of SHA-256 | High security; TLS 1.3 |
| SHA-512 | 512 | 256-bit | ~250 MB/s | 89% of SHA-256 | High security |
| SHA3-256 | 256 | 128-bit | ~120 MB/s | 43% of SHA-256 | NIST 2015; Keccak |
| BLAKE2b | 512 | 256-bit | ~1,000 MB/s | 357% of SHA-256 | Fast; cryptographic; not TLS |
| BLAKE3 | 256+ | 128-bit | ~3,500 MB/s | 1250% of SHA-256 | Fastest; 2020; parallelizable |

## Password Hashing — Cost Parameters (2024 recommendations)

| Algorithm | Recommended Config | Hash Time (target) | Memory | Notes |
|-----------|-------------------|--------------------|--------|-------|
| bcrypt | cost=12 | ~300 ms | ~4 KB | Standard; max 72 bytes input |
| bcrypt | cost=10 | ~100 ms | ~4 KB | Minimum acceptable |
| scrypt | N=32768, r=8, p=1 | ~100 ms | 32 MB | Memory-hard; OpenSSL |
| Argon2id | m=64MB, t=2, p=2 | ~100 ms | 64 MB | OWASP recommended (2024) |
| Argon2id | m=19MB, t=2, p=1 | ~50 ms | 19 MB | Minimum per OWASP |
| PBKDF2-SHA256 | iterations=600,000 | ~100 ms | <1 KB | NIST 2023 guidance |

## TLS Configuration — Current Standards (2025)

| Version | Status | Cipher Suites Supported | Notes |
|---------|--------|------------------------|-------|
| TLS 1.3 | Current (RFC 8446, 2018) | 5 suites only | Mandatory for PCI DSS 4.0 |
| TLS 1.2 | Acceptable | ~30 suites | PCI DSS 4.0 requires by Mar 2025 |
| TLS 1.1 | Deprecated (RFC 8996, 2021) | — | Forbidden in PCI DSS 4.0 |
| TLS 1.0 | Deprecated (RFC 8996, 2021) | — | Forbidden in PCI DSS 4.0 |
| SSL 3.0 | Broken (POODLE 2014) | — | Never use |

TLS 1.3 mandatory cipher suites: TLS_AES_128_GCM_SHA256, TLS_AES_256_GCM_SHA384, TLS_CHACHA20_POLY1305_SHA256.

## CVSS v3.1 Scoring Ranges

| Score Range | Severity | SLA to Patch | % of CVEs (2024) | Notes |
|-------------|----------|-------------|-----------------|-------|
| 9.0–10.0 | Critical | 24–72 hours | ~2% | Actively exploited: immediate |
| 7.0–8.9 | High | 7–14 days | ~18% | Remote code execution typical |
| 4.0–6.9 | Medium | 30 days | ~45% | Require auth or user interaction |
| 0.1–3.9 | Low | 90 days | ~20% | Physical access or limited impact |
| 0.0 | None | — | ~15% | No impact |

Notable CVEs by CVSS 10.0: Log4Shell CVE-2021-44228 (10.0), Heartbleed CVE-2014-0160 (7.5), ShellShock CVE-2014-6271 (9.8).
