#!/usr/bin/env python
# -*- coding: utf-8 -*-
# File:                Ampel-alerts/ampel/alert/reject/GeneralAlertRegister.py
# License:             BSD-3-Clause
# Author:              valery brinnel <firstname.lastname@gmail.com>
# Date:                26.05.2020
# Last Modified Date:  26.05.2020
# Last Modified By:    valery brinnel <firstname.lastname@gmail.com>

from struct import pack
from typing import BinaryIO, ClassVar, Literal

from ampel.alert.reject.BaseAlertRegister import BaseAlertRegister
from ampel.protocol.AmpelAlertProtocol import AmpelAlertProtocol


class GeneralAlertRegister(BaseAlertRegister):
	""" Logs: alert_id, stock_id, filter_res """

	__slots__: ClassVar[tuple[str, ...]] = '_write', # type: ignore
	struct: Literal['<QQB'] = '<QQB'


	def file(self, alert: AmpelAlertProtocol, filter_res: None | int = None) -> None:
		self._write(pack('<QQB', alert.id, alert.stock, filter_res or 0))


	@classmethod
	def find_stock(cls, # type: ignore[override]
		f: BinaryIO | str, stock_id: int | list[int], **kwargs
	) -> None | list[tuple[int, ...]]:
		return super().find_stock(f, stock_id=stock_id, stock_offset=8, **kwargs)
