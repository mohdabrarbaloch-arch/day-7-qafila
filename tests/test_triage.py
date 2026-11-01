"""Exception triage rules."""

from __future__ import annotations

from app.engine import triage as triage_mod
from app.engine.triage import Action, Severity, triage


def test_accident_is_critical_and_escalates():
    result = triage("Driver reports an accident on the motorway near Sukkur")
    assert result.severity is Severity.critical
    assert result.action is Action.escalate_human
    assert "safety_or_loss" in result.labels


def test_cold_chain_breach_is_critical():
    result = triage("Cold chain failed, temperature rose to 18C, cargo spoiled")
    assert result.severity is Severity.critical
    assert "cold_chain_breach" in result.labels


def test_breakdown_reassigns_carrier():
    result = triage("Truck had an engine breakdown 40km from Multan")
    assert result.severity is Severity.high
    assert result.action is Action.reassign_carrier


def test_plain_delay_is_medium_and_notifies():
    result = triage("Shipment is delayed due to traffic")
    assert result.severity is Severity.medium
    assert result.action is Action.notify_customer


def test_unmatched_text_is_not_dropped():
    result = triage("Something odd happened, not sure what")
    assert "unclassified" in result.labels
    assert result.action is Action.notify_customer


def test_empty_description_still_returns_a_triage():
    result = triage("")
    assert result.severity is Severity.low
    assert "unclassified" in result.labels


def test_high_value_raises_severity_floor():
    # A plain delay on a 2M PKR shipment is not a routine delay.
    result = triage("Shipment is delayed", declared_value_pkr=2_000_000)
    assert result.severity is Severity.high
    assert result.action is Action.escalate_human
    assert "high_value" in result.labels


def test_high_value_does_not_downgrade_critical():
    result = triage("Accident, cargo stolen", declared_value_pkr=5_000_000)
    assert result.severity is Severity.critical


def test_low_value_delay_stays_medium():
    result = triage("Shipment is delayed", declared_value_pkr=5_000)
    assert result.severity is Severity.medium


def test_worst_matching_rule_wins():
    # Mentions both a delay and a breakdown; breakdown is more severe.
    result = triage("Delayed because of a tyre puncture")
    assert result.severity is Severity.high
    assert result.action is Action.reassign_carrier


def test_triage_dict_is_json_safe():
    payload = triage("Accident").as_dict()
    assert set(payload) == {"severity", "action", "labels", "reason"}
    assert isinstance(payload["labels"], list)
    assert payload["severity"] == "critical"


def test_rules_table_is_ordered_most_severe_first():
    # The first rule must be the safety one; ordering is load-bearing.
    assert triage_mod.RULES[0][3] == "safety_or_loss"
