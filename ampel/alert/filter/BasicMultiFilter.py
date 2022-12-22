#!/usr/bin/env python
# -*- coding: utf-8 -*-
# File:                Ampel-alerts/ampel/alert/filter/BasicMultiFilter.py
# License:             BSD-3-Clause
# Author:              valery brinnel <firstname.lastname@gmail.com>
# Date:                14.01.2017
# Last Modified Date:  24.11.2021
# Last Modified By:    Jakob van Santen <jakob.van.santen@desy.de>

import operator
from ampel.abstract.AbsAlertFilter import AbsAlertFilter
from ampel.protocol.AmpelAlertProtocol import AmpelAlertProtocol

from ampel.base.AmpelBaseModel import AmpelBaseModel
from typing import Literal, ClassVar
from collections.abc import Callable, Sequence


class PhotoAlertQuery(AmpelBaseModel):
	"""
	A filter condition suitable for use with AmpelAlert.get_values()
	"""
	_ops: ClassVar[dict[str, Callable]] = {
		'>': operator.gt,
		'<': operator.lt,
		'>=': operator.ge,
		'<=': operator.le,
		'==': operator.eq,
		'!=': operator.ne,
		'AND': operator.and_,
		'OR': operator.or_
	}

	#: Name of a light curve field
	attribute: str

	#: Comparison operator
	operator: Literal['>', '<', '>=', '<=', '==', '!=', 'AND', 'OR']

	#: Value to compare to
	value: float



class BasicFilterCondition(AmpelBaseModel):

	criteria: PhotoAlertQuery | Sequence[PhotoAlertQuery]
	len: int
	operator: Literal['>', '<', '>=', '<=', '==', '!=', 'AND', 'OR']
	logicalConnection: Literal['AND', 'OR'] = 'AND'
	
	def __init__(self, **kwargs):
		super().__init__(**kwargs)
		if self.len < 0:
			raise ValueError("Len must be >= 0")
		self._operator = PhotoAlertQuery._ops[self.operator]
		self._criteria = [el.dict() for el in ([self.criteria] if isinstance(self.criteria, PhotoAlertQuery) else self.criteria)]
		self._logicalConnection = PhotoAlertQuery._ops[self.logicalConnection]


class BasicMultiFilter(AbsAlertFilter):

	filters: Sequence[BasicFilterCondition]

	def process(self, alert: AmpelAlertProtocol) -> bool:
		"""
		Filter alerts via AmpelAlert.get_values(). Criteria in each condition
		are ANDed together, and conditions can be combined with AND or OR. For
		example, the following configuration selects alerts with at least 4
		detections where `rb>0.8 and fid==1 and mag<18` OR at least 4 detections
		where `magdiff>0.01`::
		    
		    "filters": [
		      {
		        "criteria": [
		          {
		            "attribute": "rb",
		            "value": 0.8,
		            "operator": ">"
		          },
		          {
		            "attribute": "fid",
		            "value": 1,
		            "operator": "=="
		          },
		          {
		            "attribute": "magpsf",
		            "value": 18,
		            "operator": "<"
		          }
		        ],
		        "len": 4,
		        "operator": ">="
		      },
		      {
		        "logicalConnection": "OR",
		        "criteria": [
		          {
		            "attribute": "magdiff",
		            "value": 0.01,
		            "operator": ">"
		          }
		        ],
		        "len": 4
		        "operator": ">="
		      }
		    ]
		"""

		filter_res = []

		for param in self.filters:

			filter_res.append(
				param._operator(
					len(
						alert.get_values('candid', filters = param._criteria)
					),
					param.len
				)
			)

		current_res = False

		for i, param in enumerate(filter_res):

			if i == 0:
				current_res = filter_res[i]
			else:
				current_res = self.filters[i]._logicalConnection( # type: ignore[misc]
					current_res, filter_res[i]
				)

		return current_res
