import pytest

import auth
import users


@pytest.fixture
def alerts_sent(monkeypatch):
    sent = []
    monkeypatch.setattr(auth.alerts, "record_lockout", lambda *a: sent.append(("lockout",) + a))
    monkeypatch.setattr(auth.alerts, "record_ip_block", lambda *a: sent.append(("ip",) + a))
    monkeypatch.setattr(auth.alerts, "record_account_attack", lambda *a: sent.append(("acct",) + a))
    return sent


def _fail(key, ip, n, now=1000.0):
    for i in range(n):
        auth._register_fail(key, ip, now=now + i)


def test_lock_is_per_account_and_ip(alerts_sent):
    users.create_user("ana", "ana-secret-pass", "admin")
    _fail("ana", "198.51.100.9", auth._MAX_FAILS)
    assert auth._lock_remaining("ana", "198.51.100.9", now=1010) > 0
    # proprietarul contului, de pe alt IP, nu e blocat
    assert auth._lock_remaining("ana", "192.168.68.8", now=1010) == 0
    assert alerts_sent[0][:2] == ("lockout", "ana")


def test_ip_trying_many_accounts_is_blocked(alerts_sent):
    for i in range(auth._IP_MAX_FAILS):
        auth._register_fail("user%d" % i, "203.0.113.5", now=1000.0 + i)
    assert auth._lock_remaining("someone-else", "203.0.113.5", now=1030) > 0
    assert auth._lock_remaining("someone-else", "203.0.113.6", now=1030) == 0
    assert auth._lock_remaining("x", "203.0.113.5", now=1000 + 19 + auth._IP_LOCK_SECONDS + 1) == 0
    assert ("ip", "203.0.113.5", auth._IP_MAX_FAILS, auth._IP_WINDOW, auth._IP_LOCK_SECONDS) in alerts_sent


def test_ip_failures_outside_the_window_do_not_count(alerts_sent):
    for i in range(auth._IP_MAX_FAILS - 1):
        auth._register_fail("u%d" % i, "203.0.113.5", now=1000.0)
    auth._register_fail("u", "203.0.113.5", now=1000.0 + auth._IP_WINDOW + 1)
    assert auth._lock_remaining("u", "203.0.113.5", now=1000.0 + auth._IP_WINDOW + 2) == 0


def test_distributed_attack_locks_the_account(alerts_sent):
    for i in range(auth._ACCT_MAX_FAILS):
        auth._register_fail("ana", "10.0.%d.%d" % (i // 250, i % 250), now=1000.0 + i)
    assert auth._lock_remaining("ana", "192.168.68.8", now=1100) > 0
    assert any(a[0] == "acct" for a in alerts_sent)


def test_old_pair_failures_are_forgotten(alerts_sent):
    _fail("ana", "198.51.100.9", auth._MAX_FAILS - 1)
    auth._register_fail("ana", "198.51.100.9", now=1000.0 + auth._IP_WINDOW + 10)
    assert auth._lock_remaining("ana", "198.51.100.9", now=1000.0 + auth._IP_WINDOW + 11) == 0


def test_success_clears_only_the_pair(alerts_sent):
    _fail("ana", "198.51.100.9", 3)
    auth._clear_fails("ana", "198.51.100.9")
    assert ("ana", "198.51.100.9") not in auth._fails
    assert len(auth._ip_fails["198.51.100.9"]) == 3


def test_prune_keeps_memory_bounded(alerts_sent, monkeypatch):
    monkeypatch.setattr(auth, "_PRUNE_AT", 10)
    for i in range(30):
        auth._register_fail("u%d" % i, "10.1.0.%d" % i, now=1000.0)
    auth._register_fail("late", "10.9.9.9", now=1000.0 + auth._ACCT_WINDOW + 1)
    assert len(auth._fails) + len(auth._ip_fails) + len(auth._acct_fails) <= 6


@pytest.mark.parametrize("peer,fwd,proxies,ip", [
    ("192.168.68.8", "6.6.6.6", "", "192.168.68.8"),                # fara proxy de incredere: antetul e ignorat
    ("172.29.0.1", "6.6.6.6", "", "172.29.0.1"),
    ("172.29.0.1", "198.51.100.7", "172.16.0.0/12", "198.51.100.7"),
    ("172.29.0.1", "6.6.6.6, 198.51.100.7", "172.16.0.0/12", "198.51.100.7"),  # primul hop poate fi falsificat
    ("172.29.0.1", "198.51.100.7, 172.20.0.3", "172.16.0.0/12", "198.51.100.7"),
    ("172.29.0.1", "", "172.16.0.0/12", "172.29.0.1"),
    ("172.29.0.1", "junk", "172.16.0.0/12", "junk"),
    (None, "6.6.6.6", "", None),
])
def test_client_ip_trusts_forwarded_only_from_proxies(peer, fwd, proxies, ip):
    assert auth.client_ip(peer, fwd, proxies) == ip
