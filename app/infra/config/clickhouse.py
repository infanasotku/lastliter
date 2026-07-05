from pydantic import BaseModel, ClickHouseDsn


class ClickhouseSettings(BaseModel):
    dsn: ClickHouseDsn
