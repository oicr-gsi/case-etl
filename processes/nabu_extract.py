import csv
import requests

from dataclasses import dataclass
from enum import Enum

def get_signoffs(nabu_url: str, nabu_key: str) -> list[dict]:
    return _get(nabu_url, "/case/sign-off", nabu_key)

def get_case_archives(nabu_url: str, nabu_key: str) -> list[dict]:
    return _get(nabu_url, "/cases", nabu_key)

def _get(base_url: str, relative_url: str, api_key: str):
    result = requests.get(f"{base_url}{relative_url}", timeout=120, headers=_make_headers(api_key))
    result.raise_for_status()
    return result.json()

def _make_headers(nabu_key: str):
    return {
        "X-API-KEY": nabu_key
    }

class RetentionUnits(Enum):
    DAYS = "days"
    MONTHS = "months"
    YEARS = "years"


@dataclass
class ArchiveTarget:
    destination: str
    retention: int
    retention_units: RetentionUnits

def read_archive_config(filepath: str) -> dict[str, ArchiveTarget]:
    archive_targets = {}
    with open(filepath) as file:
        reader = csv.reader(file)
        next(reader) # skip headings row
        for row in reader:
            if not row:
                continue # skip blank lines
            archive_targets[row[0]] = ArchiveTarget(row[1], int(row[2]), RetentionUnits(row[3]))
    return archive_targets