#!/usr/bin/env python
# -*- coding: utf-8 -*-
# File:                Ampel-alerts/ampel/abstract/AbsAlertLoader.py
# License:             BSD-3-Clause
# Author:              valery brinnel <firstname.lastname@gmail.com>
# Date:                26.06.2021
# Last Modified Date:  19.12.2022
# Last Modified By:    valery brinnel <firstname.lastname@gmail.com>

from ampel.types import T
from typing import Generic
from collections.abc import Iterator
from ampel.struct.Resource import Resource
from ampel.log.AmpelLogger import AmpelLogger
from ampel.base.AmpelABC import AmpelABC
from ampel.base.decorator import abstractmethod
from ampel.base.AmpelBaseModel import AmpelBaseModel


class AbsAlertLoader(Generic[T], AmpelABC, AmpelBaseModel, abstract=True):

	def __init__(self, **kwargs) -> None:
		super().__init__(**kwargs)
		self.logger: AmpelLogger = AmpelLogger.get_logger()
		self.resources: dict[str, Resource] = {}

	def set_logger(self, logger: AmpelLogger) -> None:
		self.logger = logger

	def add_resource(self, name: str, value: Resource) -> None:
		self.resources[name] = value

	def __iter__(self) -> Iterator[T]: # type: ignore
		return self

	@abstractmethod
	def __next__(self) -> T:
		...

	def acknowledge(self, alerts: Iterator[T]) -> None:
		"""Inform the source that a batch of alerts has been handled"""
		...
