# AMap Geocode, WGS84, and Static Map Notes

This reference supports the `activity-push` skill when an extracted activity has an address and needs coordinates or a static map image URL.

Read this file when:
- you need to turn `activityAddress` into coordinates
- you need to generate a static map URL for the final Markdown
- you need to explain why the workflow uses AMap geocoding plus a local conversion step
- you need to debug address-to-coordinate enrichment

## Core model

The workflow is:
1. call AMap geocode API with the structured address
2. read the returned `location`
3. treat that location as AMap coordinates
4. convert AMap coordinates to WGS84 locally
5. build an AMap static map URL from the AMap coordinates
6. append GCJ-02, WGS84, and static-map fields to the structured activity data

## Why there is a local conversion step

The AMap geocode API returns AMap coordinates for the address lookup result.

AMap's own JS documentation states:
- WGS84 is the international GPS coordinate system
- GCJ-02 is the coordinate system used by AMap in China
- `convertFrom()` converts non-AMap coordinates into AMap coordinates

From that, this skill infers:
- the geocode `location` returned by AMap should be treated as GCJ-02 / AMap coordinates
- if the user wants WGS84, the conversion must happen locally after geocoding

This is an inference from AMap coordinate-system documentation, not a separate AMap Web Service endpoint that directly returns WGS84.

## Required key

Typical variable:

```bash
AMAP_WEB_SERVICE_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

Use a Web Service key for:
- `https://restapi.amap.com/v3/geocode/geo`
- `https://restapi.amap.com/v3/staticmap`

## Output fields

Recommended fields appended to each activity:
- `activityLongitudeGCJ02`
- `activityLatitudeGCJ02`
- `activityLongitudeWGS84`
- `activityLatitudeWGS84`
- `activityGeoProvider`
- `activityGeoStatus`
- `activityStaticMapUrl`
- `activityStaticMapStatus`

Statuses:
- `ok`
- `not_found`
- `skipped`
- `missing_key`

## Bundled CLI

Use:
- [`amap_geocode_wgs84.py`](/Users/yujian/Code/py/aj-skills/skills/activity-push/scripts/amap_geocode_wgs84.py)

The CLI:
- reads `activity-structured.json`
- geocodes `activityAddress`
- converts GCJ-02 to WGS84 locally
- builds a static map URL with the same AMap key
- writes a geo-enriched JSON file

It also supports offline testing through:
- `--fixture-file`

## Sources

Geocode API reference:
- https://amap.apifox.cn/api-14546468

Static map API reference:
- https://amap.apifox.cn/api-14554037

AMap coordinate-system explanation:
- https://a.amap.com/jsapi/static/doc/20230922/index.html#convertFrom
