from clickhouse_connect.driver.asyncclient import AsyncClient


class ClickHouseRepository:
    def __init__(self, client: AsyncClient) -> None:
        self._client = client
