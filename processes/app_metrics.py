from prometheus_client import CollectorRegistry, Gauge, push_to_gateway

_registry = CollectorRegistry()

nabu_signoff_errors = Gauge("nabu_signoff_errors",
        "Number of signoffs from Nabu that could not be matched to cases in QC-Gate-ETL",
        registry=_registry)
nabu_archive_errors = Gauge("nabu_archive_errors",
        "Number of archives from Nabu that could not be matched to cases in QC-Gate-ETL because "
        + "either the case doesn't exist, or there are multiple archives for the same case",
        registry=_registry)
unconfigured_element = Gauge("unconfigured_element",
        "Number of elements that are not configured in QC-Gate-ETL",
        registry=_registry)
autoverification_errors = Gauge("autoverification_errors",
        "Number of errors autoverification code encountered",
        registry=_registry)
unhandled_metric_names = []
unhandled_metrics = Gauge("unhandled_metrics",
        "Number of unhandled metrics encountered",
        registry=_registry)
qcetl_conflicting_values = Gauge("qc_etl_conflicting_values",
        "Number of samples for which inconsistent merged LIMS IDs were found in QC-ETL",
        ["cache", "table", "lims_id"],
        registry=_registry)

def push(prometheus_url, environment):
    push_to_gateway(prometheus_url, job="case-etl", registry=_registry,
            grouping_key={"environment": environment})