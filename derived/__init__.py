"""Derived entity registry."""
from derived.ccc import CCC
from derived.dpi import DPI
from derived.ots import OTS
from derived.soy import SOY

REGISTRY = {
    "ots": OTS,
    "soy": SOY,
    "dpi": DPI,
    "ccc": CCC,
}
