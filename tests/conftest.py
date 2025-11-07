from pathlib import Path

import mongomock
import pytest
import yaml

from ampel.abstract.AbsAlertFilter import AbsAlertFilter
from ampel.dev.DevAmpelContext import DevAmpelContext
from ampel.protocol.AmpelAlertProtocol import AmpelAlertProtocol


@pytest.fixture
def _patch_mongo(monkeypatch):
    monkeypatch.setattr("ampel.core.AmpelDB.MongoClient", mongomock.MongoClient)


@pytest.fixture
def testing_config():
    return Path(__file__).parent / "testing-config.yaml"


@pytest.fixture
def first_pass_config(testing_config):
    with open(testing_config, "rb") as f:
        return yaml.safe_load(f)


@pytest.fixture
def dev_context(_patch_mongo, testing_config):
    return DevAmpelContext.load(testing_config)


class DummyFilter(AbsAlertFilter):
    def process(self, alert: AmpelAlertProtocol) -> None | bool | int:
        return True


@pytest.fixture
def _dummy_units(dev_context: DevAmpelContext):

    # register dummy units in-process so gen_config_id can find them
    from ampel.test import dummy  # noqa: PLC0415
    for name, klass in dummy.__dict__.items():
        if name.startswith("Dummy"):
            dev_context.register_unit(klass)
    dev_context.register_unit(DummyFilter)
