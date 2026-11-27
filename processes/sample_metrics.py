from model.pinery import (ASSAY_METRIC_CATEGORY_BY_QCABLE_TYPE, MetricLevel, MetricType,
        PreprocessedAssay, PreprocessedPinerySample, PreprocessedRun, QcableType, SampleMetric,
        ThresholdType, clone_id_pattern)


# Gates whose metric values come from MISO sample fields rather than from QC-ETL or run metrics
SAMPLE_FIELD_METRIC_GATES = (QcableType.RECEIPT_INSPECTION, QcableType.EXTRACTION,
        QcableType.LIBRARY_PREPARATION)

# These metrics have no value. Dimsum links to the attachment in MISO instead, so they are left out
# of the sample metrics to keep that display
ATTACHMENT_METRIC_PREFIXES = ("Adaptor Contamination", "AUC between")


def uses_sample_field_metrics(sample: PreprocessedPinerySample) -> bool:
    """True if all of the sample's metric values come from MISO sample fields: receipts,
    extractions, library preparations, and library qualifications that are library aliquots (not
    run-libraries)"""
    return (sample.qcable_type in SAMPLE_FIELD_METRIC_GATES
            or (sample.qcable_type == QcableType.LIBRARY_QUALIFICATION
                    and sample.sequencing_run_id is None))


def add_sample_field_metrics(sample: PreprocessedPinerySample, assay: PreprocessedAssay) -> None:
    if assay is None or not uses_sample_field_metrics(sample):
        return
    if (sample.qcable_type == QcableType.LIBRARY_PREPARATION
            and has_library_qualification_clone(sample)):
        # This library aliquot is also output as the library qualification (see
        # generate_missing_library_qualifications), and sample metrics aren't separated by gate.
        # Leave its metrics out so library preparation metrics don't appear as library
        # qualification metrics
        return
    add_metrics_from_assay(sample, assay, sample.qcable_type, None)


def has_library_qualification_clone(sample: PreprocessedPinerySample) -> bool:
    return any(clone_id_pattern.match(child_id) for child_id in sample.child_ids)


def add_metrics_from_assay(sample: PreprocessedPinerySample, assay: PreprocessedAssay,
        metric_category: QcableType, run: PreprocessedRun) -> None:
    all_metric_subcategories = assay.metric_categories.get(
            ASSAY_METRIC_CATEGORY_BY_QCABLE_TYPE[metric_category])
    if all_metric_subcategories is None:
        return
    from_sample_fields = uses_sample_field_metrics(sample)
    matching_metric_subcategories = [ms for ms in all_metric_subcategories if (
            # If there's a library design on the metric subcategory, it must match
            ms.library_design is None or sample.library_design == ms.library_design
        )]
    for ms in matching_metric_subcategories:
        required_metrics_by_name: dict[str, SampleMetric] = {}
        for metric in ms.metrics:
            if from_sample_fields and metric.name.startswith(ATTACHMENT_METRIC_PREFIXES):
                continue
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
                    sample.metrics[metric.name] = SampleMetric(
                        name=metric.name,
                        metric_level=metric_level,
                        threshold_type=threshold_type,
                        threshold_min=metric.minimum,
                        threshold_max=metric.maximum,
                        top_up=metric.top_up,
                        value=get_sample_metric_value(sample, metric.name),
                        qc_passed=(get_qc_passed(sample.qc_state)
                                if from_sample_fields and threshold_type == ThresholdType.BOOLEAN
                                else None),
                        units=metric.units
                    )
            elif not metric.optional:
                if metric.name in required_metrics_by_name:
                    required_metric = required_metrics_by_name[metric.name]
                    # units are included, but change to "?" if there's a conflict
                    if required_metric.units != metric.units:
                        required_metric.units = '?'
                else:
                    required_metrics_by_name[metric.name] = SampleMetric(
                        name=metric.name,
                        metric_level=metric_level,
                        units=metric.units
                    )
        for required_metric in required_metrics_by_name.values():
            if not required_metric.name in sample.metrics:
                required_metric.add_sample_value(
                        get_sample_metric_value(sample, required_metric.name), False)
                sample.metrics[required_metric.name] = required_metric


def get_sample_metric_value(sample: PreprocessedPinerySample, metric_name: str) -> float:
    match metric_name:
        case None:
            return None
        case "Appropriate volume" | "Volume":
            return sample.volume
        case "Yield" | "Yield (Qubit)":
            if sample.volume is None or sample.concentration is None:
                return None
            return float(sample.volume) * float(sample.concentration)
        case "DV200":
            return sample.dv200
        case "Coverage (Raw)":
            # Must be in nM
            return sample.concentration if sample.concentration_units == "NANOMOLAR" else None
        case "Collapsed Coverage":
            return sample.collapsed_coverage
        case "Quantitative PCR (qPCR)":
            return sample.concentration
        case "Tumour Content":
            return sample.tumour_content
    if metric_name.startswith("Concentration"):
        return sample.concentration
    if metric_name.startswith("Avg Size Distribution"):
        return sample.library_size
    return None


def get_qc_passed(qc_state: str) -> bool:
    match qc_state:
        case "Ready":
            return True
        case "Failed":
            return False
        case _:
            return None
