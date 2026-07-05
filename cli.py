import argparse
import asyncio

from app.infra.clickhouse.migrations.env import ClickHouseMigrationError
from app.infra.clickhouse.migrations.env import run_command as run_clickhouse_migration


def add_clickhouse_migrations_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("click", help="Run ClickHouse SQL migrations")
    command_parsers = parser.add_subparsers(dest="migration_command", required=True)

    upgrade_parser = command_parsers.add_parser("upgrade", help="Apply migrations up to revision_name")
    upgrade_parser.add_argument("revision_name")

    downgrade_parser = command_parsers.add_parser("downgrade", help="Roll migrations back to revision_name")
    downgrade_parser.add_argument("revision_name")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="lastliter CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    add_clickhouse_migrations_parser(subparsers)

    return parser.parse_args()


async def run() -> None:
    args = parse_args()

    match args.command:
        case "click":
            await run_clickhouse_migration(args.migration_command, args.revision_name)
        case _:
            raise ClickHouseMigrationError(f"Unknown command: {args.command}")


def main() -> None:
    try:
        asyncio.run(run())
    except ClickHouseMigrationError as error:
        raise SystemExit(str(error)) from error


if __name__ == "__main__":
    main()
