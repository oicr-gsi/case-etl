from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
from model.pinery import MetricLevel, PreprocessedPinerySample, PreprocessedRun
from processes.turnaround_time import parse_date

_QC_STATE_PENDING = "Not Ready"
_QC_STATE_FAILED = "Failed"
_QC_STATE_PASSED = "Ready"

class AutoverificationMode(StrEnum):
    DISABLED = "disabled"
    DRY_RUN = "dry-run"
    ENABLED = "enabled"

@dataclass
class Decisions:
    passed_runs: list[PreprocessedRun] = field(default_factory=list)
    failed_runs: list[PreprocessedRun] = field(default_factory=list)
    passed_samples: list[PreprocessedPinerySample] = field(default_factory=list)
    topup_samples: list[PreprocessedPinerySample] = field(default_factory=list)
    failed_samples: list[PreprocessedPinerySample] = field(default_factory=list)


def autoverify_runs(mode: AutoverificationMode, start_date: date,
        runs_by_id: dict[int, PreprocessedRun], sample_ids_by_run: dict[int, set[str]],
        samples_by_id: dict[str, PreprocessedPinerySample]):
    if mode == AutoverificationMode.DISABLED:
        return
    print("Beginning autoverification")
    decisions = _make_decisions(mode, start_date, runs_by_id, sample_ids_by_run, samples_by_id)
    _process_signoffs(mode, decisions)


def _make_decisions(mode: AutoverificationMode, start_date: date,
        runs_by_id: dict[int, PreprocessedRun], sample_ids_by_run: dict[int, set[str]],
        samples_by_id: dict[str, PreprocessedPinerySample]) -> Decisions:
    decisions = Decisions()
    for run in runs_by_id.values():
        # skip incomplete runs and already failed runs
        if not run.completion_date or run.qc_state == _QC_STATE_FAILED:
            continue
        # skip runs completed before the autoverify start date
        if start_date and parse_date(run.completion_date) < start_date:
            continue
        sample_ids = sample_ids_by_run.get(run.id, [])
        # skip runs with no samples
        if not sample_ids:
            continue

        if mode == AutoverificationMode.DRY_RUN:
            print(f"...checking run {run.name}")

        run_signoff_needed = run.qc_state == _QC_STATE_PENDING
        run_metrics_available = False
        run_values_missing = False
        run_metrics_failing = False
        signoff_passed_run_samples = []
        signoff_topup_run_samples = []
        signoff_failed_run_samples = []
        for sample_id in sample_ids:
            sample = samples_by_id[sample_id]
            # skip samples with no metrics
            if not sample.metrics:
                continue
            sample_signoff_needed = sample.qc_state == _QC_STATE_PENDING
            # skip if neither sample nor run needs signoff
            if not sample_signoff_needed and not run_signoff_needed:
                continue
            sample_run_metrics_available = False
            sample_metrics_available = False
            sample_values_missing = False
            sample_needs_topup = False
            sample_metrics_failing = False
            for metric in sample.metrics.values():
                if metric.metric_level in [MetricLevel.RUN, MetricLevel.LANE]:
                    run_metrics_available = True
                    sample_run_metrics_available = True
                    if metric.qc_passed is None or metric.preliminary:
                        run_values_missing = True
                    elif metric.qc_passed == False:
                        run_metrics_failing = True
                else:
                    sample_metrics_available = True
                    if metric.qc_passed is None or metric.preliminary:
                        sample_values_missing = True
                    elif metric.qc_passed == False:
                        if metric.top_up:
                            sample_needs_topup = True
                        else:
                            sample_metrics_failing = True
            if (sample_signoff_needed and sample_metrics_available and sample_run_metrics_available
                    and not sample_values_missing):
                if sample_metrics_failing:
                    signoff_failed_run_samples.append(sample)
                elif sample_needs_topup:
                    signoff_topup_run_samples.append(sample)
                else:
                    signoff_passed_run_samples.append(sample)

        if run_signoff_needed:
            # skip all if run isn't ready for signoff
            if not run_metrics_available or run_values_missing:
                continue
            # sign off run and skip runlibs if run is failing
            if run_metrics_failing:
                decisions.failed_runs.append(run)
                continue
            # run is passed - apply all signoff decisions
            decisions.passed_runs.append(run)
            decisions.passed_samples.extend(signoff_passed_run_samples)
            decisions.topup_samples.extend(signoff_topup_run_samples)
            decisions.failed_samples.extend(signoff_failed_run_samples)
        elif run.qc_state == _QC_STATE_PASSED:
            # run is already passed - apply all sample signoff decisions
            decisions.passed_samples.extend(signoff_passed_run_samples)
            decisions.topup_samples.extend(signoff_topup_run_samples)
            decisions.failed_samples.extend(signoff_failed_run_samples)
    return decisions


def _process_signoffs(mode: AutoverificationMode, decisions: Decisions):
    match mode:
        case AutoverificationMode.DRY_RUN:
            _log_all_signoffs(decisions)
        case _:
            # enabled mode not yet implemented
            # if disabled, we shouldn't havee gotten this far
            raise ValueError(f"Unexpected Autoverification mode: {mode}")


def _log_all_signoffs(decisions: Decisions):
    print("AUTOVERIFICATION DECISIONS")
    _log_signoffs("Passing Runs", [run.name for run in decisions.passed_runs])
    _log_signoffs("Failing Runs", [run.name for run in decisions.failed_runs])
    _log_signoffs("Passing Samples", [sample.oicr_internal_name for sample in decisions.passed_samples])
    _log_signoffs("Top-up Samples", [sample.oicr_internal_name for sample in decisions.topup_samples])
    _log_signoffs("Failing Samples", [sample.oicr_internal_name for sample in decisions.failed_samples])


def _log_signoffs(message: str, item_names: list[str]):
    print(f"* {message}:{' (none)' if not item_names else ''}")
    if item_names:
        for item_name in item_names:
            print(f"  * {item_name}")
