#!/usr/bin/env python
# -*- coding: utf-8 -*-
# File:                Ampel-alerts/ampel/alert/FilteringAlertSupplier.py
# License:             BSD-3-Clause
# Author:              valery brinnel <firstname.lastname@gmail.com>
# Date:                28.05.2020
# Last Modified Date:  24.11.2021
# Last Modified By:    valery brinnel <firstname.lastname@gmail.com>

from collections.abc import Iterator

from ampel.abstract.AbsAlertSupplier import AbsAlertSupplier
from ampel.base.AuxUnitRegister import AuxUnitRegister
from ampel.log.AmpelLogger import AmpelLogger
from ampel.model.UnitModel import UnitModel
from ampel.protocol.AmpelAlertProtocol import AmpelAlertProtocol


class FilteringAlertSupplier(AbsAlertSupplier):
	"""
	See AbsAlertSupplier docstring.
	example:
	UnitLoader.new_aux_unit(
		UnitModel(
			unit="FilteringAlertSupplier",
			config={
				"supplier": {"unit": "ZiAlertSupplier"},
				"match_ids": [770239962715015024]
			}
		)
	)
	"""

	supplier: UnitModel
	match_ids: list[int]


	def __init__(self, **kwargs) -> None:
		super().__init__(**kwargs)
		self.underlying_alert_supplier: AbsAlertSupplier = AuxUnitRegister.new_unit(
			model = self.supplier, sub_type = AbsAlertSupplier
		)

	def __iter__(self) -> Iterator[AmpelAlertProtocol]:
		"""
		:returns: a dict with a structure that AlertConsumer understands
		:raises StopIteration: when alert_loader dries out.
		:raises AttributeError: if alert_loader was not set properly before this method is called
		"""
		for el in self.underlying_alert_supplier:
			if el.id in self.match_ids:
				yield el

	def set_logger(self, logger: AmpelLogger) -> None:
		self.logger = logger
		self.underlying_alert_supplier.set_logger(logger)
