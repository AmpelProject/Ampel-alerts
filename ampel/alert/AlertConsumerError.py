#!/usr/bin/env python
# -*- coding: utf-8 -*-
# File:                Ampel-alerts/ampel/alert/AlertConsumerError.py
# License:             BSD-3-Clause
# Author:              valery brinnel <firstname.lastname@gmail.com>
# Date:                05.08.2021
# Last Modified Date:  05.08.2021
# Last Modified By:    valery brinnel <firstname.lastname@gmail.com>

import signal
from enum import IntEnum


class AlertConsumerError(IntEnum):
	CONNECTIVITY = 1
	SIGINT = signal.SIGINT # 2
	TOO_MANY_ERRORS = 3
	SIGTERM = signal.SIGTERM # 15
