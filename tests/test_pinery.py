from model.pinery import SampleMetric, MetricLevel, MetricType, ThresholdType


def test_add_sample_level_value():
    metric = SampleMetric(MetricType.MEDIAN_INSERT.metric_label, MetricType.MEDIAN_INSERT.metric_level, ThresholdType.GE, 150, None, None)
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
    metric_ge = SampleMetric(MetricType.MEDIAN_INSERT.metric_label, MetricType.MEDIAN_INSERT.metric_level, ThresholdType.GE, 150, None, None)
    assert metric_ge.threshold_max is None
    assert metric_ge.threshold_min == 150
    assert metric_ge.evaluate_qc_passed_for_value(149) is False
    assert metric_ge.evaluate_qc_passed_for_value(150) is True
    assert metric_ge.evaluate_qc_passed_for_value(151) is True
    
    metric_gt = SampleMetric(MetricType.MEDIAN_INSERT.metric_label, MetricType.MEDIAN_INSERT.metric_label, ThresholdType.GT, 150, None, None)
    assert metric_gt.evaluate_qc_passed_for_value(149) is False
    assert metric_gt.evaluate_qc_passed_for_value(150) is False
    assert metric_gt.evaluate_qc_passed_for_value(151) is True

    metric_le = SampleMetric(MetricType.MEDIAN_INSERT.metric_label, MetricType.MEDIAN_INSERT.metric_label, ThresholdType.LE, None, 150, None)
    assert metric_le.evaluate_qc_passed_for_value(149) is True
    assert metric_le.evaluate_qc_passed_for_value(150) is True
    assert metric_le.evaluate_qc_passed_for_value(151) is False

    metric_lt = SampleMetric(MetricType.MEDIAN_INSERT.metric_label, MetricType.MEDIAN_INSERT.metric_label, ThresholdType.LT, None, 150, None)
    assert metric_lt.evaluate_qc_passed_for_value(149) is True
    assert metric_lt.evaluate_qc_passed_for_value(150) is False
    assert metric_lt.evaluate_qc_passed_for_value(151) is False

    metric_bw = SampleMetric(MetricType.MEDIAN_INSERT.metric_label, MetricType.MEDIAN_INSERT.metric_label, ThresholdType.BETWEEN, 150, 160, None)
    assert metric_bw.evaluate_qc_passed_for_value(149) is False
    assert metric_bw.evaluate_qc_passed_for_value(150) is True
    assert metric_bw.evaluate_qc_passed_for_value(155) is True
    assert metric_bw.evaluate_qc_passed_for_value(160) is True
    assert metric_bw.evaluate_qc_passed_for_value(161) is False

def test_evaluate_qc_passed_for_run_values():
    passing_lane_values = {
        1: { "R1": 85, "R2": 84 },
        2: { "R1": 85, "R2": 84 }
    }
    failing_lane_values = {
        1: { "R1": 79, "R2": 84 },
        2: { "R1": 85,
            "percent_over_q30_read2": 84
        }
    }

    q30_metric = SampleMetric(MetricType.BASES_OVER_Q30.metric_label, MetricType.BASES_OVER_Q30.metric_level, ThresholdType.GE, 80, None, None, None, None)
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

    lane_metric = SampleMetric(MetricType.MIN_CLUSTERS_PF.metric_label, MetricType.MIN_CLUSTERS_PF.metric_level, ThresholdType.GE, 80, None, None, None, None)
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
        1: {"clusters_pf": 140000},
        2: {"clusters_pf": 165000},
        3: {"clusters_pf": 150000},
        4: {"clusters_pf": 150000}
    }

    metric = SampleMetric(MetricType.MIN_CLUSTERS_PF.metric_label, MetricType.MIN_CLUSTERS_PF.metric_level, ThresholdType.GE, threshold_val, None, None, None, None, units)
    joined_lanes = False
    metric.add_run_values(605000, run_values_fail_for_separate_pass_for_joined, joined_lanes)
    assert metric.value == (sum(i for v in run_values_fail_for_separate_pass_for_joined.values() for i in v.values()))
    assert metric.qc_passed is False


def test_calculate_qc_passed_for_joined_lanes_with_run_units_passing():
    threshold_min = 200
    metric = SampleMetric(MetricType.MIN_CLUSTERS_PF.metric_label, MetricType.MIN_CLUSTERS_PF.metric_level, ThresholdType.GE, threshold_min, None, None, None, None, "M")
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
    metric = SampleMetric(MetricType.MIN_CLUSTERS_PF.metric_label, MetricType.MIN_CLUSTERS_PF.metric_level, ThresholdType.GE, threshold_min, None, None, None, None, "M")
    run_values = {1: {None: 187498233}}
    value = 187498233
    metric.add_run_values(value, run_values, True)
    assert metric.value == value
    assert metric.threshold_min == threshold_min
    assert metric.qc_passed is False

def test_qc_passed_after_sample_metric_create():
    metric_bool_pass = SampleMetric(MetricType.MEDIAN_INSERT.metric_label, MetricType.MEDIAN_INSERT.metric_level, ThresholdType.BOOLEAN, None, None, None, None, True)
    assert metric_bool_pass.qc_passed is True
    metric_bool_fail = SampleMetric(MetricType.MEDIAN_INSERT.metric_label, MetricType.MEDIAN_INSERT.metric_level, ThresholdType.BOOLEAN, None, None, None, None, False)
    assert metric_bool_fail.qc_passed is False
    metric_bool_unset = SampleMetric(MetricType.MEDIAN_INSERT.metric_label, MetricType.MEDIAN_INSERT.metric_level, ThresholdType.BOOLEAN, None, None, None, None, None)
    assert metric_bool_unset.qc_passed is None

    metric_no_initial_value = SampleMetric(MetricType.MEDIAN_INSERT.metric_label, MetricType.MEDIAN_INSERT.metric_level, ThresholdType.GE, 150, None, None)
    assert metric_no_initial_value.qc_passed is None

    metric_ge_with_value = SampleMetric(MetricType.MEDIAN_INSERT.metric_label, MetricType.MEDIAN_INSERT.metric_level, ThresholdType.GE, 150, None, None, 160)
    assert metric_ge_with_value.qc_passed is True

def test_calculate_qc_passed_for_boolean_threshold_type():
    has_joined_lanes = False
    metric_bool = SampleMetric(MetricType.MEDIAN_INSERT.metric_label, MetricType.MEDIAN_INSERT.metric_level, ThresholdType.BOOLEAN, None, None, None, None, None)
    assert metric_bool.qc_passed is None
    metric_bool.calculate_qc_passed()
    assert metric_bool.qc_passed is None
    assert metric_bool.value is None
    metric_bool.qc_passed = True
    metric_bool.calculate_qc_passed()
    assert metric_bool.qc_passed is True

def test_calculate_qc_passed_for_SOMETHING():
    """something goes here"""

def test_calculate_threshold_joined_lanes_situations():
    clusters_pf_joined_lane_values = {
        1: { "clusters_pf": 89000 },
        2: { "clusters_pf": 90000 }
    }
    clusters_pf_split_lane_values_under = {
        1: { "clusters_pf": 89000 },
        2: { "clusters_pf": 95000 }
    }
    clusters_pf_split_lane_values_over = {
        1: { "clusters_pf": 95000 },
        2: { "clusters_pf": 92000 }
    }

    clusters_pf_metric_3 = SampleMetric(MetricType.MIN_CLUSTERS_PF.metric_label, MetricType.MIN_CLUSTERS_PF.metric_level, ThresholdType.GE, 90, None, False, None, None, "K/lane")
    clusters_pf_metric_3.add_run_values(184000, clusters_pf_split_lane_values_under, False)
    # qc_passed is based off assessing each lane-level value
    assert clusters_pf_metric_3.qc_passed is False

    clusters_pf_metric_4 = SampleMetric(MetricType.MIN_CLUSTERS_PF.metric_label, MetricType.MIN_CLUSTERS_PF.metric_level, ThresholdType.GE, 90, None, False, None, None, "K/lane")
    clusters_pf_metric_4.add_run_values(950000, clusters_pf_split_lane_values_under, False)
    # qc_passed is based off assessing each lane-level value
    assert clusters_pf_metric_4.qc_passed is False

    clusters_pf_metric_5 = SampleMetric(MetricType.MIN_CLUSTERS_PF.metric_label, MetricType.MIN_CLUSTERS_PF.metric_level, ThresholdType.GE, 90, None, False, None, None, "K/lane")
    clusters_pf_metric_5.add_run_values(187000, clusters_pf_split_lane_values_over, False)
    # qc_passed is based off assessing each lane-level value
    assert clusters_pf_metric_5.qc_passed is True
    