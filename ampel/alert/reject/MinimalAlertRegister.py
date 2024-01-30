#!/usr/bin/env python
# -*- coding: utf-8 -*-
# File:                Ampel-alerts/ampel/alert/reject/MinimalAlertRegister.py
# License:             BSD-3-Clause
# Author:              valery brinnel <firstname.lastname@gmail.com>
# Date:                12.05.2020
# Last Modified Date:  27.06.2022
# Last Modified By:    valery brinnel <firstname.lastname@gmail.com>

from collections.abc import Generator
from struct import pack
from typing import BinaryIO, ClassVar, Literal

from ampel.alert.reject.BaseAlertRegister import BaseAlertRegister
from ampel.protocol.AmpelAlertProtocol import AmpelAlertProtocol
from ampel.util.register import reg_iter


class MinimalAlertRegister(BaseAlertRegister):
	"""
	Logs: alert_id, filter_res. No time stamp.

	Notes:
	- method "iter" yields tuple[<alert id>, <filter return code>]
	"""

	__slots__: ClassVar[tuple[str, ...]] = '_write', # type: ignore
	struct: Literal['<QB'] = '<QB'
	header_log_accesses: bool = False


	def file(self, alert: AmpelAlertProtocol, filter_res: int = 0) -> None:
		self._write(pack('<QB', alert.id, -filter_res))


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
			return [(el[0], -el[1]) for el in ret]
		return None


	@classmethod
	def find_stock(cls) -> None: # type: ignore[override]
		raise NotImplementedError("Minimal registers do not save stock information")
