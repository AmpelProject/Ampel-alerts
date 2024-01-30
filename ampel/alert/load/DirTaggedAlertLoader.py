#!/usr/bin/env python
# -*- coding: utf-8 -*-
# File:                Ampel-alerts/ampel/alert/load/DirTaggedAlertLoader.py
# License:             BSD-3-Clause
# Author:              valery brinnel <firstname.lastname@gmail.com>
# Date:                30.09.2021
# Last Modified Date:  04.10.2021
# Last Modified By:    valery brinnel <firstname.lastname@gmail.com>

from io import BytesIO, StringIO
from os.path import basename

from ampel.alert.load.DirAlertLoader import DirAlertLoader


class DirTaggedAlertLoader(DirAlertLoader):
	"""
	Load alerts from a (flat) directory.
	Tags potentially embedded in file names will returned  by __next__.

	For example:
	file ZTFabcdef.91T.TNS.BTS.json:
	  __next__() will return (dict,  [91T.TNS.BTS])
	file ZTFabcdef.json:
	  __next__() will return (dict,  None)

	Make sure to use a compatible alert supplier!
	"""

	def __next__(self) -> tuple[StringIO | BytesIO, None | list[str | int]]: # type: ignore[override]

		if not self._files:
			self.build_file_list()
			self._iter_files = iter(self._files)

		if (fpath := next(self._iter_files, None)) is None:
			raise StopIteration

		if self.logger.verbose > 1:
			self.logger.debug("Loading " + fpath)

		# basename("/usr/local/auth.AAA.BBB.py").split(".")[1:-1] -> ['AAA', 'BBB']
		base = basename(fpath).split(".")
		with open(fpath, self._open_mode) as alert_file:
			return (
				BytesIO(alert_file.read()) if self.binary_mode else StringIO(alert_file.read()), # type: ignore
				None if len(base) == 1 else base[1:-1]
			)
