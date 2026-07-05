import os
from typing import Literal

from dotenv import load_dotenv
from pydantic import AmqpDsn, ClickHouseDsn, PostgresDsn, RedisDsn
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.infra.config.admin import AdminSettings
from app.infra.config.clickhouse import ClickhouseSettings
from app.infra.config.postgres import PostgreSQLSettings
from app.infra.config.rabbitmq import RabbitMQSettings
from app.infra.config.redis import RedisSettings


class CommonSettings(BaseSettings):
    env: Literal["local", "ci", "prod"]

    model_config = SettingsConfigDict(env_nested_delimiter="__")


class Settings(BaseSettings):
    postgres: PostgreSQLSettings
    admin: AdminSettings
    redis: RedisSettings
    rabbitmq: RabbitMQSettings
    clickhouse: ClickhouseSettings

    model_config = SettingsConfigDict(env_nested_delimiter="__")


class TestSettings(Settings):
    postgres: PostgreSQLSettings = PostgreSQLSettings(
        dsn=PostgresDsn("postgresql+asyncpg://test_user:test_password@localhost:5432/test_db")
    )
    admin: AdminSettings = AdminSettings(username="admin", password="admin", secret="admin_secret")
    redis: RedisSettings = RedisSettings(dsn=RedisDsn("redis://localhost:6379/0"))
    rabbitmq: RabbitMQSettings = RabbitMQSettings(dsn=AmqpDsn("amqp://guest:guest@localhost:5672/"))
    clickhouse: ClickhouseSettings = ClickhouseSettings(
        dsn=ClickHouseDsn("clickhousedb://default:default@localhost:8123/default")
    )


def generate_settings():
    load_dotenv(override=True, dotenv_path=os.getcwd() + "/.env")

    common = CommonSettings()  # type: ignore

    match common.env:
        case "ci":
            return TestSettings()  # type: ignore
        case _:
            return Settings()  # type: ignore
