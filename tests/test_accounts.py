import pytest

from app.services.accounts import MAX_ATTEMPTS, SECURITY_QUESTIONS, AccountError, AccountStore

Q = SECURITY_QUESTIONS[0]


@pytest.fixture
def store(tmp_path):
    s = AccountStore(tmp_path)
    s.create_account("Alice", "password1", Q, "Fido")
    return s


def test_login_ok_and_case_insensitive_username(store):
    assert store.authenticate("alice", "password1") == "Alice"


def test_wrong_password(store):
    with pytest.raises(AccountError):
        store.authenticate("alice", "nope")
    with pytest.raises(AccountError):
        store.authenticate("ghost", "password1")


def test_no_plaintext_stored(store):
    text = store.path.read_text()
    assert "password1" not in text and "fido" not in text.lower()


def test_duplicate_and_weak_password(store):
    with pytest.raises(AccountError):
        store.create_account("ALICE", "password2", Q, "x")
    with pytest.raises(AccountError):
        store.create_account("bob", "short", Q, "x")


def test_reset_password(store):
    assert store.get_question("alice") == Q
    with pytest.raises(AccountError):
        store.reset_password("alice", "wrong", "newpassword")
    store.reset_password("alice", "  fido ", "newpassword")
    assert store.authenticate("alice", "newpassword")
    with pytest.raises(AccountError):
        store.authenticate("alice", "password1")


def test_lockout(store):
    for _ in range(MAX_ATTEMPTS):
        with pytest.raises(AccountError):
            store.authenticate("alice", "bad")
    with pytest.raises(AccountError, match="Too many"):
        store.authenticate("alice", "password1")
