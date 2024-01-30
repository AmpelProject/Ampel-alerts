#!/usr/bin/env python
# -*- coding: utf-8 -*-
# File:                Ampel-alerts/ampel/alert/load/DirFileNamesLoader.py
# License:             BSD-3-Clause
# Author:              valery brinnel <firstname.lastname@gmail.com>
# Date:                25.10.2021
# Last Modified Date:  25.10.2021
# Last Modified By:    valery brinnel <firstname.lastname@gmail.com>

import glob
import os

from ampel.abstract.AbsAlertLoader import AbsAlertLoader


class DirFileNamesLoader(AbsAlertLoader[str]):
	"""
	Returns file names from a (flat) directory
	It is then up to the associated alert supplier to load and deserialize data.
	This class can be useful when stock name and/or tags are encoded into the file name
	and not available as content
	"""

	folder: str
	extension: str
	max_entries: None | int = None

	def __init__(self, **kwargs) -> None:

		super().__init__(**kwargs)
		self.logger.debug("Building internal file list")

		files = sorted(
			glob.glob(os.path.join(self.folder, f"*.{self.extension}")),
			key=os.path.getmtime
		)

		if self.max_entries is not None:
			self.logger.debug("Filtering files using max_entries criterium")
			files = files[:self.max_entries]

		self._iter_files = iter(files)
		self.logger.debug(f"File list contains {len(files)} elements")


	def __next__(self) -> str:

		fpath = next(self._iter_files)
		if self.logger.verbose > 1:
			self.logger.debug("Returning " + fpath)

		return fpath
