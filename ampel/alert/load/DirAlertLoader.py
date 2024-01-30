#!/usr/bin/env python
# -*- coding: utf-8 -*-
# File:                Ampel-alerts/ampel/alert/load/DirAlertLoader.py
# License:             BSD-3-Clause
# Author:              valery brinnel <firstname.lastname@gmail.com>
# Date:                14.12.2017
# Last Modified Date:  19.12.2022
# Last Modified By:    valery brinnel <firstname.lastname@gmail.com>

from io import BytesIO, StringIO

from ampel.abstract.AbsAlertLoader import AbsAlertLoader


class DirAlertLoader(AbsAlertLoader[StringIO | BytesIO]):
	""" Load alerts from a (flat) directory. """

	folder: str
	extension: str
	binary_mode: bool = True
	min_index: None | int = None
	max_index: None | int = None
	max_entries: None | int = None


	def __init__(self, **kwargs) -> None:
		super().__init__(**kwargs)
		self._files: list[str] = []
		self._open_mode = "rb" if self.binary_mode else "r"


	def set_extension(self, extension: str) -> None:
		self.extension = extension


	def set_folder(self, arg: str) -> None:
		self.folder = arg
		self.logger.debug("Target incoming folder: " + self.folder)


	def set_index_range(self, min_index: None | int = None, max_index: None | int = None) -> None:
		self.min_index = min_index
		self.max_index = max_index
		self.logger.debug(f"Min index set to: {self.min_index}")
		self.logger.debug(f"Max index set to: {self.max_index}")


	def set_max_entries(self, max_entries: int):
		self.max_entries = max_entries
		self.logger.debug(f"Max entries set to: {self.max_entries}")


	def add_files(self, arg: str):
		self._files.append(arg)
		self.logger.debug(f"Adding {len(arg)} files to the list")


	def build_file_list(self) -> None:

		self.logger.debug("Building internal file list")

		import glob
		import os
		all_files = sorted(
			glob.glob(
				os.path.join(self.folder, "*." + self.extension)
			),
			key=os.path.getmtime
		)

		if self.min_index is not None:
			self.logger.debug("Filtering files using min_index criterium")
			all_files = [
				f for f in all_files
				if int(os.path.basename(f).split(".")[0]) >= self.min_index
			]

		if self.max_index is not None:
			self.logger.debug("Filtering files using max_index criterium")
			all_files = [
				f for f in all_files
				if int(os.path.basename(f).split(".")[0]) <= self.max_index
			]

		if self.max_entries is not None:
			self.logger.debug("Filtering files using max_entries criterium")
			self._files = all_files[:self.max_entries]
		else:
			self._files = all_files

		self.logger.debug(f"File list contains {len(self._files)} elements")


	def __next__(self) -> StringIO | BytesIO:

		if not self._files:
			self.build_file_list()
			self._iter_files = iter(self._files)

		if (fpath := next(self._iter_files, None)) is None:
			raise StopIteration

		if self.logger.verbose > 1:
			self.logger.debug("Loading " + fpath)

		with open(fpath, self._open_mode) as alert_file:
			return BytesIO(alert_file.read()) if self.binary_mode else StringIO(alert_file.read())
