#!/usr/bin/env python3
"""Trimite o notificare email cu setarile din data/mail.json.
Utilizare: python3 tools/notify_cli.py EVENT "Subiect" "Mesaj" [cheie]
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import notify  # noqa: E402


def main(argv):
    if len(argv) < 4:
        print(__doc__)
        return 2
    key = argv[4] if len(argv) > 4 else None
    ok = notify.notify(argv[1], argv[2], argv[3], key=key, sync=True)
    print("trimis" if ok else "netrimis (dezactivat, nesetat, limitat in timp sau eroare)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
