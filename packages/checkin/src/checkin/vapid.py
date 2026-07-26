"""Generate the VAPID key pair Web Push needs.

    uv run python -m checkin.vapid

Run once. The private key signs every push; the public key is compiled into the
app so the browser can verify the sender. Losing the private key does not leak
health data — nothing clinical is stored in a subscription — but it does mean
every installed app must re-subscribe, so keep it out of git.
"""

import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

COORDINATE_BYTES = 32
"""P-256. Both coordinates are fixed-width — left-padding matters, because a key
whose x happens to start with a zero byte is otherwise silently one byte short."""


def generate() -> tuple[str, str]:
    """Returns (private_key_pem, public_key_base64url).

    The public half goes to the browser in the uncompressed point format the
    Push API expects; the private half stays in the environment.
    """
    private_key = ec.generate_private_key(ec.SECP256R1())
    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()

    numbers = private_key.public_key().public_numbers()
    raw = (
        b"\x04"
        + numbers.x.to_bytes(COORDINATE_BYTES, "big")
        + numbers.y.to_bytes(COORDINATE_BYTES, "big")
    )
    return pem, base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def main() -> None:
    private_pem, public_b64 = generate()
    print("# Add to your environment (keep the private key out of git):")
    print(f'VAPID_PRIVATE_KEY="{private_pem.strip()}"')
    print()
    print("# Add to web/app/.env.local:")
    print(f"NEXT_PUBLIC_VAPID_PUBLIC_KEY={public_b64}")


if __name__ == "__main__":
    main()
