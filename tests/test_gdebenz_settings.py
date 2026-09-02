from ipaddress import IPv4Address, IPv6Address

import pytest
from pydantic import ValidationError

from app.infra.config.gdebenz import GdebenzSettings


@pytest.mark.parametrize(
    ("public_ip", "expected_ip", "expected_key"),
    [
        (
            "203.0.113.10",
            IPv4Address("203.0.113.10"),
            "lastliter:gdebenz:request-start:v2:egress:203.0.113.10",
        ),
        (
            "2001:0db8:0000:0000:0000:0000:0000:0001",
            IPv6Address("2001:db8::1"),
            "lastliter:gdebenz:request-start:v2:egress:2001:db8::1",
        ),
    ],
)
def test_rate_limit_key_uses_canonical_public_ip(public_ip: str, expected_ip, expected_key: str):
    settings = GdebenzSettings(fingerprint="test", expected_public_ip=public_ip)

    assert settings.expected_public_ip == expected_ip
    assert settings.rate_limit_key == expected_key


@pytest.mark.parametrize("pool_id", ["YC", "home_pool", "-home", "home-"])
def test_rejects_non_dns_label_pool_id(pool_id: str):
    with pytest.raises(ValidationError):
        GdebenzSettings(fingerprint="test", egress_pool_id=pool_id)


def test_rejects_non_positive_rate_limit():
    with pytest.raises(ValidationError):
        GdebenzSettings(fingerprint="test", rate_limit_per_second=0)
