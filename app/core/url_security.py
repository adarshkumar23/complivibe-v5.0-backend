from __future__ import annotations

import ipaddress
import socket
import urllib.parse

from fastapi import HTTPException, status


class UnsafeURLTargetError(ValueError):
    pass


def assert_public_http_url(url: str, *, field_name: str = "url") -> None:
    """Reject server-side fetch targets that resolve to non-public networks."""
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme not in {"http", "https"}:
        raise UnsafeURLTargetError(f"{field_name} must use http or https")
    if parsed.username or parsed.password:
        raise UnsafeURLTargetError(f"{field_name} must not include credentials")
    hostname = parsed.hostname
    if not hostname:
        raise UnsafeURLTargetError(f"{field_name} is missing a hostname")

    try:
        addr_infos = socket.getaddrinfo(hostname, parsed.port)
    except OSError as exc:
        raise UnsafeURLTargetError(f"{field_name} hostname could not be resolved") from exc

    for _, _, _, _, sockaddr in addr_infos:
        try:
            ip = ipaddress.ip_address(sockaddr[0])
        except ValueError:
            continue
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            raise UnsafeURLTargetError(f"{field_name} must not resolve to an internal or private address")


def raise_unsafe_url_http_error(exc: UnsafeURLTargetError, *, field_name: str = "url") -> None:
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=f"{field_name} must be a public http(s) URL; internal or private addresses are not allowed.",
    ) from exc
