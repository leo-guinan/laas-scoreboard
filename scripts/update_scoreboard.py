#!/usr/bin/env python3
"""Update scoreboard aggregates from Fathom and Stripe without exposing credentials."""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

FATHOM_SITE_ID = "XERIAWTA"
VARIANTS = {
    "essay": "essay.leoasaservice.com",
    "jay": "jay.leoasaservice.com",
    "sales": "www.leoasaservice.com",
    "quai": "quai.leoasaservice.com",
}
SOURCES = ("YouTube", "LinkedIn", "X", "Direct", "Other")


def get_json(url: str, headers: dict[str, str] | None = None) -> object:
    request = Request(url, headers=headers or {})
    with urlopen(request, timeout=30) as response:
        return json.load(response)


def fathom_token() -> str:
    raw = os.environ["FATHOM_API_KEY"].strip()
    return raw.split("|", 1)[1] if "|" in raw else raw


def date_window(start_at: str) -> tuple[str, str, datetime] | None:
    if not start_at:
        return None
    start = datetime.fromisoformat(start_at.replace("Z", "+00:00"))
    today = datetime.now(timezone.utc).date()
    return start.date().isoformat(), today.isoformat(), start


def fathom_aggregate(params: dict[str, str]) -> list[dict]:
    query = urlencode(params)
    payload = get_json(
        f"https://api.usefathom.com/v1/aggregations?{query}",
        {"Authorization": f"Bearer {fathom_token()}"},
    )
    if isinstance(payload, dict):
        return payload.get("data", [])
    return payload if isinstance(payload, list) else []


def as_int(value: object) -> int:
    try:
        return int(float(str(value or 0)))
    except (TypeError, ValueError):
        return 0


def as_money_cents(value: object) -> int:
    try:
        return int(str(value or 0))
    except (TypeError, ValueError):
        return 0


def fetch_fathom(window: tuple[str, str, datetime]) -> tuple[dict, dict, dict, dict]:
    start, end, _ = window
    base = {
        "entity": "pageview",
        "entity_id": FATHOM_SITE_ID,
        "date_from": start,
        "date_to": end,
    }
    total_rows = fathom_aggregate({**base, "aggregates": "visits,pageviews"})
    total = total_rows[0] if total_rows else {}

    variant_rows = fathom_aggregate({
        **base,
        "aggregates": "visits,pageviews",
        "field_grouping": "hostname",
        "limit": "100",
    })
    variants = {key: {"traffic": 0, "ctaClicks": 0, "bookings": 0, "paidConversions": 0, "revenue": 0} for key in VARIANTS}
    for row in variant_rows:
        hostname = row.get("hostname", "").lower()
        for variant, expected_host in VARIANTS.items():
            if hostname == expected_host:
                variants[variant]["traffic"] = as_int(row.get("visits", row.get("pageviews")))

    source_rows = fathom_aggregate({
        **base,
        "aggregates": "visits,pageviews",
        "field_grouping": "utm_source",
        "limit": "100",
    })
    sources = {}
    for row in source_rows:
        raw = (row.get("utm_source") or "").strip().lower()
        source = "YouTube" if "youtube" in raw else "LinkedIn" if "linkedin" in raw else "X" if raw in {"x", "twitter", "t.co"} else "Direct" if not raw else "Other"
        bucket = sources.setdefault(source, {"traffic": 0, "paid": 0, "revenue": 0})
        bucket["traffic"] += as_int(row.get("visits", row.get("pageviews")))

    hourly = {}
    try:
        cursor = datetime.fromisoformat(start).date()
        finish = datetime.fromisoformat(end).date()
        while cursor <= finish:
            chunk_finish = min(cursor + timedelta(days=6), finish)
            hourly_rows = fathom_aggregate({
                **base,
                "date_from": cursor.isoformat(),
                "date_to": chunk_finish.isoformat(),
                "aggregates": "visits",
                "date_grouping": "hour",
                "field_grouping": "hostname",
                "limit": "1000",
            })
            for row in hourly_rows:
                raw_time = row.get("date") or row.get("datetime") or row.get("timestamp")
                hostname = row.get("hostname", "").lower()
                if not raw_time:
                    continue
                try:
                    hour = datetime.fromisoformat(str(raw_time).replace("Z", "+00:00")).astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0).isoformat()
                except ValueError:
                    continue
                for variant, expected_host in VARIANTS.items():
                    if hostname == expected_host:
                        hourly.setdefault(hour, {})[variant] = as_int(row.get("visits"))
            cursor = chunk_finish + timedelta(days=1)
    except Exception as exc:
        print(f"hourly Fathom attribution unavailable: {exc}", file=sys.stderr)

    return {"traffic": as_int(total.get("visits", total.get("pageviews"))), "ctaClicks": 0, "bookings": 0, "paidConversions": 0, "revenue": 0}, variants, sources, hourly


def stripe_payments(window: tuple[str, str, datetime]) -> tuple[dict, dict, list[dict]]:
    start = int(window[2].timestamp())
    headers = {"Authorization": f"Bearer {os.environ['STRIPE_SECRET_KEY'].strip()}"}
    payments: list[dict] = []
    starting_after = None
    while True:
        params = {"limit": "100", "created[gte]": str(start)}
        if starting_after:
            params["starting_after"] = starting_after
        query = urlencode(params)
        payload = get_json(f"https://api.stripe.com/v1/payment_intents?{query}", headers)
        if not isinstance(payload, dict):
            raise RuntimeError("Stripe returned a non-object response")
        batch = payload.get("data", [])
        payments.extend(batch)
        if not payload.get("has_more") or not batch:
            break
        starting_after = batch[-1]["id"]

    totals = {"traffic": 0, "ctaClicks": 0, "bookings": 0, "paidConversions": 0, "revenue": 0}
    variants = {key: {"traffic": 0, "ctaClicks": 0, "bookings": 0, "paidConversions": 0, "revenue": 0} for key in VARIANTS}
    eligible = []
    for payment in payments:
        if payment.get("status") != "succeeded" or not as_money_cents(payment.get("amount_received")):
            continue
        metadata = payment.get("metadata") or {}
        if metadata.get("experiment") not in (None, "", "laas_three_way_v1", "laas_four_way_v1"):
            continue
        variant = metadata.get("landing_variant")
        amount = as_money_cents(payment.get("amount_received")) // 100
        totals["paidConversions"] += 1
        totals["revenue"] += amount
        eligible.append(payment)
        if variant in variants:
            variants[variant]["paidConversions"] += 1
            variants[variant]["revenue"] += amount
    return totals, variants, eligible


def fuzzy_attribute(payments: list[dict], hourly: dict, variants: dict) -> dict:
    """Assign untagged payments only when one variant owns the nearby traffic bucket."""
    summary = {"exact": 0, "fuzzy": 0, "ambiguous": 0, "unattributed": 0}
    for payment in payments:
        metadata = payment.get("metadata") or {}
        if metadata.get("landing_variant") in variants:
            summary["exact"] += 1
            continue
        created = payment.get("created")
        if not created:
            summary["unattributed"] += 1
            continue
        payment_hour = datetime.fromtimestamp(int(created), tz=timezone.utc).replace(minute=0, second=0, microsecond=0)
        scores = {variant: 0 for variant in VARIANTS}
        for offset in (0, -1):
            bucket = hourly.get((payment_hour + timedelta(hours=offset)).isoformat(), {})
            for variant in VARIANTS:
                scores[variant] += int(bucket.get(variant, 0))
        ordered = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        if ordered[0][1] > 0 and ordered[0][1] > ordered[1][1]:
            variant = ordered[0][0]
            amount = as_money_cents(payment.get("amount_received")) // 100
            variants[variant]["paidConversions"] += 1
            variants[variant]["revenue"] += amount
            summary["fuzzy"] += 1
        elif sum(scores.values()) > 0:
            summary["ambiguous"] += 1
        else:
            summary["unattributed"] += 1
    return summary


def main() -> int:
    path = Path(os.environ.get("SCOREBOARD_PATH", "data/scoreboard.json"))
    data = json.loads(path.read_text())
    window = date_window(data.get("experiment", {}).get("startAt", ""))
    if not window:
        data["updatedAt"] = "NOT_STARTED"
        data["source"] = "UNMEASURED — experiment.startAt is empty"
        path.write_text(json.dumps(data, indent=2) + "\n")
        print("Experiment not started; scoreboard left unmeasured.")
        return 0

    fathom_totals, fathom_variants, sources, hourly = fetch_fathom(window)
    stripe_totals, stripe_variants, payments = stripe_payments(window)
    attribution = fuzzy_attribute(payments, hourly, stripe_variants)
    totals = fathom_totals | {"paidConversions": stripe_totals["paidConversions"], "revenue": stripe_totals["revenue"]}
    variants = {}
    for key in VARIANTS:
        variants[key] = fathom_variants[key] | {
            "paidConversions": stripe_variants[key]["paidConversions"],
            "revenue": stripe_variants[key]["revenue"],
        }
    data["metrics"] = {"totals": totals, "variants": variants, "sources": sources, "attribution": attribution}
    data["updatedAt"] = datetime.now(timezone.utc).isoformat()
    data["source"] = "Fathom pageview/hourly aggregates + Stripe succeeded PaymentIntents"
    path.write_text(json.dumps(data, indent=2) + "\n")
    print(json.dumps({"window": window[:2], "startAt": window[2].isoformat(), "totals": totals, "variants": variants}, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"scoreboard update failed: {exc}", file=sys.stderr)
        raise
