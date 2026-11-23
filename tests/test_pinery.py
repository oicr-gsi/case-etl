from model.pinery import SampleMetric, MetricLevel, MetricType, ThresholdType

"""
Goal: Ensure every possible metric is evaluated correctly

for each MetricLevel (RUN, LANE, SAMPLE... and reads within lane)
	for each ThresholdType (BOOLEAN, GT, GE, LE, LT, BETWEEN)
        test pending (no value)
		test passing value
        test failing value
        test on-the-line values (e.g. pass for GE but fail for GT)

Also ensure that lane-level values don't affect run-level metrics and vice-versa
"""

"""
Sample metrics
"""

def test_sample_boolean_metric():
    metric = SampleMetric("Metric", MetricLevel.SAMPLE, ThresholdType.BOOLEAN)
    # pending
    assert metric.qc_passed is None
    # pass (no value; set directly)
    metric.qc_passed = True
    assert metric.qc_passed is True
    # fail (no value; set directly)
    metric.qc_passed = False
    assert metric.qc_passed is False

def test_sample_gt_metrics():
    metric = SampleMetric("Metric", MetricLevel.SAMPLE, ThresholdType.GT, threshold_min=10)
    # pending
    assert metric.qc_passed is None
    # pass
    metric.add_sample_value(20)
    assert metric.value == 20
    assert metric.qc_passed is True
    # fail
    metric.add_sample_value(5)
    assert metric.value == 5
    assert metric.qc_passed is False
    # on the line (fail)
    metric.add_sample_value(10)
    assert metric.value == 10
    assert metric.qc_passed is False

def test_sample_ge_metrics():
    metric = SampleMetric("Metric", MetricLevel.SAMPLE, ThresholdType.GE, threshold_min=10)
    # pending
    assert metric.qc_passed is None
    # pass
    metric.add_sample_value(20)
    assert metric.value == 20
    assert metric.qc_passed is True
    # fail
    metric.add_sample_value(5)
    assert metric.value == 5
    assert metric.qc_passed is False
    # on the line (pass)
    metric.add_sample_value(10)
    assert metric.value == 10
    assert metric.qc_passed is True

def test_sample_le_metrics():
    metric = SampleMetric("Metric", MetricLevel.SAMPLE, ThresholdType.LE, threshold_max=10)
    # pending
    assert metric.qc_passed is None
    # pass
    metric.add_sample_value(5)
    assert metric.value == 5
    assert metric.qc_passed is True
    # fail
    metric.add_sample_value(20)
    assert metric.value == 20
    assert metric.qc_passed is False
    # on the line (pass)
    metric.add_sample_value(10)
    assert metric.value == 10
    assert metric.qc_passed is True

def test_sample_lt_metrics():
    metric = SampleMetric("Metric", MetricLevel.SAMPLE, ThresholdType.LT, threshold_max=10)
    # pending
    assert metric.qc_passed is None
    # pass
    metric.add_sample_value(5)
    assert metric.value == 5
    assert metric.qc_passed is True
    # fail
    metric.add_sample_value(20)
    assert metric.value == 20
    assert metric.qc_passed is False
    # on the line (fail)
    metric.add_sample_value(10)
    assert metric.value == 10
    assert metric.qc_passed is False

def test_sample_between_metrics():
    metric = SampleMetric("Metric", MetricLevel.SAMPLE, ThresholdType.BETWEEN, threshold_min=10, threshold_max=20)
    # pending
    assert metric.qc_passed is None
    # pass
    metric.add_sample_value(15)
    assert metric.value == 15
    assert metric.qc_passed is True
    # fail - above and below
    metric.add_sample_value(5)
    assert metric.value == 5
    assert metric.qc_passed is False
    metric.add_sample_value(25)
    assert metric.value == 25
    assert metric.qc_passed is False
    # on each line (pass)
    metric.add_sample_value(10)
    assert metric.value == 10
    assert metric.qc_passed is True
    metric.add_sample_value(20)
    assert metric.value == 20
    assert metric.qc_passed is True

"""
Run metrics without lane values
"""

def test_run_boolean_metric():
    metric = SampleMetric("Metric", MetricLevel.RUN, ThresholdType.BOOLEAN)
    # pending
    assert metric.qc_passed is None
    # pass (no value; set directly)
    metric.qc_passed = True
    assert metric.qc_passed is True
    # fail (no value; set directly)
    metric.qc_passed = False
    assert metric.qc_passed is False

def test_run_gt_metrics():
    metric = SampleMetric("Metric", MetricLevel.RUN, ThresholdType.GT, threshold_min=10)
    # pending
    assert metric.qc_passed is None
    # pass
    metric.add_run_values(20, None, False)
    assert metric.value == 20
    assert metric.qc_passed is True
    # fail
    metric.add_run_values(5, None, False)
    assert metric.value == 5
    assert metric.qc_passed is False
    # on the line (fail)
    metric.add_run_values(10, None, False)
    assert metric.value == 10
    assert metric.qc_passed is False

def test_run_ge_metrics():
    metric = SampleMetric("Metric", MetricLevel.RUN, ThresholdType.GE, threshold_min=10)
    # pending
    assert metric.qc_passed is None
    # pass
    metric.add_run_values(20, None, False)
    assert metric.value == 20
    assert metric.qc_passed is True
    # fail
    metric.add_run_values(5, None, False)
    assert metric.value == 5
    assert metric.qc_passed is False
    # on the line (pass)
    metric.add_run_values(10, None, False)
    assert metric.value == 10
    assert metric.qc_passed is True

def test_run_le_metrics():
    metric = SampleMetric("Metric", MetricLevel.RUN, ThresholdType.LE, threshold_max=10)
    # pending
    assert metric.qc_passed is None
    # pass
    metric.add_run_values(5, None, False)
    assert metric.value == 5
    assert metric.qc_passed is True
    # fail
    metric.add_run_values(20, None, False)
    assert metric.value == 20
    assert metric.qc_passed is False
    # on the line (pass)
    metric.add_run_values(10, None, False)
    assert metric.value == 10
    assert metric.qc_passed is True

def test_run_lt_metrics():
    metric = SampleMetric("Metric", MetricLevel.RUN, ThresholdType.LT, threshold_max=10)
    # pending
    assert metric.qc_passed is None
    # pass
    metric.add_run_values(5, None, False)
    assert metric.value == 5
    assert metric.qc_passed is True
    # fail
    metric.add_run_values(20, None, False)
    assert metric.value == 20
    assert metric.qc_passed is False
    # on the line (fail)
    metric.add_run_values(10, None, False)
    assert metric.value == 10
    assert metric.qc_passed is False

def test_run_between_metrics():
    metric = SampleMetric("Metric", MetricLevel.RUN, ThresholdType.BETWEEN, threshold_min=10, threshold_max=20)
    # pending
    assert metric.qc_passed is None
    # pass
    metric.add_run_values(15, None, False)
    assert metric.value == 15
    assert metric.qc_passed is True
    # fail - above and below
    metric.add_run_values(5, None, False)
    assert metric.value == 5
    assert metric.qc_passed is False
    metric.add_run_values(25, None, False)
    assert metric.value == 25
    assert metric.qc_passed is False
    # on each line (pass)
    metric.add_run_values(10, None, False)
    assert metric.value == 10
    assert metric.qc_passed is True
    metric.add_run_values(20, None, False)
    assert metric.value == 20
    assert metric.qc_passed is True

"""
Run metrics with lane/read values (should be ignored)
"""

def test_run_gt_metrics_ignore_lane():
    metric = SampleMetric("Metric", MetricLevel.RUN, ThresholdType.GT, threshold_min=10)
    metric.add_run_values(20, make_lane_values(5, 5), False)
    assert metric.value == 20
    assert metric.qc_passed is True
    metric.add_run_values(20, make_read_values(5, 5, 5, 5), False)
    assert metric.value == 20
    assert metric.qc_passed is True

def test_run_ge_metrics_ignore_lane():
    metric = SampleMetric("Metric", MetricLevel.RUN, ThresholdType.GE, threshold_min=10)
    metric.add_run_values(20, make_lane_values(5, 5), False)
    assert metric.value == 20
    assert metric.qc_passed is True
    metric.add_run_values(20, make_read_values(5, 5, 5, 5), False)
    assert metric.value == 20
    assert metric.qc_passed is True

def test_run_le_metrics_ignore_lane():
    metric = SampleMetric("Metric", MetricLevel.RUN, ThresholdType.LE, threshold_max=10)
    metric.add_run_values(5, make_lane_values(15, 15), False)
    assert metric.value == 5
    assert metric.qc_passed is True
    metric.add_run_values(5, make_read_values(15, 15, 15, 15), False)
    assert metric.value == 5
    assert metric.qc_passed is True

def test_run_lt_metrics_ignore_lane():
    metric = SampleMetric("Metric", MetricLevel.RUN, ThresholdType.LT, threshold_max=10)
    metric.add_run_values(5, make_lane_values(15, 15), False)
    assert metric.value == 5
    assert metric.qc_passed is True
    metric.add_run_values(5, make_read_values(15, 15, 15, 15), False)
    assert metric.value == 5
    assert metric.qc_passed is True

def test_run_between_metrics_ignore_lane():
    metric = SampleMetric("Metric", MetricLevel.RUN, ThresholdType.BETWEEN, threshold_min=10, threshold_max=20)
    metric.add_run_values(15, make_lane_values(5, 5), False)
    assert metric.value == 15
    assert metric.qc_passed is True
    metric.add_run_values(15, make_read_values(5, 5, 25, 25), False)
    assert metric.value == 15
    assert metric.qc_passed is True

"""
Lane metrics
"""

def test_lane_boolean_metric():
    metric = SampleMetric("Metric", MetricLevel.LANE, ThresholdType.BOOLEAN)
    # pending
    assert metric.qc_passed is None
    # pass (no value; set directly)
    metric.qc_passed = True
    assert metric.qc_passed is True
    # fail (no value; set directly)
    metric.qc_passed = False
    assert metric.qc_passed is False

def test_lane_gt_metrics():
    metric = SampleMetric("Metric", MetricLevel.LANE, ThresholdType.GT, threshold_min=10)
    # pending
    assert metric.qc_passed is None
    # pass
    lane_values = make_lane_values(20, 20)
    metric.add_run_values(None, lane_values, False)
    assert metric.run_values == lane_values
    assert metric.qc_passed is True
    # fail
    lane_values = make_lane_values(20, 5)
    metric.add_run_values(None, lane_values, False)
    assert metric.run_values == lane_values
    assert metric.qc_passed is False
    # on the line (fail)
    lane_values = make_lane_values(20, 10)
    metric.add_run_values(None, lane_values, False)
    assert metric.run_values == lane_values
    assert metric.qc_passed is False

def test_lane_ge_metrics():
    metric = SampleMetric("Metric", MetricLevel.LANE, ThresholdType.GE, threshold_min=10)
    # pending
    assert metric.qc_passed is None
    # pass
    lane_values = make_lane_values(20, 20)
    metric.add_run_values(None, lane_values, False)
    assert metric.run_values == lane_values
    assert metric.qc_passed is True
    # fail
    lane_values = make_lane_values(20, 5)
    metric.add_run_values(None, lane_values, False)
    assert metric.run_values == lane_values
    assert metric.qc_passed is False
    # on the line (pass)
    lane_values = make_lane_values(20, 10)
    metric.add_run_values(None, lane_values, False)
    assert metric.run_values == lane_values
    assert metric.qc_passed is True

def test_lane_le_metrics():
    metric = SampleMetric("Metric", MetricLevel.LANE, ThresholdType.LE, threshold_max=10)
    # pending
    assert metric.qc_passed is None
    # pass
    lane_values = make_lane_values(5, 5)
    metric.add_run_values(None, lane_values, False)
    assert metric.run_values == lane_values
    assert metric.qc_passed is True
    # fail
    lane_values = make_lane_values(5, 20)
    metric.add_run_values(None, lane_values, False)
    assert metric.run_values == lane_values
    assert metric.qc_passed is False
    # on the line (pass)
    lane_values = make_lane_values(5, 10)
    metric.add_run_values(None, lane_values, False)
    assert metric.run_values == lane_values
    assert metric.qc_passed is True

def test_lane_lt_metrics():
    metric = SampleMetric("Metric", MetricLevel.LANE, ThresholdType.LT, threshold_max=10)
    # pending
    assert metric.qc_passed is None
    # pass
    lane_values = make_lane_values(5, 5)
    metric.add_run_values(None, lane_values, False)
    assert metric.run_values == lane_values
    assert metric.qc_passed is True
    # fail
    lane_values = make_lane_values(5, 20)
    metric.add_run_values(None, lane_values, False)
    assert metric.run_values == lane_values
    assert metric.qc_passed is False
    # on the line (fail)
    lane_values = make_lane_values(5, 10)
    metric.add_run_values(None, lane_values, False)
    assert metric.run_values == lane_values
    assert metric.qc_passed is False

def test_lane_between_metrics():
    metric = SampleMetric("Metric", MetricLevel.LANE, ThresholdType.BETWEEN, threshold_min=10, threshold_max=20)
    # pending
    assert metric.qc_passed is None
    # pass
    lane_values = make_lane_values(15, 15)
    metric.add_run_values(None, lane_values, False)
    assert metric.run_values == lane_values
    assert metric.qc_passed is True
    # fail - above and below
    lane_values = make_lane_values(15, 5)
    metric.add_run_values(None, lane_values, False)
    assert metric.run_values == lane_values
    assert metric.qc_passed is False
    lane_values = make_lane_values(15, 25)
    metric.add_run_values(None, lane_values, False)
    assert metric.run_values == lane_values
    assert metric.qc_passed is False
    # on each line (pass)
    lane_values = make_lane_values(15, 10)
    metric.add_run_values(None, lane_values, False)
    assert metric.run_values == lane_values
    assert metric.qc_passed is True
    lane_values = make_lane_values(15, 20)
    metric.add_run_values(None, lane_values, False)
    assert metric.run_values == lane_values
    assert metric.qc_passed is True

"""
Lane metrics - read level
"""

def test_read_gt_metrics():
    metric = SampleMetric("Metric", MetricLevel.LANE, ThresholdType.GT, threshold_min=10)
    # pending
    assert metric.qc_passed is None
    # pass
    lane_values = make_read_values(20, 20, 20, 20)
    metric.add_run_values(None, lane_values, False)
    assert metric.run_values == lane_values
    assert metric.qc_passed is True
    # fail
    lane_values = make_read_values(20, 20, 20, 5)
    metric.add_run_values(None, lane_values, False)
    assert metric.run_values == lane_values
    assert metric.qc_passed is False
    # on the line (fail)
    lane_values = make_read_values(20, 20, 20, 10)
    metric.add_run_values(None, lane_values, False)
    assert metric.run_values == lane_values
    assert metric.qc_passed is False

def test_read_ge_metrics():
    metric = SampleMetric("Metric", MetricLevel.LANE, ThresholdType.GE, threshold_min=10)
    # pending
    assert metric.qc_passed is None
    # pass
    lane_values = make_read_values(20, 20, 20, 20)
    metric.add_run_values(None, lane_values, False)
    assert metric.run_values == lane_values
    assert metric.qc_passed is True
    # fail
    lane_values = make_read_values(20, 20, 20, 5)
    metric.add_run_values(None, lane_values, False)
    assert metric.run_values == lane_values
    assert metric.qc_passed is False
    # on the line (pass)
    lane_values = make_read_values(20, 20, 20, 10)
    metric.add_run_values(None, lane_values, False)
    assert metric.run_values == lane_values
    assert metric.qc_passed is True

def test_read_le_metrics():
    metric = SampleMetric("Metric", MetricLevel.LANE, ThresholdType.LE, threshold_max=10)
    # pending
    assert metric.qc_passed is None
    # pass
    lane_values = make_read_values(5, 5, 5, 5)
    metric.add_run_values(None, lane_values, False)
    assert metric.run_values == lane_values
    assert metric.qc_passed is True
    # fail
    lane_values = make_read_values(5, 5, 5, 20)
    metric.add_run_values(None, lane_values, False)
    assert metric.run_values == lane_values
    assert metric.qc_passed is False
    # on the line (pass)
    lane_values = make_read_values(5, 5, 5, 10)
    metric.add_run_values(None, lane_values, False)
    assert metric.run_values == lane_values
    assert metric.qc_passed is True

def test_read_lt_metrics():
    metric = SampleMetric("Metric", MetricLevel.LANE, ThresholdType.LT, threshold_max=10)
    # pending
    assert metric.qc_passed is None
    # pass
    lane_values = make_read_values(5, 5, 5, 5)
    metric.add_run_values(None, lane_values, False)
    assert metric.run_values == lane_values
    assert metric.qc_passed is True
    # fail
    lane_values = make_read_values(5, 5, 5, 20)
    metric.add_run_values(None, lane_values, False)
    assert metric.run_values == lane_values
    assert metric.qc_passed is False
    # on the line (fail)
    lane_values = make_read_values(5, 5, 5, 10)
    metric.add_run_values(None, lane_values, False)
    assert metric.run_values == lane_values
    assert metric.qc_passed is False

def test_read_between_metrics():
    metric = SampleMetric("Metric", MetricLevel.LANE, ThresholdType.BETWEEN, threshold_min=10, threshold_max=20)
    # pending
    assert metric.qc_passed is None
    # pass
    lane_values = make_read_values(15, 15, 15, 15)
    metric.add_run_values(None, lane_values, False)
    assert metric.run_values == lane_values
    assert metric.qc_passed is True
    # fail - above and below
    lane_values = make_read_values(15, 15, 15, 5)
    metric.add_run_values(None, lane_values, False)
    assert metric.run_values == lane_values
    assert metric.qc_passed is False
    lane_values = make_read_values(15, 15, 15, 25)
    metric.add_run_values(None, lane_values, False)
    assert metric.run_values == lane_values
    assert metric.qc_passed is False
    # on each line (pass)
    lane_values = make_read_values(15, 15, 15, 10)
    metric.add_run_values(None, lane_values, False)
    assert metric.run_values == lane_values
    assert metric.qc_passed is True
    lane_values = make_read_values(15, 15, 15, 20)
    metric.add_run_values(None, lane_values, False)
    assert metric.run_values == lane_values
    assert metric.qc_passed is True

"""
Lane metrics with run value (should be ignored)
"""

def test_lane_gt_metrics_ignore_run():
    metric = SampleMetric("Metric", MetricLevel.LANE, ThresholdType.GT, threshold_min=10)
    lane_values = make_lane_values(20, 20)
    metric.add_run_values(5, lane_values, False)
    assert metric.value == 5
    assert metric.run_values == lane_values
    assert metric.qc_passed is True

def test_lane_ge_metrics_ignore_run():
    metric = SampleMetric("Metric", MetricLevel.LANE, ThresholdType.GE, threshold_min=10)
    lane_values = make_lane_values(20, 20)
    metric.add_run_values(5, lane_values, False)
    assert metric.value == 5
    assert metric.run_values == lane_values
    assert metric.qc_passed is True

def test_lane_le_metrics_ignore_run():
    metric = SampleMetric("Metric", MetricLevel.LANE, ThresholdType.LE, threshold_max=10)
    lane_values = make_lane_values(5, 5)
    metric.add_run_values(15, lane_values, False)
    assert metric.value == 15
    assert metric.run_values == lane_values
    assert metric.qc_passed is True

def test_lane_lt_metrics_ignore_run():
    metric = SampleMetric("Metric", MetricLevel.LANE, ThresholdType.LT, threshold_max=10)
    lane_values = make_lane_values(5, 5)
    metric.add_run_values(15, lane_values, False)
    assert metric.value == 15
    assert metric.run_values == lane_values
    assert metric.qc_passed is True

def test_lane_between_metrics_ignore_run():
    metric = SampleMetric("Metric", MetricLevel.LANE, ThresholdType.BETWEEN, threshold_min=10, threshold_max=20)
    lane_values = make_lane_values(15, 15)
    metric.add_run_values(5, lane_values, False)
    assert metric.value == 5
    assert metric.run_values == lane_values
    assert metric.qc_passed is True


"""
Misc
"""

def test_add_sample_level_value():
    metric = SampleMetric("Median Insert Size", MetricLevel.SAMPLE, ThresholdType.GE, 150, None)
    assert metric.qc_passed is None

    metric.add_sample_value(150, False)
    assert metric.value == 150
    assert metric.qc_passed is True

    metric.add_sample_value(149, False)
    assert metric.value == 149
    assert metric.qc_passed is False

    metric.value = 151
    assert metric.value == 151
    assert metric.qc_passed is True

def test_evaluate_qc_passed_for_value():
    metric_ge = SampleMetric("Median Insert Size", MetricLevel.SAMPLE, ThresholdType.GE, 150, None)
    assert metric_ge.threshold_max is None
    assert metric_ge.threshold_min == 150
    assert metric_ge._evaluate_qc_passed_for_value(149) is False
    assert metric_ge._evaluate_qc_passed_for_value(150) is True
    assert metric_ge._evaluate_qc_passed_for_value(151) is True
    
    metric_gt = SampleMetric("Median Insert Size", MetricLevel.SAMPLE, ThresholdType.GT, 150, None)
    assert metric_gt._evaluate_qc_passed_for_value(149) is False
    assert metric_gt._evaluate_qc_passed_for_value(150) is False
    assert metric_gt._evaluate_qc_passed_for_value(151) is True

    metric_le = SampleMetric("Median Insert Size", MetricLevel.SAMPLE, ThresholdType.LE, None, 150, None)
    assert metric_le._evaluate_qc_passed_for_value(149) is True
    assert metric_le._evaluate_qc_passed_for_value(150) is True
    assert metric_le._evaluate_qc_passed_for_value(151) is False

    metric_lt = SampleMetric("Median Insert Size", MetricLevel.SAMPLE, ThresholdType.LT, None, 150, None)
    assert metric_lt._evaluate_qc_passed_for_value(149) is True
    assert metric_lt._evaluate_qc_passed_for_value(150) is False
    assert metric_lt._evaluate_qc_passed_for_value(151) is False

    metric_bw = SampleMetric("Median Insert Size", MetricLevel.SAMPLE, ThresholdType.BETWEEN, 150, 160)
    assert metric_bw._evaluate_qc_passed_for_value(149) is False
    assert metric_bw._evaluate_qc_passed_for_value(150) is True
    assert metric_bw._evaluate_qc_passed_for_value(155) is True
    assert metric_bw._evaluate_qc_passed_for_value(160) is True
    assert metric_bw._evaluate_qc_passed_for_value(161) is False

def test_evaluate_qc_passed_for_run_values():
    passing_lane_values = {
        1: { "R1": 85, "R2": 84 },
        2: { "R1": 85, "R2": 84 }
    }
    failing_lane_values = {
        1: { "R1": 79, "R2": 84 },
        2: { "R1": 85, "R2": 84 }
    }

    q30_metric = SampleMetric(MetricType.BASES_OVER_Q30.metric_label, MetricType.BASES_OVER_Q30.metric_level, ThresholdType.GE, 80, None, False, None, None, None)
    control_q30_metric = SampleMetric(MetricType.CONTROL_BASES_OVER_Q30.metric_label, MetricType.CONTROL_BASES_OVER_Q30.metric_level, ThresholdType.GE, 80, None, None, None, None)

    assert q30_metric.qc_passed is None
    q30_metric.add_run_values(82, passing_lane_values, False)
    assert q30_metric.qc_passed is True
    q30_metric.add_run_values(79, failing_lane_values, False)
    assert q30_metric.qc_passed is False
    q30_metric.add_run_values(79, passing_lane_values, False)
    assert q30_metric.qc_passed is False  # only the run-level value matters

    assert control_q30_metric.qc_passed is None
    control_q30_metric.add_run_values(82, None, False)
    assert control_q30_metric.qc_passed is True
    control_q30_metric.add_run_values(79, None, False)
    assert control_q30_metric.qc_passed is False

    lane_metric = SampleMetric(MetricType.MIN_CLUSTERS_PF.metric_label, MetricType.MIN_CLUSTERS_PF.metric_level, ThresholdType.GE, 80, None, False, None, None, None)
    assert lane_metric.qc_passed is None
    lane_metric.add_run_values(1000, passing_lane_values, False)
    assert lane_metric.qc_passed is True
    lane_metric.add_run_values(1000, failing_lane_values, False)
    assert lane_metric.qc_passed is False
    lane_metric.add_run_values(1, passing_lane_values, False)
    assert lane_metric.qc_passed is True  # only the per-lane values matter


def test_calculate_qc_passed_for_run_values_with_per_lane_units():
    threshold_val = 150
    units = "K/lane"
    run_values_fail_for_separate_pass_for_joined = {
        1: {None: 140000},
        2: {None: 165000},
        3: {None: 150000},
        4: {None: 150000}
    }

    metric = SampleMetric(MetricType.MIN_CLUSTERS_PF.metric_label, MetricType.MIN_CLUSTERS_PF.metric_level, ThresholdType.GE, threshold_val, None, False, None, None, None, units)
    joined_lanes = False
    metric.add_run_values(605000, run_values_fail_for_separate_pass_for_joined, joined_lanes)
    assert metric.value == (sum(i for v in run_values_fail_for_separate_pass_for_joined.values() for i in v.values()))
    assert metric.qc_passed is False


def test_calculate_qc_passed_for_joined_lanes_with_run_units_passing():
    threshold_min = 200
    metric = SampleMetric(MetricType.MIN_CLUSTERS_PF.metric_label, MetricType.MIN_CLUSTERS_PF.metric_level, ThresholdType.GE, threshold_min, None, False, None, None, None, "M")
    run_values = {
        1: {None: 127495292},
        2: {None: 125578394},
        3: {None: 126182354},
        4: {None: 124181483}
    }
    metric.add_run_values(503437523, run_values, True)
    assert metric.qc_passed is True

def test_calculate_qc_passed_for_joined_lanes_with_run_units_failing():
    threshold_min = 200
    metric = SampleMetric(MetricType.MIN_CLUSTERS_PF.metric_label, MetricType.MIN_CLUSTERS_PF.metric_level, ThresholdType.GE, threshold_min, None, False, None, None, None, "M")
    run_values = {1: {None: 187498233}}
    value = 187498233
    metric.add_run_values(value, run_values, True)
    assert metric.value == value
    assert metric.threshold_min == threshold_min
    assert metric.qc_passed is False

def test_qc_passed_after_sample_metric_create():
    metric_bool_pass = SampleMetric("Median Insert Size", MetricLevel.SAMPLE, ThresholdType.BOOLEAN, None, None, False, None, None, True)
    assert metric_bool_pass.qc_passed is True
    metric_bool_fail = SampleMetric("Median Insert Size", MetricLevel.SAMPLE, ThresholdType.BOOLEAN, None, None, False, None, None, False)
    assert metric_bool_fail.qc_passed is False
    metric_bool_unset = SampleMetric("Median Insert Size", MetricLevel.SAMPLE, ThresholdType.BOOLEAN, None, None, False, None, None, None)
    assert metric_bool_unset.qc_passed is None

    metric_no_initial_value = SampleMetric("Median Insert Size", MetricLevel.SAMPLE, ThresholdType.GE, 150, None, False, None)
    assert metric_no_initial_value.qc_passed is None

    metric_ge_with_value = SampleMetric("Median Insert Size", MetricLevel.SAMPLE, ThresholdType.GE, 150, None, False, None, 160)
    assert metric_ge_with_value.qc_passed is True

def test_calculate_qc_passed_for_boolean_threshold_type():
    has_joined_lanes = False
    metric_bool = SampleMetric("Median Insert Size", MetricLevel.SAMPLE, ThresholdType.BOOLEAN, None, None, False, None, None, None)
    assert metric_bool.qc_passed is None
    metric_bool._calculate_qc_passed()
    assert metric_bool.qc_passed is None
    assert metric_bool.value is None
    metric_bool.qc_passed = True
    metric_bool._calculate_qc_passed()
    assert metric_bool.qc_passed is True

def test_calculate_threshold_joined_lanes_situations():
    clusters_pf_joined_lane_values = {
        1: { None: 89000 },
        2: { None: 90000 }
    }
    clusters_pf_split_lane_values_under = {
        1: { None: 89000 },
        2: { None: 95000 }
    }
    clusters_pf_split_lane_values_over = {
        1: { None: 95000 },
        2: { None: 92000 }
    }

    clusters_pf_metric_3 = SampleMetric(MetricType.MIN_CLUSTERS_PF.metric_label, MetricType.MIN_CLUSTERS_PF.metric_level, ThresholdType.GE, 90, None, False, False, None, None, "K/lane")
    clusters_pf_metric_3.add_run_values(184000, clusters_pf_split_lane_values_under, False)
    # qc_passed is based off assessing each lane-level value
    assert clusters_pf_metric_3.qc_passed is False

    clusters_pf_metric_4 = SampleMetric(MetricType.MIN_CLUSTERS_PF.metric_label, MetricType.MIN_CLUSTERS_PF.metric_level, ThresholdType.GE, 90, None, False, False, None, None, "K/lane")
    clusters_pf_metric_4.add_run_values(950000, clusters_pf_split_lane_values_under, False)
    # qc_passed is based off assessing each lane-level value
    assert clusters_pf_metric_4.qc_passed is False

    clusters_pf_metric_5 = SampleMetric(MetricType.MIN_CLUSTERS_PF.metric_label, MetricType.MIN_CLUSTERS_PF.metric_level, ThresholdType.GE, 90, None, False, False, None, None, "K/lane")
    clusters_pf_metric_5.add_run_values(187000, clusters_pf_split_lane_values_over, False)
    # qc_passed is based off assessing each lane-level value
    assert clusters_pf_metric_5.qc_passed is True

def make_lane_values(l1, l2):
    return {1: {None: l1}, 2: {None: l2}}

def make_read_values(l1r1, l1r2, l2r1, l2r2):
    return {1: {"R1": l1r1, "R2": l1r2}, 2: {"R1": l2r1, "R2": l2r2}}
    