import time
from collections import defaultdict
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple, Union, Any, TYPE_CHECKING

from pymongo import InsertOne, UpdateOne

from ampel.abstract.AbsStateT2Unit import AbsStateT2Unit
from ampel.abstract.AbsStockT2Unit import AbsStockT2Unit
from ampel.abstract.ingest.AbsAlertContentIngester import AbsAlertContentIngester
from ampel.abstract.ingest.AbsCompoundIngester import AbsCompoundIngester
from ampel.abstract.ingest.AbsStateT2Compiler import AbsStateT2Compiler
from ampel.abstract.ingest.AbsStateT2Ingester import AbsStateT2Ingester
from ampel.abstract.ingest.AbsT2Ingester import AbsT2Ingester
from ampel.alert.AmpelAlert import AmpelAlert
from ampel.content.T1Document import T1Document
from ampel.content.DataPoint import DataPoint
from ampel.content.StockDocument import StockDocument
from ampel.content.T2Document import T2Document
from ampel.compile.CompoundBluePrint import CompoundBluePrint
from ampel.compile.T1DefaultCombiner import T1DefaultCombiner
from ampel.log.AmpelLogger import AmpelLogger
from ampel.enum.T2DocumentCode import T2DocumentCode
from ampel.type import ChannelId, StockId, T2UnitResult

if TYPE_CHECKING:
    from ampel.content.PhotoT1Document import PhotoT1Document

class DummyAlertContentIngester(AbsAlertContentIngester[AmpelAlert, DataPoint]):
    alert_history_length = 1

    def ingest(self, alert: AmpelAlert) -> List[DataPoint]:
        dps = [
            DataPoint({"_id": i, "body": dp, "stock": alert.stock_id})
            for i, dp in enumerate(alert.dps)
        ]
        for dp in dps:
            self.updates_buffer.add_t0_update(InsertOne(dp))
        return dps


class DummyCompoundIngester(AbsCompoundIngester):
    """simplified PhotoCompoundIngester for testing"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.channels: Set[ChannelId] = set()
        self.engine = T1DefaultCombiner(logger=AmpelLogger.get_logger(console=False))

    def add_channel(self, channel: ChannelId) -> None:
        self.channels.add(channel)

    def ingest(
        self,
        stock_id: StockId,
        datapoints: Sequence[DataPoint],
        chan_selection: List[Tuple[ChannelId, Union[bool, int]]],
    ) -> Optional[CompoundBluePrint]:
        chans = [k for k, v in chan_selection if k in self.channels]

        if not (blue_print := self.engine.combine(stock_id, datapoints, chans)):
            return None

        for eff_comp_id in blue_print.get_effids_for_chans(chans):

            d_addtoset = {
                "channel": {
                    "$each": list(blue_print.get_chans_with_effid(eff_comp_id))
                },
                "run": self.run_id,
            }

            if blue_print.has_flavors(eff_comp_id):
                d_addtoset["flavor"] = {
                    "$each": blue_print.get_compound_flavors(eff_comp_id)
                }

            comp_dict = blue_print.get_eff_compound(eff_comp_id)

            comp_set_on_ins: PhotoT1Document = {
                "_id": eff_comp_id,
                "stock": stock_id,
                "tag": list(blue_print.get_comp_tags(eff_comp_id)),
                "tier": 0,
                "added": time.time(),
                "len": len(comp_dict),
                "body": comp_dict,
            }

            self.updates_buffer.add_t1_update(
                UpdateOne(
                    {"_id": eff_comp_id},
                    {"$setOnInsert": comp_set_on_ins, "$addToSet": d_addtoset},
                    upsert=True,
                )
            )

        return blue_print


class DummyExtendedCompoundIngester(AbsCompoundIngester):
    """
    Extended compound ingester creates compounds for datapoints that were not
    in the triggering alert.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.channels: Set[ChannelId] = set()
        self.engine = DummyCompoundIngester(
            context=self.context,
            updates_buffer=self.updates_buffer,
            logd=self.logd,
            run_id=self.run_id,
        )

    def add_channel(self, channel: ChannelId) -> None:
        self.channels.add(channel)
        self.engine.add_channel(channel)

    def ingest(
        self,
        stock_id: StockId,
        datapoints: Sequence[DataPoint],
        chan_selection: List[Tuple[ChannelId, Union[bool, int]]],
    ) -> Optional[CompoundBluePrint]:
        if not (chans := [(k, v) for k, v in chan_selection if k in self.channels]):
            return None

        # Find some new datapoints lying around, and insert them
        dps = [
            DataPoint({"_id": -(dp["_id"] + 1), "body": {}, "stock": stock_id})
            for i, dp in enumerate(datapoints)
        ]
        for dp in dps:
            self.updates_buffer.add_t0_update(InsertOne(dp))

        extended_datapoints = sorted(dps + list(datapoints), key=lambda dp: dp["_id"])

        return self.engine.ingest(stock_id, extended_datapoints, chans)


class DummyStateT2Compiler(AbsStateT2Compiler):
    def compile(
        self,
        chan_selection: List[Tuple[ChannelId, Union[bool, int]]],
        compound_blueprint: CompoundBluePrint,
    ) -> Dict[
        Tuple[str, Optional[int], Union[bytes, Tuple[bytes, ...]]], Set[ChannelId]
    ]:
        t2s_for_channels = defaultdict(set)
        for chan, ingest_model in self.get_ingest_models(chan_selection):
            t2s_for_channels[(ingest_model.unit_id, ingest_model.config)].add(chan)

        optimized_t2s: Dict[
            Tuple[str, Optional[int], Union[bytes, Tuple[bytes, ...]]], Set[ChannelId]
        ] = {}
        for k, v in t2s_for_channels.items():
            comp_ids = tuple(compound_blueprint.get_effids_for_chans(v))
            if len(comp_ids) == 1:
                optimized_t2s[k + (comp_ids[0],)] = v
            else:
                optimized_t2s[k + (comp_ids,)] = v
        return optimized_t2s


class DummyStateT2Ingester(AbsStateT2Ingester):
    compiler: AbsStateT2Compiler[CompoundBluePrint] = DummyStateT2Compiler()

    def ingest(
        self,
        stock_id: StockId,
        comp_bp: CompoundBluePrint,
        chan_selection: List[Tuple[ChannelId, Union[bool, int]]],
    ) -> None:
        """
        Simplified version of PhotoT2Ingester, with t2 docs linked to exactly
        one compound
        """
        optimized_t2s = self.compiler.compile(chan_selection, comp_bp)
        now = int(time.time())

        # Loop over t2 units to be created
        for (t2_id, run_config, link_id), chans in optimized_t2s.items():

            # Matching search criteria
            match_dict: Dict[str, Any] = {
                "stock": stock_id,
                "unit": t2_id,
                "config": run_config
                # 'link' is added below
            }

            # Attributes set if no previous doc exists
            set_on_insert: T2Document = {
                "stock": stock_id,
                "unit": t2_id,
                "config": run_config,
                "code": T2DocumentCode.NEW.value,
            }

            if self.tags:
                set_on_insert['tag'] = self.tags

            jchan, chan_add_to_set = AbsT2Ingester.build_query_parts(chans)
            add_to_set: Dict[str, Any] = {"channel": chan_add_to_set}

            assert isinstance(link_id, bytes)

            match_dict["link"] = {"$elemMatch": {"$eq": link_id}}
            add_to_set["link"] = link_id

            # Update journal
            add_to_set["journal"] = {"tier": self.tier, "dt": now, "channel": jchan}

            # Append update operation to bulk list
            self.updates_buffer.add_t2_update(
                UpdateOne(
                    match_dict,
                    {"$setOnInsert": set_on_insert, "$addToSet": add_to_set},
                    upsert=True,
                )
            )


class DummyStateT2Unit(AbsStateT2Unit):
    def run(self, compound: T1Document, datapoints: Iterable[DataPoint]) -> T2UnitResult:
        return {"size": len(compound["body"])}


class DummyStockT2Unit(AbsStockT2Unit):
    def run(self, stock_doc: StockDocument) -> T2UnitResult:
        return {"name": stock_doc["name"]}
