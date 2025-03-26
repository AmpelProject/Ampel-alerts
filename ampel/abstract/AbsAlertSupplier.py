#!/usr/bin/env python
# -*- coding: utf-8 -*-
# File:                Ampel-alerts/ampel/abstract/AbsAlertSupplier.py
# License:             BSD-3-Clause
# Author:              valery brinnel <firstname.lastname@gmail.com>
# Date:                23.04.2018
# Last Modified Date:  19.12.2022
# Last Modified By:    valery brinnel <firstname.lastname@gmail.com>

from collections.abc import Iterator

from ampel.abstract.AbsContextManager import AbsContextManager
from ampel.base.AmpelUnit import AmpelUnit
from ampel.base.decorator import abstractmethod
from ampel.log.AmpelLogger import AmpelLogger
from ampel.protocol.AmpelAlertProtocol import AmpelAlertProtocol
from ampel.struct.Resource import Resource


class AbsAlertSupplier(AmpelUnit, AbsContextManager, abstract=True):
	"""
	Iterable class that, for each alert payload provided by the underlying alert_loader,
	returns an object that implements :class:`~ampel.protocol.AmpelAlertProtocol`.
	"""

	def __init__(self, **kwargs) -> None:
		super().__init__(**kwargs)
		self.logger: AmpelLogger = AmpelLogger.get_logger()
		self.resources: dict[str, Resource] = {}

	def set_logger(self, logger: AmpelLogger) -> None:
		self.logger = logger

	def add_resource(self, name: str, value: Resource) -> None:
		self.resources[name] = value

	def __exit__(self, exc_type, exc_value, traceback) -> None:
		pass

	@abstractmethod
	def __iter__(self) -> Iterator[AmpelAlertProtocol]:
		...

	def acknowledge(self, alerts: Iterator[AmpelAlertProtocol]) -> None:
		"""Inform the source that a batch of alerts has been handled"""
		...
