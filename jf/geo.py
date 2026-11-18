"""WGS84 helpers: geodetic <-> ECEF <-> local east/north/up."""
import numpy as np

A = 6378137.0
F = 1 / 298.257223563
E2 = F * (2 - F)
FT = 0.3048
KT = 0.514444


def ecef(lat, lon, h):
    lat, lon = np.radians(lat), np.radians(lon)
    n = A / np.sqrt(1 - E2 * np.sin(lat) ** 2)
    x = (n + h) * np.cos(lat) * np.cos(lon)
    y = (n + h) * np.cos(lat) * np.sin(lon)
    z = (n * (1 - E2) + h) * np.sin(lat)
    return np.stack([x, y, z], axis=-1)


def enu_matrix(lat0, lon0):
    la, lo = np.radians(lat0), np.radians(lon0)
    return np.array([
        [-np.sin(lo), np.cos(lo), 0.0],
        [-np.sin(la) * np.cos(lo), -np.sin(la) * np.sin(lo), np.cos(la)],
        [np.cos(la) * np.cos(lo), np.cos(la) * np.sin(lo), np.sin(la)],
    ])


class Frame:
    """Local east/north/up frame at a reference point (metres)."""

    def __init__(self, lat0, lon0, h0=0.0):
        self.lat0, self.lon0, self.h0 = lat0, lon0, h0
        self.o = ecef(lat0, lon0, h0)
        self.r = enu_matrix(lat0, lon0)

    def to_enu(self, lat, lon, h):
        return (ecef(np.asarray(lat, float), np.asarray(lon, float), np.asarray(h, float)) - self.o) @ self.r.T

    def to_geo(self, enu):
        """Inverse (iterative), returns lat, lon, h."""
        p = np.asarray(enu, float) @ self.r + self.o
        x, y, z = p[..., 0], p[..., 1], p[..., 2]
        lon = np.arctan2(y, x)
        rho = np.hypot(x, y)
        lat = np.arctan2(z, rho * (1 - E2))
        for _ in range(6):
            n = A / np.sqrt(1 - E2 * np.sin(lat) ** 2)
            h = rho / np.cos(lat) - n
            lat = np.arctan2(z, rho * (1 - E2 * n / (n + h)))
        return np.degrees(lat), np.degrees(lon), h
