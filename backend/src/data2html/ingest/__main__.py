"""`python -m data2html.ingest dynamodb <source> [--table <name>]` (exit code 1 if any table fails)."""

from __future__ import annotations

import argparse
import logging
import sys

from data2html.ingest.dynamodb import DynamoIngest, IngestError
from data2html.settings import Settings
from data2html.sources.registry import DynamoDBConfig, load_sources_file


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m data2html.ingest")
    sub = parser.add_subparsers(dest="kind", required=True)
    ddb = sub.add_parser("dynamodb", help="export DynamoDB tables to S3 and refresh their Parquet")
    ddb.add_argument("source")
    ddb.add_argument("--table", help="only this table (default: every configured table)")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    settings = Settings.from_env()
    cfg = load_sources_file(settings.sources_file).sources.get(args.source)
    if not isinstance(cfg, DynamoDBConfig):
        print(f"{args.source!r} is not a dynamodb_export source in {settings.sources_file}", file=sys.stderr)
        return 2
    tables = [args.table] if args.table else list(cfg.tables)
    ingest = DynamoIngest(args.source, cfg, settings)
    failed = 0
    for table in tables:
        try:
            r = ingest.run(table)
            note = f", {sum(r.warnings.values())} values did not convert {r.warnings}" if r.warnings else ""
            print(f"{args.source}.{table}: {r.rows} rows ({r.export_arn}){note}")
        except (IngestError, OSError) as e:
            failed += 1
            print(f"{args.source}.{table}: FAILED: {e}", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
