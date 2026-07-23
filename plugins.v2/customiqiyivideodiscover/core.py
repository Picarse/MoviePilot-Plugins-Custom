"""Pure parsing helpers for the custom iQIYI discover plugin."""

import re
from typing import Any, Dict, List, Optional, Tuple


CHANNEL_PARAMS = {
    "tv": {"Id": "2", "Name": "电视剧"},
    "movie": {"Id": "1", "Name": "电影"},
    "variety": {"Id": "6", "Name": "综艺"},
    "anime": {"Id": "4", "Name": "动漫"},
    "children": {"Id": "15", "Name": "少儿"},
    "documentary": {"Id": "3", "Name": "纪录片"},
}

SORT_OPTIONS = (("11", "热播榜"), ("8", "好评榜"), ("4", "新上线"))
ACCESS_OPTIONS = (("0", "免费"), ("1", "会员"), ("2", "付费"))

REGION_OPTIONS = {
    "movie": (("1", "华语"), ("28997", "香港地区"), ("2", "美国"),
              ("3", "欧洲"), ("4", "韩国"), ("308", "日本"),
              ("1115", "泰国"), ("28999", "印度"), ("5", "其他")),
    "tv": (("15", "内地"), ("16", "港剧"), ("17", "韩剧"),
           ("18", "美剧"), ("309", "日剧"), ("1114", "泰剧"),
           ("1117", "台湾地区"), ("28916", "英剧"), ("19", "其他")),
    "variety": (("151", "内地"), ("152", "港台"), ("33306", "韩国"),
                ("154", "欧美"), ("1113", "其他")),
    "anime": (("37", "中国大陆"), ("38", "日本"), ("1106", "韩国"),
              ("30218", "欧美"), ("40", "其他")),
    "documentary": (("20323", "国内"), ("20324", "国外")),
    "children": (),
}

GENRE_OPTIONS = {
    "movie": (("8", "喜剧"), ("6", "爱情"), ("11", "动作"),
              ("291", "犯罪"), ("289", "悬疑"), ("9", "科幻"),
              ("7", "战争"), ("10", "恐怖"), ("12", "动画"),
              ("1284", "奇幻")),
    "tv": (("24", "古装"), ("20", "言情"), ("23", "武侠"),
           ("1654", "家庭"), ("24064", "都市"), ("135", "喜剧"),
           ("290", "谍战"), ("32", "悬疑"), ("149", "罪案"),
           ("34", "科幻"), ("24063", "剧情"), ("27881", "奇幻")),
    "variety": (("156", "访谈"), ("292", "晚会"), ("2118", "脱口秀"),
                ("2224", "真人秀"), ("30278", "竞技"),
                ("33163", "音乐"), ("33182", "美食"),
                ("33317", "搞笑"), ("33197", "亲子")),
    "anime": (("30230", "搞笑"), ("30232", "热血"), ("30234", "治愈"),
              ("30243", "恋爱"), ("30245", "科幻"), ("30247", "奇幻"),
              ("30248", "推理"), ("30249", "校园"), ("30267", "冒险"),
              ("32792", "武侠"), ("32793", "玄幻")),
    "documentary": (("70", "人文"), ("33908", "美食"),
                    ("33933", "自然"), ("33945", "萌宠"),
                    ("33960", "罪案"), ("72", "军事"), ("74", "历史"),
                    ("73", "探险"), ("71", "社会"), ("28119", "科技"),
                    ("310", "旅游")),
    "children": (),
}


def clamp_positive_int(value: Any, default: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return min(max(parsed, 1), maximum)


def normalize_url(value: Any) -> str:
    text = str(value or "").strip()
    if text.startswith("//"):
        return f"https:{text}"
    if text.startswith("http://"):
        return f"https://{text[7:]}"
    return text


def _names(value: Any) -> Tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    names = []
    for entry in value:
        name = entry.get("name") if isinstance(entry, dict) else entry
        name = str(name or "").strip()
        if name:
            names.append(name)
    return tuple(dict.fromkeys(names))


def _integer(value: Any) -> Optional[int]:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _score(value: Any) -> Optional[float]:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def normalize_item(item: Any, expected_channel: Optional[str] = None) -> Dict[str, Any]:
    if not isinstance(item, dict):
        return {}
    media_id = str(item.get("albumId") or "").strip()
    title = str(item.get("name") or item.get("title") or "").strip()
    channel_id = str(item.get("channelId") or "").strip()
    if not media_id or not title:
        return {}
    if expected_channel and channel_id and channel_id != expected_channel:
        return {}
    period = str(item.get("period") or "").strip()
    date_match = re.match(r"((?:19|20)\d{2})-(\d{2})-(\d{2})", period)
    categories = _names(item.get("categories"))
    areas = _names(item.get("areas"))
    people = item.get("people") if isinstance(item.get("people"), dict) else {}
    actors = _names(people.get("main_charactor"))
    return {
        "media_id": media_id,
        "title": title,
        "channel_id": channel_id,
        "poster": normalize_url(item.get("imageUrl")),
        "play_url": normalize_url(item.get("playUrl") or item.get("url")),
        "description": str(item.get("description") or "").strip() or None,
        "focus": str(item.get("focus") or "").strip() or None,
        "year": date_match.group(1) if date_match else None,
        "release_date": date_match.group(0) if date_match else None,
        "categories": categories,
        "areas": areas,
        "actors": actors,
        "score": _score(item.get("score")),
        "total_episodes": _integer(item.get("videoCount")),
        "latest_episode": _integer(item.get("latestOrder")),
        "pay_mark": _integer(item.get("payMark")),
        "exclusive": bool(item.get("exclusive")),
        "produced": bool(item.get("qiyiProduced")),
    }


def extract_items(payload: Any, mtype: str) -> List[Dict[str, Any]]:
    if not isinstance(payload, dict) or payload.get("code") != "A00000":
        return []
    data = payload.get("data")
    rows = data.get("list") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        return []
    channel_id = CHANNEL_PARAMS[mtype]["Id"]
    results = []
    seen = set()
    for row in rows:
        item = normalize_item(row, channel_id)
        if not item or item["media_id"] in seen:
            continue
        seen.add(item["media_id"])
        results.append(item)
    return results


def extract_detail(payload: Any, mtype: str) -> Dict[str, Any]:
    if not isinstance(payload, dict) or payload.get("code") != "A00000":
        return {}
    return normalize_item(payload.get("data"), CHANNEL_PARAMS[mtype]["Id"])


def merge_detail(item: Dict[str, Any], detail: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    merged = dict(item)
    if not detail:
        return merged
    for key, value in detail.items():
        if value not in (None, "", (), []):
            merged[key] = value
    return merged


def category_value(region: Optional[str], genre: Optional[str]) -> Optional[str]:
    values = [str(value).strip() for value in (region, genre) if str(value or "").strip()]
    return ",".join(dict.fromkeys(values)) or None


def media_overview(item: Dict[str, Any], mtype: str) -> Optional[str]:
    parts = []
    total = item.get("total_episodes")
    latest = item.get("latest_episode")
    if mtype in {"tv", "anime", "children"}:
        if total and latest:
            parts.append(f"共{total}集" if latest == total else f"更新至{latest}/共{total}集")
        elif latest:
            parts.append(f"更新至{latest}集")
        elif total:
            parts.append(f"共{total}集")
    elif mtype in {"variety", "documentary"} and item.get("release_date"):
        parts.append(f"更新日期：{item['release_date']}")
    for value in (item.get("focus"), item.get("description")):
        text = str(value or "").strip()
        if text and text not in parts:
            parts.append(text)
    return "\n".join(parts) or None
