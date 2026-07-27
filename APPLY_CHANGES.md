# How to apply this

Two different trust levels in this folder — treat them differently.

## Safe to drop in as-is (real source, not reconstructed)
- `config.py`
- `database.py`
- `.gitignore`
- `AUDIT_FIXES.md`
- `scripts/migrate_posts_db_to_jsonl.py`
- `scripts/check_daily_completion.py`
- `.github/workflows/daily_completion_check.yml` (brand new, nothing live to conflict with)

## Don't overwrite blindly — these three are reconstructed
`daily_post.yml`, `weekly_strategy.yml`, `monthly_cross_promo.yml` were rebuilt
from diff fragments (see `NOT_IN_THIS_ZIP.md` in the original export), not
copied from what's actually deployed. Open your REAL live files on GitHub and
apply just these specific edits by hand:

**daily_post.yml**
- `on.schedule`: replace the 3 cron lines with the 6 in this version (3
  primary + 3 catch-up, off round minutes). See the comments in the file for
  why.
- `Checkout` step: change `fetch-depth: 0` → `fetch-depth: 1`.

**weekly_strategy.yml**
- `on.schedule`: `"0 12 * * 5"` → `"19 12 * * 5"`.
- `Checkout` step: change `fetch-depth: 0` → `fetch-depth: 1`.

**monthly_cross_promo.yml**
- `on.schedule`: `"0 8 1 * *"` → `"23 8 1 * *"`.

If your real files already differ structurally from these (different step
names, extra steps, etc.), just port the specific lines above into your real
file — don't replace the whole thing.

## The posts.db → posts.jsonl migration (one-time, do this last)

**Important:** the `data/posts.jsonl` included here was generated from the
`posts.db` in the zip you gave me (6 rows, through 2026-07-26). If
`daily_post.yml` has run again since you exported that zip, your real
`posts.db` has more rows than this file does — regenerate it yourself
instead of using mine:

```bash
git pull                                    # get your latest repo state
python scripts/migrate_posts_db_to_jsonl.py # reads your REAL current posts.db,
                                             # overwrites data/posts.jsonl from it
git add data/posts.jsonl
git rm --cached data/posts.db               # stop tracking the binary — .gitignore
                                             # alone can't do this for an
                                             # already-tracked file
git commit -m "Migrate posts.db to posts.jsonl (git hygiene, AUDIT_FIXES.md #9)"
git push
```

If nothing has posted since your export, the `data/posts.jsonl` already in
this folder is correct and you can just `git add` it directly instead of
re-running the script.

Nothing else needs to change after this — the very next `daily_post.yml` run
does a fresh checkout (no `posts.db` on disk, since it's gitignored),
`database.get_conn()` rebuilds it locally from `posts.jsonl` automatically,
and every query function behaves exactly as before.

## After deploying, worth checking once
- The next `daily_post.yml` run's "Commit updated data" step should now
  show `data/posts.jsonl` in the diff, never `data/posts.db`.
- The first live run after the `fetch-depth: 1` change — this was validated
  with a local git simulation (concurrent push + shallow clone + rebase +
  push all succeeded), not against GitHub's actual infrastructure, so it's
  worth a glance.
