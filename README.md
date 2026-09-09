# Case ETL

Project for collecting and exporting data based on QM-024 QC gates. The data is served by Cardea for
use by other applications such as Dimsum and Shesmu.

## Output

Data files written by Case ETL include:

- **projects.json**: list of projects that are involved in at least one case
- **donors.json**: list of donors that are involved in at least one case
- **samples.json**: list of samples that are involved in at least one case. A "sample"
  may represent a sample, library, library aliquot, or run-library from LIMS
- **requisitions.json**: list of requisitions that are involved in at least one case
- **assays.json**: list of assays including all metrics
- **runs.json**: list of runs that are involved in at least one case
- **cases.json**: list of all cases
- **receipts_nocase.json**: list of receipt samples that are not involved in any cases
- **run_samples_nocase.json**: list of run-library samples that are not involved in any case
- **timestamp**: contains "WORKING" while data write is in progress, or the data timestamp in
  format `2022-06-03T11:41:00` otherwise

## Developer Setup

Requires `uv >= 0.11.7`

```
git clone https://github.com/oicr-gsi/case-etl.git
cd case-etl/

# Install a development version
uv sync --frozen

# Run tests
uv run pytest

# Audit all project dependencies for vulnerabilities
uv audit

# To update all dependencies:
uv lock --upgrade && uv sync --frozen && uv run pytest

# To list available commands
uv run

# Run local case-etl
uv run case-etl
```


## Installation

Requires `uv >= 0.11.7`

```
git clone https://github.com/oicr-gsi/case-etl.git
cd case-etl/

# this will install case-etl into ~/.local/bin/
uv tool install .
```

## Usage

```
usage: case-etl [-h]
  --pinery-url PINERY_URL
  [--qcetl-dir QCETL_DIR]
  --miso-db-config MISO_DB_CONFIG
  [--nabu-url NABU_URL]
  [--nabu-key-file NABU_KEY_FILE]
  [--nabu-archive-config-file NABU_ARCHIVE_CONFIG_FILE]
  [--prometheus-url PROMETHEUS_URL]
  [--environment {production,staging,development}]
  --data-output-dir DATA_OUTPUT_DIR
  [--tat-exemptions-file TAT_EXEMPTIONS_FILE]
  [--explain-tat-case EXPLAIN_TAT_CASE]

options:
  -h, --help            show this help message and exit
  --pinery-url PINERY_URL
                        Pinery URL to retrieve LIMS data from
  --qcetl-metrics-file QCETL_METRICS_FILE
                        JSON config file containing metric definitions for extraction from QC-ETL (default: None)
  --qcetl-dir QCETL_DIR
                        QC-ETL directory to retrieve QC data from. If multiple are specified, they are used in the order specified to fill in any missing data (default: None)
  --miso-db-config MISO_DB_CONFIG
                        Config file for MISO DB connection
  --nabu-url NABU_URL   Nabu URL to retrieve case sign-offs from (default: None)
  --nabu-key-file NABU_KEY_FILE
                        File containing Nabu API key (default: None)
  --nabu-archive-config-file NABU_ARCHIVE_CONFIG_FILE
                        CSV file containing archive target definitions (default: None)
  --prometheus-url PROMETHEUS_URL
                        Prometheus Pushgateway URL for metrics (default: None)
  --environment {production,staging,development}
                        Environment label for metrics (production/staging/development) (default: None)
  --data-output-dir DATA_OUTPUT_DIR
                        Write data to this directory
  --tat-exemptions-file TAT_EXEMPTIONS_FILE
                        CSV file containing date ranges to omit from TAT calculation (default: None)
  --explain-tat-case EXPLAIN_TAT_CASE
                        Print a breakdown of TAT calculation for the specified case (default: None)
```

### MISO DB Config File

This is a .ini file containing MISO database connection parameters. e.g.

```
[mysql]
user=username
password=secret
database=lims
host=localhost
port=3306
```

### TAT Exemptions File

Date ranges specified in this CSV file will not be counted in turn-around time calculations. The
format is three columns: start, end, and note, with headings in the first row. e.g.

```
start,date,note
2023-12-22,2024-01-01,2023 holiday break
```

### Nabu Archive Config File

This file provides details for the archive targets recorded in Nabu. The format is 4 columns:
target (Nabu value), destination (label), retention, and (retention) units. Units may be days,
months, or years.

```
target,destination,retention,units
DIRECT_DELETE,Direct Delete,0,days
AMAZON_GLACIER_FOR_12_MONTHS,Glacier,12,months
```

### QC-ETL Metrics File

This file should contain a JSON array detailing all metrics that are to be pulled from QC-ETL. Each
metric can have one or more sources. If there are multiple sources, they are checked in order, and
the first one that provides a value will be used. Format:

```
[
  {
    "name": string,
    "library_designs": [string],
    "step": "library_qualification" or "full_depth_sequencing",
    "overwrite": optional boolean,
    "sources": [
      {
        "cache": string,
        "table": string,
        "column": string,
        "lookup_type": "single_lane", "call_ready", or "merge_single_lane",
        "value_type": "float", "bool", or "negate_bool",
        "preliminary": optional boolean,
        "id_column": optional string,
        "whole_column": optional string,
        "whole_value: optional number,
        "filterColumn": optional string,
        "filterValue": optional string
      }
    ]
  },
  "note": optional string
]
```

#### Metric field descriptions

- `name`: metric display name
- `library_designs`: list of library design codes to include
- `step`: which QC step to include - "library_qualification" or "full_depth_sequencing"
- `overwrite`: Optional (default=false). If true, the value found in QC-ETL will overwrite any
previous value (e.g. from MISO)
- `sources`: list of sources for the metric value. If there are multiple, they are checked in order,
and the first one that provides a value is used.
  - `cache`: name of the cache containing the metric value
  - `table`: name of the table within the cache
  - `column`: name of the table column containing the metric value
  - `lookup_type`: describes how to retrieve table rows
    - "single_lane": each row of the table is for a specific run-library and has a column matching
    the `sample_id` format `<run-id>_<lane>_<aliquot-id>`, e.g. `123_4_LDI567`
    - "call_ready": each row of the table is for a group of merged run-libraries and has a merged
    IDs column containing a list of `sample_id`s
    - "merge_single_lane": table as described for single_lane, but Case-ETL should calculate a
    merged value by adding the values from samples in the same case with matching tissue origin,
    tissue type, timepoint, library design, and group ID
  - `value_type`: data type of metric
    - "float": decimal number
    - "bool": true or false
    - "negate_bool": true or false, but reverse what's in the cache
  - `preliminary`: Optional (default=false). If true, the value is displayed as preliminary and not
  used for QC decisions
  - `id_column`: Optional (default "Pinery Lims ID" for single-lane or "Merged Pinery Lims ID" for
  call-ready). Name of sample ID column in the cache table
  - `whole_column`: Optional. For calculating percent values, `column` is used as the part and this
  column is used as the whole (metric value = part * 100 / whole)
  - `whole_value`: Optional. For calculating percent values, `column` is used as the part and this
  number is used as the whole (metric value = part * 100 / whole). This is also useful for things like halving ("whole_value": 200) and doubling ("whole_value": 50) a metric value
  - `filter_column`: Optional. if provided, the cache table is filtered to rows where this column
  matches the accompanying `filter_value`
  - `filter_value`: Optional. See `filter_column`
- `note`: Optional. Does nothing - just there for misc. documentation purposes

## Usage examples

#### Run locally

This is the minimal setup.

- No QC-ETL
- No Nabu
- No Prometheus
- No TAT exemptions

```
case-etl \
--pinery-url http://pinery-stage.gsi.oicr.on.ca \
--miso-db-config misodb.ini
--data-output-dir ~/tmp/case-etl
```

## Running tests

```
cd ~/git/case-etl
uv run pytest
```

## Deploy and Release Procedure

1. Run the release script to tag the release

```
cd ~/git/case-etl
git switch main
git pull
./release.sh
```

2. Copy the CASE_ETL_VERSION output from the script into your shell
3. Update the staging branch to deploy to stage

```
cd ~/git/case-etl
git switch staging
git reset --hard HEAD
git pull
git fetch --tags
git rebase --onto tags/v${CASE_ETL_VERSION}
git push origin staging
```

4. Update the production branch to deploy to production

```
cd ~/git/case-etl
git switch production
git reset --hard HEAD
git pull
git fetch --tags
git rebase --onto tags/v${CASE_ETL_VERSION}
git push origin production
```
