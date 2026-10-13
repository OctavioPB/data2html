"""Scheduled ingestion for Import sources (DynamoDB exports, ADR 0012).

Run it from cron, the Windows Task Scheduler or a Kubernetes CronJob:

    python -m data2html.ingest dynamodb <source> [--table <name>]

The web server never schedules anything; the studio's author can also start one export at a time.
"""
