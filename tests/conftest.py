from ampel.abstract.AbsAlertFilter import AbsAlertFilter
from ampel.protocol.AmpelAlertProtocol import AmpelAlertProtocol
import mongomock
import pytest
import yaml
from pathlib import Path

from ampel.dev.DevAmpelContext import DevAmpelContext
from ampel.test.dummy import DummyPointT2Unit, DummyStateT2Unit, DummyStockT2Unit


@pytest.fixture
def patch_mongo(monkeypatch):
    monkeypatch.setattr("ampel.core.AmpelDB.MongoClient", mongomock.MongoClient)


@pytest.fixture
def testing_config():
    return Path(__file__).parent / "testing-config.yaml"


@pytest.fixture
def first_pass_config(testing_config):
    with open(testing_config, "rb") as f:
        return yaml.safe_load(f)


@pytest.fixture
def dev_context(patch_mongo, testing_config):
    return DevAmpelContext.load(testing_config)


class DummyFilter(AbsAlertFilter):
    def process(self, alert: AmpelAlertProtocol) -> None | bool | int:
        return True


@pytest.fixture
def dummy_units(dev_context: DevAmpelContext):

    # register dummy units in-process so gen_config_id can find them
    from ampel.test import dummy
    for name, klass in dummy.__dict__.items():
        if name.startswith("Dummy"):
            dev_context.register_unit(klass)
    dev_context.register_unit(DummyFilter)
