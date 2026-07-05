import argparse
import asyncio
from dataclasses import dataclass
from pathlib import Path

from clickhouse_connect.driver import AsyncClient

from app.infra.clickhouse import create_clickhouse_client
from app.infra.config import generate_settings
from app.infra.logging.logger import get_logger

logger = get_logger().getChild(__name__)

MIGRATIONS_TABLE = "__schema_migrations"
BASE_REVISION = "base"


@dataclass(frozen=True)
class Revision:
    name: str
    path: Path

    @property
    def up_path(self) -> Path:
        return self.path / "up.sql"

    @property
    def down_path(self) -> Path:
        return self.path / "down.sql"


class ClickHouseMigrationError(Exception):
    pass


def split_sql(sql: str) -> list[str]:
    statements: list[str] = []
    statement: list[str] = []
    quote: str | None = None
    line_comment = False
    block_comment = False
    i = 0

    while i < len(sql):
        char = sql[i]
        next_char = sql[i + 1] if i + 1 < len(sql) else ""

        if line_comment:
            statement.append(char)
            if char == "\n":
                line_comment = False
            i += 1
            continue

        if block_comment:
            statement.append(char)
            if char == "*" and next_char == "/":
                statement.append(next_char)
                block_comment = False
                i += 2
            else:
                i += 1
            continue

        if quote is not None:
            statement.append(char)
            if char == "\\" and next_char:
                statement.append(next_char)
                i += 2
                continue
            if char == quote:
                quote = None
            i += 1
            continue

        if char in {"'", '"', "`"}:
            quote = char
            statement.append(char)
            i += 1
            continue

        if char == "-" and next_char == "-":
            line_comment = True
            statement.append(char)
            statement.append(next_char)
            i += 2
            continue

        if char == "/" and next_char == "*":
            block_comment = True
            statement.append(char)
            statement.append(next_char)
            i += 2
            continue

        if char == ";":
            current = "".join(statement).strip()
            if current:
                statements.append(current)
            statement = []
            i += 1
            continue

        statement.append(char)
        i += 1

    current = "".join(statement).strip()
    if current:
        statements.append(current)

    return statements


def has_sql_code(statement: str) -> bool:
    quote: str | None = None
    line_comment = False
    block_comment = False
    i = 0

    while i < len(statement):
        char = statement[i]
        next_char = statement[i + 1] if i + 1 < len(statement) else ""

        if line_comment:
            if char == "\n":
                line_comment = False
            i += 1
            continue

        if block_comment:
            if char == "*" and next_char == "/":
                block_comment = False
                i += 2
            else:
                i += 1
            continue

        if quote is not None:
            if char == "\\" and next_char:
                i += 2
                continue
            if char == quote:
                quote = None
            i += 1
            continue

        if char.isspace():
            i += 1
            continue

        if char in {"'", '"', "`"}:
            return True

        if char == "-" and next_char == "-":
            line_comment = True
            i += 2
            continue

        if char == "/" and next_char == "*":
            block_comment = True
            i += 2
            continue

        return True

    return False


def get_versions_dir() -> Path:
    return Path(__file__).resolve().parent / "versions"


def load_revisions() -> list[Revision]:
    versions_dir = get_versions_dir()
    if not versions_dir.exists():
        raise ClickHouseMigrationError(f"ClickHouse migrations directory does not exist: {versions_dir}")

    revisions = [Revision(path.name, path) for path in versions_dir.iterdir() if path.is_dir()]
    revisions.sort(key=lambda revision: revision.name)

    for revision in revisions:
        if not revision.up_path.exists():
            raise ClickHouseMigrationError(f"Missing up.sql for ClickHouse revision {revision.name}")
        if not revision.down_path.exists():
            raise ClickHouseMigrationError(f"Missing down.sql for ClickHouse revision {revision.name}")

    return revisions


def get_revision_index(revisions: list[Revision], revision_name: str) -> int:
    for index, revision in enumerate(revisions):
        if revision.name == revision_name:
            return index
    raise ClickHouseMigrationError(f"Unknown ClickHouse revision: {revision_name}")


async def ensure_migrations_table(client: AsyncClient) -> None:
    await client.command(
        f"""
        CREATE TABLE IF NOT EXISTS {MIGRATIONS_TABLE}
        (
            id UInt8,
            revision String,
            updated_at DateTime64(3) DEFAULT now64(3)
        )
        ENGINE = ReplacingMergeTree(updated_at)
        ORDER BY id
        """
    )


async def get_current_revision(client: AsyncClient, revisions: list[Revision]) -> str | None:
    await ensure_migrations_table(client)
    result = await client.query(
        f"""
        SELECT revision
        FROM {MIGRATIONS_TABLE}
        WHERE id = 1
        ORDER BY updated_at DESC
        LIMIT 1
        """
    )

    if not result.result_rows:
        return None

    revision = result.result_rows[0][0]
    if revision == BASE_REVISION:
        return None

    known_revisions = {item.name for item in revisions}
    if revision not in known_revisions:
        raise ClickHouseMigrationError(f"Stored ClickHouse revision is not present in versions directory: {revision}")

    return revision


async def set_current_revision(client: AsyncClient, revision: str | None) -> None:
    await client.insert(
        MIGRATIONS_TABLE,
        [[1, revision or BASE_REVISION]],
        column_names=["id", "revision"],
    )


async def apply_sql_file(client: AsyncClient, sql_path: Path) -> None:
    sql = sql_path.read_text(encoding="utf-8")
    statements = [statement for statement in split_sql(sql) if has_sql_code(statement)]

    if not statements:
        logger.info(f"ClickHouse migration file is empty: {sql_path}")
        return

    for statement in statements:
        await client.command(statement)


async def upgrade(client: AsyncClient, target_revision: str) -> None:
    revisions = load_revisions()
    target_index = get_revision_index(revisions, target_revision)
    current_revision = await get_current_revision(client, revisions)
    current_index = get_revision_index(revisions, current_revision) if current_revision else -1

    if target_index < current_index:
        raise ClickHouseMigrationError(
            f"Cannot upgrade from {current_revision} to older revision {target_revision}; use downgrade"
        )

    for revision in revisions[current_index + 1 : target_index + 1]:
        logger.info(f"Applying ClickHouse migration upgrade: {revision.name}")
        await apply_sql_file(client, revision.up_path)
        await set_current_revision(client, revision.name)

    logger.info(f"ClickHouse schema is at revision {target_revision}")


async def downgrade(client: AsyncClient, target_revision: str) -> None:
    revisions = load_revisions()
    target_index = -1 if target_revision == BASE_REVISION else get_revision_index(revisions, target_revision)
    current_revision = await get_current_revision(client, revisions)

    if current_revision is None:
        if target_revision != BASE_REVISION:
            raise ClickHouseMigrationError(
                f"Cannot downgrade from base to newer revision {target_revision}; use upgrade"
            )
        logger.info("ClickHouse schema is already at base revision")
        return

    current_index = get_revision_index(revisions, current_revision)
    if target_index > current_index:
        raise ClickHouseMigrationError(
            f"Cannot downgrade from {current_revision} to newer revision {target_revision}; use upgrade"
        )

    for revision in reversed(revisions[target_index + 1 : current_index + 1]):
        next_index = get_revision_index(revisions, revision.name) - 1
        next_revision = revisions[next_index].name if next_index >= 0 else None
        logger.info(f"Applying ClickHouse migration downgrade: {revision.name}")
        await apply_sql_file(client, revision.down_path)
        await set_current_revision(client, next_revision)

    logger.info(f"ClickHouse schema is at revision {target_revision}")


async def run_command(command: str, revision_name: str) -> None:
    settings = generate_settings()
    async with create_clickhouse_client(settings.clickhouse) as client:
        match command:
            case "upgrade":
                await upgrade(client, revision_name)
            case "downgrade":
                await downgrade(client, revision_name)
            case _:
                raise ClickHouseMigrationError(f"Unknown command: {command}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run ClickHouse SQL migrations")
    subparsers = parser.add_subparsers(dest="command", required=True)

    upgrade_parser = subparsers.add_parser("upgrade", help="Apply migrations up to revision_name")
    upgrade_parser.add_argument("revision_name")

    downgrade_parser = subparsers.add_parser("downgrade", help="Roll migrations back to revision_name")
    downgrade_parser.add_argument("revision_name")

    return parser.parse_args()


async def run() -> None:
    args = parse_args()
    await run_command(args.command, args.revision_name)


def main() -> None:
    try:
        asyncio.run(run())
    except ClickHouseMigrationError as error:
        raise SystemExit(str(error)) from error


if __name__ == "__main__":
    main()
