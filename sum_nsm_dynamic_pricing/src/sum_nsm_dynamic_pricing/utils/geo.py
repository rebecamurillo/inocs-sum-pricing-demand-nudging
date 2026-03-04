import math
from typing import Iterable, Tuple


def haversine(coord1: Tuple[float, float], coord2: Tuple[float, float]) -> float:
    lat1, lon1 = coord1
    lat2, lon2 = coord2
    r_km = 6371.0
    lat1r, lon1r = math.radians(lat1), math.radians(lon1)
    lat2r, lon2r = math.radians(lat2), math.radians(lon2)
    dlat = lat2r - lat1r
    dlon = lon2r - lon1r
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1r) * math.cos(lat2r) * math.sin(dlon / 2) ** 2
    return 2 * r_km * math.asin(math.sqrt(a))


def haversine_m(coord1: Tuple[float, float], coord2: Tuple[float, float]) -> float:
    return haversine(coord1, coord2) * 1000.0


def nearest_station(target: Tuple[float, float], candidates: Iterable[Tuple[str, Tuple[float, float]]]) -> str:
    return min(candidates, key=lambda item: haversine(target, item[1]))[0]
