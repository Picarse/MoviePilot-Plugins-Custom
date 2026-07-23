import re
from typing import Any, Dict, Iterable, List


CHANNEL_PARAMS = {
    "tv": {"Id": "100113", "Name": "电视剧"},
    "movie": {"Id": "100173", "Name": "电影"},
    "variety": {"Id": "100109", "Name": "综艺"},
    "anime": {"Id": "100119", "Name": "动漫"},
    "children": {"Id": "100150", "Name": "少儿"},
    "documentary": {"Id": "100105", "Name": "纪录片"},
}

FILTER_PARAM_NAMES = (
    "recommend_3",
    "itrailer",
    "exclusive",
    "child_ip",
    "characteristic",
    "anime_status",
    "recommend",
    "language",
    "iregion",
    "iyear",
    "all",
    "sort",
    "ipay",
    "producer",
    "iarea",
    "pay",
    "attr",
    "item",
    "itype",
    "recommend_2",
    "recommend_1",
    "award",
    "theater",
    "gender",
)


def clamp_positive_int(value: Any, default: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return min(max(parsed, 1), maximum)


def extract_item_datas(payload: Any) -> List[Dict[str, Any]]:
    """Extract the richest Tencent item list without fixed response indexes."""
    if not isinstance(payload, dict):
        return []
    data = payload.get("data")
    if not isinstance(data, dict):
        return []
    modules = data.get("module_list_datas")
    if not isinstance(modules, list):
        return []
    candidates = []
    for module_list in modules:
        if not isinstance(module_list, dict):
            continue
        for module in module_list.get("module_datas") or []:
            if not isinstance(module, dict):
                continue
            lists = module.get("item_data_lists")
            if not isinstance(lists, dict):
                continue
            items = lists.get("item_datas")
            if isinstance(items, list) and items:
                candidates.append([item for item in items if isinstance(item, dict)])
    return max(
        candidates,
        key=lambda items: (
            sum(str(item.get("item_type")) == "2" for item in items),
            len(items),
        ),
        default=[],
    )


def build_filter_groups(items: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Group Tencent filter options by index key while retaining response order."""
    groups: Dict[str, Dict[str, Any]] = {}
    for item in items:
        if str(item.get("item_type")) != "11":
            continue
        params = item.get("item_params")
        if not isinstance(params, dict):
            continue
        key = str(params.get("index_item_key") or "").strip()
        name = str(params.get("index_name") or "").strip()
        option_name = str(params.get("option_name") or "").strip()
        option_value = str(params.get("option_value") or "").strip()
        if not key or not option_name or not option_value:
            continue
        group = groups.setdefault(key, {"key": key, "label": name, "options": []})
        if option_value == "-1":
            if not group["label"]:
                group["label"] = option_name
            continue
        if not any(option["value"] == option_value for option in group["options"]):
            group["options"].append({"value": option_value, "text": option_name})
    return [group for group in groups.values() if group["label"] and group["options"]]


def normalize_poster_url(item_params: Dict[str, Any]) -> str:
    poster = str(item_params.get("new_pic_vt") or "").strip()
    if not poster.startswith(("http://", "https://")):
        poster = str(
            item_params.get("pic_url")
            or item_params.get("image_url")
            or "https://v.qq.com/assets/default_poster.jpg"
        ).strip()
    poster = re.sub(r"/350(?=/|$)", "", poster)
    if not poster.startswith(("http://", "https://")):
        return "https://v.qq.com/assets/default_poster.jpg"
    return poster


def media_items(items: Iterable[Dict[str, Any]], count: int) -> List[Dict[str, Any]]:
    results = []
    for item in items:
        if str(item.get("item_type")) != "2":
            continue
        params = item.get("item_params")
        if not isinstance(params, dict):
            continue
        title = str(params.get("title") or "").strip()
        media_id = str(params.get("cid") or "").strip()
        if not title or not media_id:
            continue
        results.append(params)
        if len(results) >= count:
            break
    return results
