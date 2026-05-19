#!/usr/bin/env python3
"""
Trigger the daily digest cron via the internal HTTP endpoint.
"""

import json
import os
import sys
import urllib.error
import urllib.request

from core.config import get_app_base_url, get_internal_cron_token


def main() -> int:
    token = get_internal_cron_token()
    if not token:
        print("INTERNAL_CRON_TOKEN is not configured", file=sys.stderr)
        return 1

    url = f"{get_app_base_url().rstrip('/')}/internal/cron/daily-digest"
    request = urllib.request.Request(
        url,
        method="POST",
        headers={"Authorization": f"Bearer {token}"},
    )

    try:
        with urllib.request.urlopen(request, timeout=3600) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        print(f"Cron request failed ({error.code}): {body}", file=sys.stderr)
        return 1
    except urllib.error.URLError as error:
        print(f"Cron request failed: {error}", file=sys.stderr)
        return 1

    print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
