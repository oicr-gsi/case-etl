import requests as r


def get_projects(pinery_url):
    return get(f"{pinery_url}/sample/projects")


def get_sequencer_runs(pinery_url):
    return get(f"{pinery_url}/sequencerruns")


def get_instruments(pinery_url):
    return get(f"{pinery_url}/instruments")


def get_instrument_models(pinery_url):
    return get(f"{pinery_url}/instrumentmodels")


def get_instruments_with_model(pinery_url):
    instruments = get_instruments(pinery_url)
    instrument_models_by_id = {x["id"]: x for x in get_instrument_models(pinery_url)}
    for instrument in instruments:
        instrument_model = instrument_models_by_id[instrument["model_id"]]
        instrument["model"] = instrument_model
    return {x["id"]: x for x in instruments}


def get_samples(pinery_url):
    return get(f"{pinery_url}/samples")


def get_users(pinery_url):
    return get(f"{pinery_url}/users")


def get_requisitions(pinery_url):
    return get(f"{pinery_url}/requisitions")


def get_assays(pinery_url):
    return get(f"{pinery_url}/assays")


def get(full_url):
    result = r.get(full_url, timeout=120)
    result.raise_for_status()
    return result.json()
