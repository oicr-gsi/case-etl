import json
import logging
import pymysql
from configparser import ConfigParser
from math import isnan
from typing import Dict, Set
from pymysql.connections import Connection
from model.pinery import PreprocessedLane, PreprocessedPinerySample, PreprocessedRun, QcableType, MetricType, SampleMetric

config_section = 'mysql'
metrics_fetch_size = 20

def connect_db(db_config_file: str) -> Connection:
    config = _read_db_config(db_config_file)
    return pymysql.connect(**config)


def add_runscanner_data(preprocessed_runs_by_id: dict[int, PreprocessedRun], run_ids: list[int],
    sample_ids_by_run: Dict[int, Set[str]], output_samples_by_id: Dict[str, PreprocessedPinerySample], connection: Connection) -> None:
  cursor = connection.cursor()
  query = '''
      SELECT r.runId, r.metrics
      FROM Run r
      WHERE r.runId IN ({ids})
      '''.format(ids=",".join([str(x) for x in run_ids]))
  cursor.execute(query)
  records = cursor.fetchmany(metrics_fetch_size)
  while records:
    for record in records:
      if record[1]:
        run = preprocessed_runs_by_id[record[0]]
        metrics = json.loads(record[1])
        run.percent_over_q30 = _get_percent_over_q30(metrics)
        run.clusters_pf = _get_clusters_pf(metrics)
        _populate_clusters_pf_by_lane(run, metrics)
        _populate_read_level_metrics(run, metrics)
        if run.id in sample_ids_by_run:
            for sample_id in sample_ids_by_run[run.id]:
                if MetricType.BASES_OVER_Q30.metric_label in output_samples_by_id[sample_id].metrics:
                    output_samples_by_id[sample_id].metrics[MetricType.BASES_OVER_Q30.metric_label].add_run_values(_get_percent_over_q30(metrics), _get_read_level_metrics_q30(metrics), run.joined_lanes)
                if MetricType.CONTROL_BASES_OVER_Q30.metric_label in output_samples_by_id[sample_id].metrics:
                    output_samples_by_id[sample_id].metrics[MetricType.CONTROL_BASES_OVER_Q30.metric_label].add_run_values(_get_control_percent_over_q30(metrics), None, run.joined_lanes)
                if MetricType.MIN_CLUSTERS_PF.metric_label in output_samples_by_id[sample_id].metrics:
                    output_samples_by_id[sample_id].metrics[MetricType.MIN_CLUSTERS_PF.metric_label].add_run_values(_get_clusters_pf(metrics), _get_lane_level_metrics_clusters_pf(metrics), run.joined_lanes)
                if MetricType.OUTPUT_READS.metric_label in output_samples_by_id[sample_id].metrics:
                    output_samples_by_id[sample_id].metrics[MetricType.OUTPUT_READS.metric_label].add_run_values(_get_output_reads(metrics), None, run.joined_lanes)
                if MetricType.PHIX.metric_label in output_samples_by_id[sample_id].metrics:
                    output_samples_by_id[sample_id].metrics[MetricType.PHIX.metric_label].add_run_values(None, _get_read_level_metrics_phix(metrics), run.joined_lanes)

    records = cursor.fetchmany(metrics_fetch_size)
  cursor.close()


def add_transfer_data(preprocessed_samples: dict[str, PreprocessedPinerySample], connection) -> None:
    cursor = connection.cursor()
    query = '''
    SELECT s.name, t.transferTime
    FROM Transfer t
    JOIN Transfer_Sample ts ON ts.transferId = t.transferId
    JOIN _Group sender ON sender.groupId = t.senderGroupId
    JOIN _Group recipient ON recipient.groupId = t.recipientGroupId
    JOIN Sample s ON s.sampleId = ts.sampleId
    JOIN SampleClass sc ON sc.sampleClassId = s.sampleClassId
    WHERE sender.name = 'TP'
    AND recipient.name = 'TGL'
    AND sc.sampleCategory IN ('Stock', 'Aliquot');
    '''
    cursor.execute(query)

    for (sample_id, transfer_time) in cursor:
        if sample_id in preprocessed_samples:
            _add_transfer_date(preprocessed_samples[sample_id], transfer_time, preprocessed_samples)

    cursor.close()


def _add_transfer_date(sample: str, transfer_time: str,
        preprocessed_samples: dict[str, PreprocessedPinerySample]) -> None:
    if sample.qcable_type == QcableType.EXTRACTION:
        sample.extraction_transfer_dates.append(transfer_time)
    if sample.parent_id != None:
        parent = preprocessed_samples[sample.parent_id]
        if parent.requisition_id == sample.requisition_id:
            _add_transfer_date(parent, transfer_time, preprocessed_samples)


def _read_db_config(filename):
    parser = ConfigParser()
    parser.read(filename)

    config = {}
    if parser.has_section(config_section):
        items = parser.items(config_section)
        for item in items:
            config[item[0]] = item[1]
    else:
        raise Exception('[{0}] section not found in the {1} file'.format(
            config_section, filename))

    # pymysql requires port as an int
    if "port" in config:
        config['port']=int(config['port'])

    return config


def _get_percent_over_q30(metrics: dict) -> float:
    display_value = _get_run_metric(metrics, '% > Q30')
    if not display_value:
      return None
    value = float(display_value.rstrip(' %'))
    return None if isnan(value) else value

def _get_control_percent_over_q30(metrics: dict) -> float:
    display_value = _get_run_metric(metrics, 'Control Sample Bases > Q30 %')
    if not display_value:
      return None
    value = float(display_value.rstrip(' %'))
    return None if isnan(value) else value

def _get_output_reads(metrics: dict) -> int:
    display_value = _get_run_metric(metrics, 'Output Reads')
    if not display_value:
        return None
    else:
        return int(display_value.replace(',', ''))

def _get_clusters_pf(metrics: dict) -> float:
    display_value = _get_run_metric(metrics, 'Clusters PF')
    if not display_value:
      return None
    else:
      return int(display_value.replace(',', ''))


def _get_run_metric(metrics: dict, metric: str) -> float:
    charts = [x for x in metrics if x['type'] == 'chart']
    if not charts:
        return None
    elif len(charts) == 1:
        values = [x for x in charts[0]['values'] if x['name'] == metric]
        if not values:
            return None
        elif len(values) == 1:
            return values[0]['value']
        else:
            raise Exception(f'multiple values found for {metric}')
    else:
        raise Exception('multiple charts found in metrics')


def _populate_clusters_pf_by_lane(run: PreprocessedRun, metrics: dict) -> None:
    by_lane = [x for x in metrics if x['type'] == 'illumina-clusters-by-lane']
    if not by_lane:
        return None
    elif len(by_lane) == 1:
        clusters_pf = [
            x for x in by_lane[0]['series'] if x['name'] == 'Clusters PF'
        ]
        if not clusters_pf:
            return None
        elif len(clusters_pf) == 1:
            for i in range(len(clusters_pf[0]['data'])):
                lane = _get_lane(run, i + 1)
                lane.clusters_pf = clusters_pf[0]['data'][i]
        else:
            raise Exception(f'multiple clusters PF metrics found for {run.name}')
    else:
        raise Exception('multiple by lane metrics found')


def _populate_read_level_metrics(run: PreprocessedRun, metrics: dict) -> None:
    table = [x for x in metrics if x['type'] == 'table']
    if not table:
        return None
    elif len(table) == 1:
        for lane_row in table[0]['rows']:
            lane_number = lane_row['lane']
            lane = _get_lane(run, lane_number)
            lane.percent_over_q30_read1 = _parse_q30(lane_row, 'errors0')
            lane.percent_over_q30_read2 = _parse_q30(lane_row, 'errors3')
            lane.percent_phix_read1 = _parse_phix(lane_row, 'aligned0')
            lane.percent_phix_read2 = _parse_phix(lane_row, 'aligned3')
    else:
        raise Exception('multiple tables found in metrics')


def _get_read_level_metrics_q30(metrics: dict) -> dict:
    table = [x for x in metrics if x['type'] == 'table']
    read_metrics = {}
    if not table:
        return None
    elif len(table) == 1:
        for lane_row in table[0]['rows']:
            lane_number = lane_row['lane']
            read_metrics[lane_number] = {
                "R1": _parse_q30(lane_row, 'errors0'),
                "R2": _parse_q30(lane_row, 'errors3')
            }
    else:
        raise Exception('multiple tables found in metrics')
    return read_metrics


def _get_read_level_metrics_phix(metrics: dict) -> dict:
    table = [x for x in metrics if x['type'] == 'table']
    read_metrics = {}
    if not table:
        return None
    elif len(table) == 1:
        for lane_row in table[0]['rows']:
            lane_number = lane_row['lane']
            read_metrics[lane_number] = {
                "R1": _parse_phix(lane_row, 'aligned0'),
                "R2": _parse_phix(lane_row, 'aligned3')
            }
    else:
        raise Exception('multiple tables found in metrics')
    return read_metrics

def _get_lane_level_metrics_clusters_pf(metrics: dict) -> None:
    by_lane = [x for x in metrics if x['type'] == 'illumina-clusters-by-lane']
    lane_metrics = {}
    if not by_lane:
        return None
    elif len(by_lane) == 1:
        clusters_pf = [
            x for x in by_lane[0]['series'] if x['name'] == 'Clusters PF'
        ]
        if not clusters_pf:
            return None
        elif len(clusters_pf) == 1:
            for i in range(len(clusters_pf[0]['data'])):
                lane_number = i + 1
                lane_metrics[lane_number] = {
                    None: clusters_pf[0]['data'][i]
                }
        else:
            raise Exception(f'multiple clusters PF metrics found')
    else:
        raise Exception('multiple by lane metrics found')
    return lane_metrics


def _get_lane(run: PreprocessedRun, lane_number: int) -> PreprocessedLane:
  if not lane_number in run.lanes:
    run.lanes[lane_number] = PreprocessedLane(lane_number=lane_number)
  return run.lanes[lane_number]


def _parse_q30(lane_row: dict, property: str) -> float:
    if property not in lane_row:
        return None
    value = lane_row[property];
    if value == 'N/A':
        return None
    try:
        return float(value)
    except ValueError:
        logging.exception(f'Unexpected Q30 value: {value}')
        return None


def _parse_phix(lane_row: dict, property: str) -> float:
    if property not in lane_row:
        return None
    value = lane_row[property];
    if value == 'N/A':
        return None
    try:
        # expected value format example: "0.43 ± 0.0096"
        return float(value.split(' ')[0])
    except ValueError:
        logging.exception(f'Unexpected PhiX value: {value}')
        return None
