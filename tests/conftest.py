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
    # work around https://github.com/mongomock/mongomock/issues/912
    add_update = mongomock.collection.BulkOperationBuilder.add_update
    def _add_update(self, *args, sort=None, **kwargs):
        if sort is not None:
            raise NotImplementedError("sort not implemented in mongomock")
        return add_update(self, *args, **kwargs)
    monkeypatch.setattr("mongomock.collection.BulkOperationBuilder.add_update", _add_update)


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
