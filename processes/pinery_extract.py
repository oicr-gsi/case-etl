import logging

from collections import defaultdict
from utils.pinery import get_samples


def _get_sample_data(sample):
    id = sample["id"]
    project = sample["project_name"]
    name = sample["name"]
    sample_type = sample["sample_type"]
    attributes = _get_attributes(sample)
    requisitioned = "Requisition ID" in attributes

    if "preparation_kit" in sample:
        library_kit = sample["preparation_kit"]["name"]
    else:
        library_kit = None
    
    return {"id": id,
            "project": project,
            "name": name,
            "sample_type": sample_type,
            "library_kit": library_kit,
            "attributes": attributes,
            "status": sample["status"],
            "volume": attributes.get("Initial Volume"),
            "concentration": sample.get("concentration"),
            "concentration_units": sample.get("concentration_units"),
            "entered_date": sample.get("created_date"),
            "received_date": attributes.get("Receive Date"),
            "created_date": attributes.get("In-lab Creation Date"),
            "ghost": attributes.get("Synthetic") == "True",
            "requisitioned": requisitioned,
            "analysis_skipped": sample.get("analysis_skipped")}


def _get_attributes(sample):
    return {attr["name"]: attr["value"] for attr in sample["attributes"]}


def get_pinery_samples(pinery_url, sequencer_runs, users_by_id):
    samples_by_id = {sample["id"]: sample for sample in get_samples(pinery_url)}

    # add sequenced samples (aka run sample, aka IUS) to samples collection
    # construct the sequenced sample to look like a Pinery sample
    for sequencer_run in sequencer_runs:
        containers = sequencer_run.get("containers", [])
        if len(containers) > 1:
            logging.warning(f"Run {sequencer_run['id']} has multiple containers, which is not supported. Skipping run-libraries.")
            continue

        sequencer_run_id = sequencer_run["id"]
        run_entered = sequencer_run["created_date"]
        run_created = sequencer_run["start_date"] if "start_date" in sequencer_run else run_entered

        for container in containers:
            for position in container.get("positions", []):
                if position.get("qc_status") == "On-instrument QC only":
                    continue
                lane_number = position["position"]
                lane_purpose = position["runPurpose"]
                for sample in position.get("samples", []):
                    run_lane_sample_id = sample["id"]
                    sample_id = f"{sequencer_run_id}_{lane_number}_{run_lane_sample_id}"
                    parent_id = run_lane_sample_id
                    parent_sample = samples_by_id[run_lane_sample_id]
                    project_name = parent_sample["project_name"]
                    run_lane_sample_purpose = sample["runPurpose"] if "runPurpose" in sample else lane_purpose
                    data_reviewer = users_by_id.get(sample.get("data_reviewer_id"))
                    data_reviewer_name = f'{data_reviewer["firstname"]} {data_reviewer["lastname"]}' if data_reviewer else None
                    sample_type = parent_sample["sample_type"]
                    name = parent_sample["name"]

                    if "status" in sample:
                        status = sample["status"]
                    else:
                        status = {"name": "Not Ready",
                                "state": "Not Ready"}
                    
                    # Skip conditions checked here:
                    # * lane QC specifies skipped analysis
                    # * run QC failed
                    # * run-library QC failed
                    # NOT checked here:
                    # * consent revoked - set later when collapsing parent attributes
                    # * case stopped - set in case-etl script when building cases
                    analysis_skipped = (position["analysis_skipped"] or status["state"] == "Failed"
                            or ("status" in sequencer_run and sequencer_run["status"].get("state") == "Failed"))

                    # create a sample object for the sequenced sample
                    sequenced_sample = {
                        "id": sample_id,
                        "project_name": project_name,
                        "sample_type": sample_type,
                        "sequencing_info": {
                            "sequencer_run_id": sequencer_run_id,
                            "sequencer_run_lane": lane_number,
                            "run_purpose": run_lane_sample_purpose,
                            "data_review_state": sample.get("data_review"),
                            "data_review_user": data_reviewer_name,
                            "data_review_date": sample.get("data_review_date")
                        },
                        "parents": [{"id": parent_id}],
                        "name": name,
                        "attributes": [],
                        "status": status,
                        "run_entered_date": run_entered,
                        "run_created_date": run_created,
                        "ghost": False,
                        "requisitioned": False,
                        "analysis_skipped": analysis_skipped
                    }
                    samples_by_id[sample_id] = sequenced_sample

    sample_hierarchy = {}
    for sample in samples_by_id.values():
        # get QC user name
        if "status" in sample and "user_id" in sample["status"] and sample["status"]["user_id"] != 0:
            user = users_by_id[sample["status"]["user_id"]]
            sample["status"]["user_name"] = f'{user["firstname"]} {user["lastname"]}'
        
        # get nucleic acid type
        if "DNA" in sample["sample_type"]:
            sample["attributes"].append({
                "name": "Nucleic Acid Type",
                "value": "DNA"
            })
        elif "RNA" in sample["sample_type"]:
            sample["attributes"].append({
                "name": "Nucleic Acid Type",
                "value": "RNA"
            })
        
        parent = None
        if "parents" in sample:
            parents = sample["parents"]
            if len(parents) == 0:
                parent = None
            elif len(parents) == 1:
                parent = parents[0]["id"]
            else:
                raise Exception("multiple parents")
        if sample["id"] in sample_hierarchy:
            raise Exception("sample already exists")
        else:
            sample_hierarchy[sample["id"]] = parent

    sample_children = defaultdict(list)
    for child_id, parent_id in sample_hierarchy.items():
        sample_children[parent_id].append(child_id)

    sample_ancestors = {}
    for sample in samples_by_id.values():
        sample_id = sample["id"]
        ancestors = []
        current_id = sample_id
        while True:  # (python 3.9?) parent_id:=sample_hierarchy[sample_id] is not None:
            parent_id = sample_hierarchy[current_id]
            if parent_id is None:
                break
            else:
                ancestors.append(parent_id)
                current_id = parent_id
        sample_ancestors[sample_id] = ancestors

    samples_with_parent_info = []
    for sample in samples_by_id.values():
        sample_id = sample["id"]
        attributes = {}
        parent_id = sample_hierarchy[sample_id]
        if sample_ancestors[sample_id]:
            donor_id = sample_ancestors[sample_id][-1]
        else:
            donor_id = sample_id
        for ancestor_id in reversed(sample_ancestors[sample_id]):
            parent_attributes = _get_attributes(samples_by_id[ancestor_id])
            attributes.update(parent_attributes)

        if sample.get("sequencing_info") and attributes.get("Consent") == "REVOKED":
            sample["analysis_skipped"] = True

        # get the current sample's children from the hierarchy
        child_ids = sample_children[sample_id]

        current_sample = _get_sample_data(sample)
        attributes.update(current_sample["attributes"])
        if "sequencing_info" in sample:
            entered = sample["run_entered_date"]
            created = sample["run_created_date"]
        else:
            entered = current_sample["entered_date"]
            created = current_sample["created_date"]

        samples_with_parent_info.append({"id": current_sample["id"],
                                         "donor_id": donor_id,
                                         "parent_id": parent_id,
                                         "child_ids": child_ids,
                                         "project": current_sample["project"],
                                         "name": current_sample["name"],
                                         "sequencing_info": sample.get("sequencing_info", {}),
                                         "sample_type": current_sample["sample_type"],
                                         "library_kit": current_sample["library_kit"],
                                         "attributes": attributes,
                                         "status": current_sample["status"],
                                         "volume": current_sample.get("volume"),
                                         "concentration": current_sample.get("concentration"),
                                         "concentration_units": current_sample.get("concentration_units"),
                                         "entered": entered,
                                         "created": created,
                                         "received": current_sample["received_date"],
                                         "ghost": current_sample["ghost"],
                                         "requisitioned": current_sample["requisitioned"],
                                         "analysis_skipped": current_sample.get("analysis_skipped")
                                         })
    return samples_with_parent_info
