import json
import re
from typing import Any, Dict, Iterable, List, Optional


CHANNEL_PARAMS = {
    "tv": {"Path": "webtv", "Name": "电视剧"},
    "movie": {"Path": "webmovie", "Name": "电影"},
    "variety": {"Path": "webvariety", "Name": "综艺"},
    "anime": {"Path": "webcomic", "Name": "动漫"},
    "children": {"Path": "webchild", "Name": "少儿"},
    "documentary": {"Path": "webdocumentary", "Name": "纪录片"},
}

INITIAL_DATA_MARKER = "window.__INITIAL_DATA__ ="
DEFAULT_POSTER = "https://img.alicdn.com/imgextra/i2/O1CN01BeAcgL1ywY0G5nSn8_!!6000000006643-2-tps-195-195.png"


def clamp_positive_int(value: Any, default: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return min(max(parsed, 1), maximum)


def parse_initial_data(html: Any) -> Dict[str, Any]:
    """Parse Youku's server-rendered channel data without executing scripts."""
    if not isinstance(html, str):
        return {}
    marker_index = html.find(INITIAL_DATA_MARKER)
    if marker_index < 0:
        return {}
    start = marker_index + len(INITIAL_DATA_MARKER)
    end = html.find("</script>", start)
    if end < 0:
        return {}
    source = html[start:end].strip().rstrip(";")
    # The payload is JSON except that optional values can be emitted as the
    # JavaScript literal `undefined`.
    source = re.sub(
        r"([:,\[])\s*undefined(?=\s*[,}\]])",
        r"\1null",
        source,
    )
    try:
        payload = json.loads(source)
    except (TypeError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _component_items(module: Any) -> Iterable[Dict[str, Any]]:
    if not isinstance(module, dict):
        return
    for component in module.get("components") or []:
        if not isinstance(component, dict):
            continue
        # Short-video components represent clips rather than MoviePilot media.
        if "SHORT_VIDEO" in str(component.get("typeName") or ""):
            continue
        for item in component.get("itemList") or []:
            if isinstance(item, dict):
                yield item


def normalize_poster_url(value: Any) -> str:
    poster = str(value or "").strip()
    if poster.startswith("//"):
        poster = f"https:{poster}"
    elif poster.startswith("http://"):
        poster = f"https://{poster[7:]}"
    if not poster.startswith("https://"):
        return DEFAULT_POSTER
    return poster


def _media_id(item: Dict[str, Any]) -> str:
    action = item.get("action") if isinstance(item.get("action"), dict) else {}
    track_show = (
        item.get("trackShow") if isinstance(item.get("trackShow"), dict) else {}
    )
    candidates = (
        item.get("action_value"),
        action.get("value"),
        track_show.get("id"),
        item.get("id"),
    )
    for candidate in candidates:
        value = str(candidate or "").strip()
        if value:
            return value
    return ""


def _year(item: Dict[str, Any]) -> Optional[str]:
    for key in ("year", "releaseYear", "publishYear"):
        value = str(item.get(key) or "").strip()
        if re.fullmatch(r"(?:19|20)\d{2}", value):
            return value
    return None


def extract_media_items(payload: Any) -> List[Dict[str, Optional[str]]]:
    """Extract unique long-form media cards, preferring Youku's feed drawer."""
    if not isinstance(payload, dict):
        return []
    modules = payload.get("moduleList")
    if not isinstance(modules, list):
        return []
    feed_modules = [
        module
        for module in modules
        if isinstance(module, dict)
        and str(module.get("typeName") or "") == "FEED_DRAWER_PAGINATION"
    ]
    candidates = feed_modules or modules
    results: List[Dict[str, Optional[str]]] = []
    seen = set()
    for module in candidates:
        for item in _component_items(module):
            if item.get("isYkAd") or item.get("ad_flag") or item.get("rawAdData"):
                continue
            action_type = str(item.get("action_type") or "")
            if action_type and action_type not in {"JUMP_TO_SHOW", "JUMP_TO_VIDEO"}:
                continue
            title = str(item.get("title") or "").strip()
            media_id = _media_id(item)
            if not title or not media_id or media_id in seen:
                continue
            seen.add(media_id)
            results.append({
                "title": title,
                "year": _year(item),
                "media_id": media_id,
                "poster": normalize_poster_url(item.get("img") or item.get("hImg")),
            })
    return results


def page_items(
    items: Iterable[Dict[str, Optional[str]]], page: int, count: int
) -> List[Dict[str, Optional[str]]]:
    values = list(items)
    start = (page - 1) * count
    return values[start:start + count]
