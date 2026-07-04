from pydantic import BaseModel, RedisDsn


class RedisSettings(BaseModel):
    dsn: RedisDsn

    client: str = "control"
