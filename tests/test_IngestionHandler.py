import pytest

from ampel.alert.AmpelAlert import AmpelAlert
from ampel.alert.IngestionHandler import IngestionHandler
from ampel.mongo.update.DBUpdatesBuffer import DBUpdatesBuffer
from ampel.mongo.update.StockIngester import StockIngester
from ampel.log.AmpelLogger import AmpelLogger, DEBUG
from ampel.log.LogsBufferDict import LogsBufferDict
from ampel.model.AlertProcessorDirective import AlertProcessorDirective

from .dummy_units import DummyAlertContentIngester


def get_handler(context, directives):
    run_id = 0
    logger = AmpelLogger.get_logger(console={"level": DEBUG})
    updates_buffer = DBUpdatesBuffer(context.db, run_id=run_id, logger=logger)
    logd = LogsBufferDict({"logs": [], "extra": {}})
    return IngestionHandler(
        context=context,
        logger=logger,
        run_id=0,
        updates_buffer=updates_buffer,
        directives=directives,
    )


def test_no_directive(dev_context):
    with pytest.raises(ValueError):
        get_handler(dev_context, [])


def test_minimal_directive(dev_context):
    directive = {
        "channel": "TEST_CHANNEL",
        "stock_update": {"unit": StockIngester},
    }
    handler = get_handler(dev_context, [AlertProcessorDirective(**directive)])
    assert isinstance(handler.stock_ingester, StockIngester)
    handler.logd["logs"].append(f"doing a good thing")
    handler.ingest(
        AmpelAlert(id="alert", stock_id="stockystock", dps=[]), [("TEST_CHANNEL", True)]
    )
    handler.logd["logs"].append(f"doing a bad thing")
    handler.logd["err"] = True
    handler.ingest(
        AmpelAlert(id="alert", stock_id="stockystock", dps=[]), [("TEST_CHANNEL", True)]
    )
    handler.updates_buffer.push_updates()
    stock = dev_context.db.get_collection("stock")
    assert stock.count_documents({}) == 1
    assert stock.count_documents({"_id": "stockystock"}) == 1


def test_legacy_directive(dev_context, legacy_directive):
    handler = get_handler(dev_context, [legacy_directive])
    assert isinstance(handler.stock_ingester, StockIngester)
    assert isinstance(handler.datapoint_ingester, DummyAlertContentIngester)

    # enable retro-complete, for more compounds
    handler.retro_complete = ["TEST_CHANNEL"]
    handler.ingest(
        AmpelAlert(id="alert", stock_id="stockystock", dps=[{}, {}]),
        [("TEST_CHANNEL", True)],
    )
    handler.updates_buffer.push_updates()
    t0 = dev_context.db.get_collection("t0")
    assert t0.count_documents({}) == 2
    assert t0.count_documents({"stock": "stockystock"}) == 2
    assert t0.count_documents({"_id": 0}) == 1

    t1 = dev_context.db.get_collection("t1")
    assert t1.count_documents({}) == 2

    t2 = dev_context.db.get_collection("t2")
    assert len(docs := list(t2.find({}))) == 2 + 3
    print(docs)
    assert docs[0]["stock"] == "stockystock"
    assert docs[0]["unit"] == "DummyStockT2Unit"
    assert docs[0]["link"] == "stockystock"
    assert docs[0]["col"] == "stock"
    for i in range(1, 3):
        assert docs[i]["stock"] == "stockystock"
        assert docs[i]["unit"] == "DemoPointT2Unit"
        assert isinstance(docs[i]["link"], int)
    for i in range(3, 5):
        assert docs[i]["stock"] == "stockystock"
        assert docs[i]["unit"] == "DummyStateT2Unit"
        assert len(docs[i]["link"]) == 1


def test_standalone_t1_directive(dev_context, standalone_t1_directive):
    """
    Extended history is created if a channel requests it
    """
    handler = get_handler(dev_context, [standalone_t1_directive])

    handler.ingest(
        AmpelAlert(id="alert", stock_id="stockystock", dps=[{}]),
        [("TEST_CHANNEL", True)],
    )

    handler.updates_buffer.push_updates()
    t0 = dev_context.db.get_collection("t0")
    assert t0.count_documents({}) == 2
    assert t0.count_documents({"stock": "stockystock"}) == 2
    assert t0.count_documents({"_id": 0}) == 1
    assert t0.count_documents({"_id": -1}) == 1

    t1 = dev_context.db.get_collection("t1")
    assert (
        t1.count_documents({}) == 2
    ), "two compounds created (for one inserted dp, one from archive)"

    t2 = dev_context.db.get_collection("t2")
    assert (
        t2.count_documents({}) == 2
    ), "two t2 docs created (for one inserted dp, one from archive)"


def test_standalone_t1_channel_dispatch(dev_context, standalone_t1_directive):
    """
    Extended history compounds are created only for channels that request it
    """
    long_channel = {**standalone_t1_directive.dict(), **{"channel": "LONG_CHANNEL"}}
    short_channel = {**standalone_t1_directive.dict(), **{"channel": "SHORT_CHANNEL"}}
    del short_channel["t1_combine"]

    handler = get_handler(
        dev_context,
        [
            AlertProcessorDirective(**directive)
            for directive in (long_channel, short_channel)
        ],
    )

    handler.ingest(
        AmpelAlert(id="alert", stock_id=1, dps=[{}]),
        [("LONG_CHANNEL", True), ("SHORT_CHANNEL", True)],
    )

    handler.updates_buffer.push_updates()
    t0 = dev_context.db.get_collection("t0")
    assert t0.count_documents({}) == 2
    assert t0.count_documents({"stock": 1}) == 2
    assert t0.count_documents({"_id": 0}) == 1

    t1 = dev_context.db.get_collection("t1")
    assert t1.count_documents({}) == 2
    assert t1.count_documents({"channel": "SHORT_CHANNEL"}) == 1

    t2 = dev_context.db.get_collection("t2")
    assert t2.count_documents({}) == 2
    assert t2.count_documents({"channel": "SHORT_CHANNEL"}) == 1


def test_standalone_t1_elision(dev_context, standalone_t1_directive):
    """
    Extended history points are skipped when only short channels pass
    """
    long_channel = {**standalone_t1_directive.dict(), **{"channel": "LONG_CHANNEL"}}
    short_channel = {**standalone_t1_directive.dict(), **{"channel": "SHORT_CHANNEL"}}
    del short_channel["t1_combine"]

    handler = get_handler(
        dev_context,
        [
            AlertProcessorDirective(**directive)
            for directive in (long_channel, short_channel)
        ],
    )

    handler.ingest(
        AmpelAlert(id="alert", stock_id=1, dps=[{}]), [("SHORT_CHANNEL", True)],
    )

    handler.updates_buffer.push_updates()
    t0 = dev_context.db.get_collection("t0")
    assert t0.count_documents({}) == 1
    assert t0.count_documents({"stock": 1}) == 1
    assert t0.count_documents({"_id": 0}) == 1

    t1 = dev_context.db.get_collection("t1")
    assert t1.count_documents({}) == 1

    t2 = dev_context.db.get_collection("t2")
    assert t2.count_documents({}) == 1
