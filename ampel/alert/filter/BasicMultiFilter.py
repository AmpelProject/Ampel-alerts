#!/usr/bin/env python
# -*- coding: utf-8 -*-
# File              : Ampel-alerts/ampel/alert/filter/BasicMultiFilter.py
# License           : BSD-3-Clause
# Author            : vb <vbrinnel@physik.hu-berlin.de>
# Date              : 14.01.2017
# Last Modified Date: 30.01.2020
# Last Modified By  : vb <vbrinnel@physik.hu-berlin.de>

import operator
from ampel.abstract.AbsAlertFilter import AbsAlertFilter
from ampel.alert.PhotoAlert import PhotoAlert


class BasicMultiFilter(AbsAlertFilter[PhotoAlert]):

	version = 0.1

	ops = {
		'>': operator.gt,
		'<': operator.lt,
		'>=': operator.ge,
		'<=': operator.le,
		'==': operator.eq,
		'!=': operator.ne,
		'AND': operator.and_,
		'OR': operator.or_
	}


	def __init__(self, on_match_t2_units, base_config=None, run_config=None, logger=None):
		""" """

		if run_config is None or not isinstance(run_config, dict):
			raise ValueError("run_config type must be a dict")

		if "logicalConnection" in run_config['filters'][0]:
			raise ValueError("First filter element cannot contain parameter logicalConnection")

		self.on_match_default_t2_units = on_match_t2_units
		self.filters = []
		self.logical_ops = [None]

		for param in run_config['filters']:

			self.filters.append(
				{
					'operator': BasicMultiFilter.ops[
						param['operator']
					],
					'criteria': param['criteria'],
					'len': param['len']
				}
			)

			if "logicalConnection" in param:
				self.logical_ops.append(
					BasicMultiFilter.ops[
						param["logicalConnection"]
					]
				)

		logger.info(f"Following BasicMultiFilter criteria were configured: {self.filters}")


	def get_version(self):
		return BasicMultiFilter.version


	def apply(self, alert):
		"""
		Doc will follow
		"""

		filter_res = []

		for param in self.filters:

			filter_res.append(
				param['operator'](
					len(
						alert.get_values(
							'candid',
							filters = param['criteria']
						)
					),
					param['len']
				)
			)

		current_res = False

		for i, param in enumerate(filter_res):

			if i == 0:
				current_res = filter_res[i]
			else:
				current_res = self.logical_ops[i](
					current_res, filter_res[i]
				)

		if current_res:
			return self.on_match_default_t2_units

		return None