"""Phase 7A-1 channel tests: protocol, simulated, and SMTP relay channel."""

import pytest

from backend.channels.base import Channel, ChannelConfigError, ChannelError, ChannelResult
from backend.channels.simulated import SimulatedExecutionChannel
from backend.channels.smtp import SmtpRelayChannel

ACTION = {
    "id": "a1b2c3d4e5f60708",
    "case_id": "case-1234",
    "target": "ASUS Support",
    "content": "Please reassess the rejected warranty claim.",
}


class FakeSMTP:
    instances = []

    def __init__(self, host, port, timeout=None):
        self.host = host
        self.port = port
        self.sent = []
        self.login_calls = 0
        self.starttls_calls = 0
        FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def send_message(self, message):
        self.sent.append(message)

    def login(self, username, password):
        self.login_calls += 1

    def starttls(self):
        self.starttls_calls += 1


# --- Protocol / simulated ---


def test_simulated_channel_result_has_reference_and_result():
    result = SimulatedExecutionChannel().submit(ACTION)
    assert isinstance(result, ChannelResult)
    assert result.reference == f"RESOLVE-ACTION-{ACTION['id'][:8].upper()}"
    assert "simulated" in result.result
    assert "nothing was actually sent" in result.result


def test_simulated_channel_is_duck_typing_channel():
    assert isinstance(SimulatedExecutionChannel(), Channel)


def test_channel_result_supports_tuple_unpacking():
    reference, result = ChannelResult("ref-1", "done")
    assert reference == "ref-1"
    assert result == "done"


def test_simulated_uses_deterministic_reference():
    first = SimulatedExecutionChannel().submit(ACTION)
    second = SimulatedExecutionChannel().submit(ACTION)
    assert first.reference == second.reference


# --- SMTP channel: mocked smtplib ---


@pytest.fixture
def smtp_channel(monkeypatch):
    FakeSMTP.instances = []
    monkeypatch.setattr("backend.channels.smtp.smtplib.SMTP", FakeSMTP)
    return SmtpRelayChannel(
        host="127.0.0.1",
        port=1025,
        from_addr="resolve@example.test",
        to_addrs="operator@example.test",
    )


def test_smtp_submit_sends_email(smtp_channel):
    result = smtp_channel.submit(ACTION)
    assert result.reference == f"RESOLVE-EMAIL-{ACTION['id'][:8].upper()}"
    assert "SMTP relay" in result.result
    assert len(FakeSMTP.instances) == 1
    server = FakeSMTP.instances[0]
    assert server.sent
    message = server.sent[0]
    assert message["From"] == "resolve@example.test"
    assert message["To"] == "operator@example.test"
    assert "RESOLVE action" in message["Subject"]
    assert message.get_content().strip() == ACTION["content"]


def test_smtp_recipient_never_derived_from_target(smtp_channel):
    evil = dict(ACTION, target="hacker@evil.example")
    smtp_channel.submit(evil)
    message = FakeSMTP.instances[0].sent[0]
    assert message["To"] == "operator@example.test"
    assert "hacker" not in message["To"]


def test_smtp_reference_is_deterministic(smtp_channel):
    first = smtp_channel.submit(ACTION)
    second = smtp_channel.submit(ACTION)
    assert first.reference == second.reference


def test_smtp_channel_is_duck_typing_channel(smtp_channel):
    assert isinstance(smtp_channel, Channel)
    assert smtp_channel.name == "smtp"


def test_smtp_missing_config_fails_closed(monkeypatch):
    for name in ("SMTP_HOST", "SMTP_FROM", "SMTP_TO"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(ChannelConfigError, match="missing SMTP configuration"):
        SmtpRelayChannel()


def test_smtp_missing_only_to_fails_closed(monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "127.0.0.1")
    monkeypatch.setenv("SMTP_FROM", "resolve@example.test")
    monkeypatch.delenv("SMTP_TO", raising=False)
    with pytest.raises(ChannelConfigError, match="SMTP_TO"):
        SmtpRelayChannel()


def test_smtp_invalid_port_fails_closed(monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "127.0.0.1")
    monkeypatch.setenv("SMTP_FROM", "resolve@example.test")
    monkeypatch.setenv("SMTP_TO", "operator@example.test")
    monkeypatch.setenv("SMTP_PORT", "not-a-number")
    with pytest.raises(ChannelConfigError, match="SMTP_PORT"):
        SmtpRelayChannel()


def test_smtp_error_is_sanitized(monkeypatch):
    class FailingSMTP:
        def __init__(self, host, port, timeout=None):
            self.login_calls = 0

        def __enter__(self):
            raise ConnectionRefusedError("connection refused to 127.0.0.1:1025")

        def __exit__(self, *args):
            return False

        def login(self, username, password):
            self.login_calls += 1

    monkeypatch.setattr("backend.channels.smtp.smtplib.SMTP", FailingSMTP)
    channel = SmtpRelayChannel(
        host="127.0.0.1",
        port=1025,
        from_addr="resolve@example.test",
        to_addrs="operator@example.test",
        username="smtpuser",
        password="supersecret-pw",
    )
    with pytest.raises(ChannelError, match="SMTP delivery failed"):
        channel.submit(ACTION)


def test_smtp_error_never_contains_credentials(monkeypatch):
    class LeakingSMTP:
        def __enter__(self):
            raise RuntimeError("auth failed for supersecret-pw")

        def __exit__(self, *args):
            return False

    monkeypatch.setattr("backend.channels.smtp.smtplib.SMTP", LeakingSMTP)
    channel = SmtpRelayChannel(
        host="localhost",
        port=1025,
        from_addr="resolve@example.test",
        to_addrs="operator@example.test",
        username="smtpuser",
        password="supersecret-pw",
    )
    with pytest.raises(ChannelError) as excinfo:
        channel.submit(ACTION)
    assert "supersecret-pw" not in str(excinfo.value)


def test_smtp_starttls_and_login_called_when_configured(monkeypatch):
    FakeSMTP.instances = []
    monkeypatch.setattr("backend.channels.smtp.smtplib.SMTP", FakeSMTP)
    channel = SmtpRelayChannel(
        host="127.0.0.1",
        port=1025,
        from_addr="resolve@example.test",
        to_addrs="operator@example.test",
        username="smtpuser",
        password="supersecret-pw",
        starttls=True,
    )
    channel.submit(ACTION)
    server = FakeSMTP.instances[0]
    assert server.starttls_calls == 1
    assert server.login_calls == 1