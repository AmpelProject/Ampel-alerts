from typing import Any, overload

from ampel.abstract.AbsConfigMorpher import AbsConfigMorpher
from ampel.log.AmpelLogger import AmpelLogger
from ampel.model.ingest.CompilerOptions import CompilerOptions
from ampel.model.ingest.FilterModel import FilterModel
from ampel.model.ingest.T2Compute import T2Compute
from ampel.model.UnitModel import UnitModel
from ampel.template.AbsEasyChannelTemplate import AbsEasyChannelTemplate
from ampel.types import ChannelId


class EasyAlertConsumerTemplate(AbsConfigMorpher):
    """Configure an AlertConsumer (or subclass) for a single channel"""

    #: Channel tag for any documents created
    channel: ChannelId
    #: Alert supplier unit
    supplier: str | UnitModel
    #: Optional override for alert loader
    loader: None | str | UnitModel
    #: Alert shaper
    shaper: str | UnitModel
    #: Document creation options
    compiler_opts: CompilerOptions
    #: Alert filter. None disables filtering
    filter: None | str | FilterModel
    #: Augment alerts with external content before ingestion
    muxer: None | str | UnitModel
    # Combine datapoints into states
    combiner: str | UnitModel

    #: T2 units to trigger when stock is updated. Dependencies of tied
    #: units will be added automatically.
    t2_compute: list[T2Compute] = []

    #: Unit to synthesize config for
    unit: str = "AlertConsumer"

    extra: dict = {}

    def morph(self, ampel_config: dict[str, Any], logger: AmpelLogger) -> dict[str, Any]:

        return UnitModel(
            unit=self.unit,
            config=self.extra
            | AbsEasyChannelTemplate.craft_t0_processor_config(
                channel=self.channel,
                alconf=ampel_config,
                t2_compute=self.t2_compute,
                supplier=self._get_supplier(),
                shaper=self._config_as_dict(self.shaper),
                combiner=self._config_as_dict(self.combiner),
                filter_dict=self._config_as_dict(self.filter),
                muxer=self._config_as_dict(self.muxer),
                compiler_opts=self.compiler_opts.dict(),
            ),
        ).dict(exclude_unset=True)

    @overload
    @staticmethod
    def _config_as_dict(arg: None) -> None:
        ...

    @overload
    @staticmethod
    def _config_as_dict(arg: str | UnitModel) -> dict[str, Any]:
        ...

    @staticmethod
    def _config_as_dict(arg: None | str | UnitModel) -> None | dict[str, Any]:
        if arg is None:
            return None
        return (arg if isinstance(arg, UnitModel) else UnitModel(unit=arg)).dict(exclude_unset=True)

    def _get_supplier(self) -> dict[str, Any]:

        unit_dict = self._config_as_dict(self.supplier)
        if self.loader:
            unit_dict["config"] = unit_dict.get("config", {}) | {
                "loader": self._config_as_dict(self.loader)
            }
        return unit_dict
