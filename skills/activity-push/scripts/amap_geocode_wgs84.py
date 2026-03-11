#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib import parse, request


AMAP_GEOCODE_URL = "https://restapi.amap.com/v3/geocode/geo"
AMAP_STATICMAP_URL = "https://restapi.amap.com/v3/staticmap"
VAGUE_ADDRESS_PATTERNS = (
    "线上",
    "直播间",
    "腾讯会议",
    "会议号",
    "待定",
    "待通知",
    "另行通知",
    "报名后通知",
    "群内通知",
    "详见原文",
    "详见海报",
    "见海报",
    "见文内",
    "以通知为准",
    "地点另行",
    "活动现场",
    "附近",
    "周边",
    "某地",
    "门店",
    "各门店",
    "全国",
    "全市",
    "全省",
)
PRECISE_ADDRESS_RE = re.compile(
    r"(\d|路|街|道|巷|弄|号|栋|幢|座|楼|层|室|单元|大厦|广场|中心|酒店|剧院|体育馆|会展中心|会议中心|大学|学院|校区|图书馆|美术馆|博物馆|科技馆|产业园|写字楼)"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Geocode activity addresses with AMap and convert GCJ-02 to WGS84.")
    parser.add_argument("--input", required=True, help="Path to activity-structured.json.")
    parser.add_argument("--output", required=True, help="Path to geo-enriched JSON output.")
    parser.add_argument("--amap-key", default="", help="AMap Web Service key.")
    parser.add_argument("--city-hint-field", default="", help="Optional field name to use as city hint.")
    parser.add_argument("--fixture-file", default="", help="Optional fixture JSON for offline tests.")
    return parser.parse_args()


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def is_precise_address(address: str) -> bool:
    normalized = re.sub(r"\s+", "", address)
    if not normalized or len(normalized) < 6:
        return False
    if any(pattern in normalized for pattern in VAGUE_ADDRESS_PATTERNS):
        return False
    return bool(PRECISE_ADDRESS_RE.search(normalized))


def build_static_map_url(
    amap_key: str,
    lng: float,
    lat: float,
    *,
    zoom: int = 15,
    size: str = "750*300",
    scale: int = 2,
) -> str:
    if not amap_key:
        return ""
    query = {
        "key": amap_key,
        "location": f"{lng:.6f},{lat:.6f}",
        "zoom": str(zoom),
        "size": size,
        "scale": str(scale),
    }
    return f"{AMAP_STATICMAP_URL}?{parse.urlencode(query)}"


def out_of_china(lng: float, lat: float) -> bool:
    return not (73.66 < lng < 135.05 and 3.86 < lat < 53.55)


def transform_lat(lng: float, lat: float) -> float:
    ret = -100.0 + 2.0 * lng + 3.0 * lat + 0.2 * lat * lat + 0.1 * lng * lat + 0.2 * math.sqrt(abs(lng))
    ret += (20.0 * math.sin(6.0 * lng * math.pi) + 20.0 * math.sin(2.0 * lng * math.pi)) * 2.0 / 3.0
    ret += (20.0 * math.sin(lat * math.pi) + 40.0 * math.sin(lat / 3.0 * math.pi)) * 2.0 / 3.0
    ret += (160.0 * math.sin(lat / 12.0 * math.pi) + 320 * math.sin(lat * math.pi / 30.0)) * 2.0 / 3.0
    return ret


def transform_lng(lng: float, lat: float) -> float:
    ret = 300.0 + lng + 2.0 * lat + 0.1 * lng * lng + 0.1 * lng * lat + 0.1 * math.sqrt(abs(lng))
    ret += (20.0 * math.sin(6.0 * lng * math.pi) + 20.0 * math.sin(2.0 * lng * math.pi)) * 2.0 / 3.0
    ret += (20.0 * math.sin(lng * math.pi) + 40.0 * math.sin(lng / 3.0 * math.pi)) * 2.0 / 3.0
    ret += (150.0 * math.sin(lng / 12.0 * math.pi) + 300.0 * math.sin(lng / 30.0 * math.pi)) * 2.0 / 3.0
    return ret


def gcj02_to_wgs84(lng: float, lat: float) -> tuple[float, float]:
    if out_of_china(lng, lat):
        return lng, lat
    a = 6378245.0
    ee = 0.00669342162296594323
    dlat = transform_lat(lng - 105.0, lat - 35.0)
    dlng = transform_lng(lng - 105.0, lat - 35.0)
    radlat = lat / 180.0 * math.pi
    magic = math.sin(radlat)
    magic = 1 - ee * magic * magic
    sqrt_magic = math.sqrt(magic)
    dlat = (dlat * 180.0) / ((a * (1 - ee)) / (magic * sqrt_magic) * math.pi)
    dlng = (dlng * 180.0) / (a / sqrt_magic * math.cos(radlat) * math.pi)
    mg_lat = lat + dlat
    mg_lng = lng + dlng
    return lng * 2 - mg_lng, lat * 2 - mg_lat


class AMapClient:
    def __init__(self, amap_key: str, fixture_file: Optional[Path] = None) -> None:
        self.amap_key = amap_key
        self.fixture_file = fixture_file
        self.fixture_map = read_json(fixture_file) if fixture_file else {}

    def geocode(self, address: str, city_hint: str = "") -> Dict[str, Any]:
        if self.fixture_file:
            return self.fixture_map.get(address, {"status": "0", "count": "0", "geocodes": []})
        if not self.amap_key:
            raise RuntimeError("amap key is required unless fixture-file is provided")

        query = {"key": self.amap_key, "address": address, "output": "JSON"}
        if city_hint:
            query["city"] = city_hint
        url = f"{AMAP_GEOCODE_URL}?{parse.urlencode(query)}"
        req = request.Request(url, headers={"Accept": "application/json", "User-Agent": "activity-push/1.0"})
        with request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))


def enrich_record(record: Dict[str, Any], client: AMapClient, city_hint_field: str = "") -> Dict[str, Any]:
    item = dict(record)
    address = str(item.get("activityAddress", "")).strip()
    if not address:
        item.update(
            {
                "activityLongitudeGCJ02": "",
                "activityLatitudeGCJ02": "",
                "activityLongitudeWGS84": "",
                "activityLatitudeWGS84": "",
                "activityGeoProvider": "amap",
                "activityGeoStatus": "skipped",
                "activityStaticMapUrl": "",
                "activityStaticMapStatus": "skipped",
            }
        )
        return item
    if not is_precise_address(address):
        item.update(
            {
                "activityLongitudeGCJ02": "",
                "activityLatitudeGCJ02": "",
                "activityLongitudeWGS84": "",
                "activityLatitudeWGS84": "",
                "activityGeoProvider": "amap",
                "activityGeoStatus": "skipped_vague",
                "activityStaticMapUrl": "",
                "activityStaticMapStatus": "skipped_vague",
            }
        )
        return item

    city_hint = str(item.get(city_hint_field, "")).strip() if city_hint_field else ""
    payload = client.geocode(address, city_hint=city_hint)
    geocodes = payload.get("geocodes", []) if isinstance(payload, dict) else []
    if not geocodes:
        item.update(
            {
                "activityLongitudeGCJ02": "",
                "activityLatitudeGCJ02": "",
                "activityLongitudeWGS84": "",
                "activityLatitudeWGS84": "",
                "activityGeoProvider": "amap",
                "activityGeoStatus": "not_found",
                "activityStaticMapUrl": "",
                "activityStaticMapStatus": "not_found",
            }
        )
        return item

    location = str(geocodes[0].get("location", ""))
    try:
        gcj_lng_str, gcj_lat_str = location.split(",", 1)
        gcj_lng = float(gcj_lng_str)
        gcj_lat = float(gcj_lat_str)
    except ValueError as exc:
        raise RuntimeError(f"invalid geocode location: {location}") from exc

    wgs_lng, wgs_lat = gcj02_to_wgs84(gcj_lng, gcj_lat)
    static_map_url = build_static_map_url(client.amap_key, gcj_lng, gcj_lat)
    item.update(
        {
            "activityLongitudeGCJ02": round(gcj_lng, 6),
            "activityLatitudeGCJ02": round(gcj_lat, 6),
            "activityLongitudeWGS84": round(wgs_lng, 6),
            "activityLatitudeWGS84": round(wgs_lat, 6),
            "activityGeoProvider": "amap",
            "activityGeoStatus": "ok",
            "activityStaticMapUrl": static_map_url,
            "activityStaticMapStatus": "ok" if static_map_url else "missing_key",
        }
    )
    return item


def run_geocode(args: argparse.Namespace) -> List[Dict[str, Any]]:
    input_path = Path(args.input).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()
    fixture_path = Path(args.fixture_file).expanduser().resolve() if args.fixture_file else None
    data = read_json(input_path)
    if not isinstance(data, list):
        raise RuntimeError("input must be a JSON array")

    client = AMapClient(amap_key=args.amap_key, fixture_file=fixture_path)
    enriched = [enrich_record(item, client, city_hint_field=args.city_hint_field) for item in data]
    write_json(output_path, enriched)
    return enriched


def main() -> int:
    args = parse_args()
    run_geocode(args)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)
