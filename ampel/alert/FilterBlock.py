#!/usr/bin/env python
# -*- coding: utf-8 -*-
# File:                Ampel-alerts/ampel/alert/FilterBlock.py
# License:             BSD-3-Clause
# Author:              valery brinnel <firstname.lastname@gmail.com>
# Date:                03.05.2018
# Last Modified Date:  27.06.2022
# Last Modified By:    valery brinnel <firstname.lastname@gmail.com>

from collections.abc import Callable
from logging import LogRecord
from typing import Any, cast

from ampel.abstract.AbsAlertFilter import AbsAlertFilter
from ampel.abstract.AbsAlertRegister import AbsAlertRegister
from ampel.alert.AlertConsumerMetrics import (
	stat_accepted,
	stat_autocomplete,
	stat_rejected,
	stat_time,
)
from ampel.core.AmpelContext import AmpelContext
from ampel.log.AmpelLogger import INFO, AmpelLogger
from ampel.log.handlers.ChanRecordBufHandler import ChanRecordBufHandler
from ampel.log.handlers.EnclosedChanRecordBufHandler import EnclosedChanRecordBufHandler
from ampel.log.LightLogRecord import LightLogRecord
from ampel.log.LogFlag import LogFlag
from ampel.model.ingest.FilterModel import FilterModel
from ampel.protocol.AmpelAlertProtocol import AmpelAlertProtocol
from ampel.protocol.LoggingHandlerProtocol import LoggingHandlerProtocol
from ampel.types import ChannelId, StockId


def no_filter(alert: Any) -> bool:
	return True

# ruff: noqa: PLE0237

class FilterBlock:
	"""
	Helper class for AlertConsumer.
	Among other things, it instantiates and references loggers and T0 filters.
	Note: T0 filter units get a dedicated logger which is associated with a
	RecordBufferingHandler instance because we route the produced logs either to the standard logger
	or to the "rejected logger/dumper" depending whether the alert is accepted or not.
	"""

	__slots__ = '__dict__', 'logger', 'channel', 'context', \
		'chan_str', 'min_log_msg', 'filter_func', 'ac', 'overrule', \
		'bypass', 'update_rej', 'rej_log_handler', 'rej_log_handle', \
		'file', 'log', 'forward', 'buffer', 'buf_hdlr', 'stock_ids'  # noqa: RUF023


	def __init__(self,
		index: int,
		context: AmpelContext,
		channel: ChannelId,
		filter_model: None | FilterModel,
		process_name: str,
		logger: AmpelLogger,
		check_new: bool = False,
		embed: bool = False
	) -> None:
		"""
		:param index: index of the parent AlertConsumerDirective used for creating this FilterBlock
		:param check_new: check whether a stock already exists in the stock collection
		(first tuple member of method filter (directive index) will be negative then)
		:param in_stock: whished behaviors when a stock with a given id (from the alert)
		already exists in the stock collection.
		:param process_name: associated T0 process name (as defined in the ampel conf)
		:param embed: use compact logging (channel embedded in messages).
		Produces fewer (and bigger) log documents.
		"""

		self._stock_col = context.db.get_collection('stock')
		self.filter_model = filter_model
		self.context = context
		self.idx = index

		# Channel name (ex: HU_SN or 1)
		self.channel = channel
		self.chan_str = str(self.channel)

		# stats
		self._stat_accepted = stat_accepted.labels(self.chan_str)
		self._stat_rejected = stat_rejected.labels(self.chan_str)
		self._stat_autocomplete = stat_autocomplete.labels(self.chan_str)
		self._stat_time = stat_time.labels(f"filter.{self.chan_str}")

		self.check_new = check_new
		self.rej = self.idx, False
		self.stock_ids: set[StockId] = set()

		if filter_model:

			# Minimal log entry in case filter does not log anything
			self.min_log_msg = {'c': self.channel} if embed else None

			# Instantiate/get filter class associated with this channel
			logger.info(f"Loading filter: {filter_model.unit}", extra={'c': self.channel})

			self.buf_hdlr: EnclosedChanRecordBufHandler | ChanRecordBufHandler = \
				EnclosedChanRecordBufHandler(logger.level, self.channel) if embed \
				else ChanRecordBufHandler(logger.level, self.channel)

			self.unit_instance = context.loader.new_logical_unit(
				model = filter_model,
				sub_type = AbsAlertFilter,
				logger = AmpelLogger.get_logger(
					name = "buf_" + self.chan_str,
					base_flag = (getattr(logger, 'base_flag', 0) & ~LogFlag.CORE) | LogFlag.UNIT,
					console = False,
					handlers = [self.buf_hdlr]
				)
			)

			# Log entries potentially logged by filter post_init method
			if self.buf_hdlr.buffer:
				self.buf_hdlr.forward(logger)
				self.buf_hdlr.buffer = []

			self.forward = self.buf_hdlr.forward # type: ignore
			self.buffer = self.buf_hdlr.buffer

			self.filter_func = self.unit_instance.process

			if osm := filter_model.on_stock_match:
				self.overrule = self.idx, osm in ['overrule', 'silent_overrule']
				self.bypass = self.idx, osm == 'bypass'
				self.update_rej = osm == 'overrule'
			else:
				self.overrule = self.idx, False
				self.bypass = self.idx, False
				self.update_rej = True

			self.rej_log_handle: None | Callable[[LightLogRecord | LogRecord], None] = None
			self.rej_log_handler: None | LoggingHandlerProtocol = None
			self.file: None | Callable[[AmpelAlertProtocol, int], None] = None
			self.register: None | AbsAlertRegister = None
		else:
			self.filter_func = no_filter
			self.bypass = self.idx, False
			self.overrule = self.idx, False


	def filter(self, alert: AmpelAlertProtocol) -> tuple[int, int | bool | None]:

		with self._stat_time.time():

			if self.bypass[1] and alert.stock in self.stock_ids: # type: ignore[operator]
				return self.bypass

			# Apply filter (returns None/False in case of rejection or True/int in case of match)
			res = self.filter_func(alert) or 0

			# Filter accepted alert
			if res > 0:

				self._stat_accepted.inc()

				# Write log entries to main logger
				# (note: log records already contain chan info)
				if self.buffer:
					self.forward(self.logger, stock=alert.stock, extra={'a': alert.id})

				# Log minimal entry if channel did not log anything
				else:
					extra = {'a': alert.id, 's': alert.stock}
					if self.min_log_msg: # embed is True
						self.log(INFO, self.min_log_msg if res is True \
							else {'c': self.channel, 'g': res}, extra=extra)
					else:
						extra['c'] = self.channel
						self.log(INFO, None, extra=extra)

				# stock_id 'exists' if filter bypass/overrule(s) or check_new is requested
				if self.stock_ids:
					if alert.stock in self.stock_ids:
						if self.check_new:
							return -self.idx, res
					else:
						self.stock_ids.add(alert.stock)

				return self.idx, res

			# Filter rejected alert
			self._stat_rejected.inc()

			# 'overrule' or 'silent_overrule' requested for this filter
			if self.overrule and alert.stock in self.stock_ids:

				extra_ac = {'a': alert.id, 'ac': True, 's': alert.stock, 'c': self.channel}

				# Main logger feedback
				self.log(INFO, None, extra=extra_ac)

				# Update count
				self._stat_autocomplete.inc()

				# Rejected alerts notifications can go to rejected log collection
				# even though it was "auto-completed" because it
				# was actually rejected by the filter/channel
				if self.update_rej:

					if self.buffer:
						if self.rej_log_handler:
							# Clears the buffer
							self.forward(self.rej_log_handler, stock=alert.stock, extra=extra_ac)
						else:
							self.buffer.clear()

					# Log minimal entry if channel did not log anything
					elif self.rej_log_handle:
						lrec = LightLogRecord(0, 0, None)
						lrec.stock = alert.stock
						lrec.extra = extra_ac
						self.rej_log_handle(lrec)

					if self.file:
						self.file(alert, res)

				# Use default t2 units (no group) as filter results
				return self.overrule

			if self.buffer:

				# Save possibly existing error to 'main' logs
				if self.buf_hdlr.has_error:
					self.forward(
						self.logger, stock=alert.stock, extra={'a': alert.id},
						clear=not self.rej_log_handler
					)

				if self.rej_log_handler:
					# Send rejected logs to dedicated separate logger/handler
					self.forward(self.rej_log_handler, stock=alert.stock, extra={'a': alert.id})

			if self.file:
				self.file(alert, res)

			# return rejection result
			return self.rej


	def ready(self, logger: AmpelLogger, run_id: int) -> None:
		"""
		Dependending on channel settings, this method might:
		- Builds set of transient ids for "auto complete"
		- open an alert register for rejected alerts.
		- instantiate a logging handler for rejected logs
		"""

		self.logger = logger
		self.log = logger.log

		if self.bypass[1] or self.overrule[1] or self.check_new:

			# Build set of transient ids for this channel
			self.stock_ids = {
				el['stock'] for el in self._stock_col.find(
					{'channel': self.channel}, {'stock': 1}
				)
			}

		if self.filter_model and self.filter_model.reject:

			if 'log' in self.filter_model.reject:

				# DBRejectedLogsHandler for example
				self.rej_log_handler = cast(
					LoggingHandlerProtocol,
					self.context.loader.new_context_unit(
						model = self.filter_model.reject['log'],
						context = self.context,
						channel = self.channel,
						logger = logger
					)
				)

				if not isinstance(self.rej_log_handler, LoggingHandlerProtocol):
					raise ValueError(
						f"Unit must comply with ampel.log.handler.LoggingHandlerProtocol. "
						f"Offending model:\n {self.filter_model.reject['log']}"
					)

				self.rej_log_handler.set_run_id(run_id) # type: ignore
				self.rej_log_handle = self.rej_log_handler.handle

			if 'register' in self.filter_model.reject:

				self.register = self.context.loader.new_context_unit(
					model = self.filter_model.reject['register'],
					context = self.context,
					sub_type = AbsAlertRegister,
					logger = logger,
					channel = self.channel,
					run_id = run_id
				)

				self.file = self.register.file


	def done(self) -> None:

		if self.filter_model and self.filter_model.reject:

			if self.rej_log_handler:
				self.rej_log_handler.flush()
				self.rej_log_handler = None

			if self.register:
				self.register.close()
				self.register = None
