# Worker Fabric

Campaign execution is now dispatched through Celery task routing rather than thread-local Python queues. `CampaignWorkerPool` computes a stable partition using SHA-256 over `campaign_id` and submits `process_campaign(campaign_id)` into partition-specific Celery queues.

Local threaded execution remains available only as a test-time fallback when an explicit processor is injected.
