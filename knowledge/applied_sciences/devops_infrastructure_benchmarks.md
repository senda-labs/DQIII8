---
domain: applied_sciences
type: reference_data
last_updated: 2026-03
keywords_en: [Docker, Kubernetes, k8s, CI/CD, GitHub Actions, deployment, container, CPU, memory, network, SLA, uptime, SRE, error budget, latency, throughput]
keywords_es: [Docker, Kubernetes, despliegue, contenedor, CI/CD, GitHub Actions, SLA, disponibilidad, latencia, rendimiento]
---

## Docker Container Benchmarks (2024)

| Metric | Value | Notes |
|--------|-------|-------|
| Container start time (no pull) | 50–200 ms | From docker run to process start |
| Image pull (100MB, 1Gbps) | 0.8 s | ~125 MB/s effective |
| Image build (10-layer, no cache) | 30–120 s | Depends on steps |
| Container memory overhead | ~5–10 MB | Per container, beyond app |
| Max containers per host (tested) | ~1,000 | CPU/mem bound in practice |
| Docker daemon CPU (idle, 100 containers) | ~2% | systemd cgroup overhead |

## Kubernetes Resource Defaults & Limits

| Resource | Default Request | Default Limit | Notes |
|----------|----------------|---------------|-------|
| CPU (LimitRange) | 100m (0.1 vCPU) | 500m (0.5 vCPU) | If no explicit request |
| Memory (LimitRange) | 128 Mi | 512 Mi | If no explicit limit |
| Max pods per node | 110 | configurable (max 256) | `--max-pods` kubelet flag |
| Max services per cluster | 10,000 | soft; etcd bound | |
| Max namespaces | 10,000 | soft limit | |
| kube-apiserver latency SLO | <1 s (p99) | k8s SLA target | for mutating calls |
| etcd key-value size limit | 1.5 MB | per key | default; configurable |

### Kubernetes Autoscaling Thresholds

| Type | Metric | Default Trigger | Cooldown |
|------|--------|----------------|----------|
| HPA (CPU) | CPU utilization | 80% | 5 min scale down |
| HPA (Memory) | Memory utilization | 80% | 5 min scale down |
| VPA | CPU/Memory | under/over-provisioned 10% | — |
| KEDA (custom) | Queue depth / RPS | user-defined | configurable |

## CI/CD Pipeline Benchmarks (GitHub Actions, 2024)

| Job Type | Typical Duration | Runner (ubuntu-latest) |
|----------|-----------------|------------------------|
| npm install (cold cache) | 60–90 s | 2-core, 7GB RAM |
| npm install (warm cache) | 5–15 s | 2-core, 7GB RAM |
| Python pip install (cold) | 30–60 s | 2-core, 7GB RAM |
| Docker build (no cache) | 2–5 min | 2-core, 7GB RAM |
| Docker build (layer cache) | 15–45 s | 2-core, 7GB RAM |
| pytest (1,000 tests) | 30–120 s | 2-core, 7GB RAM |
| Jest (1,000 tests) | 15–60 s | 2-core, 7GB RAM |
| Terraform plan (50 resources) | 15–30 s | 2-core, 7GB RAM |
| k8s deploy (rolling, 5 pods) | 45–120 s | depends on readiness probe |

GitHub Actions pricing (2025): Free 2,000 min/month (public free). Private: $0.008/min (Linux), $0.016/min (Windows), $0.064/min (macOS).

## SLA / SRE Reliability Targets

| Availability | Downtime/Year | Downtime/Month | Downtime/Week | Tier |
|-------------|---------------|----------------|---------------|------|
| 99% | 3.65 days | 7.31 hours | 1.68 hours | Basic |
| 99.5% | 1.83 days | 3.65 hours | 50.4 min | Standard |
| 99.9% | 8.77 hours | 43.8 min | 10.1 min | High |
| 99.95% | 4.38 hours | 21.9 min | 5.04 min | High+ |
| 99.99% | 52.6 min | 4.38 min | 1.01 min | Enterprise |
| 99.999% | 5.26 min | 26.3 sec | 6.05 sec | Mission-critical |
| 99.9999% | 31.5 sec | 2.63 sec | 0.60 sec | Carrier-grade |

Error budget (99.9%): 43.8 min/month. Burn rate >1.0 = consuming budget faster than allowed.

## Network Protocol Overhead

| Protocol | Header Size | RTTs to Establish | Overhead vs TCP |
|----------|-------------|-------------------|----------------|
| TCP | 20 bytes | 1 (SYN/SYN-ACK/ACK) | baseline |
| TLS 1.3 over TCP | +5 bytes | +1 (0-RTT resumption) | ~10 ms extra |
| TLS 1.2 over TCP | +5 bytes | +2 full handshake | ~20–40 ms extra |
| HTTP/1.1 | 200–800 bytes header | 1 TCP + optional TLS | head-of-line blocking |
| HTTP/2 | ~9 bytes framing | same as HTTP/1.1 | multiplexed, HPACK compressed |
| HTTP/3 / QUIC | ~8 bytes | 0–1 RTT (0-RTT possible) | UDP-based; 15% faster on lossy networks |
| gRPC (HTTP/2) | protobuf + framing | same as HTTP/2 | ~5–10× smaller payload vs JSON |
| WebSocket | 2–14 bytes/frame | 1 HTTP upgrade | persistent; ~0 per-msg overhead |

## Cloud Serverless Cold Start Latencies (2024)

| Provider | Runtime | Memory | Cold Start (p50) | Cold Start (p99) |
|----------|---------|--------|-----------------|-----------------|
| AWS Lambda | Python 3.12 | 128 MB | 180 ms | 700 ms |
| AWS Lambda | Python 3.12 | 1024 MB | 120 ms | 400 ms |
| AWS Lambda | Node.js 20 | 128 MB | 120 ms | 500 ms |
| AWS Lambda | Java 21 (SnapStart) | 512 MB | 50 ms | 200 ms |
| Google Cloud Functions | Python 3.12 | 256 MB | 350 ms | 1,200 ms |
| Azure Functions | Python 3.11 | 256 MB | 400 ms | 1,500 ms |
| Cloudflare Workers | JS/WASM | N/A | <5 ms | 20 ms |

Provisioned Concurrency (AWS): eliminates cold starts; cost ~$0.015/GB-hour (Lambda).
