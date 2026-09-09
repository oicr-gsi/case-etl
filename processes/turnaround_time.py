import datetime
from enum import Enum
from typing import List
from model.pinery import (PreprocessedAssayTest, PreprocessedCase, PreprocessedDeliverable,
        PreprocessedPinerySample, PreprocessedRequisition, PreprocessedRun, QcableType)


class TimestampType(Enum):
    RESUME = "resume"
    STEP_WORK = "step work"
    STEP_COMPLETE = "step completed"
    PAUSE = "pause"

    def __lt__(self, other):
        # sort by enum order
        # note: requires that any pause lasts 1 or more days (can't pause and resume same day)
        if self == other:
            return False
        for x in TimestampType:
            if x == self:
                return True
            elif x == other:
                return False
        raise RuntimeError("Unexpected sort error")


class Substep(Enum):
    PREPARATION = "preparation"
    TRANSFER = "awaiting transfer"
    LOADING_SEQUENCER = "loading sequencer"
    SEQUENCING = "sequencing"
    QC = "QC"
    TOTAL = "total" # TAT for all substeps are included in this


class Timestamp:
    
    def __init__(self, timestamp_type: TimestampType, date: datetime.datetime | str, step: QcableType = None,
            test: str = None, deliverable_category: str = None, supplemental: bool = False,
            substep: Substep = None):
        self.type = timestamp_type
        self.date = date.date() if isinstance(date, datetime.datetime) else parse_date(date)
        self.step = step # None for PAUSE/RESUME types
        self.test = test # None for case-level steps and PAUSE/RESUME types
        self.deliverable_category = deliverable_category # None for case/test-level steps and PAUSE/RESUME
        self.supplemental = supplemental
        self.substep = substep
    
    def step_sort_value(self) -> int:
        if self.step:
            return self.step.ordinal()
        if self.type == TimestampType.RESUME:
            return -1
        if self.type == TimestampType.PAUSE:
            return 100
        raise RuntimeError("Bad timestamp - has no step and is not pause or resume")


CASE_STEPS = [QcableType.RECEIPT_INSPECTION, QcableType.ANALYSIS_REVIEW,
        QcableType.RELEASE_APPROVAL, QcableType.RELEASE]
TEST_STEPS = [QcableType.EXTRACTION, QcableType.LIBRARY_PREPARATION,
        QcableType.LIBRARY_QUALIFICATION, QcableType.FULL_DEPTH_SEQUENCING]
DELIVERABLE_STEPS = [QcableType.ANALYSIS_REVIEW, QcableType.RELEASE_APPROVAL, QcableType.RELEASE]
NON_DELIVERABLE_STEPS = [QcableType.RECEIPT_INSPECTION, QcableType.EXTRACTION,
        QcableType.LIBRARY_PREPARATION, QcableType.LIBRARY_QUALIFICATION,
        QcableType.FULL_DEPTH_SEQUENCING]
TODAY = datetime.date.today()

def calculate_turnaround_times(case: PreprocessedCase, exempt_dates: List[datetime.date],
        runs_by_id: dict[int, PreprocessedRun], explain: bool):
    timestamps = _extract_timestamps(case, runs_by_id)
    if explain:
        print(f"Timestamps for case {case.get_case_id()}:")
        for timestamp in timestamps:
            print(f"{timestamp.date}: {timestamp.test or 'case'} {timestamp.step or 'non-step'}"
                  + f"{('/' + str(timestamp.substep)) if timestamp.substep else ''} {timestamp.type}"
                  + f"{' (supplemental)' if timestamp.supplemental else ''}")
    _populate_start_date(case)
    test_names = [x.name for x in case.assay_tests]
    deliverable_categories = [x.deliverable_category for x in case.deliverables]
    _populate_case_level_times(case, test_names, deliverable_categories, timestamps, exempt_dates,
            explain)
    for test in case.assay_tests:
        _populate_test_level_times(case, test_names, test, deliverable_categories, timestamps,
                exempt_dates, explain)
    for deliverable in case.deliverables:
        _populate_deliverable_level_times(case, test_names, deliverable_categories, deliverable,
                timestamps, exempt_dates, explain)


def _populate_start_date(case: PreprocessedCase):
    max = None
    for receipt in case.receipts:
        timestamp = receipt.received or receipt.created or receipt.entered
        if max == None or timestamp > max:
            max = timestamp
    case.start_date = parse_date(max)


def _extract_timestamps(case: PreprocessedCase, runs_by_id: dict[int, PreprocessedRun]
        ) -> List[Timestamp]:
    timestamps = []
    timestamps.extend(_extract_sample_timestamps(case.receipts, case.requisition, runs_by_id, None,
            QcableType.RECEIPT_INSPECTION, True))
    for test in case.assay_tests:
        timestamps.extend(_extract_test_timestamps(test, case.requisition, runs_by_id))
    timestamps.extend(_extract_deliverable_qc_timestamps(case))
    timestamps.extend(_extract_pause_timestamps(case.requisition.pauses_json))
    _sort_timestamps(timestamps)
    return timestamps


def _sort_timestamps(timestamps: List[Timestamp]):
    # sort by
    # 1. date
    # 2. QC step (pause/resume have no step; resume should be sorted first and pause last)
    # 3. type (resume > work > QC > pause; a pause must last > 1 day and pauses cannot overlap)
    timestamps.sort(key = lambda x: (x.date, x.step_sort_value(), x.type))


def _extract_test_timestamps(test: PreprocessedAssayTest, requisition: PreprocessedRequisition,
        runs_by_id: dict[int, PreprocessedRun]):
    timestamps = []
    timestamps.extend(_extract_sample_timestamps(test.extractions, requisition, runs_by_id, test,
            QcableType.EXTRACTION))
    timestamps.extend(_extract_sample_timestamps(test.library_preparations, requisition, runs_by_id,
            test, QcableType.LIBRARY_PREPARATION))
    timestamps.extend(_extract_sample_timestamps(test.library_qualifications, requisition,
            runs_by_id, test, QcableType.LIBRARY_QUALIFICATION))
    timestamps.extend(_extract_sample_timestamps(test.full_depth_sequencings, requisition,
            runs_by_id, test, QcableType.FULL_DEPTH_SEQUENCING))
    return timestamps


def _extract_sample_timestamps(samples: List[PreprocessedPinerySample],
        requisition: PreprocessedRequisition, runs_by_id: dict[int, PreprocessedRun],
        test: PreprocessedAssayTest, step: QcableType, prefer_receipt: bool = False):
    timestamps = []
    if not samples:
        return timestamps
    for sample in samples:
        supplemental = sample.requisition_id != requisition.id
        run = None
        if sample.sequencing_run_id:
            run = runs_by_id[sample.sequencing_run_id]
            if run.start_date:
                timestamps.append(Timestamp(TimestampType.STEP_WORK, run.start_date, step,
                        test.name, None, supplemental, Substep.LOADING_SEQUENCER))
            if run.completion_date:
                timestamps.append(Timestamp(TimestampType.STEP_WORK, run.completion_date, step,
                        test.name, None, supplemental, Substep.SEQUENCING))
            if run.qc_date:
                timestamps.append(Timestamp(TimestampType.STEP_WORK, run.qc_date, step, test.name,
                        None, supplemental, Substep.QC))
            if run.data_review_date:
                type = (TimestampType.STEP_COMPLETE
                        if _all_passed(sample, run) and run.data_review_date > sample.data_review_date
                        else TimestampType.STEP_WORK)
                timestamps.append(Timestamp(type, run.data_review_date, step, test.name, None,
                        supplemental, Substep.QC))
        else:
            # sample receipt/creation only used if there is no run; otherwise, run start date is used
            work_date = (sample.received if prefer_receipt and sample.received
                else sample.created or sample.entered)
            timestamps.append(Timestamp(TimestampType.STEP_WORK, work_date, step,
                    test.name if test else None, None, supplemental, Substep.PREPARATION))
        if sample.qc_date:
            type = (TimestampType.STEP_COMPLETE if sample.qc_state == "Ready"
                    and not sample.sequencing_type
                    and sample.qcable_type != QcableType.EXTRACTION
                    else TimestampType.STEP_WORK)
            timestamps.append(Timestamp(type, sample.qc_date, step, test.name if test else None,
                    None, supplemental, Substep.QC))
        if sample.data_review_date:
            type = (TimestampType.STEP_COMPLETE
                    if _all_passed(sample, run) and sample.data_review_date >= run.data_review_date
                    else TimestampType.STEP_WORK)
            timestamps.append(Timestamp(type, sample.data_review_date, step,
                    test.name if test else None, None, supplemental, Substep.QC))
        for transfer_date in sample.extraction_transfer_dates:
            timestamps.append(Timestamp(TimestampType.STEP_COMPLETE, transfer_date, step,
                    test.name if test else None, None, supplemental, Substep.TRANSFER))
    return timestamps


def _all_passed(sample: PreprocessedPinerySample, run: PreprocessedRun) -> bool:
    return (sample.qc_state == "Ready" and sample.data_review_state == "Passed"
            and run.qc_state == "Ready" and run.data_review_state == "Passed")


def _extract_deliverable_qc_timestamps(case: PreprocessedCase):
    timestamps = []
    for deliverable in case.deliverables:
        _add_deliverable_timestamp(deliverable.analysis_review_qc_date,
                deliverable.analysis_review_qc_state, deliverable.analysis_review_qc_release,
                QcableType.ANALYSIS_REVIEW, deliverable.deliverable_category, timestamps)
        _add_deliverable_timestamp(deliverable.release_approval_qc_date,
                deliverable.release_approval_qc_state, deliverable.release_approval_qc_release,
                QcableType.RELEASE_APPROVAL, deliverable.deliverable_category, timestamps)
        for release in deliverable.releases:
            _add_deliverable_timestamp(release.qc_date, release.qc_state, release.qc_release,
                QcableType.RELEASE, deliverable.deliverable_category, timestamps)
    return timestamps


def _add_deliverable_timestamp(qc_date: str, qc_state: str, qc_release: bool, step: QcableType,
        deliverable_category: str, timestamps: List[Timestamp]) -> Timestamp:
    if qc_date:
        if (qc_state == None and qc_release == None):
            type = TimestampType.STEP_WORK
        else:
            type = TimestampType.STEP_COMPLETE
        timestamps.append(Timestamp(type, qc_date, step, None, deliverable_category))


def _extract_pause_timestamps(pauses_json):
    timestamps = []
    for pause in pauses_json:
        timestamps.append(Timestamp(TimestampType.PAUSE, pause['start_date']))
        if pause['end_date']:
            timestamps.append(Timestamp(TimestampType.RESUME, pause['end_date']))
    return timestamps
    

def _populate_case_level_times(case: PreprocessedCase, test_names: List[str],
        deliverable_categories: List[str], timestamps: List[Timestamp],
        exempt_dates: List[datetime.date], explain = False):
    days_per_gate = _calculate_days_spent(case.start_date, case.requisition.stopped, timestamps,
            test_names, None, deliverable_categories, None, exempt_dates, explain)
    case.receipt_days_spent = _get_days(days_per_gate, QcableType.RECEIPT_INSPECTION)
    case.analysis_review_days_spent = _get_days(days_per_gate, QcableType.ANALYSIS_REVIEW)
    case.release_approval_days_spent = _get_days(days_per_gate, QcableType.RELEASE_APPROVAL)
    case.release_days_spent = _get_days(days_per_gate, QcableType.RELEASE)
    
    completed_date = _get_case_completed_date(case)
    case.case_days_spent, case.pause_days = _calculate_case_days(case.start_date, timestamps,
            completed_date, exempt_dates)


def _populate_test_level_times(case: PreprocessedCase, test_names: List[str],
        test: PreprocessedAssayTest, deliverable_categories: List[str],
        timestamps: List[Timestamp], exempt_dates: List[datetime.date], explain = False):
    days_per_gate = _calculate_days_spent(case.start_date, case.requisition.stopped, timestamps,
            test_names, test, deliverable_categories, None, exempt_dates, explain)
    
    test.extraction_days_spent = _get_days(days_per_gate, QcableType.EXTRACTION)
    test.extraction_preparation_days_spent = _get_days(days_per_gate, QcableType.EXTRACTION,
            Substep.PREPARATION)
    test.extraction_qc_days_spent = _get_days(days_per_gate, QcableType.EXTRACTION, Substep.QC)
    test.extraction_transfer_days_spent = _get_days(days_per_gate, QcableType.EXTRACTION,
            Substep.TRANSFER)

    test.library_preparation_days_spent = _get_days(days_per_gate, QcableType.LIBRARY_PREPARATION)
    
    test.library_qualification_days_spent = _get_days(days_per_gate,
            QcableType.LIBRARY_QUALIFICATION)
    test.library_qualification_loading_days_spent = _get_days(days_per_gate,
            QcableType.LIBRARY_QUALIFICATION, Substep.LOADING_SEQUENCER)
    test.library_qualification_sequencing_days_spent = _get_days(days_per_gate,
            QcableType.LIBRARY_QUALIFICATION, Substep.SEQUENCING)
    test.library_qualification_qc_days_spent = _get_days(days_per_gate,
            QcableType.LIBRARY_QUALIFICATION, Substep.QC)
    
    test.full_depth_sequencing_days_spent = _get_days(days_per_gate,
            QcableType.FULL_DEPTH_SEQUENCING)
    test.full_depth_sequencing_loading_days_spent = _get_days(days_per_gate,
            QcableType.FULL_DEPTH_SEQUENCING, Substep.LOADING_SEQUENCER)
    test.full_depth_sequencing_sequencing_days_spent = _get_days(days_per_gate,
            QcableType.FULL_DEPTH_SEQUENCING, Substep.SEQUENCING)
    test.full_depth_sequencing_qc_days_spent = _get_days(days_per_gate,
            QcableType.FULL_DEPTH_SEQUENCING, Substep.QC)


def _populate_deliverable_level_times(case: PreprocessedCase, test_names: List[str],
        deliverable_categories: List[str], deliverable: PreprocessedDeliverable,
        timestamps: List[Timestamp], exempt_dates: List[datetime.date], explain = False):
    days_per_gate = _calculate_days_spent(case.start_date, case.requisition.stopped, timestamps,
            test_names, None, deliverable_categories, deliverable.deliverable_category, exempt_dates, explain)
    deliverable.analysis_review_days_spent = _get_days(days_per_gate, QcableType.ANALYSIS_REVIEW)
    deliverable.release_approval_days_spent = _get_days(days_per_gate, QcableType.RELEASE_APPROVAL)
    deliverable.release_days_spent = _get_days(days_per_gate, QcableType.RELEASE)

    completed_date = _get_case_completed_date(case, deliverable.deliverable_category)
    deliverable.deliverable_days_spent, discard = _calculate_case_days(case.start_date, timestamps,
            completed_date, exempt_dates)


def _calculate_days_spent(case_start_date: datetime.date, case_stopped: bool,
        timestamps: List[Timestamp], test_names: List[str], test: PreprocessedAssayTest,
        deliverable_categories: List[str], deliverable_category: str,
        exempt_dates: List[datetime.date], explain = False) -> dict[QcableType, dict[Substep, int]]:
    if test != None:
        skip_steps = CASE_STEPS
    elif deliverable_category != None:
        skip_steps = NON_DELIVERABLE_STEPS
    else:
        skip_steps = TEST_STEPS
    
    days_per_gate = {}
    completed_steps_per_test = {x: set() for x in [None] + test_names}
    completed_steps_per_deliverable_category = {x: set() for x in deliverable_categories}
    start = timestamps[0]
    end = timestamps[0]
    paused = False
    for current in timestamps[1:]:
        if current.type == TimestampType.STEP_COMPLETE:
            if current.deliverable_category != None:
                completed_steps_per_deliverable_category[current.deliverable_category].add(current.step)
            else:
                completed_steps_per_test[current.test].add(current.step)
        if current.supplemental:
            # use supplemental only to find completed steps - don't count TAT
            continue
        if test != None and current.test not in [None, test.name]:
            continue
        if deliverable_category != None and current.deliverable_category not in [None, deliverable_category]:
            continue
        
        if current.type == TimestampType.RESUME:
            paused = False
            start = current
            end = current
            continue
        elif paused:
            continue
        elif current.type == TimestampType.PAUSE:
            paused = True

        if current.date <= case_start_date:
            # ignore time ranges before the case start date (latest receipt)
            start = current
            end = current
            continue
        if current.step != end.step or current.substep != end.substep:
            if end.step is not None and end.step not in skip_steps:
                _add_days(start.date, end.date, end.step, end.substep, days_per_gate, test,
                        deliverable_category, exempt_dates=exempt_dates, explain=explain)
            if current.type == TimestampType.PAUSE:
                pending_step = _find_pending_step(completed_steps_per_test,
                        completed_steps_per_deliverable_category, test_names, test, deliverable_categories,
                        deliverable_category, skip_steps, case_stopped)
                if pending_step not in [None] + skip_steps:
                    _add_days(end.date, current.date, pending_step, None, days_per_gate, test,
                            deliverable_category, "pre-pause", exempt_dates, explain)
            start = end
        end = current
    
    if end.step is not None:
        if end.step not in skip_steps:
            _add_days(start.date, end.date, end.step, end.substep, days_per_gate, test,
                    deliverable_category, "final timepoint", exempt_dates, explain)
        start = end
    
    # if case/test isn't finished, add days up to current date to pending step
    pending_step = _find_pending_step(completed_steps_per_test,
            completed_steps_per_deliverable_category, test_names, test, deliverable_categories,
            deliverable_category, skip_steps, case_stopped)
    if pending_step:
        _add_days(start.date, TODAY, pending_step, None, days_per_gate, test, deliverable_category,
                "pending without work", exempt_dates, explain)
    return days_per_gate


def _add_days(start_date: datetime.date, end_date: datetime.date, step: QcableType,
        substep: Substep, days_per_gate: dict[QcableType, dict[Substep, int]],
        test: PreprocessedAssayTest, deliverable_category: str | None, note: str=None,
        exempt_dates: List[datetime.date]=None, explain=False) -> None:
    effective_end_date = min(end_date, TODAY)
    if end_date < start_date:
        return
    counted_days = len([x for x in date_range_inclusive(start_date, effective_end_date)
            if x != start_date and x not in exempt_dates])
    if explain:
        total_duration = (effective_end_date - start_date).days
        if test != None:
            target = test.name
        elif deliverable_category != None:
            target = deliverable_category
        else:
            target = "case"
        print(f"Adding {counted_days} days ({start_date} - {end_date}"
                + f"{'' if total_duration == counted_days else (', ' + str(total_duration - counted_days) + ' days exempt')})"
                + f" to {target} {step.value}{('/' + substep.value) if substep else ''}"
                + (f" ({note})" if note else ""))
    days_per_gate[step] = days_per_gate.get(step, {})
    days_per_gate[step][Substep.TOTAL] = days_per_gate[step].get(Substep.TOTAL, 0) + counted_days
    if substep:
        days_per_gate[step][substep] = days_per_gate[step].get(substep, 0) + counted_days


def _get_days(days_per_gate: dict[QcableType, dict[Substep, int]], step: QcableType,
        substep: Substep=Substep.TOTAL) -> int:
    if step not in days_per_gate:
        return 0
    return days_per_gate[step].get(substep, 0)


def _find_pending_step(completed_steps_per_test, completed_steps_per_deliverable_category,
        test_names: List[str], test: PreprocessedAssayTest,
        deliverable_categories: List[str], deliverable_category: str,
        skip_steps: List[QcableType], case_stopped: bool) -> QcableType | None:
    for step in QcableType:
        if case_stopped and step not in [QcableType.RELEASE_APPROVAL, QcableType.RELEASE]:
            continue
        elif step in CASE_STEPS:
            if step in DELIVERABLE_STEPS:
                if deliverable_category is None:
                    complete = True
                    for check_deliverable in deliverable_categories:
                        if step not in completed_steps_per_deliverable_category[check_deliverable]:
                            complete = False
                    if complete:
                        continue
                elif step in completed_steps_per_deliverable_category[deliverable_category]:
                    continue
            elif step in completed_steps_per_test[None]:
                continue
        elif test is None:
            complete = True
            for check_test in test_names:
                if step not in completed_steps_per_test[check_test]:
                    complete = False
            if complete:
                continue
        elif step in completed_steps_per_test[test.name]:
            continue
        elif step == QcableType.EXTRACTION and test.extraction_skipped:
            continue
        elif step == QcableType.LIBRARY_PREPARATION and test.library_preparation_skipped:
            continue
        elif step == QcableType.LIBRARY_QUALIFICATION and test.library_qualification_skipped:
            continue

        return step if step not in skip_steps else None
    return None


def _calculate_case_days(case_start_date: datetime.date, timestamps: List[Timestamp],
        completed_date: datetime.date, exempt_dates: List[datetime.date]) -> tuple[int, int]:
    pause_start = None
    pause_dates = []
    for timestamp in timestamps:
        if completed_date != None and timestamp.date > completed_date:
            # This is mainly for looking at a specific deliverable type (to ignore others
            # paused/completed later)
            continue
        if timestamp.type == TimestampType.PAUSE:
            pause_start = timestamp.date
        elif timestamp.type == TimestampType.RESUME:
            # Only count pause days after the case start (latest receipt)
            if timestamp.date > case_start_date:
                if pause_start < case_start_date:
                    pause_start = case_start_date
                pause_dates.extend(list(date_range_inclusive(pause_start, timestamp.date))[1:])
            pause_start = None
    
    end_date = completed_date or pause_start or TODAY
    case_days_spent = len([x for x in date_range_inclusive(case_start_date, end_date)
            if x != case_start_date and x not in pause_dates and x not in exempt_dates])

    if pause_start:
        pause_end = completed_date or TODAY
        pause_dates.extend(list(date_range_inclusive(pause_start, pause_end))[1:])
    
    return case_days_spent, len(pause_dates)


def _get_case_completed_date(case: PreprocessedCase, deliverable_category: str = None):
    latest = None
    if not case.deliverables:
        return None
    for deliverable in case.deliverables:
        if deliverable_category != None and deliverable.deliverable_category != deliverable_category:
            continue
        if not deliverable.releases:
            return None
        for release in deliverable.releases:
            if (release.qc_state == None and release.qc_release == None):
                return None
            release_date = parse_date(release.qc_date)
            if latest == None or release_date > latest:
                latest = release_date
    return latest


def parse_date(string: str):
    return datetime.datetime.strptime(string[0:10], "%Y-%m-%d").date()


def date_range_inclusive(start_date, end_date):
    day_count = (end_date - start_date).days + 1
    for x in range(day_count):
        yield start_date + datetime.timedelta(x)
