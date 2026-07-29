"""Run this ONCE, locally, on a device signed into the Telegram account you
want engagement_harvest.py to read message stats as. This is NOT something
CI, or Claude, or anyone but you can do — it needs an interactive login
(your phone number, the code Telegram texts/sends you, and your 2FA
password if you have one set).

Prerequisites:
  1. pip install telethon
  2. Get TELEGRAM_API_ID and TELEGRAM_API_HASH (free) from
     https://my.telegram.org/apps — log in with the SAME phone number as
     the account you want to use, then "API development tools" ->
     "Create new application" (any name/platform is fine, those fields
     aren't checked against anything).

Usage:
    python scripts/generate_telethon_session.py

Follow the prompts. At the end it prints a long string — save that as the
TELETHON_SESSION_STRING GitHub secret, alongside TELEGRAM_API_ID and
TELEGRAM_API_HASH as their own secrets (engagement_harvest.py needs all
three). This script doesn't need to be run again after that, and the
string doesn't expire on its own — only regenerate it if you explicitly
log that session out (Telegram Settings -> Devices).

Security note: treat the printed string exactly like a password, not like
an API key you'd casually paste into a chat. Anyone who has it can act as
your Telegram account — send messages, read your chats, everything — not
just read this channel's post stats. Only ever put it in a GitHub Actions
secret (encrypted, never shown in logs); never commit it to a file or
paste it anywhere else.
"""

import getpass

from telethon.sync import TelegramClient
from telethon.sessions import StringSession


def main():
    print(__doc__)
    api_id = input("TELEGRAM_API_ID (from https://my.telegram.org/apps): ").strip()
    api_hash = input("TELEGRAM_API_HASH: ").strip()

    with TelegramClient(StringSession(), int(api_id), api_hash) as client:
        client.start(
            phone=lambda: input("Phone number, with country code (e.g. +989123456789): ").strip(),
            password=lambda: getpass.getpass(
                "2FA password (leave blank + Enter if your account doesn't have one): "
            ),
        )
        session_string = client.session.save()

    print("\n" + "=" * 70)
    print("Success! Save this as the TELETHON_SESSION_STRING GitHub secret:\n")
    print(session_string)
    print("=" * 70)
    print(
        "\nAlso save TELEGRAM_API_ID and TELEGRAM_API_HASH (the two values you "
        "entered above) as their own GitHub secrets — engagement_harvest.py "
        "needs all three to be set."
    )


if __name__ == "__main__":
    main()
