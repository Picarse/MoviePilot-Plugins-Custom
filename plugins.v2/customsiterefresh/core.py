from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse


def normalize_host(value: str) -> str:
    """Return a lowercase hostname without credentials, port, path or trailing dot."""
    raw = str(value or "").strip()
    if not raw:
        return ""
    parsed = urlparse(raw if "://" in raw else f"//{raw}")
    return str(parsed.hostname or "").lower().rstrip(".")


def parse_site_configs(siteconf: str) -> Tuple[List[Dict[str, str]], List[str]]:
    """Parse domain|username|password(|2fa) lines without logging credentials."""
    configs: List[Dict[str, str]] = []
    errors: List[str] = []
    for line_number, raw_line in enumerate(str(siteconf or "").splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        parts = [part.strip() for part in line.split("|", 3)]
        if len(parts) < 3 or not all(parts[:3]):
            errors.append(f"第 {line_number} 行格式错误")
            continue
        host = normalize_host(parts[0])
        if not host:
            errors.append(f"第 {line_number} 行域名无效")
            continue
        configs.append({
            "host": host,
            "username": parts[1],
            "password": parts[2],
            "two_step_code": parts[3] if len(parts) == 4 else "",
        })
    return configs, errors


def find_site_config(site_url: str, configs: List[Dict[str, str]]) -> Optional[Dict[str, str]]:
    """Match an exact host or a configured parent domain on a DNS label boundary."""
    site_host = normalize_host(site_url)
    if not site_host:
        return None
    exact_match = next((item for item in configs if item["host"] == site_host), None)
    if exact_match:
        return exact_match
    parent_matches = [
        item for item in configs
        if site_host.endswith(f".{item['host']}")
    ]
    if not parent_matches:
        return None
    return max(parent_matches, key=lambda item: len(item["host"]))
