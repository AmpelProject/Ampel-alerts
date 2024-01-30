#!/usr/bin/env python
# -*- coding: utf-8 -*-
# File:                Ampel-alerts/ampel/alert/load/FileAlertLoader.py
# License:             BSD-3-Clause
# Author:              valery brinnel <firstname.lastname@gmail.com>
# Date:                30.04.2018
# Last Modified Date:  11.08.2021
# Last Modified By:    valery brinnel <firstname.lastname@gmail.com>

from io import BytesIO

from ampel.abstract.AbsAlertLoader import AbsAlertLoader


class FileAlertLoader(AbsAlertLoader[BytesIO]):
	"""
	Load alerts from one of more files.
	"""

	#: paths to files to load
	files: list[str]

	def __init__(self, **kwargs) -> None:
	
		super().__init__(**kwargs)

		if not self.files:
			raise ValueError("Parameter 'files' cannot be empty")

		if self.logger:
			self.logger.info(f"Registering {len(self.files)} file(s) to load")

		self._iter_files = iter(self.files)

	def __iter__(self):
		return self

	def __next__(self) -> BytesIO:
		with open(next(self._iter_files), "rb") as alert_file:
			return BytesIO(alert_file.read())
