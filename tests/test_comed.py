"""Tests for the ComEd price client. Network is mocked with respx."""

from __future__ import annotations

import httpx
import respx

from home_auto.sources.comed import API_BASE, ComEdClient, _parse_points


def test_parse_points_sorts_oldest_first_and_skips_bad_rows():
    raw = [
        {"millisUTC": "2000", "price": "3.0"},   # newer
        {"millisUTC": "1000", "price": "2.0"},   # older
        {"oops": "missing fields"},               # bad -> skipped
        {"millisUTC": "abc", "price": "xyz"},     # unparseable -> skipped
    ]
    points = _parse_points(raw)
    assert len(points) == 2
    assert points[0].timestamp < points[1].timestamp   # sorted oldest-first
    assert points[0].price_cents == 2.0


@respx.mock
async def test_get_5min_feed_parses_response():
    respx.get(url__startswith=API_BASE).mock(
        return_value=httpx.Response(
            200, json=[{"millisUTC": "1780340700000", "price": "2.8"}]
        )
    )
    async with httpx.AsyncClient() as http:
        points = await ComEdClient(http).get_5min_feed()
    assert points[-1].price_cents == 2.8


@respx.mock
async def test_get_latest_price_returns_most_recent():
    respx.get(url__startswith=API_BASE).mock(
        return_value=httpx.Response(
            200,
            json=[
                {"millisUTC": "2000", "price": "9.0"},
                {"millisUTC": "1000", "price": "1.0"},
            ],
        )
    )
    async with httpx.AsyncClient() as http:
        latest = await ComEdClient(http).get_latest_price()
    assert latest.price_cents == 9.0  # the entry with the larger timestamp


@respx.mock
async def test_get_current_hour_average():
    respx.get(url__startswith=API_BASE).mock(
        return_value=httpx.Response(200, json=[{"millisUTC": "1", "price": "4.5"}])
    )
    async with httpx.AsyncClient() as http:
        avg = await ComEdClient(http).get_current_hour_average()
    assert avg == 4.5
