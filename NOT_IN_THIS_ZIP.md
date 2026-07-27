# What wasn't in this zip

Checked the whole export against what the code itself references. One thing
is missing, and it's not a small thing:

## `.github/workflows/` was completely absent

No `daily_post.yml`, no `weekly_strategy.yml`, no `monthly_cross_promo.yml`
— the folder didn't exist anywhere in the zip. That's the literal cron
trigger for everything else in this repo. Every piece of "autonomous"
machinery described in `INTELLIGENCE_ARCHITECTURE.md` (topic auto-refill,
spaced-repetition review, poll harvesting, weekly schedule reallocation)
only runs when something actually invokes `python main.py` /
`python weekly_strategy.py`. Without a scheduled workflow, this is a
collection of correct scripts, not a self-sustaining channel.

This isn't a guess that they're missing entirely, though — two of your own
files prove they exist somewhere:

- `story-removal-and-fixes.diff` contains hunks applied *to*
  `.github/workflows/daily_post.yml` and `.github/workflows/weekly_strategy.yml`.
- `engagement_schedule.patch` contains another hunk applied to
  `.github/workflows/weekly_strategy.yml`.

A diff only shows changed lines plus a few lines of surrounding context —
never the full file — so what I could recover from those two fragments was
partial: the "commit updated data/strategy" step, the push-retry loop, and
the admin-alert-on-push-failure block, verbatim. The trigger schedule, the
checkout/setup-python/install steps, and the main run step's env block
weren't in either diff, so I reconstructed those from `config.py`'s own
comments (`POSTS_PER_DAY`, which secrets each module reads) rather than
inventing them from nothing.

**Bottom line: the three files now in `.github/workflows/` are a
reconstruction, not a copy of what's actually deployed.** Each one says so
at the top. Diff them against whatever's live in your actual GitHub repo
before replacing anything — if they disagree, your real ones are the
source of truth, not these.

## Everything else matched

`full-diff-vs-original-upload.diff` doesn't touch `.github/` at all, which
is consistent with those files predating that diff's range rather than
being dropped from this export by accident. Every `.py` module the diffs
and `AUDIT_FIXES.md` reference is present and consistent with its own
history — nothing else in the export looked incomplete.
