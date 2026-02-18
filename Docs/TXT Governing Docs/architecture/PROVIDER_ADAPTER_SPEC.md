# PROVIDER_ADAPTER_SPEC.md
Generated: 2026-02-18T17:29:02.381145

## INTENT
Isolate third-party providers behind adapter interfaces.

---

## ADAPTER TYPES
CrawlAdapter
SERPAdapter
ProxyRotationAdapter
EmailAdapter

---

## RETRY STANDARD
Exponential backoff + circuit breaker + dead-letter queue