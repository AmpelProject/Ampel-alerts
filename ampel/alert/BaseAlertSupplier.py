#!/usr/bin/env python
# -*- coding: utf-8 -*-
# File:                Ampel-alerts/ampel/alert/BaseAlertSupplier.py
# License:             BSD-3-Clause
# Author:              valery brinnel <firstname.lastname@gmail.com>
# Date:                29.07.2021
# Last Modified Date:  19.12.2022
# Last Modified By:    valery brinnel <firstname.lastname@gmail.com>

import json
from collections.abc import Callable, Iterator
from io import IOBase
from typing import Any, Literal

from ampel.abstract.AbsAlertLoader import AbsAlertLoader
from ampel.abstract.AbsAlertSupplier import AbsAlertSupplier
from ampel.base.AuxUnitRegister import AuxUnitRegister
from ampel.base.decorator import abstractmethod
from ampel.log.AmpelLogger import AmpelLogger
from ampel.model.UnitModel import UnitModel
from ampel.protocol.AmpelAlertProtocol import AmpelAlertProtocol
from ampel.struct.Resource import Resource


def identity(arg: dict) -> dict:
	"""
	Covers the "no deserialization needed" case which might occur
	if the underlying alert loader directly returns dicts
	"""
	return arg


# mypy: disable-error-code=empty-body
class BaseAlertSupplier(AbsAlertSupplier, abstract=True):
	"""
	:param deserialize: if the alert_loader returns bytes/file_like objects,
	  deserialization is required to turn them into dicts.
	  Currently supported built-in deserialization: 'avro' or 'json'.
	  If you need other deserialization:

	  - Either implement the deserialization in your own alert_loader (that will return dicts)
	  - Provide a callable as parameter for `deserialize`
	"""

	#: Unit to use to load alerts
	loader: UnitModel

	# Underlying serialization
	deserialize: None | Literal["avro", "json", "csv"]


	def __init__(self, **kwargs) -> None:

		# Convenience
		if 'loader' in kwargs and isinstance(kwargs['loader'], str):
			kwargs['loader'] = {"unit": kwargs['loader']}

		super().__init__(**kwargs)

		self.alert_loader: AbsAlertLoader[IOBase] = AuxUnitRegister.new_unit(
			model = self.loader, sub_type = AbsAlertLoader
		)

		if self.deserialize is None:
			self._deserialize: Callable[[Any], dict] = identity

		elif self.deserialize == "json":
			self._deserialize = json.load

		elif self.deserialize == "csv":
			from csv import DictReader
			self._deserialize = DictReader # type: ignore

		elif self.deserialize == "avro":

			from fastavro import reader
			def avro_next(arg: IOBase):
				return next(reader(arg))

			self._deserialize = avro_next
		else:
			raise NotImplementedError(
				f"Deserialization '{self.deserialize}' not implemented"
			)

	def __iter__(self) -> Iterator[AmpelAlertProtocol]:
		return self

	def __enter__(self) -> "BaseAlertSupplier":
		self.alert_loader.__enter__()
		return self

	def __exit__(self, exc_type, exc_value, traceback) -> None:
		return self.alert_loader.__exit__(exc_type, exc_value, traceback)

	@abstractmethod
	def __next__(self) -> AmpelAlertProtocol:
		...

	def set_logger(self, logger: AmpelLogger) -> None:
		self.logger = logger
		self.alert_loader.set_logger(logger)

	def add_resource(self, name: str, value: Resource) -> None:
		super().add_resource(name, value)
		self.alert_loader.add_resource(name, value)
