from __future__ import annotations

SEALED_ZSET_KEY = "letter:sealed:zset"
AVAILABLE_ALL_KEY = "letter:available:all"
AVAILABLE_EMOTION_KEY = "letter:available:emotion:{emotion}"
AVAILABLE_CITY_KEY = "letter:available:city:{city}"
AVAILABLE_EMOTION_CITY_KEY = "letter:available:emotion_city:{emotion}:{city}"

ANONYMOUS_NAMES = [
    "云栖", "晚风", "青野", "月白", "南枝", "星河", "北岛", "山眠",
    "松间", "雾灯", "晴岚", "鹿鸣", "清浅", "竹影", "海棠", "白露",
]

ALLOWED_EMOTIONS = ["喜悦", "疲惫", "焦虑", "孤独", "平静"]
ALLOWED_SEAL_DAYS = [1, 7, 30]
