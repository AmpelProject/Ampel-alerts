#!/usr/bin/env python
# -*- coding: utf-8 -*-
# File:                Ampel-alerts/ampel/alert/reject/GeneralActiveAlertRegister.py
# License:             BSD-3-Clause
# Author:              valery brinnel <firstname.lastname@gmail.com>
# Date:                26.05.2020
# Last Modified Date:  24.11.2021
# Last Modified By:    valery brinnel <firstname.lastname@gmail.com>

from collections.abc import Sequence
from struct import pack
from typing import ClassVar

from ampel.alert.reject.GeneralAlertRegister import GeneralAlertRegister
from ampel.protocol.AmpelAlertProtocol import AmpelAlertProtocol


class GeneralActiveAlertRegister(GeneralAlertRegister):
	""" Logs: alert_id, stock_id, filter_res """

	__slots__: ClassVar[tuple[str, ...]] = '_write', 'alert_max', 'alert_min', 'stock_max', 'stock_min' # type: ignore
	_slot_defaults = {'alert_max': 0, 'alert_min': 2**64, 'stock_max': 0, 'stock_min': 2**64}
	new_header_size: int | str = "+1000"

	header_bounds: ClassVar[Sequence[str]] = ('alert', 'stock') # type: ignore
	alert_min: int
	alert_max: int
	stock_min: int
	stock_max: int

	def file(self, alert: AmpelAlertProtocol, filter_res: None | int = None) -> None:

		alid = alert.id
		self.alert_max = max(alid, self.alert_max)
		self.alert_min = min(alid, self.alert_min)

		sid = alert.stock
		self.stock_max = max(sid, self.stock_max) # type: ignore[assignment]
		self.stock_min = min(sid, self.stock_min) # type: ignore[assignment]

		self._write(pack('<QQB', alid, sid, filter_res or 0))
