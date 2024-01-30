#!/usr/bin/env python
# -*- coding: utf-8 -*-
# File:                Ampel-alerts/ampel/alert/reject/FullAlertRegister.py
# License:             BSD-3-Clause
# Author:              valery brinnel <firstname.lastname@gmail.com>
# Date:                14.05.2020
# Last Modified Date:  26.05.2020
# Last Modified By:    valery brinnel <firstname.lastname@gmail.com>

from collections.abc import Generator
from struct import pack
from time import time
from typing import BinaryIO, ClassVar, Literal

from ampel.alert.reject.BaseAlertRegister import BaseAlertRegister
from ampel.protocol.AmpelAlertProtocol import AmpelAlertProtocol
from ampel.util.register import reg_iter


class FullAlertRegister(BaseAlertRegister):
	"""
	Record: alert_id, stock_id, timestamp, filter_res
	"""

	__slots__: ClassVar[tuple[str, ...]] = '_write', # type: ignore
	struct: Literal['<QQIB'] = '<QQIB' # type: ignore[assignment]


	def file(self, alert: AmpelAlertProtocol, filter_res: int = 0) -> None:
		self._write(pack('<QQIB', alert.id, alert.stock, int(time()), -filter_res))


	@classmethod
	def iter(cls,
		f: BinaryIO | str,
		multiplier: int = 100000,
		verbose: bool = True,
		native: bool = False,
	) -> Generator[tuple[int, ...], None, None]:
		"""
		:param native: will not yield negative fitler results
		as these are saved as unsigned int but should work slightly faster
		"""
		if native:
			return reg_iter(f, multiplier, verbose) # type: ignore[return-value]

		for el in reg_iter(f, multiplier, verbose):
			yield el[0], el[1], el[2], -el[3]


	@classmethod
	def find_alert(cls, # type: ignore[override]
		f: BinaryIO | str, alert_id: int | list[int], **kwargs
	) -> None | list[tuple[int, ...]]:
		if ret := super().find_alert(f, alert_id=alert_id, **kwargs):
			return [(el[0], el[1], el[2], -el[3]) for el in ret]
		return None


	@classmethod
	def find_stock(cls, # type: ignore[override]
		f: BinaryIO | str, stock_id: int | list[int], **kwargs
	) -> None | list[tuple[int, ...]]:
		if ret := super().find_stock(f, stock_id=stock_id, offset_in_block=8, **kwargs):
			return [(el[0], el[1], el[2], -el[3]) for el in ret]
		return None
