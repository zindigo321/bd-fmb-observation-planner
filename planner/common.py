#!/usr/bin/env python3
"""Inherited shared data formats, I/O, time conversion and bounded stage clock."""
import os
import time
for _k in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS'):
    os.environ[_k] = '1'
import argparse
import collections
import csv
import hashlib
import importlib.metadata
import io
import json
import math
import platform
import random
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import traceback
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from xml.etree import ElementTree
import numpy as np
import yaml
from sgp4.api import Satrec
from sgp4.alpha5 import from_alpha5
from skyfield.api import EarthSatellite, load, wgs84

ROOT = Path(__file__).resolve().parents[1]
PRIORITIES = [('high', '高优先级目标.txt', 5), ('medium', '中优先级目标.txt', 3),
              ('low', '低优先级目标.txt', 2)]
CHECK_CATEGORIES = ['overlap', 'switch_gap', 'window_or_horizon', 'elevation',
                    'fault_occupancy', 'duplicate_success', 'invalid_data']
TASK_FIELDS = ['task_id', 'candidate_id', 'window_id', 'satnum', 'station_id',
               'priority', 'start_s', 'end_s', 'duration_s', 'points_int',
               'score', 'start_utc', 'end_utc', 'status']
WINDOW_FIELDS = ['window_id', 'satnum', 'station_id', 'start_s', 'end_s',
                 'start_utc', 'end_utc', 'duration_s', 'min_elevation', 'max_elevation']


class BudgetExpired(RuntimeError):
    pass


def json_write(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.tmp')
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    tmp.replace(path)


def csv_write(path, rows, fields):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.tmp')
    with tmp.open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)
    tmp.replace(path)


def csv_tasks(path):
    with Path(path).open(encoding='utf-8', newline='') as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        for key in ('satnum', 'station_id', 'start_s', 'end_s', 'duration_s', 'points_int'):
            row[key] = int(row[key])
        row['score'] = float(row['score'])
    return rows


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def utc_at(day, second):
    return (day + timedelta(seconds=int(second))).isoformat().replace('+00:00', 'Z')


class Clock:
    def __init__(self, config, out):
        self.start = time.monotonic()
        self.deadline = self.start + config['budget_seconds']
        self.margin = config['save_margin_seconds']
        self.out = out
        self.stages = []
        self.run_start = self.start
        self.logfile = (out / 'run.log').open('w', encoding='utf-8', buffering=1)

    def left(self):
        return self.deadline - time.monotonic()

    def check(self, reserve=0):
        if self.left() <= self.margin + reserve:
            raise BudgetExpired('Configured deadline: insufficient remaining time')

    def log(self, message):
        text = f'[{time.monotonic()-self.start:.3f}s cumulative; {self.left():.3f}s left] {message}'
        print(text, flush=True)
        self.logfile.write(text + '\n')

    def begin(self, name):
        self.check()
        self.log('BEGIN ' + name)
        return time.perf_counter()

    def end(self, name, start, **extra):
        now = time.monotonic()
        row = dict(stage=name, seconds=time.perf_counter()-start, cumulative_seconds=now-self.start,
                   remaining_seconds=self.deadline-now, run_elapsed_seconds=now-self.run_start, **extra)
        self.stages.append(row)
        json_write(self.out / 'timing.json', self.stages)
        self.log('END ' + name + ' ' + json.dumps(extra, ensure_ascii=False))
        self.check()


def strict_text(path):
    b = Path(path).read_bytes()
    try:
        return b.decode('utf-8-sig', errors='strict'), 'UTF-8'
    except UnicodeDecodeError:
        return b.decode('gbk', errors='strict'), 'GBK'
