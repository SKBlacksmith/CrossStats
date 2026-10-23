"""External WAN info updater: writes the JSON file the daemon's [wan_info]
reads. The daemon itself does no network I/O — this command, run on a systemd
--user timer (see service/pirostats-wan.timer), owns it: it queries a public
geo-IP endpoint over HTTPS and atomically replaces the file.

pirostats wan-update FILE

Keeps the previous file untouched when no endpoint answers; the daemon's
[wan_info] max_age then renders stale data as empty until the next refresh.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import urllib.request

# Public geo-IP endpoints, tried in order until one answers. All free, no key
# required. Field normalization per provider lives in _normalize().
ENDPOINTS = (
    "https://ipwho.is/",
    "https://ifconfig.co/json",
    "https://ipinfo.io/json",
)

TIMEOUT_S = 5


def _normalize(endpoint: str, raw: dict) -> dict:
    """Common {ip, city, country, isp} from a provider's payload. Country is
    the full name when the provider gives one (ipwho.is, ifconfig.co);
    ipinfo.io only returns the ISO code."""
    if "ipwho.is" in endpoint:
        failed = raw.get("success") is False
        isp = (raw.get("connection") or {}).get("isp") or ""
    elif "ipinfo.io" in endpoint:
        failed = False
        org = raw.get("org") or ""
        isp = org.split(" ", 1)[1] if " " in org else org
    else:  # ifconfig.co
        failed = False
        isp = raw.get("asn_org") or raw.get("company") or ""
    return {
        "ip": "" if failed else (raw.get("ip") or ""),
        "city": raw.get("city") or "",
        "country": raw.get("country") or "",
        "isp": isp,
    }


def fetch(endpoints=ENDPOINTS, timeout=TIMEOUT_S, urlopen=None) -> dict | None:
    """The first endpoint that answers with a payload carrying an IP, else
    None when every endpoint fails (transport error or unparsable body)."""
    opener = urlopen or urllib.request.urlopen
    for endpoint in endpoints:
        try:
            with opener(endpoint, timeout=timeout) as resp:
                raw = json.load(resp)
        except (OSError, ValueError):
            continue
        info = _normalize(endpoint, raw)
        if info["ip"]:
            return info
    return None


def write(path: str, info: dict) -> None:
    """Atomically replaces `path` with `info` plus an `updated` unix timestamp,
    so the daemon never sees a half-written file."""
    record = dict(info)
    record["updated"] = int(time.time())
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".wan-info.")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(record, f)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def update(path: str) -> bool:
    """One refresh cycle. False (previous file untouched) when no endpoint
    answered."""
    info = fetch()
    if info is None:
        return False
    write(path, info)
    return True


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: wan-update FILE")
    sys.exit(0 if update(sys.argv[1]) else 1)
