from typing import Any, Dict, Iterable, List


CHANNEL_PARAMS = {
    "电视剧": "2",
    "电影": "3",
    "动漫": "50",
    "少儿": "10",
    "综艺": "1",
    "纪录片": "51",
    "教育": "115",
}

FILTER_PARAM_NAMES = (
    "chargeInfo",
    "sort",
    "kind",
    "edition",
    "area",
    "fitAge",
    "year",
    "feature",
)


def clamp_positive_int(value: Any, default: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return min(max(parsed, 1), maximum)


def extract_filter_groups(payload: Any) -> List[Dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    data = payload.get("data")
    groups = data.get("listItems") if isinstance(data, dict) else None
    if not isinstance(groups, list):
        return []

    result = []
    for group in groups:
        if not isinstance(group, dict):
            continue
        key = str(group.get("eName") or "").strip()
        label = str(group.get("typeName") or "").strip()
        if key not in FILTER_PARAM_NAMES or not label:
            continue
        options = []
        seen = set()
        for item in group.get("items") or []:
            if not isinstance(item, dict):
                continue
            text = str(item.get("tagName") or "").strip()
            value = str(item.get("tagId") or "").strip()
            if not text or not value or text == "全部" or value in seen:
                continue
            seen.add(value)
            options.append({"value": value, "text": text})
        if options:
            result.append({"key": key, "label": label, "options": options})
    return result


def extract_hit_docs(payload: Any) -> List[Dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    data = payload.get("data")
    items = data.get("hitDocs") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)]


def normalize_poster_url(value: Any) -> str:
    poster = str(value or "").strip()
    if poster.startswith("//"):
        return f"https:{poster}"
    if poster.startswith("http://"):
        return f"https://{poster[7:]}"
    return poster if poster.startswith("https://") else ""


def media_items(items: Iterable[Dict[str, Any]], count: int) -> List[Dict[str, Any]]:
    result = []
    seen = set()
    for item in items or []:
        title = str(item.get("title") or "").strip()
        media_id = str(item.get("clipId") or "").strip()
        if not title or not media_id or media_id in seen:
            continue
        seen.add(media_id)
        normalized = dict(item)
        normalized["title"] = title
        normalized["clipId"] = media_id
        normalized["img"] = normalize_poster_url(item.get("img"))
        result.append(normalized)
        if len(result) >= count:
            break
    return result
