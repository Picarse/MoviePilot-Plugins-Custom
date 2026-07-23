"""Youku Video Discover custom edition for MoviePilot V2."""

import hashlib
import json
import time
from typing import Any, Dict, List, Optional, Tuple

import requests

from app import schemas
from app.core.cache import cached
from app.core.config import settings
from app.core.event import Event, eventmanager
from app.log import logger
from app.plugins import _PluginBase
from app.schemas import DiscoverSourceEventData
from app.schemas.types import ChainEventType

from .core import (
    CHANNEL_PARAMS,
    GENRE_OPTIONS,
    SECTION_OPTIONS,
    clamp_positive_int,
    extract_feed_state,
    extract_mtop_state,
    filter_media_items,
    page_items,
    parse_initial_data,
)


CHANNEL_URL = "https://www.youku.com/ku/{path}"
MTOP_URL = "https://acs.youku.com/h5/{api}/1.0/"
MTOP_APP_KEY = "24679788"
MTOP_API = "mtop.youku.columbus.home.query"
MTOP_CODE = "2019061000"
API_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Referer": "https://www.youku.com/",
}
REQUEST_TIMEOUT = 15
DEFAULT_PREFETCH_PAGES = 4
MAX_PREFETCH_PAGES = 8
IMAGE_DOMAINS = (
    "liangcang-material.alicdn.com",
    "img.alicdn.com",
    "m.ykimg.com",
    "ykimg.alicdn.com",
)


class CustomYoukuVideoDiscover(_PluginBase):
    plugin_name = "优酷视频探索（自用版）"
    plugin_desc = "让探索支持优酷视频的数据浏览。"
    plugin_icon = (
        "https://img.alicdn.com/imgextra/i2/"
        "O1CN01BeAcgL1ywY0G5nSn8_!!6000000006643-2-tps-195-195.png"
    )
    plugin_version = "1.2.0"
    plugin_author = "Picarse"
    author_url = "https://github.com/Picarse"
    plugin_config_prefix = "customyoukuvideodiscover_"
    plugin_order = 99
    auth_level = 1

    _enabled = False
    _prefetch_pages = DEFAULT_PREFETCH_PAGES

    def init_plugin(self, config: dict = None):
        config = config or {}
        self._enabled = bool(config.get("enabled"))
        self._prefetch_pages = clamp_positive_int(
            config.get("prefetch_pages"),
            default=DEFAULT_PREFETCH_PAGES,
            maximum=MAX_PREFETCH_PAGES,
        )
        for domain in IMAGE_DOMAINS:
            if domain not in settings.SECURITY_IMAGE_DOMAINS:
                settings.SECURITY_IMAGE_DOMAINS.append(domain)

    def get_state(self) -> bool:
        return self._enabled

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        return []

    def get_api(self) -> List[Dict[str, Any]]:
        return [{
            "path": "/youkuvideo_discover",
            "endpoint": self.youkuvideo_discover,
            "methods": ["GET"],
            "summary": "优酷视频探索数据源（自用版）",
            "description": "获取优酷视频探索数据",
        }]

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        return [{
            "component": "VForm",
            "content": [{
                "component": "VRow",
                "content": [
                    {
                        "component": "VCol",
                        "props": {"cols": 12, "md": 4},
                        "content": [{
                            "component": "VSwitch",
                            "props": {"model": "enabled", "label": "启用插件"},
                        }],
                    },
                    {
                        "component": "VCol",
                        "props": {"cols": 12, "md": 4},
                        "content": [{
                            "component": "VTextField",
                            "props": {
                                "model": "prefetch_pages",
                                "label": "预取后续分页数",
                                "type": "number",
                                "min": 1,
                                "max": MAX_PREFETCH_PAGES,
                                "hint": "默认4页；越大内容越多，但首次加载请求也越多",
                                "persistent-hint": True,
                            },
                        }],
                    },
                ],
            }],
        }], {"enabled": False, "prefetch_pages": DEFAULT_PREFETCH_PAGES}

    @staticmethod
    def get_page() -> List[dict]:
        return []

    @staticmethod
    def _fetch_channel(mtype: str) -> Dict[str, Any]:
        path = CHANNEL_PARAMS[mtype]["Path"]
        try:
            response = requests.get(
                CHANNEL_URL.format(path=path),
                headers=API_HEADERS,
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            return extract_feed_state(parse_initial_data(response.text))
        except (requests.RequestException, ValueError) as error:
            logger.warning(
                f"优酷频道请求失败：频道={mtype}，错误类型={type(error).__name__}"
            )
            return {
                "items": [], "session": {}, "more": False,
                "feed_page": 1, "page_num_max": 1,
            }

    @staticmethod
    def _mtop_data(
        mtype: str,
        feed_page: int,
        feed_session: Dict[str, Any],
    ) -> Tuple[str, str, Dict[str, str]]:
        channel = CHANNEL_PARAMS[mtype]
        api = channel.get("Api", MTOP_API)
        code = channel.get("Code", MTOP_CODE)
        params = {
            "debug": 0,
            "utdid": "homepage_empty_cna",
            "appPackageKey": "com.youku.pcweb",
            "appPackageId": "com.youku.pcweb",
            "ip": "127.0.0.1",
            "reqSubNode": 0,
            "userId": "",
            "gray": 0,
            "pageNo": feed_page,
            "bizKey": "kuflix_pc_home",
            "showNodeList": 0,
            "nodeKey": channel["Node"],
            "appKey": MTOP_APP_KEY,
            "session": json.dumps(
                feed_session, ensure_ascii=False, separators=(",", ":")
            ),
            "bizContext": "{}",
        }
        system_info = {
            "appPackageKey": "com.youku.pcweb",
            "appPackageId": "com.youku.pcweb",
            "device": "pcweb",
            "os": "pcweb",
            "ver": "1.0.0.0",
            "userAgent": API_HEADERS["User-Agent"],
            "guid": "1590141704165YXe",
            "young": 0,
            "brand": "",
            "network": "",
            "ouid": "",
            "idfa": "",
            "scale": "",
            "operator": "",
            "resolution": "",
            "pid": "",
            "childGender": 0,
            "zx": 0,
            "zx_list": "",
            "appkey": MTOP_APP_KEY,
            "disableUserRec": 0,
        }
        data = json.dumps(
            {
                "ms_codes": code,
                "params": json.dumps(
                    params, ensure_ascii=False, separators=(",", ":")
                ),
                "system_info": json.dumps(
                    system_info, ensure_ascii=False, separators=(",", ":")
                ),
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return api, code, {"data": data}

    @staticmethod
    def _fetch_feed_pages(
        mtype: str,
        start_page: int,
        page_count: int,
        session_json: str,
    ) -> List[Dict[str, Any]]:
        try:
            feed_session = json.loads(session_json)
            if not isinstance(feed_session, dict) or not feed_session:
                return []
            client = requests.Session()

            def call(api: str, request_data: Dict[str, str], token: str = ""):
                timestamp = str(int(time.time() * 1000))
                sign_source = (
                    f"{token}&{timestamp}&{MTOP_APP_KEY}&{request_data['data']}"
                )
                query = {
                    "jsv": "2.7.2",
                    "appKey": MTOP_APP_KEY,
                    "t": timestamp,
                    "sign": hashlib.md5(sign_source.encode()).hexdigest(),
                    "api": api,
                    "v": "1.0",
                    "type": "originaljson",
                    "dataType": "json",
                    **request_data,
                }
                response = client.get(
                    MTOP_URL.format(api=api),
                    params=query,
                    headers={
                        **API_HEADERS,
                        "Referer": CHANNEL_URL.format(
                            path=CHANNEL_PARAMS[mtype]["Path"]
                        ),
                        "Origin": "https://www.youku.com",
                    },
                    timeout=REQUEST_TIMEOUT,
                )
                response.raise_for_status()
                return response.json()

            api, _, request_data = CustomYoukuVideoDiscover._mtop_data(
                mtype, start_page, feed_session
            )
            call(api, request_data)
            token = next(
                (
                    cookie.value.split("_", 1)[0]
                    for cookie in client.cookies
                    if cookie.name == "_m_h5_tk"
                ),
                "",
            )
            if not token:
                return []
            results = []
            seen = set()
            for feed_page in range(start_page, start_page + page_count):
                api, code, request_data = CustomYoukuVideoDiscover._mtop_data(
                    mtype, feed_page, feed_session
                )
                state = extract_mtop_state(call(api, request_data, token), code)
                for item in state["items"]:
                    if item["media_id"] in seen:
                        continue
                    seen.add(item["media_id"])
                    results.append(item)
                if state["session"]:
                    feed_session = state["session"]
                if not state["more"]:
                    break
            return results
        except (requests.RequestException, TypeError, ValueError) as error:
            logger.warning(
                f"优酷分页请求失败：频道={mtype}，起始页={start_page}，"
                f"错误类型={type(error).__name__}"
            )
            return []

    @staticmethod
    def _fetch_feed(
        mtype: str,
        feed_page: int,
        session_json: str,
    ) -> List[Dict[str, Any]]:
        return CustomYoukuVideoDiscover._fetch_feed_pages(
            mtype, feed_page, 1, session_json
        )

    @cached(region="custom_youkuvideo_channel_v12", ttl=900, skip_none=True)
    def _request_channel(self, mtype: str) -> Dict[str, Any]:
        return self._fetch_channel(mtype)

    @cached(region="custom_youkuvideo_feed_batch", ttl=1800, skip_none=True)
    def _request_feed_pages(
        self,
        mtype: str,
        start_page: int,
        page_count: int,
        session_json: str,
    ) -> List[Dict[str, Any]]:
        return self._fetch_feed_pages(
            mtype, start_page, page_count, session_json
        )

    @cached(region="custom_youkuvideo_catalog", ttl=1800, skip_none=True)
    def _request_catalog(
        self, mtype: str, prefetch_pages: int
    ) -> List[Dict[str, Any]]:
        state = self._request_channel(mtype)
        items = list(state.get("items") or [])
        session = state.get("session") or {}
        if not session or not state.get("more"):
            return items
        session_json = json.dumps(
            session,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        feed_page = clamp_positive_int(state.get("feed_page"), 1, 1000) + 1
        feed_limit = min(
            prefetch_pages,
            max(0, int(state.get("page_num_max") or feed_page) - feed_page + 1),
        )
        if feed_limit < 1:
            return items
        seen = {item["media_id"] for item in items}
        for item in self._request_feed_pages(
            mtype, feed_page, feed_limit, session_json
        ):
            if item["media_id"] in seen:
                continue
            seen.add(item["media_id"])
            items.append(item)
        return items

    def youkuvideo_discover(
        self,
        mtype: str = "tv",
        genre: Optional[str] = None,
        access: Optional[str] = None,
        progress: Optional[str] = None,
        section: Optional[str] = None,
        page: int = 1,
        count: int = 10,
    ) -> List[schemas.MediaInfo]:
        if not self._enabled:
            return []
        if mtype not in CHANNEL_PARAMS:
            logger.warning(f"优酷视频探索收到未知频道：{mtype}")
            return []
        page = clamp_positive_int(page, default=1, maximum=1000)
        count = clamp_positive_int(count, default=10, maximum=100)
        catalog = self._request_catalog(mtype, self._prefetch_pages)
        items = filter_media_items(
            catalog, genre, access, progress, section
        )
        items = page_items(items, page, count)
        media_type = "电影" if mtype == "movie" else "电视剧"
        return [
            schemas.MediaInfo(
                type=media_type,
                title=item["title"],
                year=item.get("year"),
                title_year=(
                    f"{item['title']} ({item['year']})"
                    if item.get("year")
                    else item["title"]
                ),
                mediaid_prefix="customyoukuvideo",
                media_id=item["media_id"],
                poster_path=item["poster"],
            )
            for item in items
        ]

    @staticmethod
    def _filter_row(
        label: str,
        model: str,
        options: List[Tuple[str, str]],
        show: str = None,
    ) -> dict:
        props = {"class": "flex justify-start items-center"}
        if show:
            props["show"] = show
        return {
            "component": "div",
            "props": props,
            "content": [
                {
                    "component": "div",
                    "props": {"class": "mr-5"},
                    "content": [{"component": "VLabel", "text": label}],
                },
                {
                    "component": "VChipGroup",
                    "props": {"model": model},
                    "content": [
                        {
                            "component": "VChip",
                            "props": {"filter": True, "tile": True, "value": value},
                            "text": text,
                        }
                        for value, text in options
                    ],
                },
            ],
        }

    def youkuvideo_filter_ui(self) -> List[dict]:
        rows = [
            self._filter_row(
                "种类",
                "mtype",
                [(key, value["Name"]) for key, value in CHANNEL_PARAMS.items()],
            )
        ]
        rows.extend(
            self._filter_row(
                "题材",
                "genre",
                [(genre, genre) for genre in GENRE_OPTIONS[channel]],
                "{{mtype == '" + channel + "'}}",
            )
            for channel in CHANNEL_PARAMS
        )
        rows.extend([
            self._filter_row("内容", "section", list(SECTION_OPTIONS)),
            self._filter_row(
                "权益",
                "access",
                [("vip", "VIP"), ("exclusive", "独播"), ("premiere", "首播")],
            ),
            self._filter_row(
                "状态",
                "progress",
                [("updating", "更新中"), ("complete", "已完结")],
            ),
        ])
        return rows

    @eventmanager.register(ChainEventType.DiscoverSource)
    def discover_source(self, event: Event):
        if not self._enabled or not event or not event.event_data:
            return
        event_data: DiscoverSourceEventData = event.event_data
        filter_names = ("genre", "access", "progress", "section")
        source = schemas.DiscoverMediaSource(
            name="优酷视频（自用版）",
            mediaid_prefix="customyoukuvideo",
            api_path=(
                "plugin/CustomYoukuVideoDiscover/youkuvideo_discover"
                f"?apikey={settings.API_TOKEN}"
            ),
            filter_params={"mtype": "tv", **{name: None for name in filter_names}},
            filter_ui=self.youkuvideo_filter_ui(),
            depends={name: ["mtype"] for name in filter_names},
        )
        if event_data.extra_sources is None:
            event_data.extra_sources = []
        if not any(
            getattr(existing, "mediaid_prefix", None) == "customyoukuvideo"
            for existing in event_data.extra_sources
        ):
            event_data.extra_sources.append(source)

    @staticmethod
    def stop_service():
        return None
