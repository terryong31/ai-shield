from pydantic import SecretStr

from shield_api.services.access import resolve_clearance
from shield_engine import Clearance


def test_no_configured_secret_means_nobody_is_granted() -> None:
    assert resolve_clearance("anything", None) is Clearance.DENIED


def test_empty_passphrase_is_no_claim() -> None:
    assert resolve_clearance("", SecretStr("s")) is Clearance.NONE
