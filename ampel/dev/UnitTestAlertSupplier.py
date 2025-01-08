#!/usr/bin/env python
# -*- coding: utf-8 -*-
# File:                Ampel-alerts/ampel/dev/UnitTestAlertSupplier.py
# License:             BSD-3-Clause
# Author:              valery brinnel <firstname.lastname@gmail.com>
# Date:                28.05.2020
# Last Modified Date:  24.11.2021
# Last Modified By:    valery brinnel <firstname.lastname@gmail.com>

from ampel.abstract.AbsAlertSupplier import AbsAlertSupplier
from ampel.alert.AmpelAlert import AmpelAlert


class UnitTestAlertSupplier(AbsAlertSupplier):
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
	alerts: list[AmpelAlert]

	def __init__(self, **kwargs) -> None:
		super().__init__(**kwargs)
		self.it = iter(self.alerts)

	def __next__(self):
		return next(self.it)

	# Mandatory implementation
	def __iter__(self):
		return self.it
