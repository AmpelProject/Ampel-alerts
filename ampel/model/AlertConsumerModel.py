#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File:                Ampel-alerts/ampel/model/AlertConsumerModel.py
# License:             BSD-3-Clause
# Author:              valery brinnel <firstname.lastname@gmail.com>
# Date:                12.08.2022
# Last Modified Date:  12.08.2022
# Last Modified By:    valery brinnel <firstname.lastname@gmail.com>

from collections.abc import Sequence

from ampel.base.AmpelBaseModel import AmpelBaseModel
from ampel.model.ingest.CompilerOptions import CompilerOptions
from ampel.model.ingest.DualIngestDirective import DualIngestDirective
from ampel.model.ingest.IngestDirective import IngestDirective
from ampel.model.UnitModel import UnitModel


class AlertConsumerModel(AmpelBaseModel):
	""" Standardized model for AlertConsumers """

	# General options
	#: Maximum number of alerts to consume in :func:`run`
	iter_max: int = 50000

	#: Maximum number of exceptions to catch before cancelling :func:`run`
	error_max: int = 20

	#: Mandatory T0 unit
	shaper: UnitModel

	#: Mandatory alert processor directives. This parameter will
	#: determines how the underlying :class:`~ampel.alert.FilterBlocksHandler.FilterBlocksHandler`
	#: and :class:`~ampel.alert.ChainedIngestionHandler.ChainedIngestionHandler` instances are set up.
	directives: Sequence[IngestDirective | DualIngestDirective]

	#: How to store log record in the database (see :class:`~ampel.alert.FilterBlocksHandler.FilterBlocksHandler`)
	db_log_format: str = "standard"

	#: Unit to use to supply alerts (str is just a shortcut for a configless UnitModel(unit=str))
	supplier: UnitModel

	compiler_opts: None | CompilerOptions

	ingester: UnitModel = UnitModel(unit="MongoIngester")

	#: Calls `sys.exit()` with `exit_if_no_alert` as return code in case
	#: no alert was processed (iter_count == 0)
	exit_if_no_alert: None | int = None

	#: Fields from alert.extra to include in journal entries, of the form
	#: journal_key: dotted.path.in.extra.dict
	include_alert_extra_with_keys: dict[str, str] = {}
