import os
from typing import Literal

from dotenv import load_dotenv
from pydantic import PostgresDsn
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.infra.config.admin import AdminSettings
from app.infra.config.postgres import PostgreSQLSettings


class CommonSettings(BaseSettings):
    env: Literal["local", "ci", "prod"]

    model_config = SettingsConfigDict(env_nested_delimiter="__")


class Settings(BaseSettings):
    postgres: PostgreSQLSettings
    admin: AdminSettings

    model_config = SettingsConfigDict(env_nested_delimiter="__")


class TestSettings(Settings):
    postgres: PostgreSQLSettings = PostgreSQLSettings(
        dsn=PostgresDsn("postgresql+asyncpg://test_user:test_password@localhost:5432/test_db")
    )
    admin: AdminSettings = AdminSettings(username="admin", password="admin", secret="admin_secret")


def generate_settings():
    load_dotenv(override=True, dotenv_path=os.getcwd() + "/.env")

    common = CommonSettings()  # type: ignore

    match common.env:
        case "ci":
            return TestSettings()  # type: ignore
        case _:
            return Settings()  # type: ignore
