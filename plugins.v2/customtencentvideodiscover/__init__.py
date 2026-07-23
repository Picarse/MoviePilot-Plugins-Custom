"""
Tencent Video Discover custom edition.

Derived from DDSRem-Dev/MoviePilot-Plugins TencentVideoDiscover v1.0.3.
Original author: DDSRem. Modified by Picarse. Licensed under GNU GPL v3.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
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
    FILTER_PARAM_NAMES,
    build_filter_groups,
    clamp_positive_int,
    extract_item_datas,
    media_items,
    normalize_poster_url,
)


API_URL = (
    "https://pbaccess.video.qq.com/"
    "trpc.universal_backend_service.page_server_rpc.PageServer/GetPageData"
)
API_PARAMS = {
    "video_appid": "1000005",
    "vplatform": "2",
    "vversion_name": "8.9.10",
    "new_mark_label_enabled": "1",
}
API_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Referer": "https://v.qq.com/",
}
REQUEST_TIMEOUT = 12


class CustomTencentVideoDiscover(_PluginBase):
    plugin_name = "腾讯视频探索（自用版）"
    plugin_desc = "让探索支持腾讯视频的数据浏览。"
    plugin_icon = (
        "https://raw.githubusercontent.com/DDSRem-Dev/"
        "MoviePilot-Plugins/main/icons/tencentvideo_A.png"
    )
    plugin_version = "1.0.0"
    plugin_author = "DDSRem, Picarse"
    author_url = "https://github.com/DDSRem"
    plugin_config_prefix = "customtencentvideodiscover_"
    plugin_order = 99
    auth_level = 1

    _enabled = False
    _filter_rows: List[dict] = []

    def init_plugin(self, config: dict = None):
        self._enabled = bool((config or {}).get("enabled"))
        self._filter_rows = []
        if "puui.qpic.cn" not in settings.SECURITY_IMAGE_DOMAINS:
            settings.SECURITY_IMAGE_DOMAINS.append("puui.qpic.cn")
        if self._enabled:
            self._filter_rows = self._load_filter_rows()

    def get_state(self) -> bool:
        return self._enabled

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        return []

    def get_api(self) -> List[Dict[str, Any]]:
        return [{
            "path": "/tencentvideo_discover",
            "endpoint": self.tencentvideo_discover,
            "methods": ["GET"],
            "summary": "腾讯视频探索数据源（自用版）",
            "description": "获取腾讯视频探索数据",
        }]

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        return [{
            "component": "VForm",
            "content": [{
                "component": "VRow",
                "content": [{
                    "component": "VCol",
                    "props": {"cols": 12, "md": 4},
                    "content": [{
                        "component": "VSwitch",
                        "props": {"model": "enabled", "label": "启用插件"},
                    }],
                }],
            }],
        }], {"enabled": False}

    @staticmethod
    def get_page() -> List[dict]:
        return []

    @staticmethod
    def _page_body(channel_id: str, page: int = 1, filters: Dict[str, str] = None):
        page_params = {
            "channel_id": channel_id,
            "page_type": "channel_operation",
            "page_id": "channel_list_second_page",
        }
        if filters:
            page_params["filter_params"] = "&".join(
                f"{key}={value}" for key, value in filters.items() if value is not None
            )
        body = {"page_params": page_params}
        if page != 1:
            body["page_context"] = {
                "data_src_647bd63b21ef4b64b50fe65201d89c6e_page": str(page - 1)
            }
        return body

    @staticmethod
    def _fetch_page(channel_id: str, page: int = 1, filters: Dict[str, str] = None):
        try:
            response = requests.post(
                API_URL,
                params=API_PARAMS,
                json=CustomTencentVideoDiscover._page_body(channel_id, page, filters),
                headers=API_HEADERS,
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            return extract_item_datas(response.json())
        except (requests.RequestException, ValueError) as error:
            logger.warning(
                f"腾讯视频接口请求失败：频道={channel_id}，"
                f"错误类型={type(error).__name__}"
            )
            return []

    def _load_filter_rows(self) -> List[dict]:
        rows_by_channel: Dict[str, List[dict]] = {}
        with ThreadPoolExecutor(max_workers=len(CHANNEL_PARAMS)) as executor:
            futures = {
                executor.submit(self._fetch_page, channel["Id"]): key
                for key, channel in CHANNEL_PARAMS.items()
            }
            for future in as_completed(futures):
                channel_key = futures[future]
                try:
                    groups = build_filter_groups(future.result())
                except Exception as error:
                    logger.warning(
                        f"腾讯视频筛选项解析失败：频道={channel_key}，"
                        f"错误类型={type(error).__name__}"
                    )
                    groups = []
                rows_by_channel[channel_key] = [
                    {
                        "component": "div",
                        "props": {
                            "class": "flex justify-start items-center",
                            "show": "{{mtype == '" + channel_key + "'}}",
                        },
                        "content": [
                            {
                                "component": "div",
                                "props": {"class": "mr-5"},
                                "content": [{"component": "VLabel", "text": group["label"]}],
                            },
                            {
                                "component": "VChipGroup",
                                "props": {"model": group["key"]},
                                "content": [
                                    {
                                        "component": "VChip",
                                        "props": {
                                            "filter": True,
                                            "tile": True,
                                            "value": option["value"],
                                        },
                                        "text": option["text"],
                                    }
                                    for option in group["options"]
                                ],
                            },
                        ],
                    }
                    for group in groups
                ]
        return [
            row
            for channel_key in CHANNEL_PARAMS
            for row in rows_by_channel.get(channel_key, [])
        ]

    @cached(region="custom_tencentvideo_discover", ttl=1800, skip_none=True)
    def _request(self, page: int, mtype: str, **filters) -> List[Dict[str, Any]]:
        return self._fetch_page(CHANNEL_PARAMS[mtype]["Id"], page, filters)

    def tencentvideo_discover(
        self,
        mtype: str = "tv",
        recommend_3: Optional[str] = None,
        itrailer: Optional[str] = None,
        exclusive: Optional[str] = None,
        child_ip: Optional[str] = None,
        characteristic: Optional[str] = None,
        anime_status: Optional[str] = None,
        recommend: Optional[str] = None,
        language: Optional[str] = None,
        iregion: Optional[str] = None,
        iyear: Optional[str] = None,
        all: Optional[str] = None,
        sort: Optional[str] = None,
        ipay: Optional[str] = None,
        producer: Optional[str] = None,
        iarea: Optional[str] = None,
        pay: Optional[str] = None,
        attr: Optional[str] = None,
        item: Optional[str] = None,
        itype: Optional[str] = None,
        recommend_2: Optional[str] = None,
        recommend_1: Optional[str] = None,
        award: Optional[str] = None,
        theater: Optional[str] = None,
        gender: Optional[str] = None,
        page: int = 1,
        count: int = 10,
    ) -> List[schemas.MediaInfo]:
        if not self._enabled:
            return []
        if mtype not in CHANNEL_PARAMS:
            logger.warning(f"腾讯视频探索收到未知频道：{mtype}")
            return []
        page = clamp_positive_int(page, default=1, maximum=1000)
        count = clamp_positive_int(count, default=10, maximum=100)
        supplied = locals()
        filters = {
            name: supplied[name]
            for name in FILTER_PARAM_NAMES
            if supplied.get(name) is not None
        }
        items = media_items(self._request(page, mtype, **filters), count)
        media_type = "电影" if mtype == "movie" else "电视剧"
        return [
            schemas.MediaInfo(
                type=media_type,
                title=params.get("title"),
                year=params.get("year"),
                title_year=(
                    f"{params.get('title')} ({params.get('year')})"
                    if params.get("year")
                    else str(params.get("title"))
                ),
                mediaid_prefix="customtencentvideo",
                media_id=str(params.get("cid")),
                poster_path=normalize_poster_url(params),
            )
            for params in items
        ]

    def tencentvideo_filter_ui(self) -> List[dict]:
        category_row = {
            "component": "div",
            "props": {"class": "flex justify-start items-center"},
            "content": [
                {
                    "component": "div",
                    "props": {"class": "mr-5"},
                    "content": [{"component": "VLabel", "text": "种类"}],
                },
                {
                    "component": "VChipGroup",
                    "props": {"model": "mtype"},
                    "content": [
                        {
                            "component": "VChip",
                            "props": {"filter": True, "tile": True, "value": key},
                            "text": value["Name"],
                        }
                        for key, value in CHANNEL_PARAMS.items()
                    ],
                },
            ],
        }
        return [category_row, *self._filter_rows]

    @eventmanager.register(ChainEventType.DiscoverSource)
    def discover_source(self, event: Event):
        if not self._enabled or not event or not event.event_data:
            return
        event_data: DiscoverSourceEventData = event.event_data
        source = schemas.DiscoverMediaSource(
            name="腾讯视频（自用版）",
            mediaid_prefix="customtencentvideo",
            api_path=(
                "plugin/CustomTencentVideoDiscover/tencentvideo_discover"
                f"?apikey={settings.API_TOKEN}"
            ),
            filter_params={"mtype": "tv", **{name: None for name in FILTER_PARAM_NAMES}},
            filter_ui=self.tencentvideo_filter_ui(),
            depends={name: ["mtype"] for name in FILTER_PARAM_NAMES},
        )
        if event_data.extra_sources is None:
            event_data.extra_sources = []
        if not any(
            getattr(existing, "mediaid_prefix", None) == "customtencentvideo"
            for existing in event_data.extra_sources
        ):
            event_data.extra_sources.append(source)

    @staticmethod
    def stop_service():
        return None
