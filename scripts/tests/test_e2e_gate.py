import e2e_gate
import pytest


@pytest.mark.parametrize("url", ["http://127.0.0.1:54421", "http://localhost:54421"])
def test_local_supabase_is_accepted(url: str) -> None:
    assert e2e_gate.require_local(url) == url


@pytest.mark.parametrize(
    "url", ["https://abc.supabase.co", "http://localhost.example.com", "http://10.0.0.5:54421", ""]
)
def test_other_hosts_are_refused(url: str) -> None:
    with pytest.raises(e2e_gate.GateError):
        e2e_gate.require_local(url)


def test_existing_account_gets_a_new_password(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, str]] = []

    def fake(base: str, key: str, method: str, path: str, body: object = None) -> object:
        calls.append((method, path))
        return {"users": [{"id": "u1", "email": e2e_gate.EMAIL}]}

    monkeypatch.setattr(e2e_gate, "admin_request", fake)
    passwords = {e2e_gate.prepare_account("http://localhost", "key") for _ in range(2)}

    assert len(passwords) == 2
    assert ("PUT", "users/u1") in calls
    assert all(method != "POST" for method, _ in calls)


def test_paid_provider_keys_are_cleared() -> None:
    assert {"GOOGLE_API_KEY", "GROQ_API_KEY", "STRIPE_SECRET_KEY"} <= set(e2e_gate.NO_KEYS)
