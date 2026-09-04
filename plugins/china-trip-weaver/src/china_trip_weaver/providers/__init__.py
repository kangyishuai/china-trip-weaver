"""Read-only provider adapters."""

from .amap import AMapAdapter
from .anysearch import AnySearchAdapter
from .flyai import FlyAIAdapter
from .host_web import HostWebAdapter
from .rail12306 import Rail12306Adapter
from .variflight import VariFlightAdapter

__all__ = [
    "AMapAdapter",
    "AnySearchAdapter",
    "FlyAIAdapter",
    "HostWebAdapter",
    "Rail12306Adapter",
    "VariFlightAdapter",
]

