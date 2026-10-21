#!/usr/bin/env python3
"""Watchdog pe gazda: verifica health check-ul GoldRetriever si anunta adminii cand nu raspunde.
Din cron, la 5 minute:  */5 * * * * /usr/bin/python3 /DATA/AppData/gold-retriever/tools/uptime_check.py
Adresa verificata: GR_HEALTH_URL (implicit http://localhost:8501/_stcore/health).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import uptime  # noqa: E402

if __name__ == "__main__":
    sys.exit(uptime.run())
