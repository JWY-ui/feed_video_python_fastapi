# -*- coding: utf-8 -*-
"""
UTC time helpers -- the single definition of this project's time convention.

=== The convention ===

1. Every DateTime column stores a **naive UTC wall clock**. MySQL's DATETIME
   has no timezone, so an aware value handed to the driver gets its tzinfo
   stripped and the wall clock stored as-is. Verified empirically: values are
   written with datetime.now(timezone.utc), and reading them back gives UTC.

2. Python-side "now" is always aware UTC: `utc_now()`. The driver strips the
   tzinfo on the way in, which is exactly what we want.

3. **Values read back from the DB are naive but semantically UTC.** This is the
   trap this module exists to close: `naive_dt.timestamp()` makes Python assume
   LOCAL time, so on a UTC+8 machine every epoch exported to a client came out
   8 hours early -- which silently broke cursor pagination (the cursor pointed
   8h too far back, so the previous page's last row was never excluded and
   reappeared on the next page).

   Rule: before any epoch math or datetime arithmetic, run the value through
   `as_utc()`.

=== Why not store aware values instead? ===

MySQL DATETIME cannot hold an offset, so awareness would be lost on the round
trip anyway. Normalizing on read keeps the DB representation unambiguous and
puts the correction in one place.
"""
from datetime import datetime, timezone


def as_utc(dt: datetime) -> datetime:
    """
    Return `dt` as an aware UTC datetime.

    A naive value is *assumed* to be UTC (that is what the database stores).
    An aware value is converted to UTC.

    This is the fix for the offset bug: call it before `.timestamp()`.
    """
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def utc_now() -> datetime:
    """Current time as aware UTC. Use this instead of datetime.now() / func.now()."""
    return datetime.now(timezone.utc)


def epoch_seconds(dt: datetime) -> int:
    """Unix seconds for a datetime from any source (naive DB value or aware)."""
    return int(as_utc(dt).timestamp())


def epoch_ms(dt: datetime) -> int:
    """Unix milliseconds -- the unit the feed cursor endpoints expect."""
    return int(as_utc(dt).timestamp() * 1000)


def utc_from_epoch(seconds: float) -> datetime:
    """
    Build an aware UTC datetime from Unix seconds.

    Used when turning a client-supplied cursor back into a value for a WHERE
    clause. Passing an aware value is safe: the driver stores/compares its wall
    clock, which is the same UTC wall clock the column holds (verified).
    """
    return datetime.fromtimestamp(seconds, tz=timezone.utc)
