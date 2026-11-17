"""PANs are envelope-encrypted: a data key per value, wrapped by a keyring, bound to a Customer."""

import random
from collections.abc import Callable

import pytest

from kosha_domain.vault import LocalKeyring, PanVault, VaultError

ALICE = "cus_01JZ8Q4V9X2M3N4P5Q6R7S8T9V"
BOB = "cus_01JZ8Q4V9X2M3N4P5Q6R7S8T9W"
PAN = "ABCPS1234D"


@pytest.fixture
def vault() -> PanVault:
    return PanVault(LocalKeyring("local-only passphrase for tests"))


def test_a_pan_round_trips_for_its_customer(vault: PanVault) -> None:
    token = vault.encrypt(PAN, customer_id=ALICE)

    assert vault.decrypt(token, customer_id=ALICE) == PAN


def test_a_token_is_tagged_and_never_contains_the_pan(vault: PanVault) -> None:
    token = vault.encrypt(PAN, customer_id=ALICE)

    assert token.startswith("kms:v1:")
    assert PAN not in token


def test_a_token_copied_to_another_customer_cannot_be_decrypted(vault: PanVault) -> None:
    token = vault.encrypt(PAN, customer_id=ALICE)

    with pytest.raises(VaultError):
        vault.decrypt(token, customer_id=BOB)


def test_another_keyring_cannot_decrypt(vault: PanVault) -> None:
    token = vault.encrypt(PAN, customer_id=ALICE)
    other = PanVault(LocalKeyring("a different passphrase"))

    with pytest.raises(VaultError):
        other.decrypt(token, customer_id=ALICE)


def _bump_version(token: str) -> str:
    return token.replace("kms:v1:", "kms:v2:")


def _tamper(token: str) -> str:
    return token[:-4] + ("BBBB" if token.endswith("AAAA") else "AAAA")


def _truncate(token: str) -> str:
    return token.partition(".")[0]


def _garbage(_: str) -> str:
    return "kms:v1:not base64!.x.y"


@pytest.mark.parametrize(
    "mangle",
    [_bump_version, _tamper, _truncate, _garbage],
    ids=["version", "tampered ciphertext", "truncated", "garbage"],
)
def test_a_damaged_token_is_refused(vault: PanVault, mangle: Callable[[str], str]) -> None:
    token = vault.encrypt(PAN, customer_id=ALICE)

    with pytest.raises(VaultError):
        vault.decrypt(mangle(token), customer_id=ALICE)


def test_each_encryption_uses_a_fresh_data_key(vault: PanVault) -> None:
    assert vault.encrypt(PAN, customer_id=ALICE) != vault.encrypt(PAN, customer_id=ALICE)


def test_seeded_randomness_makes_tokens_reproducible(vault: PanVault) -> None:
    first = vault.encrypt(PAN, customer_id=ALICE, randbytes=random.Random(7).randbytes)
    again = vault.encrypt(PAN, customer_id=ALICE, randbytes=random.Random(7).randbytes)

    assert first == again
    assert vault.decrypt(first, customer_id=ALICE) == PAN


def test_a_keyring_needs_a_passphrase() -> None:
    with pytest.raises(ValueError, match="passphrase"):
        LocalKeyring("")
