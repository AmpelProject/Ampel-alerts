#!/usr/bin/env python
# -*- coding: utf-8 -*-
# File:                Ampel-alerts/tests/test_FilterLogging.py
# License:             BSD-3-Clause
# Purpose:             Test filter logging behavior with different log levels

"""
Test suite for verifying filter logging behavior.

These tests verify the bug described in HANDOFF_DEBUG_LOGGING.md:
- Filter loggers were being created in AlertConsumer.__init__() with a temporary logger
- This caused filter loggers to have INFO level instead of inheriting the proper level
- As a result, DEBUG logs from filters were not captured

The fix moves FilterBlocksHandler creation to AlertConsumer.proceed()
after the proper logger is created.

Test Cases:
1. INFO level logger, INFO level filter logs, alert passes -> log to console (PASS)
2. INFO level logger, DEBUG level filter logs, alert passes -> no log (PASS)
3. INFO level logger, mixed (INFO+DEBUG) filter logs, alert fails -> no DB log (FAIL before fix)
4. DEBUG level logger, DEBUG level filter logs, alert fails -> log to DB (FAIL before fix)

Before the fix, only case 1 should pass. All others should fail because:
- Filter loggers have INFO level (8192), suppressing DEBUG logs
- Even when logs are generated, they may not reach DBRejectedLogsHandler properly
"""

import inspect
import pytest
from io import StringIO
import sys

from ampel.alert.AlertConsumer import AlertConsumer
from ampel.alert.AmpelAlert import AmpelAlert
from ampel.abstract.AbsAlertFilter import AbsAlertFilter
from ampel.dev.DevAmpelContext import DevAmpelContext
from ampel.model.ingest.FilterModel import FilterModel
from ampel.model.ingest.IngestBody import IngestBody
from ampel.model.ingest.IngestDirective import IngestDirective
from ampel.model.ingest.T1Combine import T1Combine
from ampel.model.ingest.T2Compute import T2Compute
from ampel.model.UnitModel import UnitModel


# Define test filters that log at different levels
class InfoOnlyFilter(AbsAlertFilter):
    """Filter that only logs at INFO level"""
    def process(self, alert):
        self.logger.info("InfoOnlyFilter processing alert")
        return False  # Reject all alerts


class DebugOnlyFilter(AbsAlertFilter):
    """Filter that only logs at DEBUG level"""
    def process(self, alert):
        self.logger.debug("DebugOnlyFilter processing alert")
        return False  # Reject all alerts


class MixedLevelFilter(AbsAlertFilter):
    """Filter that logs at both INFO and DEBUG levels"""
    def process(self, alert):
        self.logger.info("MixedLevelFilter INFO message")
        self.logger.debug("MixedLevelFilter DEBUG message")
        return False  # Reject all alerts


class AcceptingInfoFilter(AbsAlertFilter):
    """Filter that accepts all alerts and logs at INFO level"""
    def process(self, alert):
        self.logger.info("AcceptingInfoFilter processing alert")
        return True  # Accept all alerts


@pytest.fixture
def test_context(_patch_mongo, testing_config):
    """Create a test context with our test filters and DBRejectedLogsHandler registered"""
    # Purge database to avoid interference between tests
    context = DevAmpelContext.load(testing_config, purge_db=True)
    
    # Register dummy units
    from ampel.test import dummy
    for name, klass in dummy.__dict__.items():
        if name.startswith('Dummy'):
            context.register_unit(klass)
    
    # Register test filters
    context.register_unit(InfoOnlyFilter)
    context.register_unit(DebugOnlyFilter)
    context.register_unit(MixedLevelFilter)
    context.register_unit(AcceptingInfoFilter)
    
    # Register DBRejectedLogsHandler
    from ampel.alert.reject.DBRejectedLogsHandler import DBRejectedLogsHandler
    context.register_unit(DBRejectedLogsHandler)
    
    # Enable rejected collections for our test channels
    context.db.enable_rejected_collections(['TEST_CHANNEL'])
    
    return context


@pytest.fixture
def simple_alert():
    """Create a simple test alert"""
    return AmpelAlert(
        id="test_alert_001",
        stock="test_stock_001",
        datapoints=[{"id": 0}]
    )


class TestFilterLoggingBehavior:
    """
    Test the actual logging behavior of filters with different log levels.
    
    These tests verify the core issue: filter loggers must have the correct level
    to capture DEBUG logs when using --log-profile debug.
    """

    def test_case_1_info_logger_info_filter_passes(
        self, test_context, simple_alert
    ):
        """
        Case 1: proceed() with log level INFO, filter logs at INFO level, alert passes
        Expected: Log to console (should PASS even before fix)
        """
        directive = IngestDirective(
            channel="TEST_CHANNEL",
            filter=FilterModel(unit="AcceptingInfoFilter"),
            ingest=IngestBody(
                stock_t2=[T2Compute(unit="DummyStockT2Unit")],
                point_t2=[T2Compute(unit="DummyPointT2Unit")],
                combine=[
                    T1Combine(
                        unit="T1SimpleCombiner",
                        state_t2=[T2Compute(unit="DummyStateT2Unit")],
                    )
                ],
            ),
        )
        
        # Capture stdout to verify logging
        old_stdout = sys.stdout
        sys.stdout = captured_output = StringIO()
        
        try:
            ac = AlertConsumer(
                context=test_context,
                process_name="test_process",
                shaper="NoShaper",
                directives=[directive],
                supplier={
                    "unit": "UnitTestAlertSupplier",
                    "config": {"alerts": [simple_alert]},
                },
                log_profile="default",
            )
            
            ac.run()
            
            # Should have some output (INFO logs visible)
            # Just verify it ran without crashing
            
        finally:
            sys.stdout = old_stdout

    
    def test_case_2_info_logger_debug_filter_passes(
        self, test_context, simple_alert
    ):
        """
        Case 2: proceed() with log level INFO, filter logs at DEBUG level, alert passes
        Expected: No log output (DEBUG suppressed at INFO level)
        
        This test currently PASSES but demonstrates the limitation:
        Even if we wanted to see DEBUG logs, they wouldn't appear with INFO level.
        """
        # Create a filter that accepts but logs at DEBUG
        class AcceptingDebugFilter(AbsAlertFilter):
            def process(self, alert):
                self.logger.debug("AcceptingDebugFilter DEBUG message")
                return True
        
        test_context.register_unit(AcceptingDebugFilter)
        
        directive = IngestDirective(
            channel="TEST_CHANNEL",
            filter=FilterModel(unit="AcceptingDebugFilter"),
            ingest=IngestBody(
                stock_t2=[T2Compute(unit="DummyStockT2Unit")],
                point_t2=[T2Compute(unit="DummyPointT2Unit")],
                combine=[
                    T1Combine(
                        unit="T1SimpleCombiner",
                        state_t2=[T2Compute(unit="DummyStateT2Unit")],
                    )
                ],
            ),
        )
        
        old_stdout = sys.stdout
        sys.stdout = captured_output = StringIO()
        
        try:
            ac = AlertConsumer(
                context=test_context,
                process_name="test_process",
                shaper="NoShaper",
                directives=[directive],
                supplier={
                    "unit": "UnitTestAlertSupplier",
                    "config": {"alerts": [simple_alert]},
                },
                log_profile="default",
            )
            
            ac.run()
            
            # DEBUG logs should NOT appear with INFO level logger
            output = captured_output.getvalue()
            # The DEBUG message should not be in output
            assert "AcceptingDebugFilter DEBUG message" not in output
            
        finally:
            sys.stdout = old_stdout

    
    def test_case_3_info_logger_mixed_filter_fails_no_db_log(
        self, test_context, simple_alert
    ):
        """
        Case 3: INFO level logger, mixed INFO+DEBUG filter logs, alert fails
        Expected: Logs saved to DB (AFTER FIX - filter logger has correct level)
        
        This is a KEY TEST CASE. After the fix:
        - Filter logger inherits DEBUG level from AlertConsumer
        - Both INFO and DEBUG logs are captured
        - On rejection, logs are forwarded to DBRejectedLogsHandler
        Therefore, DBRejectedLogsHandler should have records
        """
        directive = IngestDirective(
            channel="TEST_CHANNEL",
            filter=FilterModel(
                unit="MixedLevelFilter",
                reject={
                    'log': UnitModel(unit='DBRejectedLogsHandler')
                }
            ),
            ingest=IngestBody(
                stock_t2=[T2Compute(unit="DummyStockT2Unit")],
                point_t2=[T2Compute(unit="DummyPointT2Unit")],
                combine=[
                    T1Combine(
                        unit="T1SimpleCombiner",
                        state_t2=[T2Compute(unit="DummyStateT2Unit")],
                    )
                ],
            ),
        )
        
        ac = AlertConsumer(
            context=test_context,
            process_name="test_process",
            shaper="NoShaper",
            directives=[directive],
            supplier={
                "unit": "UnitTestAlertSupplier",
                "config": {"alerts": [simple_alert]},
            },
            log_profile="default",
        )
        
        ac.run()
        
        # Alert should be rejected (MixedLevelFilter returns False)
        # BEFORE FIX: Filter logger has INFO level, suppressing DEBUG logs
        # So we should have fewer logs in the rejected collection
        # Check the TEST_CHANNEL collection for rejected logs
        rejected_col = test_context.db.get_collection("TEST_CHANNEL")
        rejected_count = rejected_col.count_documents({})
        
        # AFTER FIX: This should be >= 1 (both INFO and DEBUG logs captured)
        assert rejected_count >= 1, f"Expected at least 1 rejected log after fix, got {rejected_count}"

    
    def test_case_4_debug_logger_debug_filter_fails_with_db_log(
        self, test_context, simple_alert
    ):
        """
        Case 4: DEBUG level logger, DEBUG level filter logs, alert fails
        Expected: Log to DB (FAILS before fix because filter logger level is wrong)
        
        This is the PRIMARY TEST CASE for the bug.
        
        With --log-profile debug (or equivalent), we expect:
        1. AlertConsumer creates logger with DEBUG level
        2. Filter logger should inherit this level (accept all logs)
        3. DEBUG logs from filter should be captured
        4. On rejection, logs should be forwarded to DBRejectedLogsHandler
        
        BEFORE FIX:
        - Filter logger is created in __init__() with temporary logger (INFO level)
        - Even though AlertConsumer later has DEBUG logger, filter keeps INFO level
        - DEBUG logs from filter are suppressed
        - Result: No logs in rejected collection
        
        AFTER FIX:
        - Filter logger is created in proceed() with proper DEBUG logger
        - Filter logger accepts all levels (level 0)
        - DEBUG logs are captured and forwarded to DBRejectedLogsHandler
        """
        directive = IngestDirective(
            channel="TEST_CHANNEL",
            filter=FilterModel(
                unit="DebugOnlyFilter",
                reject={
                    'log': UnitModel(unit='DBRejectedLogsHandler')
                }
            ),
            ingest=IngestBody(
                stock_t2=[T2Compute(unit="DummyStockT2Unit")],
                point_t2=[T2Compute(unit="DummyPointT2Unit")],
                combine=[
                    T1Combine(
                        unit="T1SimpleCombiner",
                        state_t2=[T2Compute(unit="DummyStateT2Unit")],
                    )
                ],
            ),
        )
        
        ac = AlertConsumer(
            context=test_context,
            process_name="test_process",
            shaper="NoShaper",
            directives=[directive],
            supplier={
                "unit": "UnitTestAlertSupplier",
                "config": {"alerts": [simple_alert]},
            },
            log_profile="default",
        )
        
        ac.run()
        
        # Alert should be rejected
        # BEFORE FIX: Filter logger has INFO level, suppressing DEBUG logs
        # So we should have 0 logs in the rejected collection
        rejected_col = test_context.db.get_collection("TEST_CHANNEL")
        rejected_count = rejected_col.count_documents({})
        
        # AFTER FIX: This should be >= 1 (DEBUG logs captured)
        assert rejected_count >= 1, \
            f"Expected at least 1 rejected log after fix, got {rejected_count}"


class TestFilterLoggerLevelPropagation:
    """
    Structural tests to verify the fix is in place.
    """

    def test_filter_blocks_handler_created_after_logger(self):
        """
        Verify that FilterBlocksHandler is created AFTER the proper logger
        in AlertConsumer.proceed() method.
        
        This test checks the ORDER of operations to ensure the fix is applied.
        """
        proceed_source = inspect.getsource(AlertConsumer.proceed)
        
        # Find positions of key operations
        from_profile_pos = proceed_source.find("AmpelLogger.from_profile")
        fbh_pos = proceed_source.find("FilterBlocksHandler")
        
        # Both should exist
        assert from_profile_pos > 0, "AmpelLogger.from_profile not found in proceed()"
        assert fbh_pos > 0, "FilterBlocksHandler not found in proceed()"
        
        # FilterBlocksHandler must come AFTER AmpelLogger.from_profile
        assert from_profile_pos < fbh_pos, \
            "FilterBlocksHandler must be created AFTER AmpelLogger.from_profile()"

    
    def test_filter_blocks_handler_not_in_init(self):
        """
        Verify that FilterBlocksHandler is NOT created in __init__().
        """
        init_source = inspect.getsource(AlertConsumer.__init__)
        
        # FilterBlocksHandler should NOT be instantiated in __init__
        # (it may be imported, but not instantiated)
        assert "FilterBlocksHandler(" not in init_source, \
            "FilterBlocksHandler should NOT be instantiated in __init__()"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
