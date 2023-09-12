from typing import Any, TYPE_CHECKING
from ampel.model.ChannelModel import ChannelModel
import pytest, yaml
import contextlib

from ampel.log.AmpelLogger import AmpelLogger
from ampel.template.AbsEasyChannelTemplate import AbsEasyChannelTemplate

if TYPE_CHECKING:   
    from ampel.config.builder.FirstPassConfig import FirstPassConfig

class LegacyChannelTemplate(AbsEasyChannelTemplate):

    # Mandatory implementation
    def get_processes(
        self, logger: "AmpelLogger", first_pass_config: "FirstPassConfig"
    ) -> list[dict[str, Any]]:

        ret: list[dict[str, Any]] = []

        ret.insert(
            0,
            self.craft_t0_process(
                first_pass_config,
                controller={},
                supplier={},
                shaper={},
                combiner={},
                muxer={},
            ),
        )

        return ret


@pytest.mark.parametrize(
    "t2_compute,target,expected,exception",
    [
        # single, statebound T2
        (
            [{"unit": "DummyStateT2Unit"}],
            ["ingest", "combine", 0, "state_t2"],
            {"unit": "DummyStateT2Unit"},
            None
        ),
        # statebound T2 with configured statebound dependency, not requested
        (
            [
                {
                    "unit": "DummyTiedStateT2Unit",
                    "config": {"t2_dependency": [{"unit": "DummyStateT2Unit"}]},
                },
            ],
            ["ingest", "combine", 0, "state_t2"],
            {"unit": "DummyStateT2Unit"},
            ValueError,
        ),
        # statebound T2 with implicit (default) statebound dependency
        pytest.param(
            [{"unit": "DummyTiedStateT2Unit"}],
            ["ingest", "combine", 0, "state_t2"],
            {"unit": "DummyStateT2Unit"},
            None,
            marks=pytest.mark.xfail(reason="default dependencies aren't automatically resolved")
        ),
        # statebound T2 with statebound dependency, also explicitly configured
        (
            [
                {"unit": "DummyStateT2Unit"},
                {
                    "unit": "DummyTiedStateT2Unit",
                    "config": {"t2_dependency": [{"unit": "DummyStateT2Unit"}]},
                },
            ],
            ["ingest", "combine", 0, "state_t2"],
            {"unit": "DummyStateT2Unit"},
            None
        ),
        # statebound T2 with point dependency
        (
            [
                {
                    "unit": "DummyTiedStateT2Unit",
                    "config": {"t2_dependency": [{"unit": "DummyPointT2Unit"}]},
                },
                {"unit": "DummyPointT2Unit"}
            ],
            ["ingest", "combine", 0, "point_t2"],
            {"unit": "DummyPointT2Unit"},
            None,
        ),
        # statebound T2 with stock dependency
        (
            [
                {
                    "unit": "DummyTiedStateT2Unit",
                    "config": {"t2_dependency": [{"unit": "DummyStockT2Unit"}]},
                },
                {"unit": "DummyStockT2Unit"}
            ],
            ["ingest", "stock_t2"],
            {"unit": "DummyStockT2Unit"},
            None,
        ),
    ],
)
def test_state_t2_instantiation(t2_compute, target, expected, exception, dev_context, dummy_units):
    """
    Template creates state T2s and checks for missing dependencies
    """
    # _craft_t0_process should raise ValueError if dependencies are missing
    with (
        pytest.raises(exception)
        if exception
        else contextlib.nullcontext()
    ):
        processes = LegacyChannelTemplate(
            **{
                "channel": "foo",
                "retro_complete": False,
                "version": 0,
                "t0_filter": {"unit": "DummyFilter"},
                "t2_compute": t2_compute,
            }
        ).get_processes(None, dev_context.config.get())
    if exception:
        return

    assert processes
    proc = processes[0]
    assert proc["tier"] == 0
    assert (directives := proc["processor"]["config"]["directives"])
    directive = directives[0]

    def get(item, keys):
        while keys:
            item = item[keys.pop(0)]
        return item

    items = get(directive, list(target))
    assert expected in items
    assert (
        len([i for i in items if expected == i]) == 1
    ), "exactly one instance of each unit"


@pytest.mark.parametrize("key", ["t2_compute", "t3_supervise"])
def test_single_element_to_sequence(key):
    kwargs = {"channel": "foo", "version": 0, "t0_filter": {"unit": "Nonesuch"}}
    single = LegacyChannelTemplate(**(kwargs | {key: {"unit": "Nonesuch"}}))
    sequence = LegacyChannelTemplate(**(kwargs | {key: [{"unit": "Nonesuch"}]}))
    assert getattr(single, key) == getattr(sequence, key)

def test_get_channel():
    template = LegacyChannelTemplate(
        channel = "FOO",
        version = 0,
        t0_filter = {"unit": "NoFilter"},
    )
    channel = template.get_channel(logger=AmpelLogger.get_logger())
    assert ChannelModel(**channel).dict() == channel
