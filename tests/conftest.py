from pathlib import Path

import mongomock
import pytest

from ampel.demo.unit.base.DemoPointT2Unit import DemoPointT2Unit
from ampel.dev.DevAmpelContext import DevAmpelContext
from ampel.mongo.update.PointT2Ingester import PointT2Ingester
from ampel.mongo.update.StockIngester import StockIngester
from ampel.mongo.update.StockT2Ingester import StockT2Ingester
from ampel.model.AlertProcessorDirective import AlertProcessorDirective

from .dummy_units import (
    DummyAlertContentIngester,
    DummyCompoundIngester,
    DummyExtendedCompoundIngester,
    DummyStateT2Ingester,
    DummyStateT2Unit,
    DummyStockT2Unit,
)


@pytest.fixture
def patch_mongo(monkeypatch):
    monkeypatch.setattr("ampel.core.AmpelDB.MongoClient", mongomock.MongoClient)


@pytest.fixture
def dev_context(patch_mongo):
    return DevAmpelContext.load(Path(__file__).parent / "testing-config.yaml",)


@pytest.fixture
def legacy_directive():
    return AlertProcessorDirective(
        **{
            "channel": "TEST_CHANNEL",
            "stock_update": {"unit": StockIngester},
            "t0_add": {
                "ingester": DummyAlertContentIngester,
                "t1_combine": [
                    {
                        "ingester": DummyCompoundIngester,
                        "t2_compute": {
                            "ingester": DummyStateT2Ingester,
                            "units": [{"unit": DummyStateT2Unit}],
                        },
                    }
                ],
                "t2_compute": {
                    "ingester": PointT2Ingester,
                    "units": [{"unit": DemoPointT2Unit}],
                },
            },
            "t2_compute": {
                "ingester": StockT2Ingester,
                "units": [{"unit": DummyStockT2Unit}],
            },
        }
    )


@pytest.fixture
def standalone_t1_directive():
    return AlertProcessorDirective(
        **{
            "channel": "TEST_CHANNEL",
            "stock_update": {"unit": StockIngester},
            "t0_add": {
                "ingester": DummyAlertContentIngester,
                "t1_combine": [
                    {
                        "ingester": DummyCompoundIngester,
                        "t2_compute": {
                            "ingester": DummyStateT2Ingester,
                            "units": [{"unit": DummyStateT2Unit}],
                        },
                    }
                ],
            },
            "t1_combine": [
                {
                    "ingester": DummyExtendedCompoundIngester,
                    "t2_compute": {
                        "ingester": DummyStateT2Ingester,
                        "units": [{"unit": DummyStateT2Unit}],
                    },
                }
            ],
        }
    )
