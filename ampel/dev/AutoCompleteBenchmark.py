#!/usr/bin/env python
# -*- coding: utf-8 -*-
# File:                Ampel-alerts/ampel/alert/AutoCompleteBenchmark.py
# License:             BSD-3-Clause
# Author:              valery brinnel <firstname.lastname@gmail.com>
# Date:                03.05.2018
# Last Modified Date:  29.04.2020
# Last Modified By:    valery brinnel <firstname.lastname@gmail.com>

from collections.abc import Callable, Sequence
from functools import wraps
from multiprocessing import Pool, Semaphore, shared_memory
from time import time
from typing import Any

from pymongo import MongoClient

from ampel.core.AmpelContext import AmpelContext
from ampel.types import ChannelId, StockId


def timeit(f):
	@wraps(f)
	def wrap(*args, **kw):
		start = time()
		result = f(*args, **kw)
		if kw.get('verbose', False):
			print(f'func {f.__name__} with args {args[1:]} took: {round(time()-start, 1)}s')
		return result
	return wrap


class AutoCompleteBenchmark:
	"""
	Benchmark notes:

	test collections stats (uses snappy compression):
	================================================
	{
		"ns" : "Ampel_big.big",
		"size" : 270000000,   (Note: 210000000 if 'channel' is renamed into 'c')
		"count" : 10000000,
		"avgObjSize" : 27,
		"storageSize" : 91054080,
		"capped" : false,
		"nindexes" : 2,
		"totalIndexSize" : 164880384,
		"indexSizes" : {
			"_id_" : 118820864,
			"channel_1" : 46059520
		}
	}

	Example document
	================
	{
		"_id" : 2194,
		"channel" : 3
	}

	Output of benchmark([2, 3, 4])
	==============================

	Benchmarking get_ids_using_find
	-------------------------------
	func get_ids_using_find with args (2,) took: 8.6s
	func get_ids_using_find with args (3,) took: 8.8s
	func get_ids_using_find with args (4,) took: 9.1s
	func get_ids_using_find with args ([2, 3, 4],) took: 26.4s
	2: 2500229
	3: 2500615
	4: 2499883


	Benchmarking get_ids_using_distinct
	-----------------------------------
	distinct too big, 16mb cap
	get_ids_using_distinct(...) failed


	Benchmarking get_ids_using_aggregate
	------------------------------------
	BSONObj size: 31391887 (0x1DF008F) is invalid. Size must be between 0 and 16793600(16MB) First element: _id: null
	get_ids_using_aggregate(...) failed


	Benchmarking get_ids_using_paged_aggregate
	------------------------------------------
	func get_ids_using_paged_aggregate with args (2,) took: 13.3s
	func get_ids_using_paged_aggregate with args (3,) took: 13.4s
	func get_ids_using_paged_aggregate with args (4,) took: 13.3s
	func get_ids_using_paged_aggregate with args ([2, 3, 4],) took: 40.0s
	2: 2500229
	3: 2500615
	4: 2499883


	Benchmarking get_ids_using_paged_group_aggregate
	------------------------------------------------
	func get_ids_using_paged_group_aggregate with args ([2, 3, 4],) took: 76.9s
	2: 2500229
	3: 2500615
	4: 2499883


	Benchmarking get_ids_using_parallel_aggregate
	---------------------------------------------
	func get_ids_using_parallel_aggregate with args ([2, 3, 4],) took: 19.6s
	2: 2500229
	3: 2500615
	4: 2499883


	Benchmarking get_ids_using_parallel_find
	----------------------------------------
	func get_ids_using_parallel_find with args ([2, 3, 4],) took: 11.8s
	2: 2500229
	3: 2500615
	4: 2499883
	"""

	def __init__(self, context: AmpelContext) -> None:
		"""
		:param bool single_rej_col:
		- False: rejected logs are saved in channel specific collections
		(collection name equals channel name)
		- True: rejected logs are saved in a single collection called 'logs'
		"""

		#self._stock_col = context.db.get_collection('stock')
		mc = MongoClient() # type: ignore
		db = mc.Ampel_big
		self._stock_col = db.big


		# Channel name (ex: HU_SN or 1)
		#self.channel = model.channel
		#self.chan_str = str(self.channel) if isinstance(self.channel, int) \
		#	else self.channel

		#self.auto_accept = model.filter.auto_accept
		#self.retro_complete = model.filter.retro_complete
		#self.ac = self.auto_accept + self.retro_complete > 0

	def _create_task_done(self, chan, stop_buf, debug):

		def task_done(arg):
			if arg:
				if debug:
					print(f' Updating channel {chan} with {len(arg)} ids')
				self.ret[chan].update(arg)
			else:
				if debug:
					print(f' ########### Removing key {chan} ################ ')
				if chan in self.keys:
					self.keys.remove(chan)
					stop_buf[0] = 1
			self.sem.release()

		return task_done


	def benchmark(self, channel: ChannelId):

		for name in (
			'get_ids_using_find', 'get_ids_using_distinct', 'get_ids_using_aggregate',
			'get_ids_using_paged_aggregate', 'get_ids_using_paged_group_aggregate',
			'get_ids_using_parallel_aggregate', 'get_ids_using_parallel_find'
		):
			try:
				print(f'Benchmarking {name}')
				print('-------------' + '-' * len(name))
				r = getattr(self, name)(channel, verbose=True)
				if isinstance(r, dict):
					for k in r:
						print(f'{k}: {len(r[k])}')
				else:
					print(f'channel: {len(r)}')
				print('')
				print('')
			except Exception as e:  # noqa: PERF203
				print(e)
				print(f'{name}(...) failed')
				print('')
				print('')


	@timeit
	def get_ids_using_find(self, channel: ChannelId, *, verbose=True):
		""" Warning: slow for large collections """
		if isinstance(channel, int | str):
			return {el['_id'] for el in self._stock_col.find({'channel': channel}, {'_id': 1})}
		return {k: self.get_ids_using_find(k, verbose=verbose) for k in channel}


	@timeit
	def get_ids_using_parallel_find(self, channel: ChannelId, *, batch_size=1000000, verbose=True):
		""" Winner method """
		if isinstance(channel, int | str):
			return {el['_id'] for el in self._stock_col.find({'channel': channel}, {'_id': 1}).batch_size(batch_size)}

		pool = Pool(4)

		ret: dict[ChannelId, set[StockId]] = {k: set() for k in channel}

		results = [
			pool.apply_async(
				AutoCompleteBenchmark.find_worker, (k, batch_size),
				callback = ret[k].update,
				error_callback = self.error_cb
			)
			for k in channel
		]

		for r in results:
			r.wait()

		pool.close()
		return ret


	@timeit
	def get_ids_using_distinct(self, channel: ChannelId, *, verbose: bool = True):
		""" Warning: fails for large collections """
		if isinstance(channel, int | str):
			return set(self._stock_col.distinct('_id', filter={'channel': channel}))
		return {k: self.get_ids_using_distinct(k, verbose=verbose) for k in channel}


	@timeit
	def get_ids_using_aggregate(self, channel: ChannelId, *, verbose: bool = True):
		""" Warning: fails for large collections """
		if isinstance(channel, int | str):
			return next(
				self._stock_col.aggregate(
					[
						{'$match': {'channel': channel}},
						{'$group': {'_id': None, 'ids': {'$push': '$_id'}}}
					]
				)
			)['ids']
		return {k: self.get_ids_using_aggregate(k, verbose=verbose) for k in channel}


	@timeit
	def get_ids_using_paged_aggregate(self, channel: ChannelId, *, verbose: bool = True, page_size=1000000):
		"""
		Note: page_size has large impact on the function performance: the larger the better.
		However, it cannot grow indefinetely since BSON has a 16 MB limitation.
		The max working value depends on the type of _id's used (int32, int64, etc...).
		For int32, you can go up to 1300000. Larger _ids will require a lower page_size
		and result in noticible performance drawbacks.
		All in all, parallel "parallel find(...)" works all the time better in all circumstances.
		"""
		if isinstance(channel, int | str):

			s = set()
			skip = 0
			while True:
				d = next(
					self._stock_col.aggregate(
						[
							{'$match': {'channel': channel}},
							{'$skip': skip},
							{'$limit': page_size},
							{'$group': {'_id': None, 'ids': {'$push': '$_id'}}}
						]
					), None
				)

				if d:
					s.update(d['ids'])
					skip += page_size
					continue

				return s

		return {k: self.get_ids_using_paged_aggregate(k, verbose=verbose) for k in channel}


	@timeit
	def get_ids_using_paged_group_aggregate(self, channel: ChannelId, *, verbose: bool = True, page_size=1000000):
		"""
		One could think that letting the DB itself perform a mutli-channel (indexed) search and
		also do the grouping would yield good performance but it is not the case.
		Firing one request per channel and grouping the result in python yield much better performance.
		"""

		if isinstance(channel, int | str):
			return self.get_ids_using_paged_aggregate(channel)

		skip = 0
		ret = {k: set() for k in channel}
		ok = False

		while True:

			for el in self._stock_col.aggregate(
				[
					{'$match': {'channel': {'$in': channel}}},
					{'$skip': skip},
					{'$limit': page_size},
					{'$group': {'_id': '$channel', 'ids': {'$push': '$_id'}}}
				]
			):
				ok = True
				ret[el['_id']].update(el['ids'])

			if ok:
				skip += page_size
				ok = False
				continue

			return ret


	@timeit
	def get_ids_using_parallel_aggregate(self,
		channels: Sequence[ChannelId], *,
		page_size: int = 1000000,
		verbose: bool = True,
		debug: bool = False
	) -> dict[ChannelId, set[StockId]]:
		"""
		Builds sets of transient ids if the channel was configured
		to make use of the 'accept' or 'reject' auto_complete feature.
		self.stock_ids will hold a set of stock ids listing all known
		transients currently available in the DB for this particular channel.

		col2.create_index([('channel', 1)])

		In []: len({el['_id'] for el in col2.find({'channel': 4})})
		Out[]: 500411

		In []: %timeit {el['_id'] for el in col2.find({'channel': 4})}
		1.59 s ± 34.5 ms per loop (mean ± std. dev. of 7 runs, 1 loop each)

		In []: %timeit set(col2.distinct('_id', filter={'channel': 4}))
		1.3 s ± 5.78 ms per loop (mean ± std. dev. of 7 runs, 1 loop each)

		In []: %timeit set(next(col2.aggregate([{'$match': {'channel': 4}}, {'$group': {'_id': None, 'ids': {'$addToSet': '$_id'}}}]))['ids'])
		1.14 s ± 7.06 ms per loop (mean ± std. dev. of 7 runs, 1 loop each)
		"""

		col_max = self._stock_col.estimated_document_count()

		start = time()
		skip = 0
		pool = Pool(4)
		self.sem = Semaphore(pool._processes) # type: ignore  # noqa: SLF001
		self.keys = list(channels)
		results = []

		self.ret: dict[ChannelId, set[StockId]] = {}
		self.task_done: dict[ChannelId, Callable] = {}
		self.stops: dict[ChannelId, Any] = {}

		for kk in channels:
			self.stops[kk] = shared_memory.SharedMemory(create=True, size=1)
			self.ret[kk] = set()
			self.task_done[kk] = self._create_task_done(kk, self.stops[kk].buf, debug)


		while skip < col_max and len(self.keys) > 0:

			if debug:
				print(f'While keys: {self.keys}')

			for k in self.keys:
				if self.stops[k].buf[0] == 0:
					if debug:
						print(f' ++ NEW pool process: {skip}, range: {page_size}, chan: {k}')
					results.append(
						pool.apply_async(
							AutoCompleteBenchmark.aggregate_worker, (k, skip, page_size, self.stops[k], debug),
							callback = self.task_done[k],
							error_callback = self.error_cb
						)
					)
					self.sem.acquire()

			skip += page_size
			if debug:
				print('@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@')

		for r in results:
			r.wait()

		if debug:
			print(f'{time()-start}s')
			for k in self.ret:
				print(f'{k}: {len(self.ret[k])}')

		for kk in channels:
			self.stops[kk].close()
			self.stops[kk].unlink()

		pool.close()
		return self.ret


	def error_cb(self, e):
		print(f'Error: {e}')
		self.sem.release()


	@staticmethod
	def aggregate_worker(chan, skip, page_size, shared_stop, debug):

		mc = MongoClient()
		db = mc.Ampel_big
		col2 = db.big

		if shared_stop.buf[0] == 1:
			if debug:
				print(f' /\\ Aye Aye captain /\\ {chan}, skip: {skip}, range: {page_size}')
			return None

		try:
			if debug:
				print(f'Start chan: {chan}, skip: {skip}, range: {page_size}')
			d = next(
				col2.aggregate(
					[
						{'$match': {'channel': int(chan)}},
						{'$skip': skip},
						{'$limit': page_size},
						{'$group': {'_id': None, 'ids': {'$push': '$_id'}}}
					]
				)
			)
			if debug:
				print(f'Stop chan: {chan}, skip: {skip}, range: {page_size}')
			return d['ids']
		except StopIteration:
			if debug:
				print(f' ============ StopIteration: {chan} ============== ')
			shared_stop.buf[1] = 1
			return None


	@staticmethod
	def find_worker(chan, batch_size):
		mc = MongoClient()
		db = mc.Ampel_big
		return {el['_id'] for el in db.big.find({'channel': chan}, {'_id': 1}).batch_size(batch_size)}


	def other(self):

		if self.auto_accept or self.retro_complete:

			# Build set of transient ids for this channel
			self.stock_ids = {
				el['_id'] for el in self._stock_col.find(
					{'channel': self.channel},
					{'_id': 1}
				)
			}
