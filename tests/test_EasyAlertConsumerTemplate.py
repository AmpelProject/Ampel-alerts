from contextlib import contextmanager
from pathlib import Path
import sys
from typing import TYPE_CHECKING

import pytest

from ampel.dev.DevAmpelContext import DevAmpelContext
from ampel.log.AmpelLogger import AmpelLogger
from ampel.template.EasyAlertConsumerTemplate import EasyAlertConsumerTemplate
from ampel.alert.AmpelAlert import AmpelAlert

from ampel.cli.main import main

if TYPE_CHECKING:
    from ampel.config.builder.FirstPassConfig import FirstPassConfig





@pytest.mark.parametrize(["muxer"], [(None,), ("DummyMuxer",)])
def test_instantiation(
    first_pass_config, dev_context: DevAmpelContext, muxer, dummy_units
):

    tpl = EasyAlertConsumerTemplate(
        **{
            "channel": "TEST_CHANNEL",
            "supplier": {
                "unit": "UnitTestAlertSupplier",
                "config": {
                    "alerts": [
                        AmpelAlert(
                            id=0,
                            stock="stockystock",
                            datapoints=[{"id": 0, "body": {"thing": 1}}],
                        )
                    ]
                },
            },
            "shaper": "NoShaper",
            "compiler_opts": {},
            "combiner": "T1SimpleCombiner",
            "filter": "DummyFilter",
            "muxer": muxer,
            "t2_compute": [
                {"unit": "DummyStockT2Unit"},
                {"unit": "DummyPointT2Unit"},
                {"unit": "DummyStateT2Unit"},
                {
                    "unit": "DummyTiedStateT2Unit",
                    "config": {"t2_dependency": [{"unit": "DummyStockT2Unit"}]},
                },
            ],
        }
    )

    model = tpl.get_model(first_pass_config, AmpelLogger.get_logger())

    consumer = dev_context.new_context_unit(
        model.unit, process_name="foo", **model.config
    )
    assert consumer.run() == 1

    # extra points inserted by muxer
    extra = 5 if muxer else 0
    for tier, count in [(0, 1 + extra), (1, 1), (2, 4 + extra)]:
        assert (
            dev_context.db.get_collection(f"t{tier}").estimated_document_count()
            == count
        )


@contextmanager
def argv_context(args: list[str]):
    argv = sys.argv
    try:
        sys.argv = args
        yield
    finally:
        sys.argv = argv


def run(args: list[str]) -> None | int | str:
    try:
        with argv_context(args):
            main()
        return None
    except SystemExit as se:
        return se.code


def test_job_file(
    testing_config,
    dev_context: DevAmpelContext, dummy_units
):
    assert (
        run(
            [
                "ampel",
                "job",
                "--config",
                str(testing_config),
                "--schema",
                str(Path(__file__).parent / "template_job.yaml"),
            ]
        ) is None
    )
