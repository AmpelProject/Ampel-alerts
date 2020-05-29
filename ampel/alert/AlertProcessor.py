#!/usr/bin/env python
# -*- coding: utf-8 -*-
# File              : Ampel-alerts/ampel/alert/AlertProcessor.py
# License           : BSD-3-Clause
# Author            : vb <vbrinnel@physik.hu-berlin.de>
# Date              : 10.10.2017
# Last Modified Date: 29.05.2020
# Last Modified By  : vb <vbrinnel@physik.hu-berlin.de>

import json, signal
import numpy as np
from time import time
from io import IOBase
from logging import LogRecord, INFO
from pymongo.errors import PyMongoError
from typing import Sequence, List, Dict, Union, Any, Iterable, Tuple, Callable, Optional, Generic

from ampel.type import ChannelId
from ampel.core.AmpelContext import AmpelContext
from ampel.core.UnitLoader import UnitLoader
from ampel.util.mappings import merge_dict
from ampel.util.Freeze import Freeze
from ampel.metrics.GraphiteFeeder import GraphiteFeeder
from ampel.db.DBUpdatesBuffer import DBUpdatesBuffer
from ampel.alert.FilterBlocksHandler import FilterBlocksHandler
from ampel.alert.IngestionHandler import IngestionHandler

from ampel.abstract.AbsRunnable import AbsRunnable
from ampel.abstract.AbsAlertSupplier import AbsAlertSupplier, T

from ampel.log.AmpelLogger import AmpelLogger
from ampel.log.LogRecordFlag import LogRecordFlag
from ampel.log.LogUtils import LogUtils
from ampel.log.DBEventDoc import DBEventDoc
from ampel.log.handlers.DBLoggingHandler import DBLoggingHandler
from ampel.log.AmpelLoggingError import AmpelLoggingError

from ampel.model.PlainUnitModel import PlainUnitModel
from ampel.model.AlertProcessingModel import AlertProcessingModel

CONNECTIVITY = 1
INTERRUPTED = 2
TOO_MANY_ERRORS = 3


class AlertProcessor(Generic[T], AbsRunnable):
	"""
	Class handling the processing of alerts (T0 level).
	For each alert, following tasks are performed:
	* Load the alert
	* Filter alert based on the configured T0 filter
	* Ingest alert based on the configured ingester

	:param publish_stats: publish performance metrics:
	- graphite: send t0 metrics to graphite (graphite server must be defined in ampel_config)
	- mongo: include t0 metrics in the process event document which is written into the DB
	:param iter_max: main loop (in method run()) will stop processing alerts when this limit is reached
	:param error_max: main loop (in method run()) will stop processing alerts when this limit is reached
	:param directives: mandatory alert processor directives (AlertProcessingModel). This parameter will
	determine how the underlying FilterBlocksHandler and IngestionHandler instances are set up.
	:param db_log_format: see `ampel.alert.FilterBlocksHandler.FilterBlocksHandler` docstring
	:param log_profile: log profile key as defined in the ampel conf (ex: 'standard', 'quiet', 'silent')
	:param supplier: alert supplier, no time explain more currently
	:param run_type: LogRecordFlag.SCHEDULED_RUN or LogRecordFlag.MANUAL_RUN
	:param db_logging_handler_kwargs: optional kwargs to be passed to the DBLoggingHandler constructor.
	:param raise_exc: whether the AP should raise Exceptions rather than catching them (default False)
	:param verbose: 1 -> verbose mode, 2 -> debug mode

	Potential update: maybe allow an alternative way of initialization for this class
	through direct input of (possibly customized, that is the point) FilterBlocksHandler and
	IngestionHandler instances rather than through (deserialized) directives.
	"""

	# General options
	iter_max: int = 50000
	error_max: int = 20
	directives: Sequence[AlertProcessingModel]
	publish_stats: Sequence[str] = 'graphite', 'mongo'
	log_profile: str = "default"
	db_log_format: str = "standard"
	single_rej_col: bool = False
	supplier: Optional[Union[AbsAlertSupplier, PlainUnitModel, str]]
	db_logging_handler_kwargs: Dict[str, Any] = {}

	# Run time options
	raise_exc: bool = False
	run_type: LogRecordFlag = LogRecordFlag.SCHEDULED_RUN


	@classmethod
	def from_process(cls, context: AmpelContext, process_name: str, override: Optional[Dict] = None):
		"""
		Convenience method instantiating an AP using the config entry from a given T0 process
		example: AlertProcessor.from_process(
			context, process_name="VAL_TEST2/T0/ztf_uw_public", override={'publish_stats': []}
		)
		"""
		args = context.get_config().get( # type: ignore
			f"process.{process_name}.processor.config", dict
		)

		if args is None:
			raise ValueError(f"process.{process_name}.processor.config is None")

		if override:
			args = Freeze.recursive_unfreeze(args) # type: ignore
			merge_dict(args, override)

		return cls(context=context, **args)


	def __init__(self, **kwargs) -> None:
		"""
		:raises: ValueError if no process can be loaded or if a process is
		associated with an unknown channel
		"""

		if isinstance(kwargs['directives'], dict):
			kwargs['directives'] = (kwargs['directives'], )

		super().__init__(**kwargs)

		self._ampel_db = self.context.get_database()
		self.log_flag: int = (LogRecordFlag.T0 | LogRecordFlag.CORE | self.run_type).__int__()
		logger = self.context.get_unique_logger(level = self.log_flag)

		if self.supplier:
			if isinstance(self.supplier, AbsAlertSupplier):
				self.alert_supplier: AbsAlertSupplier[T] = self.supplier
			else:
				if isinstance(self.supplier, str):
					self.supplier = PlainUnitModel(unit=self.supplier)
				self.alert_supplier = UnitLoader.new_aux_unit(
					model = self.supplier, sub_type = AbsAlertSupplier
				)
		else:
			self.alert_supplier = None # type: ignore[assignment]

		if self.verbose:
			logger.verbose("AlertProcessor setup")

		# Load filter blocks
		self._fbh = FilterBlocksHandler(
			self.context, logger, self.directives,
			self.db_log_format, self.run_type
		)

		if self.verbose:

			gather_t2_units = lambda node: [el.unit for el in node.t2_compute.units] \
				if node.t2_compute else []

			for model in self.directives:

				t2_units = []

				if model.t0_add.t1_combine:
					for el in model.t0_add.t1_combine:
						if el.t2_compute:
							t2_units += gather_t2_units(el)

				if model.t0_add.t2_compute:
					t2_units += gather_t2_units(model.t0_add)

				if model.t1_combine:
					for el in model.t1_combine:
						t2_units += gather_t2_units(el)

				if model.t2_compute:
					t2_units += gather_t2_units(model)

				logger.verbose(f"{model.channel} combined on match t2 units: {t2_units}")

		# Graphite
		if "graphite" in self.publish_stats:
			self._gfeeder = GraphiteFeeder(
				self.context.get_config().get('resource.graphite.default'), # type: ignore
				autoreconnect = True
			)

		signal.signal(signal.SIGTERM, self.sig_exit)
		signal.signal(signal.SIGINT, self.sig_exit)

		logger.info("AlertProcessor setup completed")


	def sig_exit(self, signum: int, frame) -> None:
		""" Executed when SIGTERM/SIGINT is caught. Stops alert processing in run() """
		self._cancel_run = INTERRUPTED


	def set_supplier(self, alert_supplier: AbsAlertSupplier[T]) -> None:
		"""
		Allows to set a custom alert supplier.
		AlertSupplier instances provide AmpelAlert instances
		and need to be sourced by an alert loader instance
		"""
		self.alert_supplier = alert_supplier


	def set_loader(self, alert_loader: Iterable) -> None:
		"""
		Source the current alert suplier with the provided alert loader.
		AlertLoader instances typically provide file-like objects
		:raises ValueError: if self.alert_supplier is None
		"""
		if not self.alert_supplier:
			raise ValueError("Please set alert supplier first")
		self.alert_supplier.set_alert_source(alert_loader)


	def process_alerts(self, alert_loader: Iterable[IOBase]) -> None:
		"""
		shortcut method to process all alerts from a given loader until its dries out
		:param alert_loader: iterable returning alert payloads
		:raises ValueError: if self.alert_supplier is None
		"""
		if not self.alert_supplier:
			raise ValueError("Please set alert supplier first")
		self.alert_supplier.set_alert_source(alert_loader)
		processed_alerts = self.iter_max
		while processed_alerts == self.iter_max:
			processed_alerts = self.run()

		#self.logger.info("Alert loader dried out")


	def run(self) -> int:
		"""
		Run alert processing using the internal alert_loader/alert_supplier
		:raises: LogFlushingError, PyMongoError
		"""

		# An AlertSupplier deserializes file-like objects provided by the AlertLoader
		# and returns an AmpelAlert/PhotoAlert
		if not self.alert_supplier or not self.alert_supplier.ready():
			raise ValueError("Alert supplier not set or not sourced")

		# Save current time to later evaluate processing time
		run_start = time()

		logger = self.context.get_unique_logger(level=self.log_flag, profile=self.log_profile)
		if self.verbose:
			logger.verbose("Pre-run setup")

		# Setup logging
		###############

		# DBLoggingHandler formats, saves and pushes log records into the DB
		db_logging_handler = DBLoggingHandler(
			self._ampel_db, auto_flush = False, **self.db_logging_handler_kwargs
		)

		run_id = db_logging_handler.get_run_id()

		# Add db logging handler to the logger stack of handlers
		logger.handlers.append(db_logging_handler)

		# Add new doc in the 'events' collection
		event_doc = DBEventDoc(self._ampel_db, event_name="ap", tier=0)
		event_doc.add_run_id(run_id)

		# Collects and executes pymongo.operations
		updates_buffer = DBUpdatesBuffer(
			self._ampel_db, run_id, logger,
			error_callback = self.set_cancel_run,
			catch_signals = False # we do it ourself
		)

		# Setup stats
		#############

		# Duration statistics
		dur_stats: Dict[str, Any] = {
			'preIngestTime': [],
			'dbBulkTimeStock': [],
			'dbBulkTimeT0': [],
			'dbBulkTimeT1': [],
			'dbBulkTimeT2': [],
			'dbPerOpMeanTimeStock': [],
			'dbPerOpMeanTimeT0': [],
			'dbPerOpMeanTimeT1': [],
			'dbPerOpMeanTimeT2': [],
			'allFilters': np.empty(self.iter_max),
			'filters': {}
		}

		# Count statistics (incrementing integer values)
		count_stats: Dict[str, Any] = {
			'alerts': 0, 'matches': {'any': 0}, 'auto_complete': {'any': 0}
		}

		dur_stats['allFilters'].fill(np.nan)
		for fb in self._fbh.filter_blocks:
			# dur_stats['filters'][fb.channel] records filter performances
			# nan will remain only if exception occur for particular alerts
			dur_stats['filters'][fb.channel] = np.empty(self.iter_max)
			dur_stats['filters'][fb.channel].fill(np.nan)
			count_stats['matches'][fb.channel] = 0
			count_stats['auto_complete'][fb.channel] = 0


		# Setup ingesters
		ing_hdlr = IngestionHandler(
			self.context, self.directives, updates_buffer,
			logger, run_id, verbose = self.verbose
		)

		# Loop variables
		iter_max = self.iter_max
		iter_count = 0
		any_match = 0
		auto_complete = 0
		err = 0
		reduced_chan_names = self._fbh.chan_names[0] if len(self._fbh.chan_names) == 1 else self._fbh.chan_names
		fblocks = self._fbh.filter_blocks
		filter_stats = dur_stats['filters']
		all_filters_stats = dur_stats['allFilters']
		filter_results: List[Tuple[ChannelId, Union[bool, int]]] = []

		# Builds set of stock ids for autocomplete, if needed
		self._fbh.ready(logger, run_id, ing_hdlr)

		# Save pre run time
		pre_run = time()
		self._cancel_run = 0


		# Process alerts
		################

		logger.shout(f"Processing alerts (run: {run_id})")
		#logger.level -= LogRecordFlag.CORE

		with updates_buffer.run_in_thread():

			# Iterate over alerts
			for alert in self.alert_supplier:

				if self._cancel_run:

					print("")
					if self._cancel_run == INTERRUPTED:
						logger.info("Interrupting run() procedure")
						print("Interrupting run() procedure")
					else: # updates_buffer requested to stop processing
						print("Abording run() procedure")

					# Flush loggers (possible Exceptions handled by method)
					self._conclude_logging(logger, iter_count, db_logging_handler)

					return iter_count

				# Associate upcoming log entries with the current transient id
				stock_id = alert.stock_id

				# stats
				all_filters_start = time()

				extra: Dict[str, Any] = {'alert': alert.id}
				filter_results = []

				# Loop through filter blocks
				for fblock in fblocks:

					try:

						# stats
						per_filter_start = time()

						# Apply filter (returns None/False in case of rejection or True/int in case of match)
						if res := fblock.filter(alert):
							filter_results.append(res)

						# stats
						filter_stats[fblock.channel][iter_count] = time() - per_filter_start

					# Unrecoverable (logging related) errors
					except (PyMongoError, AmpelLoggingError) as e:
						print("%s: abording run() procedure" % e.__class__.__name__)
						self._report_ap_error(e, logger, run_id, extra=extra)
						raise e

					# Possibly tolerable errors (could be an error from a contributed filter)
					except Exception as e:

						fblock.forward(db_logging_handler, stock=stock_id, extra=extra)
						self._report_ap_error(
							e, logger, run_id, extra={**extra, 'section': 'filter', 'channel': fblock.channel}
						)

						if self.raise_exc:
							raise e
						else:
							if self.error_max:
								err += 1
							if err == self.error_max:
								logger.error("Max number of error reached, breaking alert processing")
								self.set_cancel_run(TOO_MANY_ERRORS)

				# time required for all filters
				all_filters_stats[iter_count] = time() - all_filters_start

				if filter_results:

					# stats
					any_match += 1

					try:
						ing_hdlr.ingest(alert, filter_results)
					except (PyMongoError, AmpelLoggingError) as e:

						print("%s: abording run() procedure" % e.__class__.__name__)
						self._report_ap_error(e, logger, run_id, extra=extra)
						raise e

					except Exception as e:

						self._report_ap_error(
							e, logger, run_id, filter_results,
							extra={**extra, 'section': 'ingest', 'alert': alert.dict()}
						)

						if self.raise_exc:
							raise e
						else:
							if self.error_max:
								err += 1
							if err == self.error_max:
								logger.error("Max number of error reached, breaking alert processing")
								self.set_cancel_run(TOO_MANY_ERRORS)

				else:

					# All channels reject this alert
					# no log entries goes into the main logs collection sinces those are redirected to Ampel_rej.

					# So we add a notification manually. For that, we don't use logger
					# cause rejection messages were alreary logged into the console
					# by the StreamHandler in channel specific RecordBufferingHandler instances.
					# So we address directly db_logging_handler, and for that, we create
					# a LogRecord manually.
					lr = LogRecord(None, INFO, None, None, None, None, None) # type: ignore
					lr.extra = { # type: ignore
						'stock': stock_id,
						'alert': alert.id,
						'allout': True,
						'channel': reduced_chan_names
					}
					db_logging_handler.handle(lr)

				iter_count += 1

				if iter_count == iter_max:
					logger.info("Reached max number of iterations")
					break

				updates_buffer.check_push()
				db_logging_handler.check_flush()

		# Save post run time
		post_run = time()

		# Post run section
		try:

			# TODO: move into dedicated class
			if self.publish_stats is not None and iter_count > 0:

				# include loop counts
				count_stats['alerts'] = iter_count
				count_stats['matches']['any'] = any_match
				if alert_stats := self.alert_supplier.get_stats():
					count_stats.update(alert_stats)
				if t0_stats := ing_hdlr.datapoint_ingester.get_stats():
					count_stats.update(t0_stats)
				count_stats['dbop'] = updates_buffer.stats
				count_stats['auto_complete']['any'] = auto_complete

				# Compute mean time & std dev in microseconds
				#############################################

				logger.info("Computing job stats")

				dur_stats['preIngestTime'] = self._compute_stat(
					dur_stats['preIngestTime']
				)

				# For ingest metrics
				for time_metric in ('dbBulkTime', 'dbPerOpMeanTime'):
					for col in ("Stock", "T0", "T1", "T2"):
						key = time_metric + col
						if updates_buffer.metrics[key]:
							dur_stats[key] = self._compute_stat(
								updates_buffer.metrics[key]
							)

				# per chan filter metrics
				for key in self._fbh.chan_names:
					dur_stats['filters'][key] = self._compute_stat(
						dur_stats['filters'][key], mean=np.nanmean, std=np.nanstd
					)

				# all filters metric
				dur_stats['allFilters'] = self._compute_stat(
					dur_stats['allFilters'], mean=np.nanmean, std=np.nanstd
				)

				# Durations in seconds
				dur_stats['apPreLoop'] = int(pre_run - run_start)
				dur_stats['apMain'] = int(post_run - pre_run)
				dur_stats['apPostLoop'] = int(time() - post_run)

				# Make sure all dict *keys* are str (and not int)
				# otherwise, graphite/mongod will complain
				dur_stats = json.loads(json.dumps(dur_stats))
				count_stats = json.loads(json.dumps(count_stats))

				# Publish metrics to graphite
				if "graphite" in self.publish_stats:
					logger.info("Sending stats to Graphite")
					self._gfeeder.add_stats_with_mean_std(
						{
							"count": count_stats,
							"duration": dur_stats
						},
						prefix="t0"
					)
					self._gfeeder.send()

				# Publish metrics into document in collection 'events'
				if "mongo" in self.publish_stats:
					event_doc.set_event_info(
						{
							'metrics': {
								"count": count_stats,
								"duration": dur_stats
							}
						}
					)

			logger.shout(
				f"Processing completed (time required: {int(time() - run_start)}s)"
			)

			# Flush loggers
			self._conclude_logging(logger, iter_count, db_logging_handler)

			event_doc.publish()

		except Exception as e:

			# Try to insert doc into trouble collection (raises no exception)
			# Possible exception will be logged out to console in any case
			LogUtils.report_exception(
				self._ampel_db, logger, tier=0, exc=e,
				run_id=db_logging_handler.get_run_id()
			)

		# Return number of processed alerts
		return iter_count


	def set_cancel_run(self, reason: int = CONNECTIVITY) -> None:
		"""
		Cancels current processing of alerts (when DB becomes unresponsive for example).
		"""
		self._cancel_run = CONNECTIVITY


	def _conclude_logging(self,
		logger: AmpelLogger, iter_count: int, db_logging_handler: DBLoggingHandler
	) -> None:
		""" :raises: None """

		try:

			# Flush loggers
			if iter_count > 0:

				# Main logs logger. This can raise exceptions
				db_logging_handler.flush()

			else:
				db_logging_handler.purge()

			# If needed: close ampel registers, flush rejected logs
			self._fbh.done()

			# Remove DB logging handler
			logger.removeHandler(db_logging_handler)

		except Exception as e:

			# Try to insert doc into trouble collection (raises no exception)
			# Possible exception will be logged out to console in any case
			LogUtils.report_exception(
				self._ampel_db, logger, tier=0, exc=e,
				run_id=db_logging_handler.get_run_id()
			)


	def _report_ap_error(self,
		arg_e: Exception, logger: AmpelLogger, run_id: Union[int, List[int]],
		filter_results: Optional[List[Tuple[Union[int, str], Union[bool, int]]]] = None,
		extra: Optional[Dict[str, Any]] = None
	) -> None:
		"""
		:param extra: optional extra key/value fields to add to 'trouble' doc
		"""

		info = {}

		if extra:
			for k in extra.keys():
				info[k] = extra[k]

		if filter_results:
			info['channel'] = [el[0] for el in filter_results]

		# Try to insert doc into trouble collection (raises no exception)
		# Possible exception will be logged out to console in any case
		LogUtils.report_exception(
			self._ampel_db, logger, tier=0,
			exc=arg_e, run_id=run_id, info=info
		)


	@staticmethod
	def _compute_stat(
		seq, mean: Callable[[Sequence], float] = np.mean,
		std: Callable[[Sequence], float] = np.std
	) -> Tuple[int, int]:
		"""
		Returns mean time & std dev in microseconds
		"""
		if np.all(np.isnan(seq)):
			return (0, 0)

		# mean time & std dev in microseconds
		return (
			int(round(mean(seq) * 1000000)),
			int(round(std(seq) * 1000000))
		)