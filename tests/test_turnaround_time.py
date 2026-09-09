import datetime
from model.pinery import PreprocessedAssayTest, QcableType
from processes.turnaround_time import CASE_STEPS, NON_DELIVERABLE_STEPS, TEST_STEPS, Substep, Timestamp, TimestampType, _calculate_case_days, _calculate_days_spent, _find_pending_step, _sort_timestamps
from unittest.mock import Mock


class ExpectedTotal:
    def __init__(self, test: str, step: QcableType, days: int,
            deliverable_category: str = None, substep: Substep=Substep.TOTAL):
        self.test = test
        self.step = step
        self.days = days
        self.deliverable_category = deliverable_category
        self.substep = substep


def days_since(year: int, month: int, day: int):
    return (TODAY - datetime.date(year, month, day)).days


def make_test_mock(name: str):
    test = Mock()
    test.name = name
    test.extraction_skipped = False
    test.library_preparation_skipped = False
    test.library_qualification_skipped = False
    return test


test_names = ["Normal WG (0)", "Tumour WG (1)"]
tests = [make_test_mock(test_names[0]), make_test_mock(test_names[1])]
deliverable_category_data = "Data Release"
deliverable_category_clinical = "Clinical Report"
TODAY = datetime.date.today()


def test_simple_pending_case_calculations():
    timestamps = [
        Timestamp(TimestampType.STEP_WORK, '2023-01-01', QcableType.RECEIPT_INSPECTION, None),
        Timestamp(TimestampType.STEP_WORK, '2023-01-01', QcableType.RECEIPT_INSPECTION, None),
        Timestamp(TimestampType.STEP_WORK, '2023-01-01', QcableType.RECEIPT_INSPECTION, None),
        Timestamp(TimestampType.STEP_COMPLETE, '2023-01-01', QcableType.RECEIPT_INSPECTION, None),
        Timestamp(TimestampType.STEP_COMPLETE, '2023-01-01', QcableType.RECEIPT_INSPECTION, None),
        Timestamp(TimestampType.STEP_COMPLETE, '2023-01-01', QcableType.RECEIPT_INSPECTION, None),
        Timestamp(TimestampType.STEP_WORK, '2023-01-02', QcableType.EXTRACTION, test_names[0]),
        Timestamp(TimestampType.STEP_COMPLETE, '2023-01-02', QcableType.EXTRACTION, test_names[0]),
        Timestamp(TimestampType.STEP_WORK, '2023-01-02', QcableType.EXTRACTION, test_names[1]),
        Timestamp(TimestampType.STEP_COMPLETE, '2023-01-02', QcableType.EXTRACTION, test_names[1]),
        Timestamp(TimestampType.STEP_WORK, '2023-01-03', QcableType.LIBRARY_PREPARATION, test_names[0]),
        Timestamp(TimestampType.STEP_COMPLETE, '2023-01-03', QcableType.LIBRARY_PREPARATION, test_names[0]),
        Timestamp(TimestampType.STEP_WORK, '2023-01-04', QcableType.LIBRARY_PREPARATION, test_names[1]),
        Timestamp(TimestampType.STEP_COMPLETE, '2023-01-05', QcableType.LIBRARY_PREPARATION, test_names[1]),
    ]
    totals = [
        ExpectedTotal(None, QcableType.RECEIPT_INSPECTION, 0),
        ExpectedTotal(test_names[0], QcableType.EXTRACTION, 1),
        ExpectedTotal(test_names[1], QcableType.EXTRACTION, 1),
        ExpectedTotal(test_names[0], QcableType.LIBRARY_PREPARATION, 1),
        ExpectedTotal(test_names[1], QcableType.LIBRARY_PREPARATION, 3),
        ExpectedTotal(test_names[0], QcableType.LIBRARY_QUALIFICATION, days_since(2023, 1, 3)),
        ExpectedTotal(test_names[1], QcableType.LIBRARY_QUALIFICATION, days_since(2023, 1, 5)),
        ExpectedTotal(test_names[0], QcableType.FULL_DEPTH_SEQUENCING, 0),
        ExpectedTotal(test_names[1], QcableType.FULL_DEPTH_SEQUENCING, 0),
        ExpectedTotal(None, QcableType.ANALYSIS_REVIEW, 0),
        ExpectedTotal(None, QcableType.RELEASE_APPROVAL, 0),
        ExpectedTotal(None, QcableType.RELEASE, 0),
    ]
    assert_calculations(datetime.date(2023, 1, 1), False, timestamps, totals, 0)


def test_simple_completed_case_calculations_with_all_substeps():
    timestamps = [
        Timestamp(TimestampType.STEP_WORK, '2023-01-01', QcableType.RECEIPT_INSPECTION, None),
        Timestamp(TimestampType.STEP_WORK, '2023-01-01', QcableType.RECEIPT_INSPECTION, None),
        Timestamp(TimestampType.STEP_WORK, '2023-01-01', QcableType.RECEIPT_INSPECTION, None),
        Timestamp(TimestampType.STEP_COMPLETE, '2023-01-01', QcableType.RECEIPT_INSPECTION, None),
        Timestamp(TimestampType.STEP_COMPLETE, '2023-01-01', QcableType.RECEIPT_INSPECTION, None),
        Timestamp(TimestampType.STEP_COMPLETE, '2023-01-01', QcableType.RECEIPT_INSPECTION, None),
        Timestamp(TimestampType.STEP_WORK, '2023-01-02', QcableType.EXTRACTION, test_names[0]),
        Timestamp(TimestampType.STEP_COMPLETE, '2023-01-02', QcableType.EXTRACTION, test_names[0]),
        Timestamp(TimestampType.STEP_WORK, '2023-01-02', QcableType.EXTRACTION, test_names[1]),
        Timestamp(TimestampType.STEP_COMPLETE, '2023-01-02', QcableType.EXTRACTION, test_names[1]),
        Timestamp(TimestampType.STEP_WORK, '2023-01-03', QcableType.LIBRARY_PREPARATION, test_names[0]),
        Timestamp(TimestampType.STEP_COMPLETE, '2023-01-03', QcableType.LIBRARY_PREPARATION, test_names[0]),
        Timestamp(TimestampType.STEP_WORK, '2023-01-04', QcableType.LIBRARY_PREPARATION, test_names[1]),
        Timestamp(TimestampType.STEP_COMPLETE, '2023-01-05', QcableType.LIBRARY_PREPARATION, test_names[1]),
        Timestamp(TimestampType.STEP_WORK, '2023-01-06', QcableType.LIBRARY_QUALIFICATION, test_names[0], substep=Substep.LOADING_SEQUENCER),
        Timestamp(TimestampType.STEP_WORK, '2023-01-06', QcableType.LIBRARY_QUALIFICATION, test_names[1], substep=Substep.LOADING_SEQUENCER),
        Timestamp(TimestampType.STEP_WORK, '2023-01-07', QcableType.LIBRARY_QUALIFICATION, test_names[0], substep=Substep.SEQUENCING),
        Timestamp(TimestampType.STEP_WORK, '2023-01-07', QcableType.LIBRARY_QUALIFICATION, test_names[1], substep=Substep.SEQUENCING),
        Timestamp(TimestampType.STEP_WORK, '2023-01-08', QcableType.LIBRARY_QUALIFICATION, test_names[0], substep=Substep.QC),
        Timestamp(TimestampType.STEP_WORK, '2023-01-08', QcableType.LIBRARY_QUALIFICATION, test_names[1], substep=Substep.QC),
        Timestamp(TimestampType.STEP_COMPLETE, '2023-01-08', QcableType.LIBRARY_QUALIFICATION, test_names[0], substep=Substep.QC),
        Timestamp(TimestampType.STEP_COMPLETE, '2023-01-08', QcableType.LIBRARY_QUALIFICATION, test_names[1], substep=Substep.QC),
        Timestamp(TimestampType.STEP_WORK, '2023-01-10', QcableType.FULL_DEPTH_SEQUENCING, test_names[0], substep=Substep.LOADING_SEQUENCER),
        Timestamp(TimestampType.STEP_WORK, '2023-01-10', QcableType.FULL_DEPTH_SEQUENCING, test_names[1], substep=Substep.LOADING_SEQUENCER),
        Timestamp(TimestampType.STEP_WORK, '2023-01-10', QcableType.FULL_DEPTH_SEQUENCING, test_names[0], substep=Substep.SEQUENCING),
        Timestamp(TimestampType.STEP_WORK, '2023-01-10', QcableType.FULL_DEPTH_SEQUENCING, test_names[1], substep=Substep.SEQUENCING),
        Timestamp(TimestampType.STEP_WORK, '2023-01-11', QcableType.FULL_DEPTH_SEQUENCING, test_names[0], substep=Substep.QC),
        Timestamp(TimestampType.STEP_COMPLETE, '2023-01-11', QcableType.FULL_DEPTH_SEQUENCING, test_names[0], substep=Substep.QC),
        Timestamp(TimestampType.STEP_WORK, '2023-01-12', QcableType.FULL_DEPTH_SEQUENCING, test_names[1], substep=Substep.QC),
        Timestamp(TimestampType.STEP_COMPLETE, '2023-01-12', QcableType.FULL_DEPTH_SEQUENCING, test_names[1], substep=Substep.QC),
        Timestamp(TimestampType.STEP_COMPLETE, '2023-01-13', QcableType.ANALYSIS_REVIEW, None, deliverable_category_data),
        Timestamp(TimestampType.STEP_COMPLETE, '2023-01-15', QcableType.RELEASE_APPROVAL, None, deliverable_category_data),
        Timestamp(TimestampType.STEP_COMPLETE, '2023-01-18', QcableType.RELEASE, None, deliverable_category_data),
    ]
    totals = [
        ExpectedTotal(None, QcableType.RECEIPT_INSPECTION, 0),
        ExpectedTotal(test_names[0], QcableType.EXTRACTION, 1),
        ExpectedTotal(test_names[1], QcableType.EXTRACTION, 1),
        ExpectedTotal(test_names[0], QcableType.LIBRARY_PREPARATION, 1),
        ExpectedTotal(test_names[1], QcableType.LIBRARY_PREPARATION, 3),
        ExpectedTotal(test_names[0], QcableType.LIBRARY_QUALIFICATION, 5),
        ExpectedTotal(test_names[0], QcableType.LIBRARY_QUALIFICATION, 3, substep=Substep.LOADING_SEQUENCER),
        ExpectedTotal(test_names[0], QcableType.LIBRARY_QUALIFICATION, 1, substep=Substep.SEQUENCING),
        ExpectedTotal(test_names[0], QcableType.LIBRARY_QUALIFICATION, 1, substep=Substep.QC),
        ExpectedTotal(test_names[1], QcableType.LIBRARY_QUALIFICATION, 3),
        ExpectedTotal(test_names[1], QcableType.LIBRARY_QUALIFICATION, 1, substep=Substep.LOADING_SEQUENCER),
        ExpectedTotal(test_names[1], QcableType.LIBRARY_QUALIFICATION, 1, substep=Substep.SEQUENCING),
        ExpectedTotal(test_names[1], QcableType.LIBRARY_QUALIFICATION, 1, substep=Substep.QC),
        ExpectedTotal(test_names[0], QcableType.FULL_DEPTH_SEQUENCING, 3),
        ExpectedTotal(test_names[0], QcableType.FULL_DEPTH_SEQUENCING, 2, substep=Substep.LOADING_SEQUENCER),
        ExpectedTotal(test_names[0], QcableType.FULL_DEPTH_SEQUENCING, 0, substep=Substep.SEQUENCING),
        ExpectedTotal(test_names[0], QcableType.FULL_DEPTH_SEQUENCING, 1, substep=Substep.QC),
        ExpectedTotal(test_names[1], QcableType.FULL_DEPTH_SEQUENCING, 4),
        ExpectedTotal(test_names[1], QcableType.FULL_DEPTH_SEQUENCING, 2, substep=Substep.LOADING_SEQUENCER),
        ExpectedTotal(test_names[1], QcableType.FULL_DEPTH_SEQUENCING, 0, substep=Substep.SEQUENCING),
        ExpectedTotal(test_names[1], QcableType.FULL_DEPTH_SEQUENCING, 2, substep=Substep.QC),
        ExpectedTotal(None, QcableType.ANALYSIS_REVIEW, 1, deliverable_category_data),
        ExpectedTotal(None, QcableType.RELEASE_APPROVAL, 2, deliverable_category_data),
        ExpectedTotal(None, QcableType.RELEASE, 3, deliverable_category_data),
        ExpectedTotal(None, QcableType.ANALYSIS_REVIEW, 1),
        ExpectedTotal(None, QcableType.RELEASE_APPROVAL, 2),
        ExpectedTotal(None, QcableType.RELEASE, 3),
    ]
    assert_calculations(datetime.date(2023, 1, 1), False, timestamps, totals, 0,
            datetime.date(2023, 1, 18))


def test_partial_completion_calculations():
    timestamps = [
        Timestamp(TimestampType.STEP_WORK, '2023-01-01', QcableType.RECEIPT_INSPECTION, None),
        Timestamp(TimestampType.STEP_WORK, '2023-01-01', QcableType.RECEIPT_INSPECTION, None),
        Timestamp(TimestampType.STEP_WORK, '2023-01-01', QcableType.RECEIPT_INSPECTION, None),
        Timestamp(TimestampType.STEP_COMPLETE, '2023-01-01', QcableType.RECEIPT_INSPECTION, None),
        Timestamp(TimestampType.STEP_COMPLETE, '2023-01-01', QcableType.RECEIPT_INSPECTION, None),
        Timestamp(TimestampType.STEP_COMPLETE, '2023-01-01', QcableType.RECEIPT_INSPECTION, None),
        Timestamp(TimestampType.STEP_WORK, '2023-01-02', QcableType.EXTRACTION, test_names[0]),
        Timestamp(TimestampType.STEP_COMPLETE, '2023-01-02', QcableType.EXTRACTION, test_names[0]),
        Timestamp(TimestampType.STEP_WORK, '2023-01-02', QcableType.EXTRACTION, test_names[1]),
        Timestamp(TimestampType.STEP_COMPLETE, '2023-01-02', QcableType.EXTRACTION, test_names[1]),
        Timestamp(TimestampType.STEP_WORK, '2023-01-03', QcableType.LIBRARY_PREPARATION, test_names[0]),
        Timestamp(TimestampType.STEP_COMPLETE, '2023-01-03', QcableType.LIBRARY_PREPARATION, test_names[0]),
        Timestamp(TimestampType.STEP_WORK, '2023-01-04', QcableType.LIBRARY_PREPARATION, test_names[1]),
        Timestamp(TimestampType.STEP_COMPLETE, '2023-01-05', QcableType.LIBRARY_PREPARATION, test_names[1]),
        Timestamp(TimestampType.STEP_WORK, '2023-01-06', QcableType.LIBRARY_QUALIFICATION, test_names[0]),
        Timestamp(TimestampType.STEP_WORK, '2023-01-06', QcableType.LIBRARY_QUALIFICATION, test_names[1]),
        Timestamp(TimestampType.STEP_COMPLETE, '2023-01-08', QcableType.LIBRARY_QUALIFICATION, test_names[0]),
        Timestamp(TimestampType.STEP_COMPLETE, '2023-01-08', QcableType.LIBRARY_QUALIFICATION, test_names[1]),
        Timestamp(TimestampType.STEP_WORK, '2023-01-10', QcableType.FULL_DEPTH_SEQUENCING, test_names[0]),
        Timestamp(TimestampType.STEP_WORK, '2023-01-10', QcableType.FULL_DEPTH_SEQUENCING, test_names[1]),
        Timestamp(TimestampType.STEP_COMPLETE, '2023-01-11', QcableType.FULL_DEPTH_SEQUENCING, test_names[0]),
    ]
    totals = [
        ExpectedTotal(None, QcableType.RECEIPT_INSPECTION, 0),
        ExpectedTotal(test_names[0], QcableType.EXTRACTION, 1),
        ExpectedTotal(test_names[1], QcableType.EXTRACTION, 1),
        ExpectedTotal(test_names[0], QcableType.LIBRARY_PREPARATION, 1),
        ExpectedTotal(test_names[1], QcableType.LIBRARY_PREPARATION, 3),
        ExpectedTotal(test_names[0], QcableType.LIBRARY_QUALIFICATION, 5),
        ExpectedTotal(test_names[1], QcableType.LIBRARY_QUALIFICATION, 3),
        ExpectedTotal(test_names[0], QcableType.FULL_DEPTH_SEQUENCING, 3),
        ExpectedTotal(test_names[1], QcableType.FULL_DEPTH_SEQUENCING, days_since(2023, 1, 8)),
        ExpectedTotal(None, QcableType.ANALYSIS_REVIEW, 0),
        ExpectedTotal(None, QcableType.RELEASE_APPROVAL, 0),
        ExpectedTotal(None, QcableType.RELEASE, 0),
    ]
    assert_calculations(datetime.date(2023, 1, 1), False, timestamps, totals, 0)


def test_forgotten_qc_timespoint():
    timestamps = [
        Timestamp(TimestampType.STEP_WORK, '2023-01-01', QcableType.RECEIPT_INSPECTION, None),
        Timestamp(TimestampType.STEP_WORK, '2023-01-01', QcableType.RECEIPT_INSPECTION, None),
        Timestamp(TimestampType.STEP_WORK, '2023-01-01', QcableType.RECEIPT_INSPECTION, None),
        Timestamp(TimestampType.STEP_COMPLETE, '2023-01-01', QcableType.RECEIPT_INSPECTION, None),
        Timestamp(TimestampType.STEP_COMPLETE, '2023-01-01', QcableType.RECEIPT_INSPECTION, None),
        Timestamp(TimestampType.STEP_COMPLETE, '2023-01-01', QcableType.RECEIPT_INSPECTION, None),
        Timestamp(TimestampType.STEP_WORK, '2023-01-02', QcableType.EXTRACTION, test_names[0]),
        Timestamp(TimestampType.STEP_COMPLETE, '2023-01-02', QcableType.EXTRACTION, test_names[0]),
        Timestamp(TimestampType.STEP_WORK, '2023-01-02', QcableType.EXTRACTION, test_names[1]),
        Timestamp(TimestampType.STEP_WORK, '2023-01-03', QcableType.LIBRARY_PREPARATION, test_names[0]),
        Timestamp(TimestampType.STEP_COMPLETE, '2023-01-03', QcableType.LIBRARY_PREPARATION, test_names[0]),
        Timestamp(TimestampType.STEP_WORK, '2023-01-04', QcableType.LIBRARY_PREPARATION, test_names[1]),
        Timestamp(TimestampType.STEP_COMPLETE, '2023-01-05', QcableType.LIBRARY_PREPARATION, test_names[1]),

        # set QC way later - days since previous timestamp will be allocated to extraction
        Timestamp(TimestampType.STEP_COMPLETE, '2023-01-12', QcableType.EXTRACTION, test_names[1]),
    ]
    totals = [
        ExpectedTotal(None, QcableType.RECEIPT_INSPECTION, 0),
        ExpectedTotal(test_names[0], QcableType.EXTRACTION, 1),
        ExpectedTotal(test_names[1], QcableType.EXTRACTION, 8),
        ExpectedTotal(test_names[0], QcableType.LIBRARY_PREPARATION, 1),
        ExpectedTotal(test_names[1], QcableType.LIBRARY_PREPARATION, 3),
        ExpectedTotal(test_names[0], QcableType.LIBRARY_QUALIFICATION, days_since(2023, 1, 3)),
        ExpectedTotal(test_names[1], QcableType.LIBRARY_QUALIFICATION, days_since(2023, 1, 12)),
        ExpectedTotal(test_names[0], QcableType.FULL_DEPTH_SEQUENCING, 0),
        ExpectedTotal(test_names[1], QcableType.FULL_DEPTH_SEQUENCING, 0),
        ExpectedTotal(None, QcableType.ANALYSIS_REVIEW, 0),
        ExpectedTotal(None, QcableType.RELEASE_APPROVAL, 0),
        ExpectedTotal(None, QcableType.RELEASE, 0),
    ]
    assert_calculations(datetime.date(2023, 1, 1), False, timestamps, totals, 0)


def test_resubmission_calculations():
    timestamps = [
        Timestamp(TimestampType.STEP_WORK, '2023-01-01', QcableType.RECEIPT_INSPECTION, None),
        Timestamp(TimestampType.STEP_WORK, '2023-01-01', QcableType.RECEIPT_INSPECTION, None),
        Timestamp(TimestampType.STEP_WORK, '2023-01-01', QcableType.RECEIPT_INSPECTION, None),
        Timestamp(TimestampType.STEP_COMPLETE, '2023-01-01', QcableType.RECEIPT_INSPECTION, None),
        Timestamp(TimestampType.STEP_COMPLETE, '2023-01-01', QcableType.RECEIPT_INSPECTION, None),
        Timestamp(TimestampType.STEP_COMPLETE, '2023-01-01', QcableType.RECEIPT_INSPECTION, None),
        Timestamp(TimestampType.STEP_WORK, '2023-01-02', QcableType.EXTRACTION, test_names[0]),
        Timestamp(TimestampType.STEP_COMPLETE, '2023-01-02', QcableType.EXTRACTION, test_names[0]),
        Timestamp(TimestampType.STEP_WORK, '2023-01-02', QcableType.EXTRACTION, test_names[1]),
        # extraction on test 1 fails here ^
        # work continues on test 0
        Timestamp(TimestampType.STEP_WORK, '2023-01-05', QcableType.LIBRARY_PREPARATION, test_names[0]),
        Timestamp(TimestampType.STEP_COMPLETE, '2023-01-06', QcableType.LIBRARY_PREPARATION, test_names[0]),
        
        # case start time resets on new sample receipt, so nothing before this is counted
        Timestamp(TimestampType.STEP_WORK, '2023-01-13', QcableType.RECEIPT_INSPECTION, None),
        Timestamp(TimestampType.STEP_COMPLETE, '2023-01-13', QcableType.RECEIPT_INSPECTION, None),
        Timestamp(TimestampType.STEP_WORK, '2023-01-14', QcableType.EXTRACTION, test_names[1]),
        Timestamp(TimestampType.STEP_COMPLETE, '2023-01-14', QcableType.EXTRACTION, test_names[1]),

        Timestamp(TimestampType.STEP_WORK, '2023-01-16', QcableType.LIBRARY_PREPARATION, test_names[1]),
        Timestamp(TimestampType.STEP_COMPLETE, '2023-01-17', QcableType.LIBRARY_PREPARATION, test_names[1]),
    ]
    totals = [
        ExpectedTotal(None, QcableType.RECEIPT_INSPECTION, 0),
        ExpectedTotal(test_names[0], QcableType.EXTRACTION, 0),
        ExpectedTotal(test_names[1], QcableType.EXTRACTION, 1),
        ExpectedTotal(test_names[0], QcableType.LIBRARY_PREPARATION, 0),
        ExpectedTotal(test_names[1], QcableType.LIBRARY_PREPARATION, 3),
        ExpectedTotal(test_names[0], QcableType.LIBRARY_QUALIFICATION, days_since(2023, 1, 13)),
        ExpectedTotal(test_names[1], QcableType.LIBRARY_QUALIFICATION, days_since(2023, 1, 17)),
        ExpectedTotal(test_names[0], QcableType.FULL_DEPTH_SEQUENCING, 0),
        ExpectedTotal(test_names[1], QcableType.FULL_DEPTH_SEQUENCING, 0),
        ExpectedTotal(None, QcableType.ANALYSIS_REVIEW, 0),
        ExpectedTotal(None, QcableType.RELEASE_APPROVAL, 0),
        ExpectedTotal(None, QcableType.RELEASE, 0),
    ]
    assert_calculations(datetime.date(2023, 1, 13), False, timestamps, totals, 0)


def test_pause_in_place_calculations():
    # no work completed during pause; no new samples; no repeated steps
    timestamps = [
        Timestamp(TimestampType.STEP_WORK, '2023-01-01', QcableType.RECEIPT_INSPECTION, None),
        Timestamp(TimestampType.STEP_WORK, '2023-01-01', QcableType.RECEIPT_INSPECTION, None),
        Timestamp(TimestampType.STEP_WORK, '2023-01-01', QcableType.RECEIPT_INSPECTION, None),
        Timestamp(TimestampType.STEP_COMPLETE, '2023-01-01', QcableType.RECEIPT_INSPECTION, None),
        Timestamp(TimestampType.STEP_COMPLETE, '2023-01-01', QcableType.RECEIPT_INSPECTION, None),
        Timestamp(TimestampType.STEP_COMPLETE, '2023-01-01', QcableType.RECEIPT_INSPECTION, None),
        Timestamp(TimestampType.STEP_WORK, '2023-01-02', QcableType.EXTRACTION, test_names[0]),
        Timestamp(TimestampType.STEP_COMPLETE, '2023-01-02', QcableType.EXTRACTION, test_names[0]),
        Timestamp(TimestampType.STEP_WORK, '2023-01-02', QcableType.EXTRACTION, test_names[1]),
        Timestamp(TimestampType.STEP_COMPLETE, '2023-01-02', QcableType.EXTRACTION, test_names[1]),
        
        Timestamp(TimestampType.PAUSE, '2023-01-03', None, None),
        Timestamp(TimestampType.RESUME, '2023-01-12', None, None),
        
        Timestamp(TimestampType.STEP_WORK, '2023-01-13', QcableType.LIBRARY_PREPARATION, test_names[0]),
        Timestamp(TimestampType.STEP_COMPLETE, '2023-01-13', QcableType.LIBRARY_PREPARATION, test_names[0]),
        Timestamp(TimestampType.STEP_WORK, '2023-01-14', QcableType.LIBRARY_PREPARATION, test_names[1]),
        Timestamp(TimestampType.STEP_COMPLETE, '2023-01-15', QcableType.LIBRARY_PREPARATION, test_names[1]),
    ]
    totals = [
        ExpectedTotal(None, QcableType.RECEIPT_INSPECTION, 0),
        ExpectedTotal(test_names[0], QcableType.EXTRACTION, 1),
        ExpectedTotal(test_names[1], QcableType.EXTRACTION, 1),
        ExpectedTotal(test_names[0], QcableType.LIBRARY_PREPARATION, 2),
        ExpectedTotal(test_names[1], QcableType.LIBRARY_PREPARATION, 4),
        ExpectedTotal(test_names[0], QcableType.LIBRARY_QUALIFICATION, days_since(2023, 1, 13)),
        ExpectedTotal(test_names[1], QcableType.LIBRARY_QUALIFICATION, days_since(2023, 1, 15)),
        ExpectedTotal(test_names[0], QcableType.FULL_DEPTH_SEQUENCING, 0),
        ExpectedTotal(test_names[1], QcableType.FULL_DEPTH_SEQUENCING, 0),
        ExpectedTotal(None, QcableType.ANALYSIS_REVIEW, 0),
        ExpectedTotal(None, QcableType.RELEASE_APPROVAL, 0),
        ExpectedTotal(None, QcableType.RELEASE, 0),
    ]
    assert_calculations(datetime.date(2023, 1, 1), False, timestamps, totals, 9)


def test_work_during_pause_calculations():
    timestamps = [
        Timestamp(TimestampType.STEP_WORK, '2023-01-01', QcableType.RECEIPT_INSPECTION, None),
        Timestamp(TimestampType.STEP_WORK, '2023-01-01', QcableType.RECEIPT_INSPECTION, None),
        Timestamp(TimestampType.STEP_WORK, '2023-01-01', QcableType.RECEIPT_INSPECTION, None),
        Timestamp(TimestampType.STEP_COMPLETE, '2023-01-01', QcableType.RECEIPT_INSPECTION, None),
        Timestamp(TimestampType.STEP_COMPLETE, '2023-01-01', QcableType.RECEIPT_INSPECTION, None),
        Timestamp(TimestampType.STEP_COMPLETE, '2023-01-01', QcableType.RECEIPT_INSPECTION, None),
        Timestamp(TimestampType.STEP_WORK, '2023-01-02', QcableType.EXTRACTION, test_names[0]),
        Timestamp(TimestampType.STEP_COMPLETE, '2023-01-02', QcableType.EXTRACTION, test_names[0]),
        Timestamp(TimestampType.STEP_WORK, '2023-01-02', QcableType.EXTRACTION, test_names[1]),
        Timestamp(TimestampType.STEP_COMPLETE, '2023-01-02', QcableType.EXTRACTION, test_names[1]),
        
        # test 0 library prep and qualification completed during pause - shouldn't be counted
        Timestamp(TimestampType.PAUSE, '2023-01-03', None, None),
        Timestamp(TimestampType.STEP_WORK, '2023-01-05', QcableType.LIBRARY_PREPARATION, test_names[0]),
        Timestamp(TimestampType.STEP_COMPLETE, '2023-01-05', QcableType.LIBRARY_PREPARATION, test_names[0]),
        Timestamp(TimestampType.STEP_WORK, '2023-01-06', QcableType.LIBRARY_QUALIFICATION, test_names[0]),
        Timestamp(TimestampType.STEP_COMPLETE, '2023-01-08', QcableType.LIBRARY_QUALIFICATION, test_names[0]),
        Timestamp(TimestampType.RESUME, '2023-01-12', None, None),

        Timestamp(TimestampType.STEP_WORK, '2023-01-14', QcableType.LIBRARY_PREPARATION, test_names[1]),
        Timestamp(TimestampType.STEP_COMPLETE, '2023-01-15', QcableType.LIBRARY_PREPARATION, test_names[1]),
    ]
    totals = [
        ExpectedTotal(None, QcableType.RECEIPT_INSPECTION, 0),
        ExpectedTotal(test_names[0], QcableType.EXTRACTION, 1),
        ExpectedTotal(test_names[1], QcableType.EXTRACTION, 1),
        ExpectedTotal(test_names[0], QcableType.LIBRARY_PREPARATION, 1),
        ExpectedTotal(test_names[1], QcableType.LIBRARY_PREPARATION, 4),
        ExpectedTotal(test_names[0], QcableType.LIBRARY_QUALIFICATION, 0),
        ExpectedTotal(test_names[1], QcableType.LIBRARY_QUALIFICATION, days_since(2023, 1, 15)),
        ExpectedTotal(test_names[0], QcableType.FULL_DEPTH_SEQUENCING, days_since(2023, 1, 12)),
        ExpectedTotal(test_names[1], QcableType.FULL_DEPTH_SEQUENCING, 0),
        ExpectedTotal(None, QcableType.ANALYSIS_REVIEW, 0),
        ExpectedTotal(None, QcableType.RELEASE_APPROVAL, 0),
        ExpectedTotal(None, QcableType.RELEASE, 0),
    ]
    assert_calculations(datetime.date(2023, 1, 1), False, timestamps, totals, 9)


def test_pause_before_resubmission_calculations():
    # pause to wait for new sample; no work completed during pause; receipt+extraction repeated
    timestamps = [
        Timestamp(TimestampType.STEP_WORK, '2023-01-01', QcableType.RECEIPT_INSPECTION, None),
        Timestamp(TimestampType.STEP_WORK, '2023-01-01', QcableType.RECEIPT_INSPECTION, None),
        Timestamp(TimestampType.STEP_WORK, '2023-01-01', QcableType.RECEIPT_INSPECTION, None),
        Timestamp(TimestampType.STEP_COMPLETE, '2023-01-01', QcableType.RECEIPT_INSPECTION, None),
        Timestamp(TimestampType.STEP_COMPLETE, '2023-01-01', QcableType.RECEIPT_INSPECTION, None),
        Timestamp(TimestampType.STEP_COMPLETE, '2023-01-01', QcableType.RECEIPT_INSPECTION, None),
        Timestamp(TimestampType.STEP_WORK, '2023-01-02', QcableType.EXTRACTION, test_names[0]),
        Timestamp(TimestampType.STEP_COMPLETE, '2023-01-02', QcableType.EXTRACTION, test_names[0]),
        Timestamp(TimestampType.STEP_WORK, '2023-01-02', QcableType.EXTRACTION, test_names[1]),
        
        Timestamp(TimestampType.PAUSE, '2023-01-03', None, None),
        Timestamp(TimestampType.RESUME, '2023-01-12', None, None),
        
        # note: new receipt counts as time for both tests
        Timestamp(TimestampType.STEP_WORK, '2023-01-13', QcableType.RECEIPT_INSPECTION, None),
        Timestamp(TimestampType.STEP_COMPLETE, '2023-01-13', QcableType.RECEIPT_INSPECTION, None),
        Timestamp(TimestampType.STEP_WORK, '2023-01-14', QcableType.EXTRACTION, test_names[1]),
        Timestamp(TimestampType.STEP_COMPLETE, '2023-01-14', QcableType.EXTRACTION, test_names[1]),

        Timestamp(TimestampType.STEP_WORK, '2023-01-15', QcableType.LIBRARY_PREPARATION, test_names[0]),
        Timestamp(TimestampType.STEP_COMPLETE, '2023-01-15', QcableType.LIBRARY_PREPARATION, test_names[0]),
        Timestamp(TimestampType.STEP_WORK, '2023-01-16', QcableType.LIBRARY_PREPARATION, test_names[1]),
        Timestamp(TimestampType.STEP_COMPLETE, '2023-01-17', QcableType.LIBRARY_PREPARATION, test_names[1]),
    ]
    totals = [
        ExpectedTotal(None, QcableType.RECEIPT_INSPECTION, 0),
        ExpectedTotal(test_names[0], QcableType.EXTRACTION, 0),
        ExpectedTotal(test_names[1], QcableType.EXTRACTION, 1),
        ExpectedTotal(test_names[0], QcableType.LIBRARY_PREPARATION, 2),
        ExpectedTotal(test_names[1], QcableType.LIBRARY_PREPARATION, 3),
        ExpectedTotal(test_names[0], QcableType.LIBRARY_QUALIFICATION, days_since(2023, 1, 15)),
        ExpectedTotal(test_names[1], QcableType.LIBRARY_QUALIFICATION, days_since(2023, 1, 17)),
        ExpectedTotal(test_names[0], QcableType.FULL_DEPTH_SEQUENCING, 0),
        ExpectedTotal(test_names[1], QcableType.FULL_DEPTH_SEQUENCING, 0),
        ExpectedTotal(None, QcableType.ANALYSIS_REVIEW, 0),
        ExpectedTotal(None, QcableType.RELEASE_APPROVAL, 0),
        ExpectedTotal(None, QcableType.RELEASE, 0),
    ]
    assert_calculations(datetime.date(2023, 1, 13), False, timestamps, totals, 0)


def test_pause_overlapping_resubmission():
    timestamps = [
        Timestamp(TimestampType.STEP_WORK, '2023-01-01', QcableType.RECEIPT_INSPECTION, None),
        Timestamp(TimestampType.STEP_WORK, '2023-01-01', QcableType.RECEIPT_INSPECTION, None),
        Timestamp(TimestampType.STEP_WORK, '2023-01-01', QcableType.RECEIPT_INSPECTION, None),
        Timestamp(TimestampType.STEP_COMPLETE, '2023-01-01', QcableType.RECEIPT_INSPECTION, None),
        Timestamp(TimestampType.STEP_COMPLETE, '2023-01-01', QcableType.RECEIPT_INSPECTION, None),
        Timestamp(TimestampType.STEP_COMPLETE, '2023-01-01', QcableType.RECEIPT_INSPECTION, None),
        Timestamp(TimestampType.STEP_WORK, '2023-01-02', QcableType.EXTRACTION, test_names[0]),
        Timestamp(TimestampType.STEP_COMPLETE, '2023-01-02', QcableType.EXTRACTION, test_names[0]),
        Timestamp(TimestampType.STEP_WORK, '2023-01-02', QcableType.EXTRACTION, test_names[1]),
        
        Timestamp(TimestampType.PAUSE, '2023-01-03', None, None),
        # new sample received and extraction completed while paused
        # should reset case start, but not count time during pause
        # pause days should only be counted after case start (latest receipt)
        Timestamp(TimestampType.STEP_WORK, '2023-01-13', QcableType.RECEIPT_INSPECTION, None),
        Timestamp(TimestampType.STEP_COMPLETE, '2023-01-14', QcableType.RECEIPT_INSPECTION, None),
        Timestamp(TimestampType.STEP_WORK, '2023-01-15', QcableType.EXTRACTION, test_names[1]),
        Timestamp(TimestampType.STEP_COMPLETE, '2023-01-15', QcableType.EXTRACTION, test_names[1]),
        Timestamp(TimestampType.RESUME, '2023-01-17', None, None),


        Timestamp(TimestampType.STEP_WORK, '2023-01-18', QcableType.LIBRARY_PREPARATION, test_names[0]),
        Timestamp(TimestampType.STEP_COMPLETE, '2023-01-18', QcableType.LIBRARY_PREPARATION, test_names[0]),
        Timestamp(TimestampType.STEP_WORK, '2023-01-19', QcableType.LIBRARY_PREPARATION, test_names[1]),
        Timestamp(TimestampType.STEP_COMPLETE, '2023-01-20', QcableType.LIBRARY_PREPARATION, test_names[1]),
    ]
    totals = [
        ExpectedTotal(None, QcableType.RECEIPT_INSPECTION, 0),
        ExpectedTotal(test_names[0], QcableType.EXTRACTION, 0),
        ExpectedTotal(test_names[1], QcableType.EXTRACTION, 0),
        ExpectedTotal(test_names[0], QcableType.LIBRARY_PREPARATION, 1),
        ExpectedTotal(test_names[1], QcableType.LIBRARY_PREPARATION, 3),
        ExpectedTotal(test_names[0], QcableType.LIBRARY_QUALIFICATION, days_since(2023, 1, 18)),
        ExpectedTotal(test_names[1], QcableType.LIBRARY_QUALIFICATION, days_since(2023, 1, 20)),
        ExpectedTotal(test_names[0], QcableType.FULL_DEPTH_SEQUENCING, 0),
        ExpectedTotal(test_names[1], QcableType.FULL_DEPTH_SEQUENCING, 0),
        ExpectedTotal(None, QcableType.ANALYSIS_REVIEW, 0),
        ExpectedTotal(None, QcableType.RELEASE_APPROVAL, 0),
        ExpectedTotal(None, QcableType.RELEASE, 0),
    ]
    assert_calculations(datetime.date(2023, 1, 13), False, timestamps, totals, 4)


def test_stopped_case():
    # When a case is stopped, we skip all remaining steps before release approval
    timestamps = [
        Timestamp(TimestampType.STEP_WORK, '2023-01-01', QcableType.RECEIPT_INSPECTION, None),
        Timestamp(TimestampType.STEP_WORK, '2023-01-01', QcableType.RECEIPT_INSPECTION, None),
        Timestamp(TimestampType.STEP_WORK, '2023-01-01', QcableType.RECEIPT_INSPECTION, None),
        Timestamp(TimestampType.STEP_COMPLETE, '2023-01-01', QcableType.RECEIPT_INSPECTION, None),
        Timestamp(TimestampType.STEP_COMPLETE, '2023-01-01', QcableType.RECEIPT_INSPECTION, None),
        Timestamp(TimestampType.STEP_COMPLETE, '2023-01-01', QcableType.RECEIPT_INSPECTION, None),
        Timestamp(TimestampType.STEP_WORK, '2023-01-02', QcableType.EXTRACTION, test_names[0]),
        Timestamp(TimestampType.STEP_COMPLETE, '2023-01-02', QcableType.EXTRACTION, test_names[0]),
        Timestamp(TimestampType.STEP_WORK, '2023-01-02', QcableType.EXTRACTION, test_names[1]),
        Timestamp(TimestampType.STEP_COMPLETE, '2023-01-02', QcableType.EXTRACTION, test_names[1]),
        Timestamp(TimestampType.STEP_WORK, '2023-01-03', QcableType.LIBRARY_PREPARATION, test_names[0]),
        Timestamp(TimestampType.STEP_COMPLETE, '2023-01-03', QcableType.LIBRARY_PREPARATION, test_names[0]),
        Timestamp(TimestampType.STEP_WORK, '2023-01-04', QcableType.LIBRARY_PREPARATION, test_names[1]),
        Timestamp(TimestampType.STEP_COMPLETE, '2023-01-05', QcableType.LIBRARY_PREPARATION, test_names[1]),
    ]
    totals = [
        ExpectedTotal(None, QcableType.RECEIPT_INSPECTION, 0),
        ExpectedTotal(test_names[0], QcableType.EXTRACTION, 1),
        ExpectedTotal(test_names[1], QcableType.EXTRACTION, 1),
        ExpectedTotal(test_names[0], QcableType.LIBRARY_PREPARATION, 1),
        ExpectedTotal(test_names[1], QcableType.LIBRARY_PREPARATION, 3),
        ExpectedTotal(test_names[0], QcableType.LIBRARY_QUALIFICATION, 0),
        ExpectedTotal(test_names[1], QcableType.LIBRARY_QUALIFICATION, 0),
        ExpectedTotal(test_names[0], QcableType.FULL_DEPTH_SEQUENCING, 0),
        ExpectedTotal(test_names[1], QcableType.FULL_DEPTH_SEQUENCING, 0),
        ExpectedTotal(None, QcableType.ANALYSIS_REVIEW, 0, deliverable_category_data),
        ExpectedTotal(None, QcableType.RELEASE_APPROVAL, days_since(2023, 1, 5), deliverable_category_data),
        ExpectedTotal(None, QcableType.RELEASE, 0, deliverable_category_data),
        ExpectedTotal(None, QcableType.ANALYSIS_REVIEW, 0),
        ExpectedTotal(None, QcableType.RELEASE_APPROVAL, days_since(2023, 1, 5)),
        ExpectedTotal(None, QcableType.RELEASE, 0),
    ]
    assert_calculations(datetime.date(2023, 1, 1), True, timestamps, totals, 0)


def test_exempt_dates_calculation():
    timestamps = [
        Timestamp(TimestampType.STEP_WORK, '2023-01-01', QcableType.RECEIPT_INSPECTION, None),
        Timestamp(TimestampType.STEP_WORK, '2023-01-01', QcableType.RECEIPT_INSPECTION, None),
        Timestamp(TimestampType.STEP_WORK, '2023-01-01', QcableType.RECEIPT_INSPECTION, None),
        Timestamp(TimestampType.STEP_COMPLETE, '2023-01-01', QcableType.RECEIPT_INSPECTION, None),
        Timestamp(TimestampType.STEP_COMPLETE, '2023-01-01', QcableType.RECEIPT_INSPECTION, None),
        Timestamp(TimestampType.STEP_COMPLETE, '2023-01-01', QcableType.RECEIPT_INSPECTION, None),
        Timestamp(TimestampType.STEP_WORK, '2023-01-02', QcableType.EXTRACTION, test_names[0]),
        Timestamp(TimestampType.STEP_COMPLETE, '2023-01-02', QcableType.EXTRACTION, test_names[0]),
        Timestamp(TimestampType.STEP_WORK, '2023-01-02', QcableType.EXTRACTION, test_names[1]),
        Timestamp(TimestampType.STEP_COMPLETE, '2023-01-02', QcableType.EXTRACTION, test_names[1]),
        Timestamp(TimestampType.STEP_WORK, '2023-01-09', QcableType.LIBRARY_PREPARATION, test_names[0]),
        Timestamp(TimestampType.STEP_COMPLETE, '2023-01-09', QcableType.LIBRARY_PREPARATION, test_names[0]),
        Timestamp(TimestampType.STEP_WORK, '2023-01-10', QcableType.LIBRARY_PREPARATION, test_names[1]),
        Timestamp(TimestampType.STEP_COMPLETE, '2023-01-11', QcableType.LIBRARY_PREPARATION, test_names[1]),
    ]
    totals = [
        ExpectedTotal(None, QcableType.RECEIPT_INSPECTION, 0),
        ExpectedTotal(test_names[0], QcableType.EXTRACTION, 1),
        ExpectedTotal(test_names[1], QcableType.EXTRACTION, 1),
        ExpectedTotal(test_names[0], QcableType.LIBRARY_PREPARATION, 4),
        ExpectedTotal(test_names[1], QcableType.LIBRARY_PREPARATION, 6),
        ExpectedTotal(test_names[0], QcableType.LIBRARY_QUALIFICATION, days_since(2023, 1, 9)),
        ExpectedTotal(test_names[1], QcableType.LIBRARY_QUALIFICATION, days_since(2023, 1, 11)),
        ExpectedTotal(test_names[0], QcableType.FULL_DEPTH_SEQUENCING, 0),
        ExpectedTotal(test_names[1], QcableType.FULL_DEPTH_SEQUENCING, 0),
        ExpectedTotal(None, QcableType.ANALYSIS_REVIEW, 0),
        ExpectedTotal(None, QcableType.RELEASE_APPROVAL, 0),
        ExpectedTotal(None, QcableType.RELEASE, 0),
    ]
    exempt_dates = [datetime.date(2023, 1, 5), datetime.date(2023, 1, 6), datetime.date(2023, 1, 7)]
    assert_calculations(datetime.date(2023, 1, 1), False, timestamps, totals, 0, exempt_dates=exempt_dates)


def test_multiple_deliverables_calculations():
    timestamps = [
        Timestamp(TimestampType.STEP_WORK, '2023-01-01', QcableType.RECEIPT_INSPECTION, None),
        Timestamp(TimestampType.STEP_WORK, '2023-01-01', QcableType.RECEIPT_INSPECTION, None),
        Timestamp(TimestampType.STEP_WORK, '2023-01-01', QcableType.RECEIPT_INSPECTION, None),
        Timestamp(TimestampType.STEP_COMPLETE, '2023-01-01', QcableType.RECEIPT_INSPECTION, None),
        Timestamp(TimestampType.STEP_COMPLETE, '2023-01-01', QcableType.RECEIPT_INSPECTION, None),
        Timestamp(TimestampType.STEP_COMPLETE, '2023-01-01', QcableType.RECEIPT_INSPECTION, None),
        Timestamp(TimestampType.STEP_WORK, '2023-01-02', QcableType.EXTRACTION, test_names[0]),
        Timestamp(TimestampType.STEP_COMPLETE, '2023-01-02', QcableType.EXTRACTION, test_names[0]),
        Timestamp(TimestampType.STEP_WORK, '2023-01-02', QcableType.EXTRACTION, test_names[1]),
        Timestamp(TimestampType.STEP_COMPLETE, '2023-01-02', QcableType.EXTRACTION, test_names[1]),
        Timestamp(TimestampType.STEP_WORK, '2023-01-03', QcableType.LIBRARY_PREPARATION, test_names[0]),
        Timestamp(TimestampType.STEP_COMPLETE, '2023-01-03', QcableType.LIBRARY_PREPARATION, test_names[0]),
        Timestamp(TimestampType.STEP_WORK, '2023-01-04', QcableType.LIBRARY_PREPARATION, test_names[1]),
        Timestamp(TimestampType.STEP_COMPLETE, '2023-01-05', QcableType.LIBRARY_PREPARATION, test_names[1]),
        Timestamp(TimestampType.STEP_WORK, '2023-01-06', QcableType.LIBRARY_QUALIFICATION, test_names[0]),
        Timestamp(TimestampType.STEP_WORK, '2023-01-06', QcableType.LIBRARY_QUALIFICATION, test_names[1]),
        Timestamp(TimestampType.STEP_COMPLETE, '2023-01-08', QcableType.LIBRARY_QUALIFICATION, test_names[0]),
        Timestamp(TimestampType.STEP_COMPLETE, '2023-01-08', QcableType.LIBRARY_QUALIFICATION, test_names[1]),
        Timestamp(TimestampType.STEP_WORK, '2023-01-10', QcableType.FULL_DEPTH_SEQUENCING, test_names[0]),
        Timestamp(TimestampType.STEP_WORK, '2023-01-10', QcableType.FULL_DEPTH_SEQUENCING, test_names[1]),
        Timestamp(TimestampType.STEP_COMPLETE, '2023-01-11', QcableType.FULL_DEPTH_SEQUENCING, test_names[0]),
        Timestamp(TimestampType.STEP_COMPLETE, '2023-01-12', QcableType.FULL_DEPTH_SEQUENCING, test_names[1]),
        Timestamp(TimestampType.STEP_COMPLETE, '2023-01-13', QcableType.ANALYSIS_REVIEW, None, deliverable_category_clinical),
        Timestamp(TimestampType.STEP_COMPLETE, '2023-01-15', QcableType.RELEASE_APPROVAL, None, deliverable_category_clinical),
        Timestamp(TimestampType.STEP_COMPLETE, '2023-01-18', QcableType.RELEASE, None, deliverable_category_clinical),
        Timestamp(TimestampType.STEP_COMPLETE, '2023-01-25', QcableType.ANALYSIS_REVIEW, None, deliverable_category_data),
    ]
    totals = [
        ExpectedTotal(None, QcableType.RECEIPT_INSPECTION, 0),
        ExpectedTotal(test_names[0], QcableType.EXTRACTION, 1),
        ExpectedTotal(test_names[1], QcableType.EXTRACTION, 1),
        ExpectedTotal(test_names[0], QcableType.LIBRARY_PREPARATION, 1),
        ExpectedTotal(test_names[1], QcableType.LIBRARY_PREPARATION, 3),
        ExpectedTotal(test_names[0], QcableType.LIBRARY_QUALIFICATION, 5),
        ExpectedTotal(test_names[1], QcableType.LIBRARY_QUALIFICATION, 3),
        ExpectedTotal(test_names[0], QcableType.FULL_DEPTH_SEQUENCING, 3),
        ExpectedTotal(test_names[1], QcableType.FULL_DEPTH_SEQUENCING, 4),
        ExpectedTotal(None, QcableType.ANALYSIS_REVIEW, 1, deliverable_category_clinical),
        ExpectedTotal(None, QcableType.RELEASE_APPROVAL, 2, deliverable_category_clinical),
        ExpectedTotal(None, QcableType.RELEASE, 3, deliverable_category_clinical),
        ExpectedTotal(None, QcableType.ANALYSIS_REVIEW, 13, deliverable_category_data),
        ExpectedTotal(None, QcableType.RELEASE_APPROVAL, days_since(2023, 1, 25), deliverable_category_data),
        ExpectedTotal(None, QcableType.RELEASE, 0, deliverable_category_data),
        ExpectedTotal(None, QcableType.ANALYSIS_REVIEW, 8),
        ExpectedTotal(None, QcableType.RELEASE_APPROVAL, 2 + days_since(2023, 1, 25)),
        ExpectedTotal(None, QcableType.RELEASE, 3),
    ]
    assert_calculations(datetime.date(2023, 1, 1), False, timestamps, totals, 0,
            datetime.date(2023, 1, 18))


def assert_calculations(start_date, case_stopped, timestamps, expected_totals: list[ExpectedTotal], expected_pause_days,
        completion_date = None, exempt_dates = None):
    """
    Tests all TAT calculations for a list of timestamps

    Parameters
    ----------
    start_date: datetime.date
        Start date for the case. Should be the date of the latest sample receipt
    case_stopped: bool
        Whether or not the case is stopped
    timestamps: list[Timestamp]
        All Timestamps for the case. These should already be sorted correctly (see _sort_timestamps)
    expected_totals: list[ExpectedTotal]
        Describes the expected case and test days spent per QC step
    expected_pause_days: int
        Number of days the case should be considered paused. This should exclude any days before the
        start date
    completion_date: datetime.date: optional
        Completion date of the case if completed
    exempt_dates: list[datetime.date]: optional
        Dates to exclude from TAT calculation. Must be between start_date and completion_date as it
        is assumed that the full length will be subtracted from case days spent
    """

    exempt_dates = exempt_dates or []
    deliverable_types = {x.deliverable_category for x in expected_totals if x.deliverable_category != None}
    case_days_per_gate = _calculate_days_spent(start_date, case_stopped, timestamps, test_names, None, deliverable_types, None, exempt_dates)
    test0_days_per_gate = _calculate_days_spent(start_date, case_stopped, timestamps, test_names, tests[0], deliverable_types, None, exempt_dates)
    test1_days_per_gate = _calculate_days_spent(start_date, case_stopped, timestamps, test_names, tests[1], deliverable_types, None, exempt_dates)
    if deliverable_category_data in deliverable_types:
        data_days_per_gate = _calculate_days_spent(start_date, case_stopped, timestamps, test_names, None, deliverable_types, deliverable_category_data, exempt_dates)
    if deliverable_category_clinical in deliverable_types:
        clinical_days_per_gate = _calculate_days_spent(start_date, case_stopped, timestamps, test_names, None, deliverable_types, deliverable_category_clinical, exempt_dates)
    case_days_spent, pause_days = _calculate_case_days(start_date, timestamps,
            find_completed_date(timestamps), exempt_dates)

    errors = []
    for total in expected_totals:
        if total.test == None:
            if total.deliverable_category == None:
                values = case_days_per_gate
            elif total.deliverable_category == deliverable_category_data:
                values = data_days_per_gate
            elif total.deliverable_category == deliverable_category_clinical:
                values = clinical_days_per_gate
        elif total.test == test_names[0]:
            values = test0_days_per_gate
        elif total.test == test_names[1]:
            values = test1_days_per_gate
        else:
            raise RuntimeError(f"Unexpected test name: {total.test}")
        if not total.step in values:
            if total.days > 0:
                errors.append(f"Missing value for {total.test or total.deliverable_category or 'Case'} {total.step.name}")
        elif values[total.step][total.substep] != total.days:
            errors.append(f"Value for {total.test or total.deliverable_category or 'Case'} {total.step.name}/{total.substep.name} ({values[total.step][total.substep]}) doesn't match expected ({total.days})")
    
    assert not errors, "Errors:\n" + "\n".join(errors)
    case_wall_time = ((completion_date - start_date).days if completion_date
            else days_since(start_date.year, start_date.month, start_date.day))
    assert case_days_spent == case_wall_time - pause_days - (len(exempt_dates) if exempt_dates else 0)
    assert pause_days == expected_pause_days


def find_completed_date(timestamps):
    for timestamp in timestamps:
        if timestamp.step == QcableType.RELEASE and timestamp.type == TimestampType.STEP_COMPLETE:
            return timestamp.date
    return None


def test_sort_timestamps_by_date():
    timestamps_ordered = [
        Timestamp(TimestampType.STEP_WORK, '2023-01-01', QcableType.RECEIPT_INSPECTION, None),
        Timestamp(TimestampType.STEP_WORK, '2023-01-02', QcableType.RECEIPT_INSPECTION, None),
        Timestamp(TimestampType.STEP_WORK, '2023-02-01', QcableType.RECEIPT_INSPECTION, None),
        Timestamp(TimestampType.STEP_WORK, '2023-02-02', QcableType.RECEIPT_INSPECTION, None),
        Timestamp(TimestampType.STEP_WORK, '2023-03-01', QcableType.RECEIPT_INSPECTION, None),
    ]
    timestamps_modified = [timestamps_ordered[3], timestamps_ordered[0], timestamps_ordered[1],
            timestamps_ordered[4], timestamps_ordered[2]]
    assert timestamps_modified != timestamps_ordered
    
    _sort_timestamps(timestamps_modified)
    assert timestamps_modified == timestamps_ordered


def test_sort_timestamps_by_type():
    timestamps_ordered = [
        Timestamp(TimestampType.RESUME, '2023-01-01', QcableType.RECEIPT_INSPECTION, None),
        Timestamp(TimestampType.STEP_WORK, '2023-01-01', QcableType.RECEIPT_INSPECTION, None),
        Timestamp(TimestampType.STEP_COMPLETE, '2023-01-01', QcableType.RECEIPT_INSPECTION, None),
        Timestamp(TimestampType.PAUSE, '2023-01-01', QcableType.RECEIPT_INSPECTION, None),
    ]
    timestamps_modified = [timestamps_ordered[3], timestamps_ordered[1], timestamps_ordered[2],
            timestamps_ordered[0]]
    assert timestamps_modified != timestamps_ordered
    
    _sort_timestamps(timestamps_modified)
    assert timestamps_modified == timestamps_ordered


def test_sort_timestamps_by_step():
    timestamps_ordered = [
        Timestamp(TimestampType.STEP_WORK, '2023-01-01', QcableType.RECEIPT_INSPECTION, None),
        Timestamp(TimestampType.STEP_WORK, '2023-01-01', QcableType.EXTRACTION, None),
        Timestamp(TimestampType.STEP_WORK, '2023-01-01', QcableType.LIBRARY_PREPARATION, None),
        Timestamp(TimestampType.STEP_WORK, '2023-01-01', QcableType.LIBRARY_QUALIFICATION, None),
        Timestamp(TimestampType.STEP_WORK, '2023-01-01', QcableType.FULL_DEPTH_SEQUENCING, None),
        Timestamp(TimestampType.STEP_WORK, '2023-01-01', QcableType.ANALYSIS_REVIEW, None, deliverable_category_data),
        Timestamp(TimestampType.STEP_WORK, '2023-01-01', QcableType.RELEASE_APPROVAL, None, deliverable_category_data),
        Timestamp(TimestampType.STEP_WORK, '2023-01-01', QcableType.RELEASE, None, deliverable_category_data),
    ]
    timestamps_modified = [timestamps_ordered[4], timestamps_ordered[1], timestamps_ordered[5],
            timestamps_ordered[0], timestamps_ordered[7], timestamps_ordered[6],
            timestamps_ordered[3], timestamps_ordered[2]]
    assert timestamps_modified != timestamps_ordered
    
    _sort_timestamps(timestamps_modified)
    assert timestamps_modified == timestamps_ordered


def test_sort_timestamps_by_step_pauses():
    timestamps_ordered = [
        Timestamp(TimestampType.RESUME, '2023-01-01', None, None),
        Timestamp(TimestampType.STEP_WORK, '2023-01-01', QcableType.EXTRACTION, None),
        Timestamp(TimestampType.STEP_COMPLETE, '2023-01-01', QcableType.EXTRACTION, None),
        Timestamp(TimestampType.PAUSE, '2023-01-01', None, None),
    ]
    timestamps_modified = [timestamps_ordered[2], timestamps_ordered[3], timestamps_ordered[1],
            timestamps_ordered[0]]
    assert timestamps_modified != timestamps_ordered

    _sort_timestamps(timestamps_modified)
    assert timestamps_modified == timestamps_ordered


def test_find_pending_receipt_step():
    test = _mock_assay_test("test1")
    test_names = [test.name]
    deliverable_types = [deliverable_category_data]
    completed_steps_per_test = {
        None: [],
        test.name: []
    }
    completed_steps_per_deliverable_type = {
        deliverable_types[0]: []
    }

    assert QcableType.RECEIPT_INSPECTION == _find_pending_step(completed_steps_per_test, completed_steps_per_deliverable_type, test_names, None, deliverable_types, None, TEST_STEPS, False)
    assert None == _find_pending_step(completed_steps_per_test, completed_steps_per_deliverable_type, test_names, test, deliverable_types, None, CASE_STEPS, False)
    assert None == _find_pending_step(completed_steps_per_test, completed_steps_per_deliverable_type, test_names, None, deliverable_types, deliverable_types[0], NON_DELIVERABLE_STEPS, False)


def test_find_pending_test_steps():
    tests = [
        _mock_assay_test("test1"),
        _mock_assay_test("test2"),
        _mock_assay_test("test3"),
        _mock_assay_test("test4"),
        _mock_assay_test("test5")
    ]
    test_names = [x.name for x in tests]
    deliverable_types = [deliverable_category_data, deliverable_category_clinical]
    completed_steps_per_test = {
        None: [QcableType.RECEIPT_INSPECTION],
        test_names[0]: [],
        test_names[1]: [QcableType.EXTRACTION],
        test_names[2]: [QcableType.EXTRACTION, QcableType.LIBRARY_PREPARATION],
        test_names[3]: [QcableType.EXTRACTION, QcableType.LIBRARY_PREPARATION, QcableType.LIBRARY_QUALIFICATION],
        test_names[4]: [QcableType.EXTRACTION, QcableType.LIBRARY_PREPARATION, QcableType.LIBRARY_QUALIFICATION, QcableType.FULL_DEPTH_SEQUENCING]
    }
    completed_steps_per_deliverable_type = {
        deliverable_types[0]: [],
        deliverable_types[1]: []
    }
    
    assert None == _find_pending_step(completed_steps_per_test, completed_steps_per_deliverable_type, test_names, None, deliverable_types, None, TEST_STEPS, False)
    assert QcableType.EXTRACTION == _find_pending_step(completed_steps_per_test, completed_steps_per_deliverable_type, test_names, tests[0], deliverable_types, None, CASE_STEPS, False)
    assert QcableType.LIBRARY_PREPARATION == _find_pending_step(completed_steps_per_test, completed_steps_per_deliverable_type, test_names, tests[1], deliverable_types, None, CASE_STEPS, False)
    assert QcableType.LIBRARY_QUALIFICATION == _find_pending_step(completed_steps_per_test, completed_steps_per_deliverable_type, test_names, tests[2], deliverable_types, None, CASE_STEPS, False)
    assert QcableType.FULL_DEPTH_SEQUENCING == _find_pending_step(completed_steps_per_test, completed_steps_per_deliverable_type, test_names, tests[3], deliverable_types, None, CASE_STEPS, False)
    assert None == _find_pending_step(completed_steps_per_test, completed_steps_per_deliverable_type, test_names, tests[4], deliverable_types, None, CASE_STEPS, False)
    assert None == _find_pending_step(completed_steps_per_test, completed_steps_per_deliverable_type, test_names, None, deliverable_types, deliverable_types[0], NON_DELIVERABLE_STEPS, False)
    assert None == _find_pending_step(completed_steps_per_test, completed_steps_per_deliverable_type, test_names, None, deliverable_types, deliverable_types[1], NON_DELIVERABLE_STEPS, False)


def test_find_pending_skipped_steps():
    tests = [
        _mock_assay_test("test1", True),
        _mock_assay_test("test2", True, True),
        _mock_assay_test("test3", True, True, True)
    ]
    test_names = [x.name for x in tests]
    deliverable_types = [deliverable_category_data, deliverable_category_clinical]
    completed_steps_per_test = {
        None: [QcableType.RECEIPT_INSPECTION],
        test_names[0]: [],
        test_names[1]: [QcableType.EXTRACTION],
        test_names[2]: [QcableType.EXTRACTION, QcableType.LIBRARY_PREPARATION],
    }
    completed_steps_per_deliverable_type = {
        deliverable_types[0]: [],
        deliverable_types[1]: []
    }
    
    assert None == _find_pending_step(completed_steps_per_test, completed_steps_per_deliverable_type, test_names, None, deliverable_types, None, TEST_STEPS, False)
    assert QcableType.LIBRARY_PREPARATION == _find_pending_step(completed_steps_per_test, completed_steps_per_deliverable_type, test_names, tests[0], deliverable_types, None, CASE_STEPS, False)
    assert QcableType.LIBRARY_QUALIFICATION == _find_pending_step(completed_steps_per_test, completed_steps_per_deliverable_type, test_names, tests[1], deliverable_types, None, CASE_STEPS, False)
    assert QcableType.FULL_DEPTH_SEQUENCING == _find_pending_step(completed_steps_per_test, completed_steps_per_deliverable_type, test_names, tests[2], deliverable_types, None, CASE_STEPS, False)
    assert None == _find_pending_step(completed_steps_per_test, completed_steps_per_deliverable_type, test_names, None, deliverable_types, deliverable_types[0], NON_DELIVERABLE_STEPS, False)
    assert None == _find_pending_step(completed_steps_per_test, completed_steps_per_deliverable_type, test_names, None, deliverable_types, deliverable_types[1], NON_DELIVERABLE_STEPS, False)


def test_pending_deliverable_type_steps_1():
    test = _mock_assay_test("test1")
    test_names = [test.name]
    deliverable_types = [deliverable_category_data, deliverable_category_clinical]
    completed_steps_per_test = {
        None: [QcableType.RECEIPT_INSPECTION],
        test.name: [QcableType.EXTRACTION, QcableType.LIBRARY_PREPARATION, QcableType.LIBRARY_QUALIFICATION, QcableType.FULL_DEPTH_SEQUENCING]
    }
    completed_steps_per_deliverable_type = {
        deliverable_types[0]: [],
        deliverable_types[1]: [QcableType.ANALYSIS_REVIEW]
    }

    assert QcableType.ANALYSIS_REVIEW == _find_pending_step(completed_steps_per_test, completed_steps_per_deliverable_type, test_names, None, deliverable_types, None, TEST_STEPS, False)
    assert None == _find_pending_step(completed_steps_per_test, completed_steps_per_deliverable_type, test_names, test, deliverable_types, None, CASE_STEPS, False)
    assert QcableType.ANALYSIS_REVIEW == _find_pending_step(completed_steps_per_test, completed_steps_per_deliverable_type, test_names, None, deliverable_types, deliverable_types[0], NON_DELIVERABLE_STEPS, False)
    assert QcableType.RELEASE_APPROVAL == _find_pending_step(completed_steps_per_test, completed_steps_per_deliverable_type, test_names, None, deliverable_types, deliverable_types[1], NON_DELIVERABLE_STEPS, False)


def test_pending_deliverable_type_steps_2():
    test = _mock_assay_test("test1")
    test_names = [test.name]
    deliverable_types = [deliverable_category_data, deliverable_category_clinical]
    completed_steps_per_test = {
        None: [QcableType.RECEIPT_INSPECTION],
        test.name: [QcableType.EXTRACTION, QcableType.LIBRARY_PREPARATION, QcableType.LIBRARY_QUALIFICATION, QcableType.FULL_DEPTH_SEQUENCING]
    }
    completed_steps_per_deliverable_type = {
        deliverable_types[0]: [QcableType.ANALYSIS_REVIEW, QcableType.RELEASE_APPROVAL],
        deliverable_types[1]: [QcableType.ANALYSIS_REVIEW, QcableType.RELEASE_APPROVAL, QcableType.RELEASE]
    }

    assert QcableType.RELEASE == _find_pending_step(completed_steps_per_test, completed_steps_per_deliverable_type, test_names, None, deliverable_types, None, TEST_STEPS, False)
    assert None == _find_pending_step(completed_steps_per_test, completed_steps_per_deliverable_type, test_names, test, deliverable_types, None, CASE_STEPS, False)
    assert QcableType.RELEASE == _find_pending_step(completed_steps_per_test, completed_steps_per_deliverable_type, test_names, None, deliverable_types, deliverable_types[0], NON_DELIVERABLE_STEPS, False)
    assert None == _find_pending_step(completed_steps_per_test, completed_steps_per_deliverable_type, test_names, None, deliverable_types, deliverable_types[1], NON_DELIVERABLE_STEPS, False)


def test_pending_step_case_complete():
    test = _mock_assay_test("test1")
    test_names = [test.name]
    deliverable_types = [deliverable_category_data, deliverable_category_clinical]
    completed_steps_per_test = {
        None: [QcableType.RECEIPT_INSPECTION],
        test.name: [QcableType.EXTRACTION, QcableType.LIBRARY_PREPARATION, QcableType.LIBRARY_QUALIFICATION, QcableType.FULL_DEPTH_SEQUENCING]
    }
    completed_steps_per_deliverable_type = {
        deliverable_types[0]: [QcableType.ANALYSIS_REVIEW, QcableType.RELEASE_APPROVAL, QcableType.RELEASE],
        deliverable_types[1]: [QcableType.ANALYSIS_REVIEW, QcableType.RELEASE_APPROVAL, QcableType.RELEASE]
    }

    assert None == _find_pending_step(completed_steps_per_test, completed_steps_per_deliverable_type, test_names, None, deliverable_types, None, TEST_STEPS, False)
    assert None == _find_pending_step(completed_steps_per_test, completed_steps_per_deliverable_type, test_names, test, deliverable_types, None, CASE_STEPS, False)
    assert None == _find_pending_step(completed_steps_per_test, completed_steps_per_deliverable_type, test_names, None, deliverable_types, deliverable_types[0], NON_DELIVERABLE_STEPS, False)
    assert None == _find_pending_step(completed_steps_per_test, completed_steps_per_deliverable_type, test_names, None, deliverable_types, deliverable_types[1], NON_DELIVERABLE_STEPS, False)


def test_pending_step_case_stopped():
    test = _mock_assay_test("test1")
    test_names = [test.name]
    deliverable_types = [deliverable_category_data, deliverable_category_clinical]
    completed_steps_per_test = {
        None: [QcableType.RECEIPT_INSPECTION],
        test.name: [QcableType.EXTRACTION, QcableType.LIBRARY_PREPARATION]
    }
    completed_steps_per_deliverable_type = {
        deliverable_types[0]: [],
        deliverable_types[1]: []
    }

    assert QcableType.RELEASE_APPROVAL == _find_pending_step(completed_steps_per_test, completed_steps_per_deliverable_type, test_names, None, deliverable_types, None, TEST_STEPS, True)
    assert None == _find_pending_step(completed_steps_per_test, completed_steps_per_deliverable_type, test_names, test, deliverable_types, None, CASE_STEPS, True)
    assert QcableType.RELEASE_APPROVAL == _find_pending_step(completed_steps_per_test, completed_steps_per_deliverable_type, test_names, None, deliverable_types, deliverable_types[0], NON_DELIVERABLE_STEPS, True)
    assert QcableType.RELEASE_APPROVAL == _find_pending_step(completed_steps_per_test, completed_steps_per_deliverable_type, test_names, None, deliverable_types, deliverable_types[1], NON_DELIVERABLE_STEPS, True)


def _mock_assay_test(name, extraction_skipped: bool = False,
        library_preparation_skipped: bool = False, library_qualification_skipped: bool = False):
    return PreprocessedAssayTest(
        name = name,
        tissue_origin = "Ab",
        tissue_type = "T",
        timepoint = None,
        group_id = None,
        targeted_sequencing = None,
        extraction_sample_type = "DNA",
        library_design = "WG",
        library_qualification_design = None,
        permitted_samples = "ALL",
        extraction_skipped=extraction_skipped,
        library_preparation_skipped=library_preparation_skipped,
        library_qualification_skipped=library_qualification_skipped
        )