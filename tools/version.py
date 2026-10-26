#!/usr/bin/env python3
"""Versiunea din cel mai recent tag git: v0.2.0 + N commit-uri = 0.2.N.
Scrie build_info.json (citit de Settings > About). Utilizare: python3 tools/version.py [--print]
"""
import datetime
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)


def main(argv):
    r = git("describe", "--tags", "--long", "--match", "v[0-9]*")
    m = re.match(r"^v(\d+)\.(\d+)\.(\d+)-(\d+)-g([0-9a-f]+)$", r.stdout.strip())
    if r.returncode or not m:
        print("nu exista niciun tag vX.Y.Z", file=sys.stderr)
        return 1
    major, minor, patch, n, sha = m.groups()
    info = {
        "version": "%s.%s.%d" % (major, minor, int(patch) + int(n)),
        "base": "%s.%s.%s" % (major, minor, patch),
        "commits": int(n),
        "sha": sha,
        "dirty": bool(git("status", "--porcelain", "--untracked-files=no").stdout.strip()),
        "built": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
    }
    print(info["version"] + (" (modificari necomise)" if info["dirty"] else ""), info["sha"])
    if "--print" not in argv:
        with open(os.path.join(ROOT, "build_info.json"), "w", encoding="utf-8") as f:
            json.dump(info, f, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
