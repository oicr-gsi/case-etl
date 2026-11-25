from datetime import date
from model.pinery import MetricLevel, PreprocessedPinerySample, PreprocessedRun, QcableType, SampleMetric, ThresholdType
from processes.autoverification import Decisions, _make_decisions

"""
Note: There is no need to test all of the different metric types in here because
1. evaluation of those metrics is already tested extensively in test_pinery.py
2. within a metric, autoverification only looks at
   a. the metric level (run/lane vs. sample)
   b. the result of the above-mentioned evaluation (pass/fail/pending)
   c. whether it's a top-up metric
   d. whether the value is preliminary.

To include that one incomplete/failing item causes the expected status:
1. Whenever an incomplete/failing metrics is included, a passing metric should also be included
2. Whenever an incomplete/failing sample is included, a passing sample should also be included
"""

START_DATE_STRING="2026-11-23"
START_DATE = date.fromisoformat(START_DATE_STRING)


def test_run_before_start_date():
    # skip runs completed before the autoverify start date
    run = make_run(1)
    run.completion_date = "2026-11-22"
    sample = make_sample(1, 1, 1)
    add_metric(sample, 1, MetricLevel.RUN, True)
    add_metric(sample, 2, MetricLevel.SAMPLE, True)

    decisions = get_decisions(run, [sample])
    assert len(decisions.passed_runs) == 0
    assert len(decisions.failed_runs) == 0
    assert len(decisions.passed_samples) == 0
    assert len(decisions.failed_samples) == 0
    assert len(decisions.topup_samples) == 0

def test_run_no_samples():
    # never sign off if there are no metrics for the item
    # no samples means no metrics
    run = make_run(1)

    decisions = get_decisions(run, [])
    assert len(decisions.passed_runs) == 0
    assert len(decisions.failed_runs) == 0
    assert len(decisions.passed_samples) == 0
    assert len(decisions.failed_samples) == 0
    assert len(decisions.topup_samples) == 0

def test_run_no_metrics():
    # never sign off if there are no metrics for the item
    run = make_run(1)
    sample = make_sample(1, 1, 1)
    add_metric(sample, 1, MetricLevel.SAMPLE, True)

    decisions = get_decisions(run, [sample])
    assert len(decisions.passed_runs) == 0
    assert len(decisions.failed_runs) == 0
    assert len(decisions.passed_samples) == 0
    assert len(decisions.failed_samples) == 0
    assert len(decisions.topup_samples) == 0

def test_run_no_metrics_on_one_sample():
    # as long as one sample provides run metrics, run signoff can proceed
    # however, a sample that is missing run metrics should not be signed off
    run = make_run(1)
    sample1 = make_sample(1, 1, 1)
    add_metric(sample1, 1, MetricLevel.RUN, True)
    add_metric(sample1, 2, MetricLevel.SAMPLE, True)
    sample2 = make_sample(1, 1, 2)
    add_metric(sample2, 1, MetricLevel.SAMPLE, True)

    decisions = get_decisions(run, [sample1, sample2])
    assert len(decisions.passed_runs) == 1
    assert run in decisions.passed_runs
    assert len(decisions.failed_runs) == 0
    assert len(decisions.passed_samples) == 1
    assert sample1 in decisions.passed_samples
    assert len(decisions.failed_samples) == 0
    assert len(decisions.topup_samples) == 0

def test_run_missing_metric_value():
    # never sign off if a metric value is missing
    run = make_run(1)
    sample1 = make_sample(1, 1, 1)
    add_metric(sample1, 1, MetricLevel.RUN, True)
    add_metric(sample1, 2, MetricLevel.RUN, None) # missing value
    add_metric(sample1, 3, MetricLevel.SAMPLE, True)
    sample2 = make_sample(1, 1, 2)
    add_metric(sample2, 1, MetricLevel.RUN, True)
    add_metric(sample2, 2, MetricLevel.SAMPLE, True)

    decisions = get_decisions(run, [sample1, sample2])
    assert len(decisions.passed_runs) == 0
    assert len(decisions.failed_runs) == 0
    assert len(decisions.passed_samples) == 0
    assert len(decisions.failed_samples) == 0
    assert len(decisions.topup_samples) == 0

def test_pre_passed_run_pre_passed_sample():
    # skip anything already signed off
    run = make_run(1)
    run.qc_state = "Ready"
    sample = make_sample(1, 1, 1)
    sample.qc_state = "Ready"
    add_metric(sample, 1, MetricLevel.RUN, True)
    add_metric(sample, 2, MetricLevel.SAMPLE, True)

    decisions = get_decisions(run, [sample])
    assert len(decisions.passed_runs) == 0
    assert len(decisions.failed_runs) == 0
    assert len(decisions.passed_samples) == 0
    assert len(decisions.failed_samples) == 0
    assert len(decisions.topup_samples) == 0

def test_pre_passed_run_failing_metrics():
    # skip anything already signed off, regardless of consensus
    run = make_run(1)
    run.qc_state = "Ready"
    sample = make_sample(1, 1, 1)
    sample.qc_state = "Ready"
    add_metric(sample, 1, MetricLevel.RUN, True)
    add_metric(sample, 2, MetricLevel.RUN, False)
    add_metric(sample, 3, MetricLevel.SAMPLE, True)

    decisions = get_decisions(run, [sample])
    assert len(decisions.passed_runs) == 0
    assert len(decisions.failed_runs) == 0
    assert len(decisions.passed_samples) == 0
    assert len(decisions.failed_samples) == 0
    assert len(decisions.topup_samples) == 0

def test_pre_passed_sample_failing_metrics():
    # skip anything already signed off, regardless of consensus
    run = make_run(1)
    run.qc_state = "Ready"
    sample = make_sample(1, 1, 1)
    sample.qc_state = "Ready"
    add_metric(sample, 1, MetricLevel.RUN, True)
    add_metric(sample, 2, MetricLevel.SAMPLE, True)
    add_metric(sample, 3, MetricLevel.SAMPLE, False)

    decisions = get_decisions(run, [sample])
    assert len(decisions.passed_runs) == 0
    assert len(decisions.failed_runs) == 0
    assert len(decisions.passed_samples) == 0
    assert len(decisions.failed_samples) == 0
    assert len(decisions.topup_samples) == 0

def test_pre_topup_marked_sample():
    # skip anything already signed off, including "Top-up Required"
    run = make_run(1)
    run.qc_state = "Ready"
    sample = make_sample(1, 1, 1)
    sample.qc_state = "Not Ready"
    sample.qc_reason = "Top-up Required"
    add_metric(sample, 1, MetricLevel.RUN, True)
    add_metric(sample, 2, MetricLevel.SAMPLE, True)

    decisions = get_decisions(run, [sample])
    assert len(decisions.passed_runs) == 0
    assert len(decisions.failed_runs) == 0
    assert len(decisions.passed_samples) == 0
    assert len(decisions.failed_samples) == 0
    assert len(decisions.topup_samples) == 0

def test_passing_run_passing_sample():
    run = make_run(1)
    sample = make_sample(1, 1, 1)
    add_metric(sample, 1, MetricLevel.RUN, True)
    add_metric(sample, 2, MetricLevel.SAMPLE, True)

    decisions = get_decisions(run, [sample])
    assert len(decisions.passed_runs) == 1
    assert run in decisions.passed_runs
    assert len(decisions.failed_runs) == 0
    assert len(decisions.passed_samples) == 1
    assert sample in decisions.passed_samples
    assert len(decisions.failed_samples) == 0
    assert len(decisions.topup_samples) == 0

def test_failing_run_passing_samples():
    # never sign off a sample if the run is failed (sample fail is implicit)
    run = make_run(1)
    sample1 = make_sample(1, 1, 1)
    add_metric(sample1, 1, MetricLevel.RUN, False)
    add_metric(sample1, 2, MetricLevel.RUN, True)
    add_metric(sample1, 3, MetricLevel.SAMPLE, True)
    sample2 = make_sample(1, 1, 2)
    add_metric(sample2, 1, MetricLevel.RUN, True)
    add_metric(sample2, 2, MetricLevel.SAMPLE, True)

    decisions = get_decisions(run, [sample1, sample2])
    assert len(decisions.passed_runs) == 0
    assert len(decisions.failed_runs) == 1
    assert run in decisions.failed_runs
    assert len(decisions.passed_samples) == 0
    assert len(decisions.failed_samples) == 0
    assert len(decisions.topup_samples) == 0

def test_pre_failed_run_passing_sample():
    # never sign off a sample if the run is failed (sample fail is implicit)
    run = make_run(1)
    run.qc_state = "Failed"
    sample = make_sample(1, 1, 1)
    add_metric(sample, 1, MetricLevel.RUN, True)
    add_metric(sample, 2, MetricLevel.SAMPLE, True)

    decisions = get_decisions(run, [sample])
    assert len(decisions.passed_runs) == 0
    assert len(decisions.failed_runs) == 0
    assert len(decisions.passed_samples) == 0
    assert len(decisions.failed_samples) == 0
    assert len(decisions.topup_samples) == 0

def test_passing_run_failing_sample():
    run = make_run(1)
    sample = make_sample(1, 1, 1)
    add_metric(sample, 1, MetricLevel.RUN, True)
    add_metric(sample, 2, MetricLevel.SAMPLE, False)
    add_metric(sample, 3, MetricLevel.SAMPLE, True)

    decisions = get_decisions(run, [sample])
    assert len(decisions.passed_runs) == 1
    assert run in decisions.passed_runs
    assert len(decisions.failed_runs) == 0
    assert len(decisions.passed_samples) == 0
    assert len(decisions.failed_samples) == 1
    assert sample in decisions.failed_samples
    assert len(decisions.topup_samples) == 0

def test_pre_passed_run_passing_sample():
    # if the run is already passed, the sample can be signed off
    run = make_run(1)
    run.qc_state = "Ready"
    sample = make_sample(1, 1, 1)
    add_metric(sample, 1, MetricLevel.RUN, True)
    add_metric(sample, 2, MetricLevel.SAMPLE, True)

    decisions = get_decisions(run, [sample])
    assert len(decisions.passed_runs) == 0
    assert len(decisions.failed_runs) == 0
    assert len(decisions.passed_samples) == 1
    assert sample in decisions.passed_samples
    assert len(decisions.failed_samples) == 0
    assert len(decisions.topup_samples) == 0

def test_sample_no_metrics():
    # never sign off if there are no metrics for the item
    run = make_run(1)
    run.qc_state = "Ready"
    sample = make_sample(1, 1, 1)
    add_metric(sample, 1, MetricLevel.RUN, True)

    decisions = get_decisions(run, [sample])
    assert len(decisions.passed_runs) == 0
    assert len(decisions.failed_runs) == 0
    assert len(decisions.passed_samples) == 0
    assert len(decisions.failed_samples) == 0
    assert len(decisions.topup_samples) == 0

def test_sample_missing_metric_value():
    # never sign off if a metric value is missing
    run = make_run(1)
    run.qc_state = "Ready"
    sample = make_sample(1, 1, 1)
    add_metric(sample, 1, MetricLevel.RUN, True)
    add_metric(sample, 2, MetricLevel.SAMPLE, None) # missing value
    add_metric(sample, 3, MetricLevel.SAMPLE, True)

    decisions = get_decisions(run, [sample])
    assert len(decisions.passed_runs) == 0
    assert len(decisions.failed_runs) == 0
    assert len(decisions.passed_samples) == 0
    assert len(decisions.failed_samples) == 0
    assert len(decisions.topup_samples) == 0

def test_top_up_passing_metric():
    # mark as pass if all metrics are passed
    run = make_run(1)
    run.qc_state = "Ready"
    sample = make_sample(1, 1, 1)
    add_metric(sample, 1, MetricLevel.RUN, True)
    add_metric(sample, 2, MetricLevel.SAMPLE, True)
    add_metric(sample, 3, MetricLevel.SAMPLE, True, top_up=True)

    decisions = get_decisions(run, [sample])
    assert len(decisions.passed_runs) == 0
    assert len(decisions.failed_runs) == 0
    assert len(decisions.passed_samples) == 1
    assert sample in decisions.passed_samples
    assert len(decisions.failed_samples) == 0
    assert len(decisions.topup_samples) == 0

def test_top_up_insufficient_metric():
    # mark top-up required if only a top-up metric is failing
    run = make_run(1)
    run.qc_state = "Ready"
    sample = make_sample(1, 1, 1)
    add_metric(sample, 1, MetricLevel.RUN, True)
    add_metric(sample, 2, MetricLevel.SAMPLE, True)
    add_metric(sample, 3, MetricLevel.SAMPLE, False, top_up=True)

    decisions = get_decisions(run, [sample])
    assert len(decisions.passed_runs) == 0
    assert len(decisions.failed_runs) == 0
    assert len(decisions.passed_samples) == 0
    assert len(decisions.failed_samples) == 0
    assert len(decisions.topup_samples) == 1
    assert sample in decisions.topup_samples

def test_top_up_insufficient_with_failing_metric():
    # a failing metric takes takes status priority over top-up required
    run = make_run(1)
    run.qc_state = "Ready"
    sample = make_sample(1, 1, 1)
    add_metric(sample, 1, MetricLevel.RUN, True)
    add_metric(sample, 2, MetricLevel.SAMPLE, True)
    add_metric(sample, 3, MetricLevel.SAMPLE, False, top_up=True)
    add_metric(sample, 4, MetricLevel.SAMPLE, False)

    decisions = get_decisions(run, [sample])
    assert len(decisions.passed_runs) == 0
    assert len(decisions.failed_runs) == 0
    assert len(decisions.passed_samples) == 0
    assert len(decisions.failed_samples) == 1
    assert sample in decisions.failed_samples
    assert len(decisions.topup_samples) == 0

def test_preliminary_passing_metric():
    # never sign off a sample if there is any preliminary value
    run = make_run(1)
    run.qc_state = "Ready"
    sample = make_sample(1, 1, 1)
    add_metric(sample, 1, MetricLevel.RUN, True)
    add_metric(sample, 2, MetricLevel.SAMPLE, True)
    add_metric(sample, 3, MetricLevel.SAMPLE, True, preliminary=True)

    decisions = get_decisions(run, [sample])
    assert len(decisions.passed_runs) == 0
    assert len(decisions.failed_runs) == 0
    assert len(decisions.passed_samples) == 0
    assert len(decisions.failed_samples) == 0
    assert len(decisions.topup_samples) == 0

def test_preliminary_failing_metric():
    # never sign off a sample if there is any preliminary value
    run = make_run(1)
    run.qc_state = "Ready"
    sample = make_sample(1, 1, 1)
    add_metric(sample, 1, MetricLevel.RUN, True)
    add_metric(sample, 2, MetricLevel.SAMPLE, True)
    add_metric(sample, 3, MetricLevel.SAMPLE, False, preliminary=True)

    decisions = get_decisions(run, [sample])
    assert len(decisions.passed_runs) == 0
    assert len(decisions.failed_runs) == 0
    assert len(decisions.passed_samples) == 0
    assert len(decisions.failed_samples) == 0
    assert len(decisions.topup_samples) == 0

    
def get_decisions(run: PreprocessedRun, samples: list[PreprocessedPinerySample]) -> Decisions:
    runs_by_id = {run.id: run}
    sample_ids_by_run: dict[int, set[PreprocessedPinerySample]] = {}
    samples_by_id = {}
    for sample in samples:
        assert sample.sample_id not in samples_by_id
        if sample.sequencing_run_id not in sample_ids_by_run:
            sample_ids_by_run[sample.sequencing_run_id] = set()
        sample_ids_by_run[sample.sequencing_run_id].add(sample.sample_id)
        samples_by_id[sample.sample_id] = sample
    return _make_decisions(START_DATE, runs_by_id, sample_ids_by_run, samples_by_id)

def make_run(run_id: int) -> PreprocessedRun:
    return PreprocessedRun(
        id=run_id,
        name=f"RUN_{run_id}",
        container_model=None,
        joined_lanes=False,
        sequencing_parameters=None,
        read_length=None,
        read_length_2=None,
        start_date=None,
        completion_date=START_DATE_STRING,
        qc_state="Not Ready",
        qc_user=None,
        qc_date=None,
        data_review_state=None,
        data_review_user=None,
        data_review_date=None
    )

def make_sample(run_id: int, lane_number: int, sample_number: int) -> PreprocessedPinerySample:
    return PreprocessedPinerySample(
        sample_id=f"{run_id}_{lane_number}_LDI{sample_number}",
        donor_id="PROJ_0001",
        parent_id=None,
        child_ids=[],
        project_name="PROJ",
        oicr_internal_name=f"PROJ_0001_{sample_number}",
        external_name=None,
        tissue_material=None,
        tissue_origin=None,
        tissue_type=None,
        purity=None,
        collapsed_coverage=None,
        timepoint=None,
        secondary_id=None,
        nucleic_acid_type=None,
        library_design=None,
        library_kit=None,
        library_size=None,
        barcodes=None,
        targeted_sequencing=None,
        sample_type=None,
        sample_category="sequenced_sample",
        volume=None,
        concentration=None,
        concentration_units=None,
        group_id=None,
        dv200=None,
        tumour_content=None,
        sequencing_type=None,
        sequencing_run_id=run_id,
        sequencing_lane=lane_number,
        qc_state="Not Ready",
        qc_reason="Not Ready",
        qc_note=None,
        qc_user=None,
        qc_date=None,
        data_review_state=None,
        data_review_user=None,
        data_review_date=None,
        entered=None,
        created=None,
        received=None,
        ghost=None,
        requisitioned=None,
        requisition_id=None
    )

def add_metric(sample: PreprocessedPinerySample, metric_number: int, metric_level: MetricLevel,
        qc_passed: bool, top_up: bool = False, preliminary: bool = False):
    metric_name = f"Test Metric {metric_number}"
    assert metric_name not in sample.metrics
    metric = SampleMetric(metric_name, metric_level, ThresholdType.BOOLEAN,
            top_up=top_up, preliminary=preliminary)
    metric.qc_passed = qc_passed
    sample.metrics[metric.name] = metric
