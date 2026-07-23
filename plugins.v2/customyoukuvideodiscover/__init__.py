"""Youku Video Discover custom edition for MoviePilot V2."""

from typing import Any, Dict, List, Tuple

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
    clamp_positive_int,
    extract_media_items,
    page_items,
    parse_initial_data,
)


CHANNEL_URL = "https://www.youku.com/ku/{path}"
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
    plugin_version = "1.0.0"
    plugin_author = "Picarse"
    author_url = "https://github.com/Picarse"
    plugin_config_prefix = "customyoukuvideodiscover_"
    plugin_order = 99
    auth_level = 1

    _enabled = False

    def init_plugin(self, config: dict = None):
        self._enabled = bool((config or {}).get("enabled"))
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
    def _fetch_channel(mtype: str) -> List[Dict[str, Any]]:
        path = CHANNEL_PARAMS[mtype]["Path"]
        try:
            response = requests.get(
                CHANNEL_URL.format(path=path),
                headers=API_HEADERS,
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            return extract_media_items(parse_initial_data(response.text))
        except (requests.RequestException, ValueError) as error:
            logger.warning(
                f"优酷频道请求失败：频道={mtype}，错误类型={type(error).__name__}"
            )
            return []

    @cached(region="custom_youkuvideo_discover", ttl=900, skip_none=True)
    def _request(self, mtype: str) -> List[Dict[str, Any]]:
        return self._fetch_channel(mtype)

    def youkuvideo_discover(
        self,
        mtype: str = "tv",
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
        items = page_items(self._request(mtype), page, count)
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

    def youkuvideo_filter_ui(self) -> List[dict]:
        return [{
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
        }]

    @eventmanager.register(ChainEventType.DiscoverSource)
    def discover_source(self, event: Event):
        if not self._enabled or not event or not event.event_data:
            return
        event_data: DiscoverSourceEventData = event.event_data
        source = schemas.DiscoverMediaSource(
            name="优酷视频（自用版）",
            mediaid_prefix="customyoukuvideo",
            api_path=(
                "plugin/CustomYoukuVideoDiscover/youkuvideo_discover"
                f"?apikey={settings.API_TOKEN}"
            ),
            filter_params={"mtype": "tv"},
            filter_ui=self.youkuvideo_filter_ui(),
            depends={},
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
