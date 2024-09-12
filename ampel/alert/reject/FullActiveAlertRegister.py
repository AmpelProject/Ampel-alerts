#!/usr/bin/env python
# -*- coding: utf-8 -*-
# File:                Ampel-alerts/ampel/alert/reject/FullActiveAlertRegister.py
# License:             BSD-3-Clause
# Author:              valery brinnel <firstname.lastname@gmail.com>
# Date:                14.05.2020
# Last Modified Date:  27.06.2022
# Last Modified By:    valery brinnel <firstname.lastname@gmail.com>

from collections.abc import Sequence
from struct import pack
from time import time
from typing import ClassVar

from ampel.alert.reject.FullAlertRegister import FullAlertRegister
from ampel.protocol.AmpelAlertProtocol import AmpelAlertProtocol


class FullActiveAlertRegister(FullAlertRegister):
	""" Logs: alert_id, stock_id, timestamp, filter_res """

	__slots__: ClassVar[tuple[str, ...]] = '_write', 'alert_max', 'alert_min', 'stock_max', 'stock_min' # type: ignore
	_slot_defaults = {
		'alert_max': 0, 'alert_min': 2**64,
		'stock_max': 0, 'stock_min': 2**64
	}

	header_hints: ClassVar[Sequence[str]] = ('alert', 'stock') # type: ignore
	alert_min: int
	alert_max: int
	stock_min: int
	stock_max: int


	def file(self, alert: AmpelAlertProtocol, filter_res: int = 0) -> None:

		alid = alert.id
		self.alert_max = max(alid, self.alert_max)
		self.alert_min = min(alid, self.alert_min)

		sid = alert.stock
		self.stock_max = max(sid, self.stock_max) # type: ignore[assignment]
		self.stock_min = min(sid, self.stock_min) # type: ignore[assignment]

		self._write(pack('<QQIB', alid, sid, int(time()), -filter_res))
