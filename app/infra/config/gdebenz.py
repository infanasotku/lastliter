from ipaddress import IPv4Address

from pydantic import BaseModel, Field, IPvAnyAddress

from app.infra.redis.common import KEY_PREFIX

RATE_LIMIT_KEY_PREFIX = KEY_PREFIX + "gdebenz:request-start:v2:egress"


class GdebenzSettings(BaseModel):
    fingerprint: str
    egress_pool_id: str = Field(default="local", pattern=r"^[a-z0-9](?:[-a-z0-9]*[a-z0-9])?$")
    expected_public_ip: IPvAnyAddress = IPv4Address("127.0.0.1")
    rate_limit_per_second: float = Field(default=2, gt=0)

    @property
    def rate_limit_key(self) -> str:
        return f"{RATE_LIMIT_KEY_PREFIX}:{self.expected_public_ip.compressed}"
