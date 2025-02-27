#!/usr/bin/env python
# -*- coding: utf-8 -*-
# File:                Ampel-alerts/ampel/alert/load/TarAlertLoader.py
# License:             BSD-3-Clause
# Author:              valery brinnel <firstname.lastname@gmail.com>
# Date:                13.05.2018
# Last Modified Date:  10.03.2022
# Last Modified By:    Marcus Fenner <mf@physik.hu-berlin.de>

import tarfile
from gzip import GzipFile
from typing import IO, TYPE_CHECKING, Literal, TypeAlias

from ampel.abstract.AbsAlertLoader import AbsAlertLoader

# use IOBase at runtime, because isinstance(anything, IO[bytes]) is always
# False. 
if TYPE_CHECKING:
	IOBase: TypeAlias = IO[bytes]
else:
	from io import IOBase


class TarAlertLoader(AbsAlertLoader[IOBase]):
	"""
	Load alerts from a ``tar`` file. The archive must be laid out like the
	`ZTF public alert archive <https://ztf.uw.edu/alerts/public/>`_, i.e. one
	alert per file.
	"""

	tar_mode: Literal["r", "r:*", "r:", "r:gz", "r:bz2", "r:xz"] = 'r:gz'
	start: int = 0
	file_obj: None | IOBase
	file_path: None | str

	def __init__(self, **kwargs) -> None:

		super().__init__(**kwargs)

		self._chained_tal: None | TarAlertLoader = None

		if self.file_obj:
			self._tar_file = tarfile.open(fileobj=self.file_obj, mode=self.tar_mode)  # noqa: SIM115
		elif self.file_path:
			self._tar_file = tarfile.open(self.file_path, mode=self.tar_mode)  # noqa: SIM115
		else:
			raise ValueError("Please provide value either for 'file_path' or 'file_obj'")

		if self.start != 0:
			for count, _ in enumerate(self._tar_file, 1):
				if count >= self.start:
					break


	def __iter__(self):
		return self


	def __next__(self) -> IOBase:
		"""
		FYI:
		from io import IOBase
		In []: tar_file = tarfile.open("file.tar")
		In []: tar_info = tar_file.next()
		In []: isinstance(tar_file.extractfile(tar_info), IOBase)
		Out[]: True
		"""
		# Free memory
		# NB: .members is not in the typeshed stub because it's not part of the
		# public interface. Beware the temptation to call getmembers() instead;
		# while this does return .members, it also reads the entire archive as
		# a side-effect.
		self._tar_file.members.clear() # type: ignore

		if self._chained_tal is not None:
			file_obj = self.get_chained_next()
			if file_obj is not None:
				return file_obj

		# Get next element in tar archive
		tar_info = self._tar_file.next()

		# Reach end of archive
		if tar_info is None:
			if hasattr(self, "file_path"):
				self.logger.info(f"Reached end of tar file {self.file_path}")
				#self.tar_file.close()
			else:
				self.logger.info("Reached end of tar")
			raise StopIteration

		# Ignore non-file entries
		if tar_info.isfile():

			# extractfile returns a file like obj
			file_obj = self._tar_file.extractfile(tar_info)
			assert file_obj is not None

			# Handle tars with nested tars
			if tar_info.name.endswith('.tar.gz'):
				self._chained_tal = TarAlertLoader(file_obj=file_obj)
				if (subfile_obj := self.get_chained_next()) is not None:
					return subfile_obj
				return next(self)
			if tar_info.name.endswith('.gz'):
				return GzipFile(mode="rb", fileobj=file_obj) # type: ignore[return-value]
			return file_obj

		return next(self)


	def get_chained_next(self) -> None | IOBase:
		assert self._chained_tal is not None
		file_obj = next(self._chained_tal, None)
		if file_obj is None:
			self._chained_tal = None
			return None

		return file_obj
