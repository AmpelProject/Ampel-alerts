"""
Common counters for AlertConsumer and worker classes
"""

from ampel.metrics.AmpelMetricsRegistry import AmpelMetricsRegistry

stat_alerts = AmpelMetricsRegistry.counter(
    "alerts_processed",
    "Number of processed alerts",
    subsystem="alertprocessor",
)
stat_accepted = AmpelMetricsRegistry.counter(
    "alerts_accepted",
    "Number of accepted alerts",
    subsystem="alertprocessor",
    labelnames=("channel",),
)
stat_rejected = AmpelMetricsRegistry.counter(
    "alerts_rejected",
    "Number of rejected alerts",
    subsystem="alertprocessor",
    labelnames=("channel",),
)
stat_autocomplete = AmpelMetricsRegistry.counter(
    "alerts_autocompleted",
    "Number of alerts accepted due to auto-complete",
    subsystem="alertprocessor",
    labelnames=("channel",),
)
stat_time = AmpelMetricsRegistry.histogram(
    "time",
    "Processing time",
    unit="seconds",
    subsystem="alertprocessor",
    labelnames=("section",),
)
stat_ingestions = AmpelMetricsRegistry.histogram(
    "ingestions",
    "Processing time",
    subsystem="alertprocessor",
    labelnames=("section",),
)


class AlertConsumerMetrics:

    alerts = stat_alerts
    accepted = stat_accepted.labels("any")

    def __init__(self, channels: list[str]):
        self.filter_accepted = [stat_accepted.labels(channel) for channel in channels]
