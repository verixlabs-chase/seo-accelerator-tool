# Celery Worker Profiles

Worker Profile A - Crawl
`CELERY_WORKER_PROFILE=crawl celery -A app worker -Q crawl_queue -c 4`

Worker Profile B - Rank
`CELERY_WORKER_PROFILE=rank celery -A app worker -Q rank_queue -c 4`

Worker Profile C - Content
`CELERY_WORKER_PROFILE=content celery -A app worker -Q content_queue -c 2`

Worker Profile D - Authority
`CELERY_WORKER_PROFILE=authority celery -A app worker -Q authority_queue -c 2`

Worker Profile E - Default
`CELERY_WORKER_PROFILE=default celery -A app worker -Q default_queue -c 2`

Optional override for prefetch multiplier:
`CELERY_WORKER_PREFETCH_MULTIPLIER=<int>`
