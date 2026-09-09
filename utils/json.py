import dataclasses
import os
from datetime import datetime
from enum import Enum

import json


class JSONEncoder(json.JSONEncoder):
    def default(self, o):
        if dataclasses.is_dataclass(o):
            return dataclasses.asdict(o)
        elif isinstance(o, Enum):
            return o.value
        elif isinstance(o, datetime):
            return o.strftime("%Y-%m-%dT%H:%M:%SZ")
        return super().default(o)


def write_json(output_dir, file_name, data):
    with open(os.path.join(output_dir, file_name), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, cls=JSONEncoder, sort_keys=False)
