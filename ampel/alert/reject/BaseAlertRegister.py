#!/usr/bin/env python
# -*- coding: utf-8 -*-
# File:                Ampel-alerts/ampel/alert/reject/BaseAlertRegister.py
# License:             BSD-3-Clause
# Author:              valery brinnel <firstname.lastname@gmail.com>
# Date:                16.05.2020
# Last Modified Date:  31.08.2020
# Last Modified By:    valery brinnel <firstname.lastname@gmail.com>

from collections.abc import Generator, Sequence
from typing import Any, BinaryIO, ClassVar, Literal

from ampel.abstract.AbsAlertRegister import AbsAlertRegister
from ampel.log import VERBOSE
from ampel.types import ChannelId
from ampel.util.register import find, reg_iter


class BaseAlertRegister(AbsAlertRegister, abstract=True):
	"""

	There are two possible setups:

	1) Name register files according to ``run_id``::
	     
	     <path>/<channel>/121.register.gz
	     <path>/<channel>/122.register.gz
	     <path>/<channel>/123.register.gz
	     ...

	   The register header is updated before each file is closed to save min and max alert IDs
	   and min and max stock ids. That way, a potential query for a given alert rejection could
	   go through all register files, parse only the header and check if min_alert < target_alert < max_alert,
	   and will by that not have to go through the file if the condition is not fulfilled.

	   Pro:
	     - Avoids any potential concurency issue (this setup should be used for re-runs)
	     - Fast query
	   Con:
	     - Can generate numerous files (which should not be a problem for any modern file system)

	2) Name register files according to ``channel_id``::
	     
	     <path>/AMPEL_CHANNEL1.register.gz
	     <path>/AMPEL_CHANNEL2.register.gz
	     ...

	   Register could be capped based on file size (file_cap='blocks') or number of run_ids (file_cap='runs').

	   Pro:
	     - Fewer files
	   Con:
	     - beware: re-run should not use this scheme, as concurent updates to a register are not supported!
	"""

	__slots__: ClassVar[tuple[str, ...]] = '_write', # type: ignore
	_write: Any

	#: channel to record results for
	channel: ChannelId
	#: current run number
	run_id: int

	#: save files in <path_channel_folder>/<channel>/<file>
	path_channel_folder: bool = True
	#: save file as <run_id|channel|string>.bin.gz
	file_prefix: str | Literal['$run_id', '$channel'] = '$channel'

	#: additionaly to the parent's class (AmpelRegister) ability to rename the current register when
	#: the number of blocks reaches a given threshold, this class can also rename the current file when
	#: the number of registered run ids in the header reaches a limit.
	#: Both parameters (runs and blocks) can be used together, the first criteria fulfilled will trigger a file rename.
	#:
	#: .. note::
	#:
	#:   File rename occurs during the opening of registers, which means that once a register is opened,
	#:   no check is performed (a register can thus grow beyond the defined limits as long as a process keeps it open).
	#: .. note::
	#:
	#:   The current file suffix number is encoded in the header. If the current suffix number is 10 and
	#:   you move files to another folder, the next rename will create ampel_register.bin.gz.11 nonetheless.
	file_cap: None | dict[Literal['runs', 'blocks'], int] # type: ignore[assignment]

	header_bounds: ClassVar[None | Sequence[str]] = None


	def __init__(self, **kwargs):

		super().__init__(autoload=False, **kwargs)

		if self.path_base is None:
			self.path_base = self.context.config.get(
				"resource.folder.rejected_alerts", str, raise_exc=True
			)

		if not self.header_extra_base:
			self.header_extra_base = {}

		self.header_extra_base['channel'] = self.channel
		self.header_extra_base['run'] = self.run_id

		if self.file_prefix == "$run_id":
			self.file_prefix = str(self.run_id)
		elif self.file_prefix == "$channel":
			self.file_prefix = self.channel

		if self.path_channel_folder:
			if self.path_extra:
				self.path_extra.append(self.channel)
			else:
				self.path_extra = [self.channel]

		self.load()
		self._write = self._inner_fh.write

		if self.header_bounds:
			hdr = self.header['payload']
			for el in self.header_bounds:
				for m in ('min', 'max'):
					if el in hdr and m in hdr[el]:
						object.__setattr__(self, f'{el}_{m}', hdr[el][m])


	def check_rename(self, header: dict[str, Any]) -> bool:

		if not self.file_cap:
			return False

		if (
			'runs' in self.file_cap and # type: ignore[operator]
			isinstance(header['run'], list) and
			len(header['run']) > self.file_cap['runs']
		):
			return True

		return super().check_rename(header)


	def onload_update_header(self) -> None:
		""" hook called by parent class """

		# Update run header field if applicable
		hdr = self.header['payload']

		if isinstance(hdr['run'], int) and self.run_id != hdr['run']:
			hdr['run'] = [hdr['run'], self.run_id]
		elif isinstance(hdr['run'], list) and self.run_id not in hdr['run']:
			hdr['run'].append(self.run_id)
		else:
			return

		if self.verbose:
			self.logger.log(VERBOSE, f"Header updated with run_id {self.run_id}")


	def close(self, **kwargs) -> None: # type: ignore[override]
		"""
		Automatically adds aggregated "header bounds" into the header before super close() call
		"""

		if self.header_bounds and hasattr(self, 'header'):
			hdr = self.header['payload']
			for el in self.header_bounds:
				if getattr(self, el + '_max') == 0:
					continue
				if el not in self.header['payload']:
					hdr[el] = {}
				hdr[el]['max'] = getattr(self, el + '_max')
				hdr[el]['min'] = getattr(self, el + '_min')

		super().close(**kwargs)


	@classmethod
	def iter(cls,
		f: BinaryIO | str, multiplier: int = 100000, verbose: bool = True
	) -> Generator[tuple[int, ...], None, None]:
		return reg_iter(f, multiplier, verbose)


	@classmethod
	def find_alert(cls,
		f: BinaryIO | str, alert_id: int | list[int], alert_id_bytes_len: int = 8, **kwargs
	) -> None | list[tuple[int, ...]]:
		"""
		:param f: file path (str) or file handle (which will not be closed)
		:param kwargs: see method `ampel.util.register.find` docstring.
		
		Example::
		  
		  In []: register.find_alert('/Users/hu/Documents/ZTF/test/aa/aa.bin.gz', alert_id=1242886)
		  Out[]: [(1242886, 16)]
		"""
		return find(
			f, match_int=alert_id, int_bytes_len=alert_id_bytes_len,
			offset=0, header_hint='alert', **kwargs
		)


	@classmethod
	def find_stock(cls,
		f: BinaryIO | str, stock_id: int | list[int],
		stock_offset: int, stock_bytes_len: int = 8, **kwargs
	) -> None | list[tuple[int, ...]]:
		"""
		:param f: file path (str) or file handle (which will not be closed)
		:param stock_offset:
		  position of the stock values within each block. For example, if the
		  blocks are made of '<QQB' and stock is the second Q, then stock_offset
		  should be set to 8.
		:returns: list of rejection info of the alerts matching the provided stock id
		"""
		return find(
			f, match_int=stock_id, int_bytes_len=stock_bytes_len,
			offset=stock_offset, header_hint='stock', **kwargs
		)
