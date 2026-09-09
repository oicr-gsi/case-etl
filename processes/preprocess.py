from model.pinery import (PreprocessedAssay, PreprocessedAssayTargets, PreprocessedMetric,
        PreprocessedMetricSubcategory, PreprocessedRequisition, PreprocessedRun, SequencingType,
        SampleType, PreprocessedPinerySample, PreprocessedDonor, QcableType, ThresholdType)
from typing import Dict, List, Tuple
import datetime
import re
import logging

from processes.turnaround_time import parse_date


old_alias_pattern = r'^\w+_\d+_[A-Z][a-z]_[A-Z]_(?:nn|\d{2})_(\d+)-\d+(?:_.*)?'
TODAY = datetime.date.today()


def preprocess_samples(samples: List[object]
        ) -> Tuple[Dict[str, PreprocessedDonor], Dict[str, PreprocessedPinerySample]]:
    preprocessed_samples = {}
    for sample in samples:
        sample_id = sample["id"]
        parent_id = sample["parent_id"]
        child_ids = sample["child_ids"]
        project_name = sample["project"]
        oicr_internal_name = sample["name"]

        # donor case
        external_name = sample["attributes"].get("External Name", None)
        if external_name is None:
            raise Exception("Missing external name")

        # convert to sequencing type
        sequencing_type = None
        if "run_purpose" in sample["sequencing_info"]:
            run_purpose = sample["sequencing_info"].get("run_purpose")
            if run_purpose in ["Quality Control"]:
                sequencing_type = SequencingType.LOW_PASS
            elif run_purpose in ["Production"]:
                sequencing_type = SequencingType.FULL_DEPTH
            else:
                sequencing_type = SequencingType.UNKNOWN
        sequencing_info = sample["sequencing_info"]
        sequencing_run_id = sequencing_info.get("sequencer_run_id", None)
        sequencing_lane = sequencing_info.get("sequencer_run_lane", None)
        data_review_state = sequencing_info.get("data_review_state", None)
        data_review_user = sequencing_info.get("data_review_user", None)
        data_review_date = sequencing_info.get("data_review_date", None)

        nucleic_acid_type = sample["attributes"].get("Nucleic Acid Type", None)
        tissue_material = sample["attributes"].get("Tissue Preparation", None)
        tissue_origin = sample["attributes"].get("Tissue Origin", None)
        tissue_type = sample["attributes"].get("Tissue Type", None)
        timepoint = sample["attributes"].get("Timepoint", None)
        secondary_id = sample["attributes"].get("Tube Id", None)
        dv200 = sample["attributes"].get("DV200", None)
        purity = sample["attributes"].get("Purity", None)
        if purity:
            purity = float(purity)
        collapsed_coverage = sample["attributes"].get("UMI-Collapsed Coverage", None)
        if collapsed_coverage:
            collapsed_coverage = float(collapsed_coverage)
        tumour_content = sample["attributes"].get("Tumour Content", None)
        if tumour_content:
            tumour_content = float(tumour_content)
        library_design = sample["attributes"].get("Source Template Type", None)
        library_kit = sample.get("library_kit", None)
        library_size = sample["attributes"].get("Read Length", None)
        targeted_sequencing = sample["attributes"].get("Targeted Resequencing", None)
        if library_size:
            library_size = int(library_size.split("x")[1])
        volume = sample.get("volume", None)
        concentration = sample.get("concentration", None)
        concentration_units = sample.get("concentration_units", None)
        group_id = sample["attributes"].get("Group ID", None)
        requisition_id = (int(sample["attributes"].get("Requisition ID"))
                if "Requisition ID" in sample["attributes"] else None)

        # convert to internal type:
        pinery_sample_category = sample["attributes"].get("Sample Category", None)
        sample_category = get_sample_category(sample_id, pinery_sample_category, sequencing_type)
        
        # get qc status
        qc_status = sample.get("status", {})
        qc_state = qc_status.get("state")
        qc_reason = qc_status.get("name")
        qc_note = qc_status.get("note")
        qc_user = qc_status.get("user_name")
        qc_date = qc_status.get("date")

        preprocessed_sample = PreprocessedPinerySample(sample_id=sample_id,
                                                       donor_id=sample["donor_id"],
                                                       parent_id=parent_id,
                                                       child_ids=child_ids,
                                                       project_name=project_name,
                                                       oicr_internal_name=oicr_internal_name,
                                                       external_name=external_name,
                                                       tissue_material=tissue_material,
                                                       tissue_origin=tissue_origin,
                                                       tissue_type=tissue_type,
                                                       timepoint=timepoint,
                                                       secondary_id=secondary_id,
                                                       purity=purity,
                                                       collapsed_coverage=collapsed_coverage,
                                                       nucleic_acid_type=nucleic_acid_type,
                                                       library_design=library_design,
                                                       library_kit=library_kit,
                                                       library_size=library_size,
                                                       barcodes=get_barcodes(sample),
                                                       targeted_sequencing=targeted_sequencing,
                                                       sample_type=sample["sample_type"],
                                                       sample_category=sample_category,
                                                       volume=volume,
                                                       concentration=concentration,
                                                       concentration_units=concentration_units,
                                                       group_id=group_id,
                                                       dv200=dv200,
                                                       tumour_content=tumour_content,
                                                       sequencing_type=sequencing_type,
                                                       sequencing_run_id=sequencing_run_id,
                                                       sequencing_lane=sequencing_lane,
                                                       qc_state=qc_state,
                                                       qc_reason=qc_reason,
                                                       qc_note=qc_note,
                                                       qc_user=qc_user,
                                                       qc_date=qc_date,
                                                       data_review_state=data_review_state,
                                                       data_review_user=data_review_user,
                                                       data_review_date=data_review_date,
                                                       entered=sample["entered"],
                                                       created=sample["created"],
                                                       received=sample["received"],
                                                       ghost=sample["ghost"],
                                                       requisitioned=sample["requisitioned"],
                                                       requisition_id=requisition_id,
                                                       analysis_skipped=sample.get("analysis_skipped"))
        preprocessed_samples[sample_id] = preprocessed_sample
    
    mark_receipts(preprocessed_samples)
    mark_extractions(preprocessed_samples)
    mark_library_preparations(preprocessed_samples)
    mark_library_qualifications(preprocessed_samples)
    mark_full_depth(preprocessed_samples)
    
    generate_missing_library_qualifications(preprocessed_samples)
    
    donors = collect_donors(preprocessed_samples)

    return donors, preprocessed_samples


def get_sample_category(sample_id: str, sample_category: str, sequencing_type: SequencingType) -> SampleType:
    if sample_id.startswith("SAM"):
        if sample_category == "Identity":
            return SampleType.IDENTITY
        elif sample_category == "Tissue":
            return SampleType.TISSUE
        elif sample_category == "Tissue Processing":
            return SampleType.TISSUE_PROCESSING
        elif sample_category == "Stock":
            return SampleType.STOCK
        elif sample_category == "Aliquot":
            return SampleType.ALIQUOT
        else:
            raise Exception(f"Invalid sample category: {sample_category}")
    elif sample_id.startswith("LIB"):
        return SampleType.LIBRARY
    elif sequencing_type != None:
        return SampleType.SEQUENCED_SAMPLE
    elif sample_id.startswith("LDI"):
        return SampleType.LIBRARY_ALIQUOT
    else:
        raise Exception(f"Invalid sample ID: {sample_id}")


def get_barcodes(pinery_sample) -> str:
    barcodes = pinery_sample["attributes"].get("Barcode")
    if not barcodes:
        return None
    if "barcode_two" in pinery_sample["attributes"]:
        barcodes = f'{barcodes}-{pinery_sample["attributes"]["Barcode Two"]}'
    return barcodes


def clone_sample(original: PreprocessedPinerySample) -> PreprocessedPinerySample:
    return PreprocessedPinerySample(sample_id=original.sample_id,
                                    donor_id=original.donor_id,
                                    parent_id=original.parent_id,
                                    child_ids=original.child_ids,
                                    project_name=original.project_name,
                                    oicr_internal_name=original.oicr_internal_name,
                                    external_name=original.external_name,
                                    tissue_material=original.tissue_material,
                                    tissue_origin=original.tissue_origin,
                                    tissue_type=original.tissue_type,
                                    timepoint=original.timepoint,
                                    secondary_id=original.secondary_id,
                                    purity=original.purity,
                                    collapsed_coverage=original.collapsed_coverage,
                                    nucleic_acid_type=original.nucleic_acid_type,
                                    library_design=original.library_design,
                                    library_kit=original.library_kit,
                                    library_size=original.library_size,
                                    barcodes=original.barcodes,
                                    targeted_sequencing=original.targeted_sequencing,
                                    sample_type=original.sample_type,
                                    sample_category=original.sample_category,
                                    volume=original.volume,
                                    concentration=original.concentration,
                                    concentration_units=original.concentration_units,
                                    group_id=original.group_id,
                                    dv200=original.dv200,
                                    tumour_content=original.tumour_content,
                                    sequencing_type=original.sequencing_type,
                                    sequencing_run_id=original.sequencing_run_id,
                                    sequencing_lane=original.sequencing_lane,
                                    qc_state=original.qc_state,
                                    qc_reason=original.qc_reason,
                                    qc_note=original.qc_note,
                                    qc_user=original.qc_user,
                                    qc_date=original.qc_date,
                                    data_review_state=original.data_review_state,
                                    data_review_user=original.data_review_user,
                                    data_review_date=original.data_review_date,
                                    entered=original.entered,
                                    created=original.created,
                                    received=original.received,
                                    ghost=original.ghost,
                                    requisitioned=original.requisitioned,
                                    requisition_id=original.requisition_id,
                                    analysis_skipped=original.analysis_skipped)


def mark_receipts(preprocessed_samples: Dict[str, PreprocessedPinerySample]) -> None:
    for sample in preprocessed_samples.values():
        # sample is receipt if it is the first non-synthetic/ghost sample, or library
        if sample.ghost or sample.sample_category == SampleType.IDENTITY:
            continue
        parent = preprocessed_samples[sample.parent_id]
        if parent.ghost or parent.sample_category == SampleType.IDENTITY or sample.requisitioned:
            sample.qcable_type = QcableType.RECEIPT_INSPECTION


def mark_extractions(preprocessed_samples: Dict[str, PreprocessedPinerySample]) -> None:
    for sample in preprocessed_samples.values():
        # sample is extraction if it is the first stock, not synthetic, and not a receipt
        if (sample.sample_category != SampleType.STOCK
            or sample.ghost
            or sample.qcable_type == QcableType.RECEIPT_INSPECTION):
            continue;
        parent = preprocessed_samples[sample.parent_id]
        if parent.sample_category != SampleType.STOCK:
            sample.qcable_type = QcableType.EXTRACTION
            receipt = get_parent_of_type(sample, preprocessed_samples, QcableType.RECEIPT_INSPECTION, True);
            sample.parent_id = receipt.sample_id


def mark_library_preparations(preprocessed_samples: Dict[str, PreprocessedPinerySample]) -> None:
    # library is always considered a library prep
    # library aliquot is considered a library prep if it is the first TS aliquot of a non-ts library
    for sample in preprocessed_samples.values():
        if sample.sample_category == SampleType.LIBRARY:
            mark_library_preparation(sample, preprocessed_samples)
        elif sample.sample_category == SampleType.LIBRARY_ALIQUOT and sample.library_design == 'TS':
            parent = preprocessed_samples[sample.parent_id]
            if parent.library_design != 'TS':
                mark_library_preparation(sample, preprocessed_samples)


def mark_library_preparation(sample: PreprocessedPinerySample, preprocessed_samples: Dict[str, PreprocessedPinerySample]) -> None:
    if (sample.qcable_type != QcableType.RECEIPT_INSPECTION):
        sample.qcable_type = QcableType.LIBRARY_PREPARATION
        parent = get_parent_of_type(sample, preprocessed_samples, QcableType.EXTRACTION, False);
        if not parent:
            parent = get_parent_of_type(sample, preprocessed_samples, QcableType.RECEIPT_INSPECTION, True);
        sample.parent_id = parent.sample_id


def is_bottom_library_or_aliquot(sample: PreprocessedPinerySample) -> bool:
    if not sample.sample_category in [SampleType.LIBRARY, SampleType.LIBRARY_ALIQUOT]:
        return False
    for child_id in sample.child_ids:
        if child_id.startswith("LDI"):
            return False
    return True


def mark_library_qualifications(preprocessed_samples: Dict[str, PreprocessedPinerySample]) -> None:
    for sample in preprocessed_samples.values():
        # bottom library aliquot is used if the test's library qualification method is library aliquot
        # handled here if separate from the library preparation (expect 2 levels of library/aliquot)
        # generate_missing_library_qualifications handles cases where it is the same
        if (sample.sample_category == SampleType.LIBRARY_ALIQUOT
              and sample.qcable_type == None
              and is_bottom_library_or_aliquot(sample)):
            mark_library_qualification(sample, preprocessed_samples)
        # low pass sequenced sample is used for library qualification if the test's library
        # qualification method is low pass sequencing
        elif (sample.sample_category == SampleType.SEQUENCED_SAMPLE
              and sample.sequencing_type == SequencingType.LOW_PASS):
            mark_library_qualification(sample, preprocessed_samples)


def mark_library_qualification(sample: PreprocessedPinerySample,
                               preprocessed_samples: Dict[str, PreprocessedPinerySample]) -> None:
    sample.qcable_type = QcableType.LIBRARY_QUALIFICATION
    parent = get_parent_of_type(sample, preprocessed_samples, QcableType.LIBRARY_PREPARATION, False)
    if not parent:
        parent = get_parent_of_type(sample, preprocessed_samples, QcableType.RECEIPT_INSPECTION, True)
    sample.parent_id = parent.sample_id


def mark_full_depth(preprocessed_samples: Dict[str, PreprocessedPinerySample]) -> None:
    for sample in preprocessed_samples.values():
        if (sample.sample_category == SampleType.SEQUENCED_SAMPLE
            and sample.sequencing_type == SequencingType.FULL_DEPTH):
            sample.qcable_type = QcableType.FULL_DEPTH_SEQUENCING
            parent = get_parent_of_type(sample, preprocessed_samples, QcableType.LIBRARY_PREPARATION, False)
            if not parent:
                parent = get_parent_of_type(sample, preprocessed_samples, QcableType.RECEIPT_INSPECTION, False)
            sample.parent_id = parent.sample_id


# TS assays expect hierarchy to include:
# 1. WG library prep (MISO library)
# 2. TS library prep (MISO library aliquot)
# 3. TS library qualification (MISO library aliquot)
# Sometimes 2 and 3 are the same library aliquot though. Handle that here
def generate_missing_library_qualifications(preprocessed_samples: Dict[str, PreprocessedPinerySample]) -> None:
    full_depth = [x for x in preprocessed_samples.values()
                  if x.qcable_type == QcableType.FULL_DEPTH_SEQUENCING and x.library_design == 'TS']
    for runlib in full_depth:
        library_preparation = preprocessed_samples[runlib.parent_id]
        library_qualification_found = False
        for child_id in library_preparation.child_ids:
            child = preprocessed_samples[child_id]
            if child.qcable_type == QcableType.LIBRARY_QUALIFICATION:
                library_qualification_found = True
                break
        if not library_qualification_found:
            library_qualification = clone_sample(library_preparation)
            library_qualification.sample_id += '_clone'
            library_qualification.parent_id = library_preparation.sample_id
            library_qualification.qcable_type = QcableType.LIBRARY_QUALIFICATION
            library_preparation.child_ids = [library_qualification.sample_id]
            preprocessed_samples[library_qualification.sample_id] = library_qualification


def get_parent_of_type(preprocessed_sample: PreprocessedPinerySample,
                       preprocessed_samples: Dict[str, PreprocessedPinerySample],
                       qcable_type: QcableType, required: bool = False
                       ) -> PreprocessedPinerySample:
    parent_id = preprocessed_sample.parent_id
    if parent_id is None:
        if required:
            raise Exception(f"Required {qcable_type.value} parent not found")
        else:
            return None
    preprocessed_sample_parent = preprocessed_samples.get(parent_id)
    if preprocessed_sample_parent is None:
        raise Exception(
            f"sample={preprocessed_sample.sample_id} is referencing parent={parent_id} which does not exist")
    if preprocessed_sample_parent.qcable_type == qcable_type:
        return preprocessed_sample_parent
    else:
        return get_parent_of_type(preprocessed_sample_parent, preprocessed_samples, qcable_type, required)


def collect_donors(preprocessed_samples: Dict[str, PreprocessedPinerySample]) -> Dict[str, PreprocessedDonor]:
    donors_by_id: Dict[str, PreprocessedDonor] = {}
    for sample in preprocessed_samples.values():
        if not sample.qcable_type:
            continue
        donor_id = sample.donor_id
        if not donor_id in donors_by_id:
            donor_sample = preprocessed_samples[donor_id]
            donors_by_id[donor_id] = PreprocessedDonor(
                id=donor_id,
                name=donor_sample.oicr_internal_name,
                external_name=sample.external_name,
                project_name=donor_sample.project_name
            )
    return donors_by_id

def preprocess_runs(pinery_runs: List[object], pinery_instruments_by_id: Dict[int, object],
        pinery_users_by_id: Dict[int, object]) -> Dict[int, PreprocessedRun]:
    runs_by_id = {}
    for pinery_run in pinery_runs:
        containers = pinery_run.get("containers", [])
        if len(containers) > 1:
            logging.warning(f"Run {pinery_run['id']} has multiple containers, which is not supported. Skipping run.")
            continue
        run_id = pinery_run["id"]
        qc_status = pinery_run.get("status", {})
        qc_user_id = qc_status.get("user_id")
        data_review_user_id = pinery_run.get("data_reviewer_id")
        pinery_read_length = pinery_run.get("read_length")
        read_length = None
        read_length_2 = None
        if pinery_read_length:
            match = re.search(r'^([12])x(\d+)$', pinery_read_length)
            if match:
                read_length = int(match.group(2))
                if int(match.group(1)) == 2:
                    read_length_2 = read_length
        pinery_instrument = pinery_instruments_by_id[pinery_run["instrument_id"]]
        joined_lanes = ('NextSeq' in pinery_instrument['model']['name']
                or pinery_run.get('workflow_type') == 'NOVASEQ_STANDARD')
        runs_by_id[run_id] = PreprocessedRun(
            id=run_id,
            name=pinery_run["name"],
            container_model=containers[0].get("container_model", None) if containers else None,
            joined_lanes=joined_lanes,
            sequencing_parameters=pinery_run.get("sequencing_parameters", None),
            read_length=read_length,
            read_length_2=read_length_2,
            start_date=pinery_run.get("start_date", None),
            completion_date=pinery_run.get("completion_date", None),
            qc_state=qc_status.get("state"),
            qc_user=get_username(qc_user_id, pinery_users_by_id),
            qc_date=qc_status.get("date"),
            data_review_state=pinery_run.get("data_review"),
            data_review_user=get_username(data_review_user_id, pinery_users_by_id),
            data_review_date=pinery_run.get("data_review_date")
        )
    return runs_by_id

def get_username(user_id: int, pinery_users_by_id: Dict[int, object]) -> str:
    if not user_id:
        return None
    else:
        user = pinery_users_by_id[user_id]
        return f'{user["firstname"]} {user["lastname"]}'

def preprocess_assays(pinery_assays: List[object]) -> List[PreprocessedAssay]:
    assays: List[PreprocessedAssay] = []
    for pinery_assay in pinery_assays:
        pinery_targets = pinery_assay.get("targets", {})
        targets = PreprocessedAssayTargets(
            case_days=pinery_targets.get("case_days"),
            receipt_days=pinery_targets.get("receipt_days"),
            extraction_days=pinery_targets.get("extraction_days"),
            library_preparation_days=pinery_targets.get("library_preparation_days"),
            library_qualification_days=pinery_targets.get("library_qualification_days"),
            full_depth_sequencing_days=pinery_targets.get("full_depth_sequencing_days"),
            analysis_review_days=pinery_targets.get("analysis_review_days"),
            release_approval_days=pinery_targets.get("release_approval_days"),
            release_days=pinery_targets.get("release_days")
        )
        assay = PreprocessedAssay(
            id=pinery_assay["id"],
            name=pinery_assay["name"],
            description=pinery_assay.get("description"),
            version=pinery_assay["version"],
            targets=targets
        )
        for pinery_metric in pinery_assay.get("metrics", []):
            metric = PreprocessedMetric(
                name=pinery_metric["name"],
                sort_priority=pinery_metric.get("sort_priority"),
                minimum=pinery_metric.get("minimum"),
                maximum=pinery_metric.get("maximum"),
                units=pinery_metric.get("units"),
                tissue_material=pinery_metric.get("tissue_material"),
                tissue_origin=pinery_metric.get("tissue_origin"),
                tissue_type=pinery_metric.get("tissue_type"),
                negate_tissue_type=pinery_metric.get("negate_tissue_type", False),
                nucleic_acid_type=pinery_metric.get("nucleic_acid_type"),
                container_model=pinery_metric.get("container_model"),
                read_length=pinery_metric.get("read_length"),
                read_length_2=pinery_metric.get("read_length_2"),
                threshold_type=ThresholdType.of(pinery_metric["threshold_type"])
            )
            category = pinery_metric["category"]
            if not category in assay.metric_categories:
                assay.metric_categories[category] = []
            subcategories = assay.metric_categories[category]
            pinery_subcategory = pinery_metric.get("subcategory")
            subcategory_name = pinery_subcategory["name"] if pinery_subcategory else None
            subcategories_filtered = [x for x in subcategories if x.name == subcategory_name]
            if subcategories_filtered:
                subcategory = subcategories_filtered[0]
            elif pinery_subcategory:
                subcategory = PreprocessedMetricSubcategory(
                    name=subcategory_name,
                    sort_priority=pinery_subcategory.get("sort_priority", 0),
                    library_design=pinery_subcategory.get("design_code")
                )
                subcategories.append(subcategory)
            else:
                subcategory = PreprocessedMetricSubcategory(
                    name=subcategory_name,
                    sort_priority=0,
                    library_design=None
                )
                subcategories.append(subcategory)
            subcategory.metrics.append(metric)
        assays.append(assay)
    return assays

def preprocess_requisitions(pinery_requisitions: List[object], pinery_users_by_id: List[object]) -> List[PreprocessedRequisition]:
    return {x['id']: preprocess_requisition(x, pinery_users_by_id) for x in pinery_requisitions}

def preprocess_requisition(pinery_requisition: object, pinery_users_by_id: List[object]) -> PreprocessedRequisition:
    pause = _get_ongoing_pause(pinery_requisition)
    requisition = PreprocessedRequisition(
        id=pinery_requisition.get('id'),
        name=pinery_requisition.get('name'),
        stopped=pinery_requisition.get('stopped'),
        stop_reason=pinery_requisition.get('stop_reason'),
        paused=pause != None,
        pause_reason=pause['reason'] if pause else None,
        pauses_json=pinery_requisition.get('pauses', []),
        assay_ids=pinery_requisition.get('assay_ids', []),
    )
    return requisition

def _get_ongoing_pause(pinery_requisition: object):
    for pause in pinery_requisition.get('pauses', []):
        if ((not pause['end_date'] or parse_date(pause['end_date']) > TODAY)
                and parse_date(pause['start_date']) < TODAY):
            return pause
    return None