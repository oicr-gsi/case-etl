import argparse
import csv
import logging
import os
import processes.app_metrics as app_metrics
import processes.nabu_extract as nabu
import timeit

from datetime import date, datetime, timezone, timedelta
from dateutil.relativedelta import relativedelta
from model.pinery import (ArchivingStatus, MetricLevel, MetricType, PreprocessedAssay,
        PreprocessedAssayTest, PreprocessedCase, PreprocessedDeliverable, PreprocessedDonor,
        PreprocessedProject, PreprocessedProjectDeliverable, PreprocessedRelease, PreprocessedRun,
        PreprocessedRequisition, PreprocessedAnalysisQcGroup, RequiredCase, SampleMetric,
        SampleType, PreprocessedPinerySample, QcableType, ThresholdType, clone_id_pattern)
from processes.nabu_extract import RetentionUnits
from processes.qcetl_extract import add_qcetl_data
from processes.pinery_extract import get_pinery_samples
from processes.preprocess import (preprocess_assays, preprocess_requisitions, preprocess_runs,
        preprocess_samples)
from typing import Dict, List, Set
from processes.miso_db_extract import add_runscanner_data, add_transfer_data, connect_db
from processes.turnaround_time import calculate_turnaround_times, date_range_inclusive, parse_date
from utils.json import write_json
from utils.pinery import (get_instruments_with_model, get_requisitions, get_assays, get_projects,
        get_sequencer_runs, get_users)


def read_tat_exemptions(exemption_filepath: str):
    exempt_dates = []
    with open(exemption_filepath) as exemption_file:
        reader = csv.reader(exemption_file)
        next(reader) # skip headings row
        for row in reader:
            if not row:
                continue # skip blank lines
            start_date = parse_date(row[0])
            end_date = parse_date(row[1])
            for date in date_range_inclusive(start_date, end_date):
                exempt_dates.append(date)
    return exempt_dates


def sample_valid_for_case(case: PreprocessedCase, sample: PreprocessedPinerySample) -> bool:
    return (sample.tissue_origin == case.tissue_origin
            and sample.tissue_type == case.tissue_type
            and sample.timepoint == case.timepoint)


def sample_valid_for_test(pinery_test: dict, sample: PreprocessedPinerySample) -> bool:
    # match by tissue origin always
    if 'tissue_origin' in pinery_test:
        if pinery_test.get('negate_tissue_origin', False):
            if sample.tissue_origin == pinery_test['tissue_origin']:
                return False
        elif sample.tissue_origin != pinery_test['tissue_origin']:
            return False
    # match by tissue type always
    if 'tissue_type' in pinery_test:
        if pinery_test.get('negate_tissue_type', False):
            if sample.tissue_type == pinery_test['tissue_type']:
                return False
        elif sample.tissue_type != pinery_test['tissue_type']:
            return False
    if (sample.qcable_type == QcableType.LIBRARY_QUALIFICATION):
        if pinery_test['library_qualification_method'] == 'NONE':
            return False
        if sample.sequencing_run_id is None:
            if pinery_test['library_qualification_method'] == 'LOW_DEPTH_SEQUENCING':
                return False
        elif pinery_test['library_qualification_method'] == 'ALIQUOT':
            return False
    # match by extraction_class if extraction
    if sample.qcable_type == QcableType.EXTRACTION:
        if 'extraction_sample_type' in pinery_test and sample.sample_type != pinery_test['extraction_sample_type']:
            return False
    # match by qualification_design_code if library qual or full depth and qualification_design_code is specified
    elif (sample.qcable_type in [QcableType.LIBRARY_QUALIFICATION, QcableType.FULL_DEPTH_SEQUENCING]
        and 'library_qualification_source_template_type' in pinery_test):
        if sample.library_design != pinery_test['library_qualification_source_template_type']:
            return False
    # match by design_code if library prep, or library qual/full depth with no qualification_design_code specified
    elif (sample.qcable_type in
        [QcableType.LIBRARY_PREPARATION, QcableType.LIBRARY_QUALIFICATION, QcableType.FULL_DEPTH_SEQUENCING]
        and 'library_source_template_type' in pinery_test
        and sample.library_design != pinery_test['library_source_template_type']):
            return False
    return True


def include_in_test(case: PreprocessedCase, test: dict, sample: PreprocessedPinerySample) -> bool:
    return (((not test['repeat_per_timepoint']) or sample_valid_for_case(case, sample))
            and sample_valid_for_test(test, sample))


def collect_qcable_children(samples: List[PreprocessedPinerySample],
        preprocessed_samples: Dict[str, PreprocessedPinerySample]):
    children = []
    for sample in samples:
        children.extend(collect_children_within_requisition(sample, preprocessed_samples))
    return [x for x in children if x.qcable_type]


def collect_children_within_requisition(parent: PreprocessedPinerySample,
        preprocessed_samples: Dict[str, PreprocessedPinerySample]) -> list[PreprocessedPinerySample]:
    if not parent.child_ids:
        return []
    samples = []
    for child_id in parent.child_ids:
        child = preprocessed_samples[child_id]
        # exclude if the child is in a different requisition
        if child.requisition_id == parent.requisition_id:
            samples.append(child)
            samples.extend(collect_children_within_requisition(child, preprocessed_samples))
    return samples


def collect_supplemental_samples(pinery_requisition: dict,
        preprocessed_samples: Dict[str, PreprocessedPinerySample]
        ) -> list[PreprocessedPinerySample]:
    supplemental = []
    samples = []
    for sample_id in pinery_requisition.get("supplemental_sample_ids", []):
        sample = preprocessed_samples[sample_id]
        supplemental.append(sample)
        while sample.qcable_type != QcableType.RECEIPT_INSPECTION:
            if sample.qcable_type != None:
                samples.append(sample) # upstream qcable
            sample = preprocessed_samples[sample.parent_id]
        samples.append(sample) # receipt
    samples.extend(collect_qcable_children(supplemental, preprocessed_samples)) # downstream
    return samples


def add_required_case(donor: PreprocessedDonor, requisition: PreprocessedRequisition,
        pinery_assay: dict, sample: PreprocessedPinerySample,
        requisition_samples: List[PreprocessedPinerySample],
        supplemental_samples: List[PreprocessedPinerySample],
        required_cases: Dict[str, RequiredCase]) -> None:
    case_string = (f'{requisition.id}_{pinery_assay["id"]}_{donor.name}__{sample.tissue_origin}'
                + f'_{sample.tissue_type}_{sample.timepoint or ""}')
    if not case_string in required_cases:
        required_cases[case_string] = RequiredCase(
            donor=donor,
            assay=pinery_assay,
            tissue_origin=sample.tissue_origin,
            tissue_type=sample.tissue_type,
            timepoint=sample.timepoint,
            requisition=requisition,
            requisition_samples=[sample for sample in requisition_samples
                    if sample.donor_id == donor.id],
            supplemental_samples=[sample for sample in supplemental_samples
                    if sample.donor_id == donor.id]
        )


def find_required_tests(pinery_test: dict, samples: List[PreprocessedPinerySample]
        ) -> List[PreprocessedAssayTest]:
    tests: List[PreprocessedAssayTest] = []
    # Create tests for every distinct grouping criteria on samples beginning with full depth and
    # working backwards through lib_quals, lib_preps, extractions, and receipts.
    #    * ignore group ID for receipts as we don't want to create tests for group IDs existing only
    #      on receipt samples
    #    * ignore targeted sequencing except on run-libraries and library aliquots
    #    * for run-libraries, group_id must match the test; for others, it can be None or match
    for gate in [QcableType.FULL_DEPTH_SEQUENCING, QcableType.LIBRARY_QUALIFICATION,
            QcableType.LIBRARY_PREPARATION, QcableType.EXTRACTION, QcableType.RECEIPT_INSPECTION]:
        gate_samples = [x for x in samples if x.qcable_type == gate]
        for gate_sample in gate_samples:
            matching_tests = [x for x in tests if x.tissue_origin == gate_sample.tissue_origin
                    and x.tissue_type == gate_sample.tissue_type
                    and x.timepoint == gate_sample.timepoint
                    and (gate == QcableType.RECEIPT_INSPECTION
                            or gate_sample.group_id == x.group_id
                            or (gate_sample.sample_category != SampleType.SEQUENCED_SAMPLE
                                    and gate_sample.group_id == None))
                    and (x.targeted_sequencing == gate_sample.targeted_sequencing
                            or gate_sample.sample_category
                            not in [SampleType.LIBRARY_ALIQUOT, SampleType.SEQUENCED_SAMPLE])]
            if not matching_tests:
                # Omit group ID for tests created based on receipt samples only
                tests.append(make_preprocessed_test(pinery_test, gate_sample, gate == QcableType.RECEIPT_INSPECTION))


    # If no tests created yet, create an empty test
    if not tests:
        tests.append(PreprocessedAssayTest(
            name=pinery_test['name'],
            tissue_origin=None,
            tissue_type=None,
            timepoint=None,
            group_id=None,
            targeted_sequencing=None,
            extraction_sample_type=pinery_test['extraction_sample_type'],
            library_design=pinery_test['library_source_template_type'],
            library_qualification_design=pinery_test.get('library_qualification_source_template_type'),
            permitted_samples=pinery_test.get('permitted_samples', 'ALL')
        ))

    return tests


def make_preprocessed_test(pinery_test: dict, sample: PreprocessedPinerySample,
        omit_group_id: bool) -> PreprocessedAssayTest:
    return PreprocessedAssayTest(
        name=pinery_test['name'],
        tissue_origin=sample.tissue_origin,
        tissue_type=sample.tissue_type,
        timepoint=sample.timepoint,
        group_id=None if omit_group_id else sample.group_id,
        targeted_sequencing=sample.targeted_sequencing,
        extraction_sample_type=pinery_test['extraction_sample_type'],
        library_design=pinery_test['library_source_template_type'],
        library_qualification_design=pinery_test.get('library_qualification_source_template_type'),
        permitted_samples=pinery_test.get('permitted_samples', 'ALL'),
        library_qualification_skipped=(pinery_test.get('library_qualification_method') == 'NONE')
    )


def add_case_sample(case: PreprocessedCase, sample: PreprocessedPinerySample, supplemental: bool,
        output_samples_by_id: Dict[str, PreprocessedPinerySample], output_run_ids: Set[int],
        output_assays_by_id: Dict[int, PreprocessedAssay], preprocessed_runs_by_id: Dict[int, PreprocessedRun]) -> None:
    if sample.qcable_type == QcableType.RECEIPT_INSPECTION:
        if not sample in case.receipts:
            case.receipts.append(sample)
    else:
        inclusion_count = 0
        for test in case.assay_tests:
            if supplemental:
                if test.permitted_samples == 'REQUISITIONED':
                    continue
            else:
                if test.permitted_samples == 'SUPPLEMENTAL':
                    continue
            # ignore targeted sequencing except on run-libraries and library aliquots
            if sample.sample_category in [SampleType.SEQUENCED_SAMPLE, SampleType.LIBRARY_ALIQUOT]:
                if sample.targeted_sequencing != test.targeted_sequencing:
                    continue
            # for run-libraries, group_id must match the test; for others, it can be None or match
            if sample.sample_category == SampleType.SEQUENCED_SAMPLE:
                if sample.group_id != test.group_id:
                    continue
            elif sample.group_id not in [None, test.group_id]:
                continue
            if sample.library_design:
                # if the test specifies lib_qual design, lib_quals and full_depth must match it
                if (test.library_qualification_design and
                        sample.qcable_type in [QcableType.LIBRARY_QUALIFICATION,
                                QcableType.FULL_DEPTH_SEQUENCING]):
                    if sample.library_design != test.library_qualification_design:
                        continue
                # other qcables with design must match test library design
                elif sample.library_design != test.library_design:
                    continue
            # extractions must match the test extration class
            if (sample.qcable_type == QcableType.EXTRACTION
                    and sample.sample_type != test.extraction_sample_type):
                continue
            # all samples must match test tissue origin, tissue type, and timepoint
            if (sample.tissue_origin == test.tissue_origin
                    and sample.tissue_type == test.tissue_type
                    and sample.timepoint == test.timepoint):
                inclusion_count += 1
                if sample.qcable_type == QcableType.EXTRACTION:
                    test.extractions.append(sample)
                elif sample.qcable_type == QcableType.LIBRARY_PREPARATION:
                    test.library_preparations.append(sample)
                elif sample.qcable_type == QcableType.LIBRARY_QUALIFICATION:
                    test.library_qualifications.append(sample)
                    if not supplemental:
                        # supplemental samples get QCed based on the metrics for the assay in their original requisition
                        add_metrics_from_assay(sample, output_assays_by_id.get(case.assay_id), QcableType.LIBRARY_QUALIFICATION, preprocessed_runs_by_id.get(sample.sequencing_run_id))
                        if case.requisition.stopped:
                            sample.analysis_skipped = True
                elif sample.qcable_type == QcableType.FULL_DEPTH_SEQUENCING:
                    test.full_depth_sequencings.append(sample)
                    if not supplemental:
                        # supplemental samples get QCed based on the metrics for the assay in their original requisition
                        add_metrics_from_assay(sample, output_assays_by_id.get(case.assay_id), QcableType.FULL_DEPTH_SEQUENCING, preprocessed_runs_by_id.get(sample.sequencing_run_id))
                        if case.requisition.stopped:
                            sample.analysis_skipped = True
                else:
                    raise Exception(f'Unexpected qcable type: {sample.qcable_type.name} for sample {sample.sample_id} in requisition {case.requisition.id}')

            if sample.sequencing_run_id:
                if sample.sequencing_run_id in sample_ids_by_run:
                    sample_ids_by_run[sample.sequencing_run_id].add(sample.sample_id)
                else:
                    sample_ids_by_run[sample.sequencing_run_id] = {sample.sample_id}

        if inclusion_count < 1:
            raise Exception(f'No tests found for sample {sample.sample_id}')
    if not clone_id_pattern.match(sample.sample_id):
        output_samples_by_id[sample.sample_id] = sample
    if sample.sequencing_run_id:
        output_run_ids.add(sample.sequencing_run_id)


def mark_skipped_gates(case: PreprocessedCase, test: PreprocessedAssayTest,
        preprocessed_samples: dict[str, PreprocessedPinerySample]) -> None:
    if not test.library_preparations:
        # mark extraction AND library prep skipped if applicable libraries were received
        for receipt in case.receipts:
            if (receipt.sample_category == SampleType.LIBRARY
                    and receipt.library_design == test.library_design):
                test.library_preparation_skipped = True
                test.extraction_skipped = True
                break
    if not test.extractions and not test.extraction_skipped:
        # mark extraction skipped if applicable stocks, aliquots, or libraries were received
        # (library would have been caught above if library aliquot is used for library prep)
        for receipt in case.receipts:
            if (receipt.sample_category in [SampleType.STOCK, SampleType.ALIQUOT]
                    and receipt.sample_type == test.extraction_sample_type):
                test.extraction_skipped = True
                break
            if receipt.sample_category == SampleType.LIBRARY:
                parent = preprocessed_samples[receipt.parent_id]
                if parent.sample_type == test.extraction_sample_type:
                    test.extraction_skipped = True
                    break


def get_identity(preprocessed_sample: PreprocessedPinerySample) -> PreprocessedPinerySample:
    project_prefixed_parent_id = preprocessed_sample.project_prefixed_parent_id
    if project_prefixed_parent_id is None:
        return None
    preprocessed_sample_parent = preprocessed_samples.get(project_prefixed_parent_id)
    if preprocessed_sample_parent is None:
        raise Exception(
            f"sample={preprocessed_sample.project_prefixed_sample_id} is referencing parent={project_prefixed_parent_id} which does not exist")
    if preprocessed_sample_parent.sample_category == SampleType.IDENTITY:
        return preprocessed_sample_parent
    else:
        return get_identity(preprocessed_sample_parent)


def add_metrics_from_assay(sample: PreprocessedPinerySample, assay: PreprocessedAssay, metric_category: QcableType, run: PreprocessedRun):
    all_metric_subcategories = assay.metric_categories[metric_category.name] if metric_category.name in assay.metric_categories else None
    if all_metric_subcategories is None:
        return
    matching_metric_subcategories = [ms for ms in all_metric_subcategories if (
            # If there's a library design on the metric subcategory, it must match. Otherwise, true if any metrics apply
            (sample.library_design == ms.library_design) if ms.library_design else
            (any(True for m in ms.metrics if m.applies(sample, run)))
        )]
    for ms in matching_metric_subcategories:
        for metric in ms.metrics:
            metric_type = MetricType.of(metric.name)
            metric_level = metric_type.metric_level if metric_type else MetricLevel.SAMPLE
            threshold_type = ThresholdType(metric.threshold_type)  # Will raise if it encounters a threshold type that is not yet configured

            if metric.applies(sample, run):
                # Add metric to sample
                if metric.name in sample.metrics:
                    # Error only if the metric thresholds are different from what's already on the sample.
                    # A reference sample in the same requisition as multiple tumour samples at different timepoints will be included in multiple cases, and shouldn't error.
                    existing_metric = sample.metrics[metric.name]
                    if metric.matches_thresholds(existing_metric.name, existing_metric.threshold_min, existing_metric.threshold_max, existing_metric.threshold_type):
                        continue
                    else:
                        raise Exception(f"""Attempted to add duplicate metric {metric.name} to {sample.sample_id} with different thresholds.
    Check if:
        - the requisition for sample {sample.sample_id} has multiple assays with different thresholds (ask the lab to fix the req to only have one assay)
        - assay {assay.id} has duplicate metrics for the assay test that the sample is involved with
        - there's a problem with the PreprocessedMetric.matches_thresholds functions.""")
                else:
                    # Include values that come from the sample itself immediately. Others are added later
                    value = get_sample_metric_value(sample, metric.name)
                    sample.metrics[metric.name] = SampleMetric(
                        name=metric.name, metric_level=metric_level, threshold_type=threshold_type, threshold_min=metric.minimum,
                        threshold_max=metric.maximum, value=value, units=metric.units)


def get_sample_metric_value(sample: PreprocessedPinerySample, metric_name: str):
    match metric_name:
        case None:
            return None
        case "Collapsed Coverage":
            return sample.collapsed_coverage
        case "Quantitative PCR (qPCR)":
            return sample.concentration
        case "Tumour Content":
            return sample.tumour_content
        case _:
            return None


def get_qcable_id(sample: PreprocessedPinerySample):
    return f"{sample.qcable_type.value}:{sample.project_prefixed_sample_id}"


def write_timestamp(output_dir: str, contents) -> None:
    with open(os.path.join(output_dir, 'timestamp'), "w", encoding="utf-8") as file:
        file.write(contents)


def collect_projects(case: PreprocessedCase,
        output_projects_by_name: Dict[str, PreprocessedProject], pinery_projects: Dict[str, dict]
        ) -> None:
    # include supplemental and donor projects in output
    for project_name in case.get_project_names(True):
        add_project(project_name, pinery_projects, output_projects_by_name)

    # determine deliverables based on requisitioned projects only
    deliverables_by_category: dict[str, PreprocessedProjectDeliverable] = {}
    included_releases_by_category: dict[str, list[str]] = {}
    for project_name in case.get_project_names(False):
        project = output_projects_by_name[project_name]
        for deliverable_category in project.deliverables:
            for project_deliverable in project.deliverables[deliverable_category]:
                deliverable = deliverables_by_category.setdefault(deliverable_category, PreprocessedDeliverable(
                    deliverable_category = deliverable_category,
                    analysis_review_skipped = True
                ))
                included_releases = included_releases_by_category.setdefault(deliverable_category, [])
                if project_deliverable.name not in included_releases:
                    included_releases.append(project_deliverable.name)
                    release = PreprocessedRelease(deliverable = project_deliverable.name)
                    deliverable.releases.append(release)
                if project_deliverable.analysis_review_required:
                    deliverable.analysis_review_skipped = False
        case.deliverables = list(deliverables_by_category.values())


def add_project(project_name: str, pinery_projects: Dict[str, dict],
        output_projects_by_name: Dict[str, PreprocessedProject]) -> None:
    if project_name not in output_projects_by_name:
            pinery_project = pinery_projects[project_name]
            deliverables = {}
            for pinery_deliverable in pinery_project.get('deliverables', []):
                deliverable_category = pinery_deliverable['category']
                deliverable = PreprocessedProjectDeliverable(
                    name = pinery_deliverable['name'],
                    analysis_review_required = pinery_deliverable['analysis_review_required']
                )
                category_deliverables = deliverables.get(deliverable_category, [])
                category_deliverables.append(deliverable)
                deliverables[deliverable_category] = category_deliverables
            output_projects_by_name[project_name] = PreprocessedProject(
                name = project_name,
                pipeline = pinery_project['pipeline'],
                deliverables = deliverables
            )


def collect_analysis_metrics(output_cases: List[PreprocessedCase]):
    for case in output_cases:
        for test in case.assay_tests:
            for sample in test.full_depth_sequencings:
                qc_groups = [x for x in case.qc_groups if x.tissue_origin == sample.tissue_origin
                and x.tissue_type == sample.tissue_type
                and x.library_design == sample.library_design
                and x.group_id == sample.group_id
                and missing_or_equal(x.purity, sample.purity)
                and missing_or_equal(x.collapsed_coverage, sample.collapsed_coverage)
                and missing_or_equal(x.callability, sample.callability)]
                if qc_groups:
                    for qc_group in qc_groups:
                        if sample.purity:
                            qc_group.purity = sample.purity
                        if sample.collapsed_coverage:
                            qc_group.collapsed_coverage = sample.collapsed_coverage
                        if sample.callability:
                            qc_group.callability = sample.callability
                else:
                    case.qc_groups.append(PreprocessedAnalysisQcGroup(
                        tissue_origin=sample.tissue_origin,
                        tissue_type=sample.tissue_type,
                        library_design=sample.library_design,
                        group_id=sample.group_id,
                        purity=sample.purity,
                        collapsed_coverage=sample.collapsed_coverage,
                        callability=sample.callability
                    ))


def missing_or_equal(value1, value2):
    return not value1 or not value2 or value1 == value2



def read_nabu_key_file(filename):
    with open(filename, 'r') as f:
        # It's assumed the file contains a single line, with the key
        return f.read().strip()


def add_nabu_signoffs(output_cases: list[PreprocessedCase], nabu_url: str, nabu_key: str):
    nabu_signoffs = nabu.get_signoffs(nabu_url, nabu_key)
    cases_by_id = {x.get_case_id(): x for x in output_cases}
    for nabu_signoff in nabu_signoffs:
        case = cases_by_id.get(nabu_signoff["caseIdentifier"])
        if not case:
            app_metrics.nabu_signoff_errors.inc()
            logging.warning("Found Nabu signoff for unknown case: %s", nabu_signoff)
            continue
        deliverable_category = nabu_signoff["deliverableType"]
        deliverable_type_matched = False
        for deliverable in case.deliverables:
            if deliverable.deliverable_category == deliverable_category:
                deliverable_type_matched = True
                qc_state = ("Ready" if nabu_signoff["qcPassed"] == True
                    else "Failed" if nabu_signoff["qcPassed"] == False
                    else None)
                qc_release = nabu_signoff.get("release")
                qc_user = nabu_signoff["username"]
                qc_date = nabu_signoff["created"][0:10] # keep date portion only
                qc_note = nabu_signoff["comment"]
                if nabu_signoff["signoffStepName"] == "ANALYSIS_REVIEW":
                    deliverable.analysis_review_qc_state = qc_state
                    deliverable.analysis_review_qc_release = qc_release
                    deliverable.analysis_review_qc_user = qc_user
                    deliverable.analysis_review_qc_date = qc_date
                    deliverable.analysis_review_qc_note = qc_note
                elif nabu_signoff["signoffStepName"] == "RELEASE_APPROVAL":
                    deliverable.release_approval_qc_state = qc_state
                    deliverable.release_approval_qc_release = qc_release
                    deliverable.release_approval_qc_user = qc_user
                    deliverable.release_approval_qc_date = qc_date
                    deliverable.release_approval_qc_note = qc_note
                elif nabu_signoff["signoffStepName"] == "RELEASE":
                    deliverable_matched = False
                    for release in deliverable.releases:
                        if release.deliverable == nabu_signoff["deliverable"]:
                            deliverable_matched = True
                            release.qc_state = qc_state
                            release.qc_release = qc_release
                            release.qc_user = qc_user
                            release.qc_date = qc_date
                            release.qc_note = qc_note
                            break
                    if not deliverable_matched:
                        app_metrics.nabu_signoff_errors.inc()
                        logging.warning("Nabu signoff has unmatched deliverable: %s", nabu_signoff)
                else:
                    app_metrics.nabu_signoff_errors.inc()
                    logging.warning("Unexpected Nabu signoffStepName: %s", nabu_signoff)
                break
        if not deliverable_type_matched:
            app_metrics.nabu_signoff_errors.inc()
            logging.warning("Nabu signoff has unmatched deliverableType: %s", nabu_signoff)


def add_archive_info(output_cases: list[PreprocessedCase], nabu_url: str, nabu_key: str,
        archive_targets: dict[str, nabu.ArchiveTarget]):
    nabu_archives = nabu.get_case_archives(nabu_url, nabu_key)
    archives_by_case_id = {}
    for archive in nabu_archives:
        case_id = archive["caseIdentifier"]
        if case_id in archives_by_case_id:
            app_metrics.nabu_archive_errors.inc()
            logging.warning(f"Multiple Nabu archives found for case {case_id}")
            if archive["created"] > archives_by_case_id[case_id]["created"]:
                archives_by_case_id[case_id] = archive
        else:
            archives_by_case_id[case_id] = archive

    today = date.today()
    for case in output_cases:
        case_id = case.get_case_id()
        if case_id in archives_by_case_id:
            archive = archives_by_case_id[case_id]
            # remove from dict so we can see which are orphaned later
            del archives_by_case_id[case_id]
            case.archiving_status = get_nabu_archive_status(archive)
            nabu_archive_target = archive["archiveTarget"]
            if nabu_archive_target not in archive_targets:
                raise Exception(f"Config missing for archive target {nabu_archive_target}")
            archive_target = archive_targets[nabu_archive_target]
            case.archiving_destination = archive_target.destination
            if case.archiving_status == ArchivingStatus.COMPLETE:
                if archive_target.retention == 0:
                    case.archiving_status = ArchivingStatus.DELETED
                else:
                    # use staging date since we don't have the actual archive date
                    archive_date = parse_date(archive["filesCopiedToOffsiteArchiveStagingDir"])
                    match archive_target.retention_units:
                        case RetentionUnits.DAYS:
                            expiry_date = archive_date + timedelta(days=archive_target.retention)
                        case RetentionUnits.MONTHS:
                            expiry_date = archive_date + relativedelta(months=archive_target.retention)
                        case RetentionUnits.YEARS:
                            expiry_date = archive_date + relativedelta(years=archive_target.retention)
                        case _:
                            raise Exception(f"Unhandled retention units: {archive_target.retention_units}")
                    if today > expiry_date:
                        case.archiving_status = ArchivingStatus.EXPIRED
                    else:
                        case.archiving_ttl_days = (expiry_date - today).days
        elif is_complete(case):
            if has_sequencing(case):
                case.archiving_status = ArchivingStatus.PENDING
            else:
                case.archiving_status = ArchivingStatus.NOT_APPLICABLE

    for case_id in archives_by_case_id.keys():
        app_metrics.nabu_archive_errors.inc()
        logging.warning("Nabu archive case not found: %s", case_id)


def get_nabu_archive_status(nabu_archive) -> ArchivingStatus:
    if nabu_archive["filesUnloaded"]:
        return ArchivingStatus.COMPLETE
    elif nabu_archive["stopProcessing"]:
        return ArchivingStatus.PAUSED
    else:
        return ArchivingStatus.STARTED


def is_complete(case: PreprocessedCase) -> bool:
    if not case.deliverables:
        return False
    for deliverable in case.deliverables:
            if not deliverable.releases:
                return False
            for release in deliverable.releases:
                if release.qc_state == None and release.qc_release == None:
                    return False
    return True


def has_sequencing(case: PreprocessedCase) -> bool:
    for test in case.assay_tests:
        if test.full_depth_sequencings:
            return True
        if test.library_qualifications:
            for sample in test.library_qualifications:
                if sample.sequencing_run_id:
                    return True


# noinspection PyTypeChecker
argparser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
argparser.add_argument("--pinery-url",
                       required=True,
                       help="Pinery URL to retrieve LIMS data from")
argparser.add_argument("--qcetl-metrics-file",
                       help="JSON config file containing metric definitions for extraction from "
                       + "QC-ETL")
argparser.add_argument("--qcetl-dir",
                       action="append",
                       help="QC-ETL directory to retrieve QC data from. If multiple are "
                       + "specified, they are used in the order specified to fill in any missing "
                       + "data")
argparser.add_argument('--miso-db-config',
                       required=True,
                       help='Config file for MISO DB connection')
argparser.add_argument('--nabu-url',
                       help='Nabu URL to retrieve case sign-offs from')
argparser.add_argument('--nabu-key-file',
                       help='File containing Nabu API key')
argparser.add_argument('--nabu-archive-config-file',
                       help='CSV file containing archive target definitions')
argparser.add_argument('--prometheus-url',
                       help='Prometheus Pushgateway URL for metrics')
argparser.add_argument('--environment',
                       choices=["production", "staging", "development"],
                       help='Environment label for metrics (production/staging/development)')
argparser.add_argument("--data-output-dir",
                       required=True,
                       help="Write data to this directory")
argparser.add_argument("--tat-exemptions-file",
                       help="CSV file containing date ranges to omit from TAT calculation")
argparser.add_argument("--explain-tat-case",
                       action="append",
                       help="Print a breakdown of TAT calculation for the specified case")
args = argparser.parse_args()
pinery_url = args.pinery_url
miso_db_config = args.miso_db_config
nabu_url = args.nabu_url
nabu_key_file = args.nabu_key_file
nabu_archive_config_file = args.nabu_archive_config_file
prometheus_url = args.prometheus_url
environment = args.environment
data_output_directory = args.data_output_dir
qcetl_metrics_file = args.qcetl_metrics_file
qcetl_dirs = args.qcetl_dir
tat_exempt_dates = read_tat_exemptions(args.tat_exemptions_file) if args.tat_exemptions_file else []
explain_tat_case_ids = args.explain_tat_case or []

if prometheus_url and not environment:
    argparser.error("--environment is required when specifying --prometheus-url")

if nabu_url:
    if not nabu_key_file:
        argparser.error("--nabu-key-file is required when specifying --nabu-url")
    if not nabu_archive_config_file:
        argparser.error("--nabu-archive-config-file is required when specifying --nabu-url")
    nabu_key = read_nabu_key_file(nabu_key_file)
    archive_targets = nabu.read_archive_config(nabu_archive_config_file)

if qcetl_metrics_file and not qcetl_dirs:
    argparser.error("--qcetl-dir is required when specifying --qcetl-metrics-file")

os.makedirs(data_output_directory, exist_ok=True)

# load data from Pinery
start_time = timeit.default_timer()
pinery_users_by_id = {x['id']: x for x in get_users(pinery_url)}
pinery_instruments_by_id = get_instruments_with_model(pinery_url)
pinery_requisitions = get_requisitions(pinery_url)
pinery_runs = get_sequencer_runs(pinery_url)
pinery_samples = get_pinery_samples(pinery_url, pinery_runs, pinery_users_by_id)
pinery_projects = {project["name"]: project for project in get_projects(pinery_url)}
pinery_assays_by_id = {x['id']: x for x in get_assays(pinery_url)}
print(f"Completed extraction from pinery in {timeit.default_timer() - start_time:.1f}s")

# preprocess pinery data
start_time = timeit.default_timer()
preprocessed_runs_by_id = preprocess_runs(pinery_runs, pinery_instruments_by_id, pinery_users_by_id)
preprocessed_donors, preprocessed_samples = preprocess_samples(pinery_samples)
preprocessed_requisitions_by_id = preprocess_requisitions(pinery_requisitions, pinery_users_by_id)

# remove references to allow GC
del pinery_users_by_id
del pinery_instruments_by_id
del pinery_runs
del pinery_samples

# collect cases
output_cases: List[PreprocessedCase] = []
output_requisitions_by_id: Dict[int, PreprocessedRequisition] = {}
output_donors_by_id: Dict[str, PreprocessedDonor] = {}
output_samples_by_id: Dict[str, PreprocessedPinerySample] = {}
output_projects_by_name = {}
output_run_ids: set[int] = set()
output_assays = preprocess_assays(pinery_assays_by_id.values())
output_assays_by_id = {x.id: x for x in output_assays}

required_cases: Dict[str, RequiredCase] = {}
sample_ids_by_run: Dict[int, Set[str]] = {}

for pinery_requisition in pinery_requisitions:
    if not 'assay_ids' in pinery_requisition or not 'sample_ids' in pinery_requisition:
        continue

    for assay_id in pinery_requisition['assay_ids']:
        pinery_assay = pinery_assays_by_id[assay_id]
        if not 'tests' in pinery_assay:
            continue

        preprocessed_requisition = preprocessed_requisitions_by_id[pinery_requisition['id']]
        output_requisitions_by_id[preprocessed_requisition.id] = preprocessed_requisition

        requisition_receipts = [preprocessed_samples[sample_id] for sample_id in
                pinery_requisition.get('sample_ids', [])]

        requisition_samples = collect_qcable_children(requisition_receipts, preprocessed_samples)
        supplemental_samples = collect_supplemental_samples(pinery_requisition, preprocessed_samples)
        for sample in supplemental_samples:
            if sample.requisition_id:
                output_requisitions_by_id[sample.requisition_id] = preprocessed_requisitions_by_id[sample.requisition_id]

        # form cases based on requisitioned receipt samples only
        for sample_id in pinery_requisition['sample_ids']:
            sample = preprocessed_samples[sample_id]
            for test in pinery_assay.get('tests'):
                if test['repeat_per_timepoint'] and sample_valid_for_test(test, sample):
                    donor_id = sample.donor_id
                    donor = preprocessed_donors[donor_id]
                    output_donors_by_id[donor_id] = donor
                    add_required_case(donor, preprocessed_requisition, pinery_assay, sample,
                            requisition_receipts + requisition_samples, supplemental_samples,
                            required_cases)
                    break

del pinery_requisitions
del pinery_assays_by_id

for required_case in required_cases.values():
    case = PreprocessedCase(
        donor=required_case.donor,
        assay_id=required_case.assay['id'],
        assay_name=required_case.assay['name'],
        tissue_origin=required_case.tissue_origin,
        tissue_type=required_case.tissue_type,
        timepoint=required_case.timepoint,
        requisition=required_case.requisition
    )

    requisition_samples_by_id: Dict[str, PreprocessedPinerySample] = {}
    supplemental_samples_by_id: Dict[str, PreprocessedPinerySample] = {}
    for test in required_case.assay['tests']:
        permitted_samples = test.get('permitted_samples', 'ALL')
        if permitted_samples == 'SUPPLEMENTAL':
            requisition_samples = []
        else:
            requisition_samples = [sample for sample in required_case.requisition_samples
                    if include_in_test(case, test, sample)]
        if permitted_samples == 'REQUISITIONED':
            supplemental_samples = []
        else:
            # exclude requisitioned samples in-case of related requisitioned+supplemental samples
            supplemental_samples = [sample for sample in required_case.supplemental_samples
                    if sample not in requisition_samples and include_in_test(case, test, sample)]
        # group by tissue origin, tissue type, timepoint, group ID
        if permitted_samples == 'REQUISITIONED':
            required_tests = find_required_tests(test, requisition_samples)
        elif permitted_samples == 'SUPPLEMENTAL':
            required_tests = find_required_tests(test, supplemental_samples)
        else:
            required_tests = find_required_tests(test, requisition_samples + supplemental_samples)
        case.assay_tests.extend(required_tests)
        requisition_samples_by_id.update({x.sample_id: x for x in requisition_samples})
        supplemental_samples_by_id.update({x.sample_id: x for x in supplemental_samples})
    for sample in requisition_samples_by_id.values():
        add_case_sample(case, sample, False, output_samples_by_id, output_run_ids, output_assays_by_id, preprocessed_runs_by_id)
        if sample.qcable_type == QcableType.RECEIPT_INSPECTION:
            sample.assay_ids.add(case.assay_id)
            children = collect_children_within_requisition(sample, preprocessed_samples)
            for child in children:
                child.assay_ids.add(case.assay_id)
    for sample in supplemental_samples_by_id.values():
        add_case_sample(case, sample, True, output_samples_by_id, output_run_ids, output_assays_by_id, preprocessed_runs_by_id)
    for test in case.assay_tests:
        mark_skipped_gates(case, test, preprocessed_samples)
    collect_projects(case, output_projects_by_name, pinery_projects)
    output_cases.append(case)

# normally, a sample is only assigned assays based on the cases that it is used in within its own
# requisition. If a supplemental sample has no cases of its own (e.g. reference sample alone in its
# own req), add all of the assays from its own requisition so that metrics can be shown.
for case in output_cases:
    for receipt in case.receipts:
        if receipt.requisition_id and not receipt.assay_ids:
            requisition = output_requisitions_by_id[receipt.requisition_id]
            children = collect_children_within_requisition(receipt, preprocessed_samples)
            for assay_id in requisition.assay_ids:
                receipt.assay_ids.add(assay_id)
                for child in children:
                    child.assay_ids.add(assay_id)

omitted_samples = [x for x in preprocessed_samples.values()
        if x.qcable_type == QcableType.RECEIPT_INSPECTION
        and x.sample_id not in output_samples_by_id
        and pinery_projects[x.project_name]['active']
        and pinery_projects[x.project_name]['pipeline'] != "Sample Tracking only"]
for sample in omitted_samples:
    add_project(sample.project_name, pinery_projects, output_projects_by_name)
    output_donors_by_id[sample.donor_id] = preprocessed_donors[sample.donor_id]
    requisition_id = sample.requisition_id
    if requisition_id:
        output_requisitions_by_id[requisition_id] = preprocessed_requisitions_by_id[requisition_id]

omitted_runlibs = [x for x in preprocessed_samples.values()
        if x.sample_category == SampleType.SEQUENCED_SAMPLE
        and x.sequencing_run_id in output_run_ids
        and x.sample_id not in output_samples_by_id]

del pinery_projects
print(f"Completed transformation in {timeit.default_timer() - start_time:.1f}s")

start_time = timeit.default_timer()
miso_db_connection = connect_db(miso_db_config)
add_runscanner_data(preprocessed_runs_by_id, output_run_ids, sample_ids_by_run, output_samples_by_id, miso_db_connection)
add_transfer_data(preprocessed_samples, miso_db_connection)
miso_db_connection.close()
print(f"Completed extraction from MISO DB in {timeit.default_timer() - start_time:.1f}s")

if qcetl_dirs:
    start_time = timeit.default_timer()
    add_qcetl_data(output_samples_by_id.values(), qcetl_metrics_file, qcetl_dirs)
collect_analysis_metrics(output_cases)
if qcetl_dirs:
    print(f"Completed extraction from QC-ETL in {timeit.default_timer() - start_time:.1f}s")

if nabu_url:
    start_time = timeit.default_timer()
    add_nabu_signoffs(output_cases, nabu_url, nabu_key)
    add_archive_info(output_cases, nabu_url, nabu_key, archive_targets)
    print(f"Completed extraction from Nabu in {timeit.default_timer() - start_time:.1f}s")

start_time = timeit.default_timer()
for case in output_cases:
    calculate_turnaround_times(case, tat_exempt_dates, preprocessed_runs_by_id,
            explain=case.get_case_id() in explain_tat_case_ids)
print(f"Completed TAT calculation in {timeit.default_timer() - start_time:.1f}s")

start_time = timeit.default_timer()
write_timestamp(data_output_directory, 'WORKING')
write_json(data_output_directory, 'projects.json', [x for x in output_projects_by_name.values()])
write_json(data_output_directory, 'cases.json', [x.to_dict() for x in output_cases])
write_json(data_output_directory, 'donors.json',
        [x.to_dict() for x in output_donors_by_id.values()])
write_json(data_output_directory, 'requisitions.json',
        [x.to_dict() for x in output_requisitions_by_id.values()])
write_json(data_output_directory, 'assays.json', [x.to_dict() for x in output_assays])
write_json(data_output_directory, 'runs.json',
        [x.to_dict() for x in preprocessed_runs_by_id.values() if x.id in output_run_ids])
write_json(data_output_directory, 'samples.json',
        [x.to_dict() for x in output_samples_by_id.values()])
write_json(data_output_directory, 'receipts_nocase.json',
        [x.to_minimal_sample() for x in omitted_samples])
write_json(data_output_directory, 'run_samples_nocase.json',
        [x.to_omitted_runlibrary() for x in omitted_runlibs])
write_timestamp(data_output_directory, datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'))
print(f"Completed load to file in {timeit.default_timer() - start_time:.1f}s")

if prometheus_url:
    app_metrics.push(prometheus_url, environment)

def main():
    pass
