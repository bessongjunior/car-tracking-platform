import math


def haversine_distance(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Return distance in metres between two GPS coordinates."""
    R = 6_371_000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def point_in_polygon(lat: float, lng: float, coordinates: list) -> bool:
    """
    Ray-casting algorithm for GeoJSON polygon coordinates.
    `coordinates` is the first ring of a GeoJSON Polygon: [[lng, lat], ...]
    """
    n = len(coordinates)
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = coordinates[i][0], coordinates[i][1]
        xj, yj = coordinates[j][0], coordinates[j][1]
        if ((yi > lat) != (yj > lat)) and (lng < (xj - xi) * (lat - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


def vehicle_in_geofence(lat: float, lng: float, geofence: dict) -> bool:
    """
    Check whether a GPS point is inside the given geofence geometry dict.
    Supports:
      - fence_type='circle'  → geometry = {center: {lat, lng}, radius_m: N}
      - fence_type='polygon' → geometry = GeoJSON Polygon {type, coordinates}
    """
    fence_type = geofence.get('fence_type', 'polygon')
    geometry = geofence.get('geometry', {})

    try:
        if fence_type == 'circle':
            center = geometry.get('center', {})
            # support both 'radius_m' and 'radius' keys
            radius = geometry.get('radius_m', geometry.get('radius', 0))
            distance = haversine_distance(
                lat, lng,
                center.get('lat', 0), center.get('lng', 0),
            )
            return distance <= radius

        if fence_type == 'polygon':
            coords = geometry.get('coordinates', [[]])[0]
            return point_in_polygon(lat, lng, coords)
    except Exception:
        return False

    return False
