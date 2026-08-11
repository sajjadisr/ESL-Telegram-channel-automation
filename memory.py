import datetime
import json
import os
import tempfile


def load_json(path, default):
    """Load a JSON file, or return `default` if it doesn't exist yet.

    Bug fix: a truncated/corrupted file used to raise json.JSONDecodeError
    straight out of this function. Since this is the sole read path for
    every *.json file the whole pipeline depends on, one bad write used to
    permanently break every future run. Now: a corrupt file is renamed
    aside (never silently overwritten or discarded -- it's still there for
    forensics) and treated as if it were missing, so the run continues
    with `default` instead of crashing. Always prints loudly either way,
    so a real problem still shows up in the run log.
    """
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as exc:
        stamp = datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        quarantine_path = f"{path}.corrupt-{stamp}"
        print(f"memory.load_json: {path} is corrupt/unreadable ({exc}); "
              f"moving it to {quarantine_path} and continuing with a fresh default.")
        try:
            os.replace(path, quarantine_path)
        except OSError as rename_exc:
            print(f"memory.load_json: could not even move aside {path}: {rename_exc}")
        return default


def save_json(path, data):
    """Write `data` to `path` as JSON, atomically.

    Bug fix: this used to write straight to `path`. A process kill, OOM,
    or CI timeout mid-write left a truncated file behind -- which
    load_json() above then had no way to recover from. Now it writes to a
    temp file in the same directory and atomically renames it into place
    (os.replace is atomic on POSIX, and on Windows for files on the same
    volume), so `path` itself is either the old complete file or the new
    complete file, never a partial one.
    """
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=directory, prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except BaseException:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise
