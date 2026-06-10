"""Tests for the trigger store (CRUD + ids) and the evaluation engine."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from home_auto.engine.triggers import evaluate_triggers
from home_auto.triggers import Trigger, TriggerCreate, TriggerStore


def _store(tmp_path) -> TriggerStore:
    return TriggerStore(tmp_path / "triggers.json")


def test_add_assigns_unique_ids_and_persists(tmp_path):
    store = _store(tmp_path)
    a = store.add(TriggerCreate(name="cheap", operator="<", value=3.0))
    b = store.add(TriggerCreate(name="pricey", operator=">", value=10.0))
    assert a.id != b.id
    # A fresh store over the same file sees both (persisted).
    assert {t.id for t in _store(tmp_path).list()} == {a.id, b.id}


def test_update_and_delete(tmp_path):
    store = _store(tmp_path)
    t = store.add(TriggerCreate(name="cheap", operator="<", value=3.0))

    updated = store.update(t.id, TriggerCreate(name="cheaper", operator="<", value=2.0))
    assert updated is not None and updated.name == "cheaper" and updated.value == 2.0
    assert store.update("nope", TriggerCreate(name="x", operator="<", value=1.0)) is None

    assert store.delete(t.id) is True
    assert store.delete(t.id) is False
    assert store.list() == []


def _trigger(**kw) -> Trigger:
    base = dict(id="1", name="t", operator="<", value=3.0)
    base.update(kw)
    return Trigger(**base)


def test_evaluate_fires_on_match_only():
    now = datetime.now(timezone.utc)
    t = _trigger(operator="<", value=3.0)
    # price below 3.0 -> fires
    fired = evaluate_triggers([t], price_cents=2.5, hour_average=None, now=now, last_fired={})
    assert len(fired) == 1
    # price above 3.0 -> no fire
    fired = evaluate_triggers([t], price_cents=4.0, hour_average=None, now=now, last_fired={})
    assert fired == []


def test_evaluate_respects_enabled_and_cooldown():
    now = datetime.now(timezone.utc)
    t = _trigger(operator="<", value=3.0, cooldown_minutes=60, enabled=True)

    disabled = _trigger(enabled=False)
    assert evaluate_triggers([disabled], price_cents=1.0, hour_average=None, now=now, last_fired={}) == []

    # Fired 10 minutes ago, cooldown is 60 -> still suppressed.
    last = {t.id: now - timedelta(minutes=10)}
    assert evaluate_triggers([t], price_cents=1.0, hour_average=None, now=now, last_fired=last) == []
    # Fired 70 minutes ago -> allowed again.
    last = {t.id: now - timedelta(minutes=70)}
    assert len(evaluate_triggers([t], price_cents=1.0, hour_average=None, now=now, last_fired=last)) == 1


def test_evaluate_skips_when_metric_unavailable():
    now = datetime.now(timezone.utc)
    t = _trigger(metric="hour_average", operator=">", value=5.0)
    # hour_average is None this cycle -> cannot evaluate, no fire.
    assert evaluate_triggers([t], price_cents=9.0, hour_average=None, now=now, last_fired={}) == []
