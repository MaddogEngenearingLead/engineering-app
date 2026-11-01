"""Local user accounts for the desktop app, stored in <data dir>/accounts.json.

Passwords and security answers are stored only as salted PBKDF2 hashes.
Accounts are per computer; there is no server.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import time
from pathlib import Path

ITERATIONS = 200_000
MIN_PASSWORD_LEN = 8
MAX_ATTEMPTS = 5
LOCKOUT_SECONDS = 60

SECURITY_QUESTIONS = [
    "What was the name of your first pet?",
    "What city were you born in?",
    "What was the name of your first school?",
    "What is your mother's maiden name?",
    "What was the make of your first car?",
]


class AccountError(ValueError):
    """User-facing account error."""


def _hash(secret: str, salt: bytes) -> str:
    return hashlib.pbkdf2_hmac("sha256", secret.encode("utf-8"), salt, ITERATIONS).hex()


def _normalise_answer(answer: str) -> str:
    return re.sub(r"\s+", " ", answer.strip().lower())


def _make_hash(secret: str) -> dict:
    salt = secrets.token_bytes(16)
    return {"salt": salt.hex(), "hash": _hash(secret, salt)}


def _verify(secret: str, record: dict) -> bool:
    expected = _hash(secret, bytes.fromhex(record["salt"]))
    return hmac.compare_digest(expected, record["hash"])


class AccountStore:
    def __init__(self, data_dir: str | Path):
        self.path = Path(data_dir) / "accounts.json"
        self._failures: dict[str, list[float]] = {}

    # -- persistence ---------------------------------------------------

    def _load(self) -> dict:
        if not self.path.is_file():
            return {}
        try:
            return json.loads(self.path.read_text())
        except (OSError, ValueError):
            return {}

    def _save(self, users: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(users, indent=2))
        os.replace(tmp, self.path)

    @staticmethod
    def _key(username: str) -> str:
        return username.strip().lower()

    def has_accounts(self) -> bool:
        return bool(self._load())

    # -- rate limiting -------------------------------------------------

    def _check_lock(self, key: str) -> None:
        now = time.time()
        recent = [t for t in self._failures.get(key, []) if now - t < LOCKOUT_SECONDS]
        self._failures[key] = recent
        if len(recent) >= MAX_ATTEMPTS:
            wait = int(LOCKOUT_SECONDS - (now - recent[0])) + 1
            raise AccountError(f"Too many failed attempts. Try again in {wait} seconds.")

    def _fail(self, key: str) -> None:
        self._failures.setdefault(key, []).append(time.time())

    # -- operations ----------------------------------------------------

    @staticmethod
    def validate_password(password: str) -> None:
        if len(password) < MIN_PASSWORD_LEN:
            raise AccountError(f"Password must be at least {MIN_PASSWORD_LEN} characters.")

    def create_account(self, username: str, password: str, question: str, answer: str) -> None:
        key = self._key(username)
        if not key:
            raise AccountError("Username is required.")
        if question not in SECURITY_QUESTIONS:
            raise AccountError("Choose a security question.")
        if not _normalise_answer(answer):
            raise AccountError("Security answer is required.")
        self.validate_password(password)
        users = self._load()
        if key in users:
            raise AccountError("That username is already taken.")
        users[key] = {
            "username": username.strip(),
            "password": _make_hash(password),
            "question": question,
            "answer": _make_hash(_normalise_answer(answer)),
        }
        self._save(users)

    def authenticate(self, username: str, password: str) -> str:
        """Return the stored username on success; raise AccountError otherwise."""
        key = self._key(username)
        self._check_lock(key)
        user = self._load().get(key)
        if not user or not _verify(password, user["password"]):
            self._fail(key)
            raise AccountError("Invalid username or password.")
        self._failures.pop(key, None)
        return user["username"]

    def get_question(self, username: str) -> str:
        user = self._load().get(self._key(username))
        if not user:
            raise AccountError("No account with that username.")
        return user["question"]

    def reset_password(self, username: str, answer: str, new_password: str) -> None:
        key = self._key(username)
        self._check_lock("reset:" + key)
        users = self._load()
        user = users.get(key)
        if not user or not _verify(_normalise_answer(answer), user["answer"]):
            self._fail("reset:" + key)
            raise AccountError("Security answer is incorrect.")
        self.validate_password(new_password)
        user["password"] = _make_hash(new_password)
        users[key] = user
        self._save(users)
        self._failures.pop("reset:" + key, None)
