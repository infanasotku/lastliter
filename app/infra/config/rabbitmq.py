from pydantic import AmqpDsn, BaseModel


class RabbitMQSettings(BaseModel):
    dsn: AmqpDsn
