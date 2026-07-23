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
              ("131", "枪战"), ("291", "犯罪"), ("128", "惊悚"),
              ("289", "悬疑"), ("10", "恐怖"), ("12", "动画"),
              ("27356", "家庭"), ("1284", "奇幻"), ("129", "魔幻"),
              ("9", "科幻"), ("7", "战争"), ("130", "青春")),
    "tv": (("11992", "自制"), ("24", "古装"), ("20", "言情"),
           ("23", "武侠"), ("30", "偶像"), ("1654", "家庭"),
           ("1653", "青春"), ("24064", "都市"), ("135", "喜剧"),
           ("27916", "战争"), ("1655", "军旅"), ("290", "谍战"),
           ("32", "悬疑"), ("149", "罪案"), ("148", "穿越"),
           ("139", "宫廷"), ("21", "历史"), ("145", "神话"),
           ("34", "科幻"), ("27", "年代"), ("24063", "剧情"),
           ("27881", "奇幻"), ("24065", "网剧"), ("32839", "竖短片")),
    "variety": (("155", "播报"), ("156", "访谈"), ("158", "游戏"),
                ("292", "晚会"), ("293", "曲艺"), ("2118", "脱口秀"),
                ("2224", "真人秀"), ("30278", "竞技"),
                ("30279", "爱奇艺出品"), ("33860", "竞演")),
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

# Every value below is sent through ``three_category_id``.  They are kept in
# separate UI rows because iQIYI groups them by different parent categories.
EXTRA_FILTER_OPTIONS = {
    "movie": {
        "specification": ("规格", (("27397", "巨制"), ("27815", "院线"),
                                  ("30149", "独播"), ("27401", "网络电影"))),
    },
    "tv": {},
    "variety": {
        "theme": ("题材", (("33163", "音乐"), ("33172", "舞蹈"),
                           ("33173", "文化"), ("33182", "美食"),
                           ("33193", "相亲"), ("33195", "纪实"),
                           ("33196", "生活"), ("33197", "亲子"),
                           ("33316", "爱情"), ("33317", "搞笑"),
                           ("33318", "益智"), ("33319", "职场"))),
    },
    "anime": {
        "version": ("版本", (("30220", "动画"), ("30223", "特摄"),
                             ("30224", "布袋戏"), ("32782", "特别篇"),
                             ("32783", "动态漫画"), ("32784", "动画电影"),
                             ("33482", "轻动画"), ("33483", "短剧"))),
        "adaptation": ("来源", (("32796", "轻小说改编"),
                                ("32797", "漫画改编"),
                                ("32798", "游戏改编"), ("32799", "原创"))),
    },
    "documentary": {
        "producer": ("出品方", (("28468", "BBC"), ("28470", "美国历史频道"),
                                ("28471", "探索频道"), ("28472", "央视记录"),
                                ("28473", "北京纪实频道"),
                                ("28474", "上海纪实频道"), ("28480", "NHK"),
                                ("31283", "爱奇艺出品"), ("31286", "Netflix"))),
        "subtype": ("片种", (("29077", "纪录电影"), ("29078", "系列纪录片"),
                              ("29082", "网络纪录片"), ("29083", "纪实栏目"))),
        "duration": ("时长", (("29079", "微纪录"), ("29080", "长纪录"),
                               ("29081", "短纪录"))),
    },
    "children": {},
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


def high_resolution_poster(value: Any, sizes: Any = None) -> str:
    """Select a real portrait rendition instead of iQIYI's 120x160 default."""
    url = normalize_url(value)
    if not url:
        return url
    available = {str(size) for size in sizes} if isinstance(sizes, list) else set()
    preferred = next(
        (size for size in ("579_772", "390_520", "318_424", "260_360")
         if not available or size in available),
        None,
    )
    if not preferred:
        return url
    if re.search(r"_\d+_\d+(?=\.(?:jpe?g|webp|avif)(?:\?|$))", url, re.I):
        return re.sub(
            r"_\d+_\d+(?=\.(?:jpe?g|webp|avif)(?:\?|$))",
            f"_{preferred}", url, count=1, flags=re.I,
        )
    return re.sub(
        r"\.(jpe?g|webp|avif)(?=\?|$)", rf"_{preferred}.\1", url, count=1,
        flags=re.I,
    )


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
        "poster": high_resolution_poster(item.get("imageUrl"), item.get("imageSize")),
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


def category_value(*categories: Optional[str]) -> Optional[str]:
    values = [str(value).strip() for value in categories if str(value or "").strip()]
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
    labels = [*item.get("areas", ()), *item.get("categories", ())]
    labels = list(dict.fromkeys(labels))[:8]
    if labels:
        parts.append("分类：" + " · ".join(labels))
    rights = []
    if item.get("produced"):
        rights.append("爱奇艺自制")
    if item.get("exclusive"):
        rights.append("独播")
    if item.get("pay_mark") == 1:
        rights.append("VIP")
    elif item.get("pay_mark") == 2:
        rights.append("付费")
    elif item.get("pay_mark") == 0:
        rights.append("免费")
    if rights:
        parts.append("权益：" + " · ".join(rights))
    actors = item.get("actors", ())
    if actors:
        parts.append("主演：" + "、".join(actors[:6]))
    for value in (item.get("focus"), item.get("description")):
        text = str(value or "").strip()
        if text and text not in parts:
            parts.append(text)
    return "\n".join(parts) or None
