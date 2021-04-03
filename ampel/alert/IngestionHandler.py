#!/usr/bin/env python
# -*- coding: utf-8 -*-
# File              : Ampel-alerts/ampel/alert/IngestionHandler.py
# License           : BSD-3-Clause
# Author            : vb <vbrinnel@physik.hu-berlin.de>
# Date              : 01.05.2020
# Last Modified Date: 20.11.2020
# Last Modified By  : Jakob van Santen <jakob.van.santen@desy.de>

from time import time
from typing import Sequence, List, Dict, Union, Iterable, Tuple, Type, Optional
from ampel.type import ChannelId
from ampel.core.UnitLoader import PT
from ampel.core.AmpelContext import AmpelContext
from ampel.util.mappings import build_unsafe_dict_id
from ampel.mongo.update.DBUpdatesBuffer import DBUpdatesBuffer
from ampel.alert.AmpelAlert import AmpelAlert
from ampel.content.DataPoint import DataPoint
from ampel.abstract.ingest.AbsStockT2Ingester import AbsStockT2Ingester
from ampel.abstract.ingest.AbsCompoundIngester import AbsCompoundIngester
from ampel.abstract.ingest.AbsStateT2Ingester import AbsStateT2Ingester
from ampel.abstract.ingest.AbsAlertContentIngester import AbsAlertContentIngester
from ampel.abstract.ingest.AbsPointT2Ingester import AbsPointT2Ingester
from ampel.abstract.ingest.AbsStockIngester import AbsStockIngester
from ampel.log import AmpelLogger, VERBOSE
from ampel.log.utils import log_exception
from ampel.log.LogsBufferDict import LogsBufferDict
from ampel.log.LogFlag import LogFlag
from ampel.model.UnitModel import UnitModel
from ampel.model.ingest.T1CombineModel import T1CombineModel
from ampel.model.AlertProcessorDirective import AlertProcessorDirective
from ampel.alert.AlertProcessorMetrics import stat_time


class IngestionHandler:

	__slots__ = '__dict__', 'updates_buffer', 'stock_ingester', 'datapoint_ingester', \
		'stock_t2_ingesters', 'point_t2_ingesters', 'state_t2_ingesters', \
		't1_ingesters', 'retro_complete', 'ingest_stats', 'log', 'logd'

	#: Creates StockDocument
	stock_ingester: AbsStockIngester
	#: Creates DataPoints
	datapoint_ingester: Optional[AbsAlertContentIngester[AmpelAlert, DataPoint]]
	#: Creates T2Documents bound to stocks
	stock_t2_ingesters: List[AbsStockT2Ingester]
	#: Creates T2Documents bound to datapoints
	point_t2_ingesters: List[AbsPointT2Ingester]
	#: Creates T2Documents bound to compounds
	state_t2_ingesters: Dict[AbsCompoundIngester, List[AbsStateT2Ingester]]
	#: Creates compounds
	t1_ingesters: Dict[AbsCompoundIngester, List[AbsStateT2Ingester]]
	updates_buffer: DBUpdatesBuffer
	logd: LogsBufferDict
	retro_complete: List[ChannelId]
	ingest_stats: List[float]


	def __init__(self,
		context: AmpelContext,
		directives: Sequence[AlertProcessorDirective],
		updates_buffer: DBUpdatesBuffer,
		logger: AmpelLogger,
		run_id: int
	):

		self.updates_buffer = updates_buffer
		self.logger = logger
		self.log = logger.log

		# Collects logs accross the different ingesters, every ingester can
		# append values to extra without breaking log aggregation
		self.logd = {'logs': [], 'extra': {}}

		self.ingest_stats = []
		self.retro_complete = []
		self.state_t2_ingesters = {}
		self.t1_ingesters = {}
		self.point_t2_ingesters = []
		self.stock_t2_ingesters = []
		self.datapoint_ingester = None

		if not directives:
			raise ValueError("Need at least 1 directive")
		for directive in directives:
			self.setup_ingesters(
				context, directive, logger, updates_buffer=updates_buffer,
				logd=self.logd, run_id=run_id
			)

		if logger.verbose:
			logger.log(VERBOSE,
				f"Ingesters: datapoint: 1, stock: 1, "
				f"compound: {len(self.state_t2_ingesters)}, "
				f"t2_state: {sum(len(v) for v in self.state_t2_ingesters.values())}, "
				f"t2_point: {len(self.point_t2_ingesters)}, "
				f"t2_stock: {len(self.stock_t2_ingesters)}"
			)


	def setup_ingesters(self,
		context: AmpelContext, directive: AlertProcessorDirective,
		logger: AmpelLogger, **kwargs
	) -> None:
		"""
		:param kwargs:
		  are passed to method new_admin_unit from UnitLoader instance.
		  Typically these are ``updates_buffer``, ``logd``, ``run_id``.
		"""

		# An AP can for now only have a unique stock ingester
		if not hasattr(self, 'stock_ingester'):
			self.stock_ingester = context.loader.new_admin_unit(
				unit_model = directive.stock_update, # type: ignore[arg-type]
				context = context,
				sub_type = AbsStockIngester,
				**kwargs
			)

		if t0_add := directive.t0_add:

			# An AP can for now only have a unique datapoint ingester
			if not self.datapoint_ingester:
				self.datapoint_ingester = context.loader.new_admin_unit(
					unit_model = t0_add,
					context = context,
					sub_type = AbsAlertContentIngester,
					**kwargs
				)

			# States, and T2s based thereon
			for t1_combine in t0_add.t1_combine or []:
				self._setup_t1_combine(
					context,
					t1_combine,
					directive.channel,
					self.state_t2_ingesters,
					logger,
					**kwargs
				)

			# DataPoint T2s
			if point_t2 := t0_add.t2_compute:

				point_ingester = self._get_ingester(
					context, point_t2, AbsPointT2Ingester,
					self.point_t2_ingesters, directive.channel, logger, **kwargs
				)

				if point_ingester not in self.point_t2_ingesters:
					self.point_t2_ingesters.append(point_ingester)

				# Update point ingester internal config
				point_ingester.add_ingest_models(directive.channel, point_t2.units)

		# Standalone T1 processes
		for t1_combine in directive.t1_combine or []:
			self._setup_t1_combine(
				context,
				t1_combine,
				directive.channel,
				self.t1_ingesters,
				logger,
				**kwargs
			)

		# Stock T2s
		if directive.t2_compute:

			stock_t2_ingester = self._get_ingester(
				context, directive.t2_compute, AbsStockT2Ingester,
				self.stock_t2_ingesters, directive.channel, logger, **kwargs
			)

			if stock_t2_ingester not in self.stock_t2_ingesters:
				self.stock_t2_ingesters.append(stock_t2_ingester)

			stock_t2_ingester.add_ingest_models(
				directive.channel, directive.t2_compute.units
			)


	def _setup_t1_combine(self,
		context: AmpelContext, t1_combine: T1CombineModel, channel: ChannelId,
		store: Dict[AbsCompoundIngester, List[AbsStateT2Ingester]],
		logger: AmpelLogger, **kwargs
	) -> None:
		"""
		Add the ingesters specified in ``t1_combine`` to ``store``, reusing
		existing instances if possible.
		
		:param t1_combine: subclause of ingestion directive
		:param channel: channel of parent directive
		:param store: cache of existing ingesters
		"""
		# Build compound ingester id
		comp_ingester = self._get_ingester(
			context, t1_combine, AbsCompoundIngester,
			store, channel, logger, **kwargs
		)
		if comp_ingester not in store:
			store[comp_ingester] = []

		# Notify compound ingester that the current channel
		# requires the creation of states/compounds
		comp_ingester.add_channel(channel)

		# State T2s (should be defined along with t1 ingesters usually)
		if state_t2 := t1_combine.t2_compute:

			# Retrieve list of associated t2 ingesters (we allow
			# the definition of multiple different t2 ingesters)
			t2_ingesters = store[comp_ingester] # type: ignore

			t2_ingester = self._get_ingester(
				context, state_t2, AbsStateT2Ingester,
				t2_ingesters, channel, logger, **kwargs
			)

			if t2_ingester not in t2_ingesters:
				t2_ingesters.append(t2_ingester)

			# Update state ingester internal config
			t2_ingester.add_ingest_models(channel, state_t2.units)


	def _get_ingester(self,
		context: AmpelContext, model: UnitModel, sub_type: Type[PT],
		it: Iterable, channel: ChannelId, logger: AmpelLogger, **kwargs
	) -> PT:
		"""
		Method used internally to instantiate ingesters.
		If a request for instantiation is made with the same / a similar*
		config than a previous request (contained in the parameter it),
		then the previous ingester instance is returned.
		*: build_unsafe_dict_id sorts lists by default, see its docstring for details

		:raises: ValueError if new ingester instance cannot be created
		"""

		# Identifies ingesters using hashed unit id and config
		md = build_unsafe_dict_id({"unit": model.unit_name, "config": model.config}, int)

		if ingester := next((el for el in it if el.hash == md), None):

			if logger.verbose > 1:
				logger.debug(
					f"[{channel}] Updating ingester with model {model} (hash={md})"
				)
			elif logger.verbose:
				logger.log(VERBOSE,
					f"[{channel}] Updating ingester with id ..{str(md)[-6:]}"
				)

			return ingester

		if logger.verbose > 1:
			logger.debug(
				f"[{channel}] Creating new ingester with model {model} (hash={md})"
			)
		elif logger.verbose:
			logger.log(VERBOSE,
				f"[{channel}] Creating new {model.unit_name} with id ..{str(md)[-6:]}"
			)

		kwargs['hash'] = md

		# Spawn new instance
		ingester = context.loader.new_admin_unit(
			unit_model = model,
			context = context,
			sub_type = sub_type,
			**kwargs
		)

		if ingester is None:
			raise ValueError()

		return ingester

	# prettier in Python 3.9
	stat_time = stat_time.labels("ingest").time()
	@stat_time
	def ingest(self,
		alert: AmpelAlert,
		filter_results: List[Tuple[ChannelId, Union[bool, int]]]
	) -> None:
		"""
		Create database documents in response to ``alert``.

		:param alert: the alert under consideration
		:param filter_results: the value returned from
		  :func:`~ampel.abstract.AbsAlertFilter.AbsAlertFilter.apply` for each
		  channel's filter
		"""

		self.updates_buffer._block_autopush = True
		stock_id = alert.stock_id
		ingester_start = time()
		self.logd['extra'] = {'a': alert.id}

		# T0 ingestion
		if self.datapoint_ingester:
			datapoints = self.datapoint_ingester.ingest(alert) # type: ignore[union-attr]

		# Stock T2 ingestions
		if self.stock_t2_ingesters:
			for stock_t2_ingester in self.stock_t2_ingesters:
				stock_t2_ingester.ingest(stock_id, filter_results)

		# Point T2 ingestions
		if self.point_t2_ingesters:
			for point_ingester in self.point_t2_ingesters:
				point_ingester.ingest(stock_id, datapoints, filter_results)

		# Alert T1 and associated T2 ingestions
		for comp_ingester, t2_ingesters in self.state_t2_ingesters.items():
			if (comp_blueprint := comp_ingester.ingest(stock_id, datapoints, filter_results)):
				for state_ingester in t2_ingesters:
					state_ingester.ingest(stock_id, comp_blueprint, filter_results)

		# Standalone T1 and associated T2 ingestions
		for comp_ingester, t2_ingesters in self.t1_ingesters.items():
			if (comp_blueprint := comp_ingester.ingest(stock_id, datapoints, filter_results)):
				for state_ingester in t2_ingesters:
					state_ingester.ingest(stock_id, comp_blueprint, filter_results)

		self.stock_ingester.ingest(stock_id, filter_results, {'alert': alert.id})


		if self.retro_complete:

			try:

				# Part 1: Recreate previous alerts
				##################################

				# Build prev_det_sequences.
				# If datapoints looked like this:
				# [{'_id': 12}, {'_id': -11}, {'_id': 10}, {'_id': -8}, {'_id': -7}, {'_id': 6}, {'_id': -4}]
				# prev_det_sequences would be: [
				# 	[{"_id": 10}, {"_id": -8}, {"_id": -7}, {"_id": 6}, {"_id": -4}],
				# 	[{"_id": 6}, {"_id": -4}]
				# ]

				prev_det_sequences: List[Sequence[DataPoint]] = []
				el = datapoints
				while el := alert._prev_det_seq(el): # type: ignore[assignment]
					prev_det_sequences.append(el)

				if prev_det_sequences:

					# Reduce filter_results to the channels requesting 'retro/accept' auto-complete
					filter_results = [el for el in filter_results if el[0] in self.retro_complete]

					# Part 2: Ingest simulated alerts
					#################################

					# For every reconstructed previous alerts contents
					for prev_datapoints in prev_det_sequences:

						# Point T2 ingestions
						if self.point_t2_ingesters:
							for point_ingester in self.point_t2_ingesters:
								point_ingester.ingest(stock_id, prev_datapoints, filter_results)

						# T1 and associated T2 ingestions
						for comp_ingester, t2_ingesters in self.state_t2_ingesters.items():
							comp_blueprint = comp_ingester.ingest(stock_id, prev_datapoints, filter_results)
							if comp_blueprint:
								for state_ingester in t2_ingesters:
									state_ingester.ingest(stock_id, comp_blueprint, filter_results)

						# Update transient journal
						self.stock_ingester.ingest(
							stock_id, filter_results, {'ac': True, 'alert': [alert.id, len(prev_datapoints)]}
						)

			except Exception as e:
				log_exception(self.logger, e)

			finally:
				self.retro_complete.clear()

		# Log ingester messages
		logd = self.logd
		chans = [el[0] for el in filter_results] if len(filter_results) > 1 else filter_results[0][0]

		if logd['logs']:

			if 'err' in logd:
				del logd['err']
				flag = LogFlag.ERROR
			else:
				flag = LogFlag.INFO

			log = self.log
			extra = {
				"channel": chans,
				"stock": stock_id,
				**(logd.get("extra") or {})
			}
			for l in logd['logs']:
				log(flag, l, extra=extra)

			logd['logs'] = []
		else:
			self.log(
				LogFlag.INFO,
				None,
				extra={
					"channel": chans,
					"stock": stock_id,
					**(logd.get("extra") or {})
				}
			)

		self.ingest_stats.append(time() - ingester_start)
		self.updates_buffer._block_autopush = False
