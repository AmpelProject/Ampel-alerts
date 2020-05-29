#!/usr/bin/env python
# -*- coding: utf-8 -*-
# File              : Ampel-alerts/ampel/alert/filter/BasicCatalogFilter.py
# License           : BSD-3-Clause
# Author            : Matteo Giomi
# Date              : 14.01.2018
# Last Modified Date: 30.01.2020
# Last Modified By  : vb <vbrinnel@physik.hu-berlin.de>

from extcats import CatalogQuery
from pymongo import MongoClient
from numpy import mean

from ampel.abstract.AbsAlertFilter import AbsAlertFilter
from ampel.alert.PhotoAlert import PhotoAlert


class BasicCatalogFilter(AbsAlertFilter[PhotoAlert]):

	resources = ('extcats.reader', )

	def __init__(self,
		on_match_t2_units, base_config=None, run_config=None, logger=None
	):
		""" """

		self.on_match_default_t2_units = on_match_t2_units

		if run_config is None or not isinstance(run_config, dict):
			raise ValueError("run_config type must be a dict or MappingProxyType")

		# init mongo client to be passed to extcats
		dbclient = MongoClient(base_config['extcats.reader'])

		# int catalogquery object
		self.cat_query = CatalogQuery.CatalogQuery(
			cat_name = run_config['catName'],
			ra_key = run_config['catRAKey'],
			dec_key = run_config['catDecKey'],
			coll_name = base_config['catSrcCollName'],
			dbclient = dbclient,
			logger =  logger
		)

		# parameters for the query
		self.rs_arcsec = run_config['rsArcsec']
		self.alert_pos_type = run_config['alertPosType']
		self.search_method = run_config['searchMethod']

		# either accept or reject alert if a match is found
		self.reject_on_match = run_config['rejectOnMatch']

		logger.info(
			"Initialized BasicCatalogFilter. Alerts with matches in %s (rs = %.2f arcsec) will be %s" % (
			run_config['catName'], run_config['rsArcsec'],
			"dropped"*self.reject_on_match + "accepted"*(not self.reject_on_match)
			)
		)


	def apply(self, alert):
		"""
		Apply this filter to one ampel_alter object.
		The steps are the following:

		1) the transient position is estimated either as the all-epoch
		average or as the latest one.

		2) the external catalog is queryied for matches within a given
		search radius from the position estimated in step 1

		3) depending on the setting of the filter and on the outcome of the
		catalog query, the alert is accepted or rejected.
		"""

		# compute alert position
		if self.alert_pos_type == "av":
			av_values = mean( alert.get_tuples('ra', 'dec'), axis = 0 )
			ra, dec = av_values[0], av_values[1]
		elif self.alert_pos_type == "latest":
			latest = alert.get_photopoints()[0]
			ra, dec = latest['ra'], latest['dec']
		else:
			raise ValueError("Value of parameter alertPosType not recognized.")

		# catalog matching
		found_cp = self.cat_query.binaryserach(
			ra, dec, rs_arcsec = self.rs_arcsec,
			method = self.search_method
		)

		# the case of matching with catalogs of non interesting objects
		if self.reject_on_match:
			if found_cp:
				return None
			return self.on_match_default_t2_units

		# the case of matching with catalogs of interesting objects
		if found_cp:
			return self.on_match_default_t2_units

		return None