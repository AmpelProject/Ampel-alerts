#!/usr/bin/env python
# -*- coding: utf-8 -*-
# File:                Ampel-alerts/tests/test_AlertConsumer.py
# License:             BSD-3-Clause
# Author:              jvs
# Date:                Unspecified
# Last Modified Date:  24.11.2021
# Last Modified By:    vb

import os
import signal
import threading
import time
from contextlib import contextmanager

import pytest

from ampel.alert.AlertConsumer import AlertConsumer
from ampel.alert.AlertConsumerError import AlertConsumerError
from ampel.alert.AmpelAlert import AmpelAlert
from ampel.alert.filter.BasicMultiFilter import BasicMultiFilter
from ampel.dev.DevAmpelContext import DevAmpelContext
from ampel.dev.UnitTestAlertSupplier import UnitTestAlertSupplier
from ampel.metrics.AmpelMetricsRegistry import AmpelMetricsRegistry
from ampel.model.ingest.FilterModel import FilterModel
from ampel.model.ingest.IngestBody import IngestBody
from ampel.model.ingest.IngestDirective import IngestDirective
from ampel.model.ingest.T1Combine import T1Combine
from ampel.model.ingest.T2Compute import T2Compute


@contextmanager
def collect_diff(store):
    store.clear()
    before = {}
    for metric in AmpelMetricsRegistry.registry().collect():
        for sample in metric.samples:
            key = (sample.name, tuple(sample.labels.items()))
            before[key] = sample.value

    delta = {}
    yield
    for metric in AmpelMetricsRegistry.registry().collect():
        for sample in metric.samples:
            key = (sample.name, tuple(sample.labels.items()))
            delta[key] = sample.value - (before.get(key) or 0)
    store.update(delta)


@pytest.fixture
def single_source_directive(
    dev_context: DevAmpelContext, dummy_units
) -> IngestDirective:

    return IngestDirective(
        channel="TEST_CHANNEL",
        ingest=IngestBody(
            stock_t2=[T2Compute(unit="DummyStockT2Unit")],
            point_t2=[T2Compute(unit="DummyPointT2Unit")],
            combine=[
                T1Combine(
                    unit="T1SimpleCombiner",
                    state_t2=[T2Compute(unit="DummyStateT2Unit")],
                )
            ],
        ),
    )


def test_no_filter(dev_context, single_source_directive):
    stats = {}
    with collect_diff(stats):
        ap = AlertConsumer(
            context=dev_context,
            process_name="ap",
            shaper="NoShaper",
            directives=[single_source_directive],
            supplier={
                "unit": "UnitTestAlertSupplier",
                "config": {
                    "alerts": [
                        AmpelAlert(
                            id="alert", stock="stockystock", datapoints=[{"id": 0}]
                        )
                    ]
                },
            },
            raise_exc=True,
        )
        assert ap.run() == 1

    assert dev_context.db.get_collection("stock").count_documents({}) == 1
    assert stats[("ampel_alertprocessor_alerts_processed_total", ())] == 1
    assert (
        stats[
            (
                "ampel_alertprocessor_alerts_accepted_total",
                (("channel", "TEST_CHANNEL"),),
            )
        ]
        == 1
    )
    assert (
        stats[
            (
                "ampel_alertprocessor_time_seconds_sum",
                (("section", "ingest"),),
            )
        ]
        > 0
    )
    assert (
        stats[
            (
                "ampel_alertprocessor_time_seconds_sum",
                (("section", "filter.TEST_CHANNEL"),),
            )
        ]
        == 0
    )


def test_with_filter(dev_context, single_source_directive):
    stats = {}
    with collect_diff(stats):
        single_source_directive.filter = FilterModel(
            unit="BasicMultiFilter",
            config={
                "filters": [
                    {
                        "criteria": [
                            {"attribute": "nonesuch", "value": 0, "operator": "=="}
                        ],
                        "len": 0,
                        "operator": "==",
                    }
                ]
            },
        )
        ap = AlertConsumer(
            context=dev_context,
            process_name="ap",
            shaper="NoShaper",
            directives=[single_source_directive],
            supplier={
                "unit": "UnitTestAlertSupplier",
                "config": {
                    "alerts": [
                        AmpelAlert(
                            id="alert", stock="stockystock", datapoints=[{"id": 0}]
                        )
                    ]
                },
            },
        )
        assert ap.run() == 1

    assert dev_context.db.get_collection("stock").count_documents({}) == 1
    assert stats[("ampel_alertprocessor_alerts_processed_total", ())] == 1
    assert (
        stats[
            (
                "ampel_alertprocessor_alerts_accepted_total",
                (("channel", "TEST_CHANNEL"),),
            )
        ]
        == 1
    )
    assert (
        stats[
            (
                "ampel_alertprocessor_time_seconds_sum",
                (("section", "ingest"),),
            )
        ]
        > 0
    )
    assert (
        stats[
            (
                "ampel_alertprocessor_time_seconds_sum",
                (("section", "filter.TEST_CHANNEL"),),
            )
        ]
        > 0
    )


def test_suspend_in_supplier(dev_context, single_source_directive):

    # simulate a producer that blocks while waiting fo upstream input
    class BlockingAlertSupplier(UnitTestAlertSupplier):
        def __iter__(self):
            for el in super().__iter__():
                print("sleep 3")
                time.sleep(3)
                yield el

    dev_context.register_unit(BlockingAlertSupplier)
    ap = AlertConsumer(
        context=dev_context,
        process_name="ap",
        shaper="NoShaper",
        directives=[single_source_directive],
        supplier={
            "unit": "BlockingAlertSupplier",
            "config": {
                "alerts": [AmpelAlert(id="alert", stock="stockystock", datapoints=[])]
            },
        },
    )

    def alarm():
        time.sleep(0.5)
        os.kill(os.getpid(), signal.SIGINT)

    t = threading.Thread(target=alarm)
    t.start()
    t0 = time.time()
    assert ap.run() == 0, "AP suspended before first alert was processed"
    assert time.time() - t0 < 2, "AP suspended before supplier timed out"
    t.join()


def test_suspend_in_critical_section(dev_context, single_source_directive, monkeypatch):
    monkeypatch.setattr(
        BasicMultiFilter, "process", lambda *args: os.kill(os.getpid(), signal.SIGINT)
    )
    single_source_directive.filter = FilterModel(
        unit="BasicMultiFilter", config={"filters": []}
    )
    ap = AlertConsumer(
        context=dev_context,
        process_name="ap",
        shaper="NoShaper",
        directives=[single_source_directive],
        supplier={
            "unit": "UnitTestAlertSupplier",
            "config": {
                "alerts": [AmpelAlert(id="alert", stock="stockystock", datapoints=[])]
            },
        },
    )
    assert ap.run() == 1, "AP successfully processes alert"
    assert ap._cancel_run == AlertConsumerError.SIGINT


def test_journal_extra(dev_context, single_source_directive):
    value = 42
    ap = AlertConsumer(
        context=dev_context,
        process_name="ap",
        shaper="NoShaper",
        directives=[single_source_directive],
        supplier={
            "unit": "UnitTestAlertSupplier",
            "config": {
                "alerts": [
                    AmpelAlert(
                        id="alert",
                        stock="stockystock",
                        datapoints=[{"id": 0}],
                        extra={"foo": {"bar": {"baz": value}}},
                    )
                ]
            },
        },
        include_alert_extra_with_keys={"fooey": "foo.bar.baz"}
    )
    assert ap.run() == 1, "AP successfully processes alert"
    jentry = dev_context.db.get_collection("stock").find_one()["journal"][0]
    assert jentry["alert"] == "alert"
    assert jentry["fooey"] == value

