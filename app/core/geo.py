"""Shared helpers for comparing hierarchical geographic/region codes.

Region and jurisdiction codes used throughout the app (data asset
``geographic_locations``/``permitted_regions``, subprocessor locations,
framework/obligation ``jurisdiction``, residency policy ``required_countries``/
``prohibited_countries``, etc.) follow a dash-delimited hierarchy from
broadest to narrowest, e.g. ``"IN"`` (country) vs ``"IN-Mumbai"``
(country-city). Comparing these values with plain string equality or set
membership/intersection is a recurring bug: ``"IN-Mumbai" != "IN"`` as
strings even though the city is legitimately located within the country.

Use :func:`region_covers` (or :func:`location_in_countries`) instead of
``==``/``in``/set operations wherever a broader scope code needs to match a
possibly more specific location code, or vice versa.
"""

from __future__ import annotations


def region_covers(scope: str, location: str) -> bool:
    """True if the (typically broader) ``scope`` code covers ``location``.

    Scope ``"IN"`` covers locations ``"IN"`` and ``"IN-Mumbai"`` (and any
    deeper descendant like ``"IN-Mumbai-DC1"``), but scope ``"IN-Mumbai"``
    covers only ``"IN-Mumbai"`` (and its descendants) -- not the broader
    ``"IN"``. Comparison is exact after that, so unrelated codes (e.g.
    ``"IN"`` vs ``"ID"``) never match.
    """
    if not scope or not location:
        return scope == location
    if scope == location:
        return True
    return location.startswith(scope + "-")

def region_overlaps(a: str, b: str) -> bool:
    """True if `a` and `b` are the same region or one is hierarchically
    nested within the other, in either direction."""
    return region_covers(a, b) or region_covers(b, a)


def location_in_countries(location: str, countries: set[str] | frozenset[str]) -> bool:
    """True if `location` (e.g. "IN-Mumbai") falls within any of the given
    broader region/country codes (e.g. {"IN"}), matching hierarchically."""
    return any(region_covers(country, location) for country in countries)


def any_location_in_countries(locations, countries: set[str] | frozenset[str]) -> bool:
    """True if any of `locations` falls within any of `countries`, hierarchically."""
    return any(location_in_countries(loc, countries) for loc in locations)
