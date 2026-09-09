from copy import deepcopy
from dataclasses import dataclass, field
import datetime
from enum import Enum
from typing import List, Dict, Set
import re

clone_id_pattern = re.compile(r"([A-Z]{3}\d+)_clone")

class QcableType(Enum):
    RECEIPT_INSPECTION = "receipt_inspection"
    EXTRACTION = "extraction"
    LIBRARY_PREPARATION = "library_preparation"
    LIBRARY_QUALIFICATION = "library_qualification"
    FULL_DEPTH_SEQUENCING = "full_depth_sequencing"
    ANALYSIS_REVIEW = "analysis_review"
    RELEASE_APPROVAL = "release_approval"
    RELEASE = "release"

    def __lt__(self, other):
        # sort by enum order
        if self == other:
            return False
        for x in QcableType:
            if x == self:
                return True
            elif x == other:
                return False
        raise RuntimeError("Unexpected sort error")
    
    def ordinal(self) -> int:
        i = 0
        for x in QcableType:
            if x == self:
                return i
            i += 1
        raise RuntimeError("Unexpected indexing error")


class SequencingType(Enum):
    LOW_PASS = "low_pass"
    FULL_DEPTH = "full_depth"
    UNKNOWN = "unknown"


class SampleType(Enum):
    IDENTITY = "identity"
    TISSUE = "tissue"
    TISSUE_PROCESSING = "tissue_processing"
    STOCK = "stock"
    ALIQUOT = "aliquot"
    LIBRARY = "library"
    LIBRARY_ALIQUOT = "library_aliquot"
    SEQUENCED_SAMPLE = "sequenced_sample"
    UNKNOWN = "unknown"


class ThresholdType(Enum):
    GT = "GT"
    GE = "GE"
    LE = "LE"
    LT = "LT"
    BETWEEN = "BETWEEN"
    BOOLEAN = "BOOLEAN"

    def of(threshold_type: str):
        for t in ThresholdType:
            if t.value == threshold_type:
                return t
        raise ValueError(f"Unknown ThresholdType value {threshold_type}")


class MetricLevel(Enum):
    RUN = "RUN"
    LANE = "LANE"
    SAMPLE = "SAMPLE"

class MetricType(Enum):
    def __new__(cls, metric_label, metric_level):
        member = object.__new__(cls)
        member.metric_label = metric_label
        member.metric_level = metric_level
        return member

    # Run metrics
    BASES_OVER_Q30 = 'Bases Over Q30', MetricLevel.RUN
    CONTROL_BASES_OVER_Q30 = 'Control Bases Over Q30', MetricLevel.RUN
    OUTPUT_READS = 'Output Reads', MetricLevel.RUN
    MIN_CLUSTERS_PF = 'Min Clusters (PF)', MetricLevel.LANE
    PHIX = 'PhiX Control', MetricLevel.LANE

    def of(metric_label: str):
        for m in MetricType:
            if m.metric_label == metric_label:
                return m
        return None


class ArchivingStatus(Enum):
    PENDING = "PENDING"
    STARTED = "STARTED"
    PAUSED = "PAUSED"
    COMPLETE = "COMPLETE"
    DELETED = "DELETED"
    EXPIRED = "EXPIRED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


@dataclass
class SampleMetric:
    name: str
    metric_level: MetricLevel
    threshold_type: ThresholdType
    run_values: Dict[int, Dict[str, float]] = field(default_factory=dict) # {lane_num: {key: metric, ...}}
    threshold_min: float=None
    threshold_max: float=None
    preliminary: bool=None
    _value: float=None
    qc_passed: bool=None
    units: str=None
    has_joined_lanes: bool=False
    finalized: bool=False # only used in qcetl_extract, so may not be marked accurately for some metrics

    def __init__(self, name, metric_level, threshold_type, threshold_min, threshold_max, preliminary: bool=None, value: float=None, qc_passed: bool=None, units: str=None):
        self.name = name
        self.metric_level = metric_level
        self.threshold_type = threshold_type if isinstance(threshold_type, ThresholdType) else ThresholdType.of(threshold_type)
        self.units = units
        self.threshold_min = None if threshold_min is None else float(threshold_min)
        self.threshold_max = None if threshold_max is None else float(threshold_max)
        self.preliminary = preliminary
        self._value = None if value is None else float(value)
        self.run_values = None
        if qc_passed is not None:
            self.qc_passed = qc_passed
        else:
            self.calculate_qc_passed()

    @property
    def value(self):
        return self._value
    
    @value.setter
    def value(self, value):
        self._value = None if value is None else float(value)
        self.calculate_qc_passed()

    def unit_aware_threshold_value(self, val: float) -> float:
        """Return a units-aware threhold value"""
        if val is None:
            return None
        val = float(val)
        if self.units is None:
            return val
        
        # These are represented as K/M/B (/lane)
        units_portion = self.units.split('/',maxsplit=1)[0]
        multiplier  = 1
        match units_portion:
            case "K":
                multiplier = 1000
            case "M":
                multiplier = 1000000
            case "B":
                multiplier = 1000000000
            case _:
                multiplier = 1
        
        return float(val * multiplier)
    
    def add_sample_value(self, metric_value: float, preliminary: bool):
        self.preliminary = preliminary
        self.value = metric_value  # setting this calls calculate_qc_passed()

    def add_run_values(self, value: float, run_values: Dict[str, float], has_joined_lanes: bool):
        self.has_joined_lanes = has_joined_lanes
        if run_values is not None:
            run_value_floats = deepcopy(run_values)
            for k, inner in run_value_floats.items():
                for ik, v in inner.items():
                    run_value_floats[k][ik] = None if v is None else float(v)
            self.run_values = run_value_floats
        self.value = value
        self.calculate_qc_passed()

    def calculate_qc_passed(self):
        if self.threshold_type == ThresholdType.BOOLEAN:
            # ThresholdType.BOOLEAN metrics should have qc_passed set directly, based on the element's qc_state.
            # Exception: SAMPLE_AUTHENTICATED qc_passed is set in qcetl_extract
            return
        if self.name == MetricType.MIN_CLUSTERS_PF.metric_label and self.has_joined_lanes and self.units:
            if "lane" in self.units:
                raise ValueError(f"Cannot evaluate per-lane units {self.units} for metric {MetricType.MIN_CLUSTERS_PF.metric_label} on joined lanes run")
            else:
                # the lack of "/lane" in the units means it should be evaluated at the run level
                self.qc_passed = self.evaluate_qc_passed_for_value(self.value)
                return
        elif self.metric_level == MetricLevel.LANE:
            self.qc_passed = self.evaluate_qc_passed_for_run_values(self.run_values)
            return
        else:
            self.qc_passed = self.evaluate_qc_passed_for_value(self.value)
            return
    
    def evaluate_qc_passed_for_value(self, given_value):
        if given_value is None:
            return None
        t_min = self.unit_aware_threshold_value(self.threshold_min)
        t_max = self.unit_aware_threshold_value(self.threshold_max)
        match self.threshold_type:
            case ThresholdType.GE:
                return given_value >= t_min
            case ThresholdType.GT:
                return given_value > t_min
            case ThresholdType.LE:
                return given_value <= t_max
            case ThresholdType.LT:
                return given_value < t_max
            case ThresholdType.BETWEEN:
                return t_min <= given_value and given_value <= t_max
            case _:
                raise ValueError(f"Cannot calculate qc passed for ThresholdType {self.threshold_type.name}")
            
    def evaluate_qc_passed_for_run_values(self, run_values):
        if not run_values:
            return None
        for lane_values in run_values.values():
            if not all(self.evaluate_qc_passed_for_value(value) for value in lane_values.values() if value is not None):
                return False
        return True

    def to_dict(self) -> dict:
        # explicitly define how to serialize the enums, and omit fields starting with underscore
        return {
            'name': self.name,
            'threshold_type': self.threshold_type.value,
            'threshold_min': self.threshold_min,
            'threshold_max': self.threshold_max,
            'metric_level': self.metric_level.value,
            'preliminary': self.preliminary,
            'run_values': self.run_values,
            'value': self.value,
            'qc_passed': self.qc_passed,
            'units': self.units
        }



@dataclass
class PreprocessedPinerySample:
    sample_id: str
    donor_id: str
    parent_id: str
    child_ids: List[str]
    project_name: str
    oicr_internal_name: str
    external_name: str
    tissue_material: str
    tissue_origin: str
    tissue_type: str
    purity: float
    collapsed_coverage: float
    timepoint: str
    secondary_id: str
    nucleic_acid_type: str
    library_design: str
    library_kit: str
    library_size: int
    barcodes: str
    targeted_sequencing: str
    sample_type: str
    sample_category: SampleType
    volume: float
    concentration: float
    concentration_units: str
    group_id: str
    dv200: float
    tumour_content: float
    sequencing_type: SequencingType
    sequencing_run_id: int
    sequencing_lane: int
    qc_state: str
    qc_reason: str
    qc_note: str
    qc_user: str
    qc_date: str
    data_review_state: str
    data_review_user: str
    data_review_date: str
    entered: str
    created: str
    received: str
    ghost: bool
    requisitioned: bool
    requisition_id: int
    qcable_type: QcableType = None
    extraction_transfer_dates: list[str] = field(default_factory=list)
    callability: float = None
    metrics: Dict[str, SampleMetric] = field(default_factory=dict)
    assay_ids: Set[int] = field(default_factory=set)
    analysis_skipped: bool = None

    def to_dict(self) -> dict:
        # qcable_type and child_ids are omitted because they are intended for case-etl internal
        # use only. Some samples end up being used for multiple qc gates after temporary clones are
        # removed
        return {
            'sample_id': self.sample_id,
            'donor_id': self.donor_id,
            'parent_id': self.parent_id,
            'project_name': self.project_name,
            'oicr_internal_name': self.oicr_internal_name,
            'external_name': self.external_name,
            'tissue_material': self.tissue_material,
            'tissue_origin': self.tissue_origin,
            'tissue_type': self.tissue_type,
            'purity': self.purity,
            'collapsed_coverage': self.collapsed_coverage,
            'timepoint': self.timepoint,
            'secondary_id': self.secondary_id,
            'nucleic_acid_type': self.nucleic_acid_type,
            'library_design': self.library_design,
            'library_kit': self.library_kit,
            'library_size': self.library_size,
            'barcodes': self.barcodes,
            'targeted_sequencing': self.targeted_sequencing,
            'sample_type': self.sample_type,
            'sample_category': self.sample_category.value if self.sample_category else None,
            'volume': self.volume,
            'concentration': self.concentration,
            'concentration_units': self.concentration_units,
            'group_id': self.group_id,
            'dv200': self.dv200,
            'sequencing_type': self.sequencing_type.value if self.sequencing_type else None,
            'sequencing_run_id': self.sequencing_run_id,
            'sequencing_lane': self.sequencing_lane,
            'qc_state': self.qc_state,
            'qc_reason': self.qc_reason,
            'qc_note': self.qc_note,
            'qc_user': self.qc_user,
            'qc_date': self.qc_date,
            'data_review_state': self.data_review_state,
            'data_review_user': self.data_review_user,
            'data_review_date': self.data_review_date,
            'entered': self.entered,
            'created': self.created,
            'received': self.received,
            'ghost': self.ghost,
            'requisitioned': self.requisitioned,
            'requisition_id': self.requisition_id,
            'transfer_date': max(self.extraction_transfer_dates) if self.extraction_transfer_dates
                    else None,
            'callability': self.callability,
            'metrics': list(m.to_dict() for m in self.metrics.values()) if self.metrics else [],
            'assay_ids': list(self.assay_ids),
            'analysis_skipped': self.analysis_skipped
        }

    def to_minimal_sample(self) -> dict:
        return {
            'sample_id': self.sample_id,
            'donor_id': self.donor_id,
            'project_name': self.project_name,
            'oicr_internal_name': self.oicr_internal_name,
            'entered': self.entered,
            'created': self.created,
            'received': self.received,
            'requisitioned': self.requisitioned,
            'requisition_id': self.requisition_id
        }
    
    def to_omitted_runlibrary(self) -> dict:
        return {
            'sample_id': self.sample_id,
            'oicr_internal_name': self.oicr_internal_name,
            'project_name': self.project_name,
            'sequencing_run_id': self.sequencing_run_id,
            'sequencing_lane': self.sequencing_lane,
            'qc_step': self.qcable_type.name if self.qcable_type else None,
            'qc_state': self.qc_state,
            'qc_reason': self.qc_reason,
            'qc_note': self.qc_note,
            'qc_user': self.qc_user,
            'qc_date': self.qc_date,
            'data_review_state': self.data_review_state,
            'data_review_user': self.data_review_user,
            'data_review_date': self.data_review_date
        }


@dataclass
class PreprocessedLane:
    lane_number: int
    percent_over_q30_read1: float = None
    percent_over_q30_read2: float = None
    clusters_pf: int = None
    percent_phix_read1: float = None
    percent_phix_read2: float = None


@dataclass
class PreprocessedRun:
    id: int
    name: str
    container_model: str
    joined_lanes: bool
    sequencing_parameters: str
    read_length: int
    read_length_2: int
    start_date: str
    completion_date: str
    qc_state: str
    qc_user: str
    qc_date: str
    data_review_state: str
    data_review_user: str
    data_review_date: str
    percent_over_q30: float = None
    clusters_pf: int = None
    lanes: Dict[int, PreprocessedLane] = field(default_factory=dict)
    metrics: Dict[str, SampleMetric] = field(default_factory=dict)

    def to_dict(self) -> dict:
        # metrics are omitted because they are intended for case-etl internal use only
        return {
            'id': self.id,
            'name': self.name,
            'container_model': self.container_model,
            'joined_lanes': self.joined_lanes,
            'sequencing_parameters': self.sequencing_parameters,
            'read_length': self.read_length,
            'read_length_2': self.read_length_2,
            'start_date': self.start_date,
            'completion_date': self.completion_date,
            'qc_state': self.qc_state,
            'qc_user': self.qc_user,
            'qc_date': self.qc_date,
            'data_review_state': self.data_review_state,
            'data_review_user': self.data_review_user,
            'data_review_date': self.data_review_date,
            'percent_over_q30': self.percent_over_q30,
            'clusters_pf': self.clusters_pf,
            'lanes': self.lanes
        }


@dataclass
class PreprocessedAnalysisQcGroup:
    tissue_origin: str
    tissue_type: str
    library_design: str
    group_id: str
    purity: float = None
    collapsed_coverage: float = None
    callability: float = None

@dataclass
class PreprocessedRequisition:
    id: int
    name: str
    stopped: bool
    stop_reason: str
    paused: bool
    pause_reason: str
    # full pause info needed for TAT calculation, but not in output
    pauses_json: List[dict] = field(default_factory=list)
    assay_ids: List[int] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "assay_ids": self.assay_ids,
            "stopped": self.stopped,
            "stop_reason": self.stop_reason,
            "paused": self.paused,
            "pause_reason": self.pause_reason
        }

@dataclass
class PreprocessedAssayTest:
    name: str
    tissue_origin: str
    tissue_type: str
    timepoint: str
    group_id: str
    targeted_sequencing: str
    extraction_sample_type: str
    library_design: str
    library_qualification_design: str
    permitted_samples: str # { "REQUISITIONED" | "SUPPLEMENTAL" | "ALL" }
    extraction_skipped: bool = False
    library_preparation_skipped: bool = False
    library_qualification_skipped: bool = False
    extractions: List[PreprocessedPinerySample] = field(default_factory=list)
    library_preparations: List[PreprocessedPinerySample] = field(default_factory=list)
    library_qualifications: List[PreprocessedPinerySample] = field(default_factory=list)
    full_depth_sequencings: List[PreprocessedPinerySample] = field(default_factory=list)
    extraction_days_spent: int = 0
    extraction_preparation_days_spent: int = 0
    extraction_qc_days_spent: int = 0
    extraction_transfer_days_spent: int = 0
    library_preparation_days_spent: int = 0
    library_qualification_days_spent: int = 0
    library_qualification_loading_days_spent: int = 0
    library_qualification_sequencing_days_spent: int = 0
    library_qualification_qc_days_spent: int = 0
    full_depth_sequencing_days_spent: int = 0
    full_depth_sequencing_loading_days_spent: int = 0
    full_depth_sequencing_sequencing_days_spent: int = 0
    full_depth_sequencing_qc_days_spent: int = 0
    
    def get_original_id(self, sample: PreprocessedPinerySample):
        match = clone_id_pattern.match(sample.sample_id)
        if match:
            return match.group(1)
        else:
            return sample.sample_id

    def to_dict(self) -> dict:
        return {
            'name': self.name,
            'tissue_origin': self.tissue_origin,
            'tissue_type': self.tissue_type,
            'library_design': self.library_design,
            'library_qualification_design': self.library_qualification_design,
            'timepoint': self.timepoint,
            'targeted_sequencing': self.targeted_sequencing,
            'group_id': self.group_id,
            'extraction_skipped': self.extraction_skipped,
            'library_preparation_skipped': self.library_preparation_skipped,
            'library_qualification_skipped': self.library_qualification_skipped,
            'extraction_ids': [x.sample_id for x in self.extractions],
            'library_preparation_ids': [x.sample_id for x in self.library_preparations],
            'library_qualification_ids':
                    [self.get_original_id(x) for x in self.library_qualifications],
            'full_depth_sequencing_ids': [x.sample_id for x in self.full_depth_sequencings],
            'extraction_days_spent': self.extraction_days_spent,
            'extraction_preparation_days_spent': self.extraction_preparation_days_spent,
            'extraction_qc_days_spent': self.extraction_qc_days_spent,
            'extraction_transfer_days_spent': self.extraction_transfer_days_spent,
            'library_preparation_days_spent': self.library_preparation_days_spent,
            'library_qualification_days_spent': self.library_qualification_days_spent,
            'library_qualification_loading_days_spent':
                    self.library_qualification_loading_days_spent,
            'library_qualification_sequencing_days_spent':
                    self.library_qualification_sequencing_days_spent,
            'library_qualification_qc_days_spent': self.library_qualification_qc_days_spent,
            'full_depth_sequencing_days_spent': self.full_depth_sequencing_days_spent,
            'full_depth_sequencing_loading_days_spent':
                    self.full_depth_sequencing_loading_days_spent,
            'full_depth_sequencing_sequencing_days_spent':
                    self.full_depth_sequencing_sequencing_days_spent,
            'full_depth_sequencing_qc_days_spent': self.full_depth_sequencing_qc_days_spent,
        }

@dataclass
class PreprocessedDonor:
    id: str
    name: str
    external_name: str
    project_name: str

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'name': self.name,
            'external_name': self.external_name
        }

@dataclass
class PreprocessedRelease:
    deliverable: str
    qc_state: str = None
    qc_release: bool = None
    qc_user: str = None
    qc_date: str = None
    qc_note: str = None

@dataclass
class PreprocessedDeliverable:
    deliverable_category: str
    analysis_review_skipped: bool
    analysis_review_qc_state: str = None
    analysis_review_qc_release: bool = None
    analysis_review_qc_user: str = None
    analysis_review_qc_date: str = None
    analysis_review_qc_note: str = None
    release_approval_qc_state: str = None
    release_approval_qc_release: bool = None
    release_approval_qc_user: str = None
    release_approval_qc_date: str = None
    release_approval_qc_note: str = None
    releases: List[PreprocessedRelease] = field(default_factory=list)
    analysis_review_days_spent: int = 0
    release_approval_days_spent: int = 0
    release_days_spent: int = 0
    deliverable_days_spent: int = 0

@dataclass
class PreprocessedCase:
    requisition: PreprocessedRequisition
    donor: PreprocessedDonor
    assay_id: int
    assay_name: str
    tissue_origin: str
    tissue_type: str
    timepoint: str
    receipts: List[PreprocessedPinerySample] = field(default_factory=list)
    assay_tests: List[PreprocessedAssayTest] = field(default_factory=list)
    qc_groups: List[PreprocessedAnalysisQcGroup] = field(default_factory=list)
    deliverables: List[PreprocessedDeliverable] = field(default_factory=list)
    start_date: datetime.date = None
    receipt_days_spent: int = 0
    analysis_review_days_spent: int = 0
    release_approval_days_spent: int = 0
    release_days_spent: int = 0
    case_days_spent: int = 0
    pause_days: int = 0
    archiving_status: ArchivingStatus = None
    archiving_destination: str = None
    archiving_ttl_days: int = None

    def to_dict(self) -> dict:
        return {
            'id': self.get_case_id(),
            'requisition_id': self.requisition.id,
            'donor_id': self.donor.id,
            'project_names': self.get_project_names(False),
            'assay_id': self.assay_id,
            'tissue_origin': self.tissue_origin,
            'tissue_type': self.tissue_type,
            'timepoint': self.timepoint,
            'receipt_ids': [x.sample_id for x in self.receipts],
            'assay_tests': [x.to_dict() for x in self.assay_tests],
            'qc_groups': self.qc_groups,
            'deliverables': self.deliverables,
            'stopped': self.requisition.stopped,
            'start_date': self.start_date.strftime("%Y-%m-%d"),
            'receipt_days_spent': self.receipt_days_spent,
            'analysis_review_days_spent': self.analysis_review_days_spent,
            'release_approval_days_spent': self.release_approval_days_spent,
            'release_days_spent': self.release_days_spent,
            'case_days_spent': self.case_days_spent,
            'pause_days': self.pause_days,
            'archiving_status': self.archiving_status.value if self.archiving_status else None,
            'archiving_destination': self.archiving_destination,
            'archiving_ttl_days': self.archiving_ttl_days
        }
    
    def get_project_names(self, include_supplemental_and_donor: bool) -> Set[str]:
        project_names = set()
        if include_supplemental_and_donor:
            project_names.add(self.donor.project_name)
        for sample in self.receipts:
            if (sample.requisition_id == self.requisition.id
                    or include_supplemental_and_donor):
                project_names.add(sample.project_name)
        for test in self.assay_tests:
            project_names.update({x.project_name for x in test.extractions
                    + test.library_preparations + test.library_qualifications
                    + test.full_depth_sequencings if x.requisition_id == self.requisition.id
                    or include_supplemental_and_donor})
        return list(project_names)
    
    def get_case_id(self) -> str:
        return (f'R{self.requisition.id}_a{self.assay_id}_{self.donor.name}_{self.tissue_origin}'
            + f'_{self.tissue_type}{("_t" + self.timepoint) if self.timepoint else ""}')

@dataclass
class PreprocessedProjectDeliverable:
    name: str
    analysis_review_required: bool

@dataclass
class PreprocessedProject:
    name: str
    pipeline: str
    deliverables: Dict[str, List[PreprocessedProjectDeliverable]] = field(default_factory=dict)

@dataclass
class RequiredCase:
    donor: PreprocessedDonor
    assay: dict
    tissue_origin: str
    tissue_type: str
    timepoint: str
    requisition: PreprocessedRequisition
    requisition_samples: List[PreprocessedPinerySample]
    supplemental_samples: List[PreprocessedPinerySample]

@dataclass
class PreprocessedMetric:
    name: str
    sort_priority: int
    _minimum: float
    _maximum: float
    units: str
    tissue_material: str
    tissue_origin: str
    tissue_type: str
    negate_tissue_type: bool
    nucleic_acid_type: str
    container_model: str
    read_length: int
    read_length_2: int
    threshold_type: ThresholdType

    def __init__(self, name, sort_priority, minimum, maximum, units, tissue_material, tissue_origin, tissue_type, negate_tissue_type, nucleic_acid_type, container_model, read_length, read_length_2, threshold_type):
        self.name = name
        self.sort_priority = sort_priority
        self._minimum = None if minimum is None else float(minimum)
        self._maximum = None if maximum is None else float(maximum)
        self.units = units
        self.tissue_material = tissue_material
        self.tissue_origin = tissue_origin
        self.tissue_type = tissue_type
        self.negate_tissue_type = negate_tissue_type
        self.nucleic_acid_type = nucleic_acid_type
        self.container_model = container_model
        self.read_length = read_length
        self.read_length_2 = read_length_2
        self.threshold_type = threshold_type if isinstance(threshold_type, ThresholdType) else ThresholdType.of(threshold_type)

    @property
    def minimum(self):
        return self._minimum
    
    @minimum.setter
    def minimum(self, minimum):
        self._minimum = None if minimum is None else float(minimum)

    @property
    def maximum(self):
        return self._maximum
    
    @maximum.setter
    def maximum(self, maximum):
        self._maximum = None if maximum is None else float(maximum)
    
    def applies(self, sample: PreprocessedPinerySample, run: PreprocessedRun) -> bool:
        if self.tissue_material and self.tissue_material != sample.tissue_material:
            return False
        if self.tissue_origin and self.tissue_origin != sample.tissue_origin:
            return False
        if self.tissue_type:
            if self.negate_tissue_type:
                if self.tissue_type == sample.tissue_type:
                    return False
            elif self.tissue_type != sample.tissue_type:
                return False
        if self.nucleic_acid_type and self.nucleic_acid_type != sample.nucleic_acid_type:
            return False
        if self.container_model:
            if run is None or run.container_model != self.container_model:
                return False
        if self.read_length:
            if run is None:
                return False
            elif not run.read_length or abs(self.read_length - run.read_length) > 1:
                return False
            elif self.read_length_2 and (not run.read_length_2 or abs(self.read_length_2 - run.read_length_2) > 1):
                return False
        if self.name.startswith("Concentration") or self.name.startswith("Quantitative PCR"):
            match (self.units):
                case "ng/\u03bcL":
                    if sample.concentration_units != "NANOGRAMS_PER_MICROLITRE":
                        return False
                case "nM":
                    if sample.concentration_units != "NANOMOLAR":
                        return False
                case "pM":
                    if sample.concentration_units != "PICOMOLAR":
                        return False
        return True
    
    def matches_thresholds(self, name: str, minimum: float, maximum: float, threshold_type: ThresholdType) -> bool:
        return (self.name == name and
                ((self.minimum == float(minimum)) if self.minimum is not None else (self.minimum is None and minimum is None)) and
                ((self.maximum == float(maximum)) if self.maximum is not None else (self.maximum is None and maximum is None)) and
                self.threshold_type == threshold_type)
    
    def to_dict(self) -> dict:
        return {
            'name': self.name,
            'sort_priority': self.sort_priority,
            'minimum': self.minimum,
            'maximum': self.maximum,
            'units': self.units,
            'tissue_material': self.tissue_material,
            'tissue_origin': self.tissue_origin,
            'tissue_type': self.tissue_type,
            'negate_tissue_type': self.negate_tissue_type,
            'nucleic_acid_type': self.nucleic_acid_type,
            'container_model': self.container_model,
            'read_length': self.read_length,
            'read_length_2': self.read_length_2,
            'threshold_type': self.threshold_type
        }

@dataclass
class PreprocessedMetricSubcategory:
    name: str
    sort_priority: int
    library_design: str
    metrics: List[PreprocessedMetric] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            'name': self.name,
            'sort_priority': self.sort_priority,
            'library_design': self.library_design,
            'metrics': [x.to_dict() for x in self.metrics]
        }

@dataclass
class PreprocessedAssayTargets:
    case_days: int
    receipt_days: int
    extraction_days: int
    library_preparation_days: int
    library_qualification_days: int
    full_depth_sequencing_days: int
    analysis_review_days: int
    release_approval_days: int
    release_days: int

@dataclass
class PreprocessedAssay:
    id: int
    name: str
    description: str
    version: str
    targets: PreprocessedAssayTargets
    metric_categories: Dict[str, List[PreprocessedMetricSubcategory]] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'version': self.version,
            'targets': self.targets,
            'metric_categories': {k:[x.to_dict() for x in v] for (k, v) in self.metric_categories.items()}
        }
