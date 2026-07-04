from pydantic import BaseModel, PostgresDsn


class PostgreSQLSettings(BaseModel):
    dsn: PostgresDsn
