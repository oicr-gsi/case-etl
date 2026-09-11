import logging
import pandas as pd
import processes.app_metrics as app_metrics
import timeit

from collections import defaultdict
from dataclasses import dataclass
from dataclasses_json import dataclass_json
from enum import Enum
from math import isnan
from model.pinery import MetricLevel, PreprocessedPinerySample, QcableType, SampleMetric
from qcetl import QCETLMultiCache


class LookupType(Enum):
    SINGLE_LANE = "single_lane"
    CALL_READY = "call_ready"
    MERGE_SINGLE_LANE = "merge_single_lane"

class ValueType(Enum):
    FLOAT = "float"
    BOOL = "bool"
    NEGATE_BOOL = "negate_bool"

@dataclass_json
@dataclass(frozen=True)
class QcEtlMetricSource:
    cache: str
    table: str
    column: str
    lookup_type: LookupType
    value_type: ValueType
    preliminary: bool = False
    id_column: str | None = None
    whole_column: str | None = None
    whole_value: float | None = None
    filter_column: str | None = None
    filter_value: str | None = None

@dataclass_json
@dataclass(frozen=True)
class QcEtlMetricDefinition:
    name: str
    library_designs: list[str]
    step: QcableType
    sources: list[QcEtlMetricSource]
    overwrite: bool = False
    note: str | None = None

@dataclass
class MetricWork:
    metric: SampleMetric
    source: QcEtlMetricSource

@dataclass
class SampleWork:
    sample: PreprocessedPinerySample
    metrics: list[MetricWork]

@dataclass(frozen=True)
class Cache:
    name: str
    table: str
    data: pd.DataFrame


SINGLE_LIMS_ID_COLUMN = "Pinery Lims ID"
MERGED_LIMS_IDS_COLUMN = "Merged Pinery Lims ID"

# Analysis review metrics remain hard-coded for now
CALLABILITY_SOURCE = QcEtlMetricSource(
    cache="mutectcallability",
    table="mutectcallability",
    column="callability",
    lookup_type=LookupType.CALL_READY,
    value_type=ValueType.FLOAT
)

COLLAPSED_COVERAGE_SOURCE_1 = QcEtlMetricSource(
    cache="hsmetrics_consensus_cruncher",
    table="metrics",
    column="MEAN_BAIT_COVERAGE",
    lookup_type=LookupType.CALL_READY,
    value_type=ValueType.FLOAT
)

COLLAPSED_COVERAGE_SOURCE_2 = QcEtlMetricSource(
    cache="hsmetrics_umiconsensus",
    table="metrics",
    column="MEAN_BAIT_COVERAGE",
    lookup_type=LookupType.CALL_READY,
    value_type=ValueType.FLOAT
)


def _load_metric_definitions(metric_definition_file: str) -> list[QcEtlMetricDefinition]:
    with open(metric_definition_file, "r") as file:
        raw_json = file.read()
        return QcEtlMetricDefinition.schema().loads(raw_json, many=True)

def _find_metric_definition(
    metric_name: str,
    library_design: str,
    qcable_type: QcableType,
    metric_definitions: list[QcEtlMetricDefinition]
) -> QcEtlMetricDefinition:
    matches = [x for x in metric_definitions
            if x.name == metric_name
            and library_design in x.library_designs
            and x.step == qcable_type]

    if len(matches) > 1:
        raise ValueError(f"Multiple metric definitions found for metric '{metric_name}' "
                f"({library_design} {qcable_type})")

    if len(matches) == 0:
        return None
    else:
        return matches[0]

def _build_execution_plan(
    samples: list[PreprocessedPinerySample],
    metric_definitions: list[QcEtlMetricDefinition]
) -> dict[int, dict[str, dict[str, dict[str, SampleWork]]]]:
    """
    Returns:

    {
        priority: {
            cache: {
                table: {
                    sample_id: SampleWork(
                        sample: Sample
                        metrics: [MetricWork]
                    )
                }
            }
        }
    }
    """
    plan: dict[int, dict[str, dict[str, dict[str, SampleWork]]]] = defaultdict(
        lambda: defaultdict(
            lambda: defaultdict(dict)
        )
    )

    for sample in samples:
        for metric in sample.metrics.values():
            definition = _find_metric_definition(metric.name, sample.library_design,
                    sample.qcable_type, metric_definitions)
            if definition == None:
                if (
                    metric.metric_level == MetricLevel.SAMPLE
                    and metric.name not in app_metrics.unhandled_metric_names
                ):
                    logging.warning("Unhandled metric: %s", metric.name)
                    app_metrics.unhandled_metric_names.append(metric.name)
                    app_metrics.unhandled_metrics.inc()
                continue

            if metric.value is not None and not definition.overwrite:
                continue

            for priority, source in enumerate(definition.sources):
                sample_work = (
                    plan[priority]
                    .setdefault(source.cache, {})
                    .setdefault(source.table, {})
                    .setdefault(sample.sample_id, SampleWork(sample=sample, metrics=[]))
                )

                sample_work.metrics.append(MetricWork(metric=metric, source=source))

    return plan

def _connect_caches(cache_dirs: list[str]) -> QCETLMultiCache:
    etl_caches = QCETLMultiCache(cache_dirs)
    results = etl_caches.test_connection()
    failures = [cache_dirs[index] for index, result in enumerate(results) if result == False]
    if failures:
        raise ConnectionError(f"Could not connect to QC-ETL cache(s): {'; '.join(failures)}")
    return etl_caches

def _index_merge_samples(samples: list[PreprocessedPinerySample]
        ) -> dict[str, list[PreprocessedPinerySample]]:
    # index based on merge fields: donor, tissue origin, tissue type, timepoint, library design,
    # and group ID
    all_merge_samples: dict[str, list[PreprocessedPinerySample]] = {}
    for sample in samples:
        # Only passing full-depth samples get merged
        if sample.qcable_type != QcableType.FULL_DEPTH_SEQUENCING or sample.qc_state == "Failed":
            continue
        merge_index = _get_merge_index(sample)
        if not merge_index in all_merge_samples:
            all_merge_samples[merge_index] = []
        all_merge_samples[merge_index].append(sample)
    return all_merge_samples

def _get_merge_index(sample: PreprocessedPinerySample):
    return f"{sample.requisition_id}_{sample.donor_id}_{sample.tissue_origin}_{sample.tissue_type}_{sample.timepoint}_{sample.library_design}_{sample.group_id}"

# load the cache, or return empty cache if the cache is missing or seems invalid
# (based on missing ID column)
# merged means the cache is merged and has a Merged Pinery Lims ID column. The merged rows will be
# exploded so that individual Pinery Lims IDs can be used for lookup
def _load_cache(
    etl_caches: QCETLMultiCache,
    source: QcEtlMetricSource
) -> Cache:
    merged = source.lookup_type == LookupType.CALL_READY
    original_id_column = (source.id_column if source.id_column
            else MERGED_LIMS_IDS_COLUMN if merged
            else SINGLE_LIMS_ID_COLUMN)
    try:
        caches = etl_caches.load_same_version(source.cache).remove_missing(source.table)
        cache = caches.unique(source.table)
        if original_id_column not in cache:
            logging.warning(f"'{original_id_column}' column not found in cache: {source.cache}.{source.table}")
            return Cache(source.cache, source.table, pd.DataFrame())
        else:
            if merged:
                single_id_column = SINGLE_LIMS_ID_COLUMN
                cache[single_id_column] = cache[original_id_column]
                cache = cache.explode(single_id_column)
            else:
                single_id_column = original_id_column
            cache.set_index(single_id_column, inplace=True, drop=False)
            cache.sort_index(inplace=True)

            if source.filter_column:
                cache = cache[cache[source.filter_column] == source.filter_value]
            
            return Cache(source.cache, source.table, cache)
    except Exception:
            logging.exception(f'Error loading cache: {source.cache}.{source.table}')
            return Cache(source.cache, source.table, pd.DataFrame())

def _filter_by_id(cache: Cache, sample_id: str) -> pd.DataFrame:
    # pass index as a list to ensure the result is always a DataFrame
    # (otherwise annoyingly returns a Series for single result)
    return cache.data.loc[[sample_id]] if sample_id in cache.data.index else pd.DataFrame()

def _get_value(data: pd.DataFrame, column: str, sample_id: str, cache: Cache) -> any:
    unique_values = data[column].unique()
    if len(unique_values) > 1:
        app_metrics.qcetl_conflicting_values.labels(cache.name, cache.table, sample_id).inc()
        logging.warning(f"multiple values found for {sample_id} in cache '{cache.name}' table '{cache.table}' column '{column}': {unique_values}")
        return None
    value = unique_values[0].item()
    return None if value is None or isnan(value) else value

def _merge_related_values(cache: Cache, sample: PreprocessedPinerySample, sample_value: float,
        all_merge_samples: dict[str, list[PreprocessedPinerySample]], column: str) -> float:
    sum = sample_value
    merge_index = _get_merge_index(sample)
    merge_samples = all_merge_samples.get(merge_index, [])
    for merge_sample in merge_samples:
        # avoid double lookup
        if merge_sample.sample_id != sample.sample_id and merge_sample.qc_state != "Failed":
            related_results = _filter_by_id(cache, merge_sample.sample_id)
            if not related_results.empty:
                related_value = _get_value(related_results, column, merge_sample, cache)
                if related_value is None:
                    # partial results would be misleading, so return nothing instead
                    return None
                sum += related_value
    return sum

def add_qcetl_data(
    samples: list[PreprocessedPinerySample],
    metric_definition_file: str,
    cache_dirs: list[str]
) -> None:
    print("Beginning QC-ETL extraction")

    metric_definitions = _load_metric_definitions(metric_definition_file)
    plan = _build_execution_plan(samples, metric_definitions)
    all_merge_samples = _index_merge_samples(samples)
    etl_caches = _connect_caches(cache_dirs)
    
    for caches in plan.values():
        for cache_name, tables in caches.items():
            for table_name, sample_map in tables.items():
                cache_start_time = timeit.default_timer()
                load_source = None
                cache = None
                for sample_id, sample_work in sample_map.items():
                    pending = [x for x in sample_work.metrics if not x.metric.finalized]
                    if not pending:
                        continue
                    if cache is None:
                        load_source = pending[0].source
                        cache = _load_cache(etl_caches, load_source)
                        if cache.data.empty:
                            print(f"...{cache_name}.{table_name} metrics SKIPPED due to empty cache")
                            continue
                    
                    data = _filter_by_id(cache, sample_id)
                    if data.empty:
                        continue
                    for work in pending:
                        # validate - all sources with the same cache+table should have compatible lookup types and the same filter
                        if (work.source.lookup_type == LookupType.CALL_READY) != (load_source.lookup_type == LookupType.CALL_READY):
                            raise ValueError(f"Conflicting lookup types for {cache_name}.{table_name}")
                        if (work.source.filter_column != load_source.filter_column
                                or work.source.filter_value != load_source.filter_value):
                            raise ValueError(f"Conflicting filters for {cache_name}.{table_name}")
                        
                        value = _get_value(data, work.source.column, sample_id, cache)
                        if value is None:
                            continue
                        if work.source.lookup_type == LookupType.MERGE_SINGLE_LANE:
                            # don't merge a QC failed sample
                            if sample_work.sample.qc_state == "Failed":
                                continue
                            value = _merge_related_values(cache, sample_work.sample, value,
                                    all_merge_samples, work.source.column)
                            if value is None:
                                continue
                        match work.source.value_type:
                            case ValueType.FLOAT:
                                if work.source.whole_column is not None:
                                    whole = _get_value(data, work.source.whole_column,
                                            sample_id, cache)
                                    if whole is None:
                                        continue
                                    value = value * 100 / whole
                                elif work.source.whole_value is not None:
                                    value = value * 100 / work.source.whole_value
                                work.metric.add_sample_value(value, work.source.preliminary)
                                work.metric.finalized = True
                            case ValueType.BOOL:
                                work.metric.qc_passed = bool(value)
                                work.metric.finalized = True
                            case ValueType.NEGATE_BOOL:
                                work.metric.qc_passed = not value
                                work.metric.finalized = True
                            case _:
                                raise ValueError(f"Invalid value type for metric '{work.metric.name}': {work.source.value_type}")

                if cache is not None and cache.data.empty:
                    continue
                print(f"...{cache_name}.{table_name} metrics extracted for {len(sample_map)} samples in {timeit.default_timer() - cache_start_time:.1f}s")
    _add_analysis_review_data(samples, etl_caches)

def _add_analysis_review_data(
    samples: list[PreprocessedPinerySample],
    etl_caches: QCETLMultiCache
) -> None:
    fd_samples = [x for x in samples if x.qcable_type == QcableType.FULL_DEPTH_SEQUENCING]
    cache_start_time = timeit.default_timer()
    source = CALLABILITY_SOURCE
    cache = _load_cache(etl_caches, source)
    if cache.data.empty:
        print(f"...{source.cache} analysis review metrics SKIPPED due to empty cache")
    else:
        for sample in fd_samples:
            data = _filter_by_id(cache, sample.sample_id)
            if data.empty:
                continue
            value = _get_value(data, source.column, sample.sample_id, cache)
            if value is not None:
                sample.callability = value * 100
        print(f"...{source.cache}.{source.table} analysis review metrics extracted for {len(fd_samples)} samples in {timeit.default_timer() - cache_start_time:.1f}s")

    cache_start_time = timeit.default_timer()
    source = COLLAPSED_COVERAGE_SOURCE_1
    cache = _load_cache(etl_caches, source)
    if cache.data.empty:
        print(f"...{source.cache} analysis review metrics SKIPPED due to empty cache")
    else:
        # exclude samples with collapsed coverage from MISO
        fd_samples = [x for x in fd_samples if x.collapsed_coverage is None]
        count = 0
        for sample in fd_samples:
            metric = sample.metrics.get("Collapsed Coverage")
            if metric is not None:
                # already fetched for full-depth
                sample.collapsed_coverage = metric.value
            else:
                count += 1
                data = _filter_by_id(cache, sample.sample_id)
                if data.empty:
                    continue
                sample.collapsed_coverage = _get_value(data, source.column, sample.sample_id, cache)
        print(f"...{source.cache}.{source.table} analysis review metrics extracted for {count} samples in {timeit.default_timer() - cache_start_time:.1f}s")

    cache_start_time = timeit.default_timer()
    source = COLLAPSED_COVERAGE_SOURCE_2
    fd_samples = [x for x in fd_samples if x.collapsed_coverage is None]
    cache = _load_cache(etl_caches, source)
    if cache.data.empty:
        print(f"...{source.cache} analysis review metrics SKIPPED due to empty cache")
    else:
        for sample in samples:
            if sample.collapsed_coverage is None:
                data = _filter_by_id(cache, sample.sample_id)
                if data.empty:
                    continue
                sample.collapsed_coverage = _get_value(data, source.column, sample.sample_id, cache)
        print(f"...{source.cache}.{source.table} analysis review metrics extracted for {len(fd_samples)} samples in {timeit.default_timer() - cache_start_time:.1f}s")
