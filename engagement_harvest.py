"""Backfills real views/forwards for every post format via a Telethon
(MTProto) userbot session — closes the measurement gap analytics.py's own
docstring names, which the plain Bot API structurally can't close on its
own: reading a channel message's views/forwards requires a userbot
session, not a bot-token client (see analytics.py's module docstring).

Fully optional: silently no-ops (one print, changes nothing else) unless
TELEGRAM_API_ID, TELEGRAM_API_HASH, and TELETHON_SESSION_STRING are all
configured (config.py). The first two are a personal app credential from
https://my.telegram.org/apps; the third needs a ONE-TIME interactive login
(phone + code, maybe 2FA) on a device tied to your Telegram account — see
scripts/generate_telethon_session.py. Once that string is saved as a
GitHub secret, this never needs a human again: client.get_messages just
READS message metadata, it never increments a view counter the way
Telegram's own "mark as viewed" client behavior does, so it's safe to run
from the same daily cron job indefinitely.
"""

from telethon.sync import TelegramClient
from telethon.sessions import StringSession

from config import TELEGRAM_API_ID, TELEGRAM_API_HASH, TELETHON_SESSION_STRING, TELEGRAM_CHANNEL_ID
import analytics


def _configured():
    return bool(TELEGRAM_API_ID and TELEGRAM_API_HASH and TELETHON_SESSION_STRING)


def _fetch_views_forwards(message_ids):
    """Returns {message_id: (views, forwards)} for every id Telegram still
    has a message for. A deleted/inaccessible message comes back as None
    from get_messages and is simply omitted — nothing to harvest for it,
    and analytics.apply_harvested_engagement leaves that entry's metrics
    as None rather than treating the gap as zero engagement.

    Bug fix (#28): this used to open the client with `with client:`, which
    Telethon documents as being exactly equivalent to calling .start() —
    "it will automatically start() the client, logging or signing up if
    necessary." If TELETHON_SESSION_STRING is ever invalid, expired, or
    revoked, .start() performs an INTERACTIVE login, calling input() for a
    phone number/code — which would hang forever waiting on stdin in the
    non-interactive GitHub Actions runner, not raise a catchable
    exception, so the try/except in harvest_engagement_metrics couldn't
    do anything about it. connect() (documented by Telethon as the
    interactive-free building block .start() is made from) never prompts;
    is_user_authorized() is checked explicitly afterward, and a clear,
    immediately-catchable RuntimeError is raised instead of ever reaching
    the interactive path.
    """
    client = TelegramClient(
        StringSession(TELETHON_SESSION_STRING),
        int(TELEGRAM_API_ID),
        TELEGRAM_API_HASH,
    )
    results = {}
    client.connect()
    try:
        if not client.is_user_authorized():
            raise RuntimeError(
                "TELETHON_SESSION_STRING is set but is no longer authorized "
                "(expired, revoked, or logged out from another device?). Generate "
                "a fresh one with scripts/generate_telethon_session.py."
            )
        # TELEGRAM_CHANNEL_ID is whatever the Bot API side already uses
        # (typically "@channelusername") — Telethon resolves the same
        # username string directly, so no separate identifier is needed.
        messages = client.get_messages(TELEGRAM_CHANNEL_ID, ids=message_ids)
        for msg in messages:
            if msg is None:
                continue
            reactions = getattr(msg, "reactions", None)
            reaction_count = None
            if reactions is not None:
                reaction_count = getattr(reactions, "count", None)
                if reaction_count is None:
                    reaction_count = getattr(reactions, "total", None)
                try:
                    reaction_count = int(reaction_count)
                except (TypeError, ValueError):
                    reaction_count = None
            results[msg.id] = (msg.views or 0, msg.forwards or 0, reaction_count)
    finally:
        client.disconnect()
    return results


def harvest_engagement_metrics():
    """Call once per main() run, alongside harvest_pending_polls() — cheap
    no-op when not configured, and cheap even when it is: at most a
    couple weeks' worth of posts to look up, in one Telethon call."""
    if not _configured():
        print(
            "engagement_harvest: TELEGRAM_API_ID / TELEGRAM_API_HASH / TELETHON_SESSION_STRING "
            "not fully configured — skipping (see scripts/generate_telethon_session.py to set "
            "this up once; every other part of the pipeline is unaffected either way)."
        )
        return

    pending_ids = analytics.entries_pending_harvest()
    if not pending_ids:
        return

    try:
        results = _fetch_views_forwards(pending_ids)
    except Exception as exc:  # noqa: BLE001 — a Telethon hiccup must not crash the whole run
        print(f"engagement_harvest: fetch failed, skipping this run: {exc}")
        return

    updated = analytics.apply_harvested_engagement(results)
    if updated:
        print(f"engagement_harvest: backfilled views/forwards for {updated} post(s).")
