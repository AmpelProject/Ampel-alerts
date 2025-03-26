#!/usr/bin/env python
# -*- coding: utf-8 -*-
# File:                Ampel-alerts/ampel/abstract/AbsAlertLoader.py
# License:             BSD-3-Clause
# Author:              valery brinnel <firstname.lastname@gmail.com>
# Date:                26.06.2021
# Last Modified Date:  19.12.2022
# Last Modified By:    valery brinnel <firstname.lastname@gmail.com>

from collections.abc import Iterator
from typing import Generic

from ampel.abstract.AbsContextManager import AbsContextManager
from ampel.base.AmpelUnit import AmpelUnit
from ampel.base.decorator import abstractmethod
from ampel.log.AmpelLogger import AmpelLogger
from ampel.struct.Resource import Resource
from ampel.types import T


class AbsAlertLoader(AbsContextManager, AmpelUnit, Generic[T], abstract=True):

	@property
	def logger(self) -> AmpelLogger:
		return self._logger

	@property
	def resources(self) -> dict[str, Resource]:
		return self._resources

	def __init__(self, **kwargs) -> None:
		super().__init__(**kwargs)
		self._logger: AmpelLogger = AmpelLogger.get_logger()
		self._resources: dict[str, Resource] = {}

	def __exit__(self, exc_type, exc_value, traceback) -> None:
		pass

	def set_logger(self, logger: AmpelLogger) -> None:
		self._logger = logger

	def add_resource(self, name: str, value: Resource) -> None:
		self._resources[name] = value

	def __iter__(self) -> Iterator[T]: # type: ignore
		return self

	@abstractmethod
	def __next__(self) -> T:
		...

	def acknowledge(self, alerts: Iterator[T]) -> None:
		"""Inform the source that a batch of alerts has been handled"""
		...
