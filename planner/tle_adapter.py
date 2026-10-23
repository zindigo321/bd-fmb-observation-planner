"""Inherited audited TLE parser and sampled geometry adapter."""
from .common import *

def read_and_audit(config, out, clock):
    """All metrics recomputed; filenames and contents decoded separately."""
    raw = ROOT / config['input_dir']
    files = sorted(raw.iterdir(), key=lambda p: p.name)
    hashes = {p.name: {'sha256': digest(p), 'bytes': p.stat().st_size} for p in files if p.is_file()}
    json_write(out / 'input_hashes.json', hashes)
    encodings = {}
    zip_audit = []
    for filename, expected in [('数据.zip', {'站址.txt', '轨道.txt'}),
                                ('优先级.zip', {v[1] for v in PRIORITIES})]:
        clock.check()
        archive_bytes=(raw / filename).read_bytes()
        with zipfile.ZipFile(raw / filename) as z:
            decoded = []
            for info in z.infolist():
                offset=info.header_offset
                name_length=int.from_bytes(archive_bytes[offset+26:offset+28], 'little')
                bname=archive_bytes[offset+30:offset+30+name_length]
                if info.flag_bits & 0x800:
                    name, encoding = bname.decode('utf-8',errors='strict'), 'UTF-8 flagged'
                else:
                    name, encoding = bname.decode('gbk', errors='strict'), 'GBK strict expected vocabulary'
                if name not in expected:
                    raise ValueError(f'Unexpected ZIP member {filename}: {name}')
                if z.read(info) != (raw / name).read_bytes():
                    raise ValueError('Extracted source differs from ZIP: ' + name)
                try:
                    utf8_attempt = bname.decode('utf-8', errors='strict')
                except UnicodeDecodeError as e:
                    utf8_attempt = f'FAILED:{e.start}'
                zip_audit.append(dict(zip=filename, name=name, encoding=encoding,
                                      raw_name_hex=bname.hex(), utf8_attempt=utf8_attempt,
                                      extracted_content_identical=True))
                decoded.append(name)
            if set(decoded) != expected or len(decoded) != len(expected):
                raise ValueError('ZIP members mismatch')
    text, encodings['站址.txt'] = strict_text(raw / '站址.txt')
    station_rows = []
    for line in text.splitlines():
        match = re.fullmatch(r'\s*(\d+)[:：]\s*([-+\d.]+)\s*,\s*([-+\d.]+)\s*,\s*([-+\d.]+)\s*', line)
        if match:
            i, lon, lat, height = match.groups()
            lon, lat, height = map(float, (lon, lat, height))
            if not all(math.isfinite(x) for x in (lon, lat, height)) or not -90 <= lat <= 90:
                raise ValueError('Invalid station coordinates')
            station_rows.append(dict(station_id=int(i), longitude_original=lon,
                                     longitude=((lon+180) % 360)-180,
                                     latitude=lat, height_m=height))
    if len({r['station_id'] for r in station_rows}) != len(station_rows):
        raise ValueError('Duplicate station')
    if '10' not in text or '85' not in text:
        raise ValueError('Missing elevation bounds in raw station file')
    station_rows.sort(key=lambda r: r['station_id'])
    if not set(config['station_ids']).issubset(r['station_id'] for r in station_rows):
        raise ValueError('Unknown configured station')
    tle_text, encodings['轨道.txt'] = strict_text(raw / '轨道.txt')
    lines = tle_text.splitlines()
    if len(lines) % 3:
        raise ValueError('Incomplete TLE 3-line group')
    records = {}
    alpha_count = 0
    epoch_errors = []
    for i in range(0, len(lines), 3):
        if i % 300 == 0:
            clock.check()
        name, l1, l2 = lines[i:i+3]
        if not name.startswith('0 ') or len(l1) != 69 or len(l2) != 69 or not l1.startswith('1 ') or not l2.startswith('2 '):
            raise ValueError('TLE structure invalid at ' + str(i))
        for line in (l1, l2):
            checksum = sum(int(c) if c.isdigit() else 1 if c == '-' else 0 for c in line[:68]) % 10
            if checksum != int(line[68]):
                raise ValueError('TLE checksum invalid at ' + str(i))
        sat = Satrec.twoline2rv(l1, l2)
        number = int(sat.satnum)
        if number != from_alpha5(l1[2:7]) or number != from_alpha5(l2[2:7]) or number in records:
            raise ValueError('TLE ID mismatch or duplicate')
        alpha_count += not l1[2:7].strip().isdigit()
        error, pos, vel = sat.sgp4(sat.jdsatepoch, sat.jdsatepochF)
        if error or not all(math.isfinite(x) for x in (*pos, *vel)):
            epoch_errors.append(dict(satnum=number, error=error, stage='full_raw_epoch_audit'))
        year = int(l1[18:20]); year += 2000 if year < 57 else 1900
        epoch = datetime(year, 1, 1, tzinfo=timezone.utc) + timedelta(days=float(l1[20:32])-1)
        records[number] = dict(satnum=number, name=name[2:], line1=l1, line2=l2,
                               epoch_utc=epoch.isoformat(), epoch_timestamp=epoch.timestamp())
    priority_lists = {}
    union = set()
    for priority, filename, score in PRIORITIES:
        txt, encodings[filename] = strict_text(raw / filename)
        if not re.fullmatch(r'\d+(,\d+)*', txt.strip()):
            raise ValueError('Invalid priority list')
        numbers = [int(x) for x in txt.strip().split(',')]
        if len(set(numbers)) != len(numbers) or union.intersection(numbers):
            raise ValueError('Duplicate/overlapping priority list')
        union.update(numbers)
        priority_lists[priority] = sorted(numbers)
        for number in numbers:
            if number not in records:
                raise ValueError('Missing TLE for priority ID')
            records[number].update(priority=priority, full_score=score)
    if union != set(records):
        raise ValueError('Priority union differs from TLE IDs')
    paragraphs = {}
    for p in files:
        if p.suffix == '.docx':
            with zipfile.ZipFile(p) as z:
                element = ElementTree.fromstring(z.read('word/document.xml').decode('utf-8', errors='strict'))
                paragraphs[p.name] = [''.join(n.itertext()) for n in element.findall('.//{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t')]
    json_write(out / 'official_document_text.json', paragraphs)
    frozen_path = ROOT / config['frozen_sample']
    if frozen_path.exists():
        sample = json.loads(frozen_path.read_text(encoding='utf-8'))
        if sample['seed'] != config['seed'] or sample['input_hashes'] != hashes:
            raise ValueError('Frozen sample configuration/input hash mismatch')
    else:
        rng = random.Random(config['seed'])
        selected = {p: rng.sample(priority_lists[p], config['sample_counts'][p]) for p, _, _ in PRIORITIES}
        sample = dict(seed=config['seed'], sampler='random.Random.sample',
                      sampler_python=platform.python_version(), sampling_order=['high', 'medium', 'low'],
                      population_order='decimal satnum ascending', selected=selected, input_hashes=hashes)
        json_write(frozen_path, sample)  # freeze before any geometry, do not redraw
    selected = []
    for p, _, _ in PRIORITIES:
        group = sample['selected'][p]
        if len(group) != config['sample_counts'][p] or len(set(group)) != len(group) or not set(group).issubset(priority_lists[p]):
            raise ValueError('Invalid frozen sample')
        selected.extend(group)
    if len(set(selected)) != sum(config['sample_counts'].values()):
        raise ValueError('Frozen sample count mismatch')
    median = statistics.median(records[n]['epoch_timestamp'] for n in selected)
    day = datetime.fromtimestamp(median, tz=timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    if config.get('start_utc'):
        from .io_contract import parse_utc
        day = parse_utc(config['start_utc'])
    sample.update(median_epoch_utc=datetime.fromtimestamp(median, timezone.utc).isoformat(),
                  horizon_start_utc=utc_at(day, 0), horizon_end_utc=utc_at(day, config['horizon_seconds']))
    json_write(out / 'frozen_sample.json', sample)
    selected_records = [records[n] for n in selected]
    csv_write(out / 'sample.csv', selected_records,
              ['satnum', 'name', 'priority', 'full_score', 'epoch_utc', 'line1', 'line2'])
    json_write(out / 'selected_tle.json', selected_records)
    csv_write(out / 'stations.csv', station_rows,
              ['station_id', 'longitude_original', 'longitude', 'latitude', 'height_m'])
    audit = dict(tle_count=len(records), tle_unique_ids=len(records), alpha5_count=alpha_count,
                 unique_names=len({r['name'] for r in records.values()}),
                 priority_counts={p:len(v) for p,v in priority_lists.items()},
                 linkage_bidirectional_match=union == set(records), station_count=len(station_rows),
                 epoch_propagation_errors=epoch_errors, strict_encodings=encodings, zip_audit=zip_audit,
                 selected_count=len(selected), selected_station_ids=config['station_ids'],
                 input_file_count=len(hashes), source_data_modified=False)
    json_write(out / 'audit.json', audit)
    return selected_records, [r for r in station_rows if r['station_id'] in config['station_ids']], day, sample, audit


class Geometry:
    def __init__(self, records, stations, day, clock):
        self.ts = load.timescale(builtin=True)
        self.day = day
        self.clock = clock
        self.satellites = {r['satnum']: EarthSatellite(r['line1'], r['line2'], r['name'], self.ts) for r in records}
        self.stations = {r['station_id']: wgs84.latlon(r['latitude'], r['longitude'], elevation_m=r['height_m']) for r in stations}
        self.errors = []

    def times(self, seconds):
        return self.ts.utc(self.day.year, self.day.month, self.day.day, self.day.hour, self.day.minute, self.day.second + seconds)

    def elevations(self, satnum, station, seconds, times=None):
        self.clock.check()
        seconds = np.asarray(seconds, dtype=np.int64)
        t = self.times(seconds) if times is None else times
        g = self.satellites[satnum].at(t)
        alt = (g - self.stations[station].at(t)).altaz()[0].degrees
        alt = np.asarray(alt, dtype=float)
        messages = np.asarray(g.message, dtype=object)
        if messages.ndim == 0:
            messages = np.full(alt.shape, messages.item(), dtype=object)
        bad = np.array([m is not None for m in messages], dtype=bool) | ~np.isfinite(alt)
        for idx in np.flatnonzero(bad):
            self.errors.append(dict(satnum=satnum, station_id=station, second=int(seconds[idx]),
                                    utc=utc_at(self.day, seconds[idx]), message=str(messages[idx]),
                                    nonfinite=not bool(np.isfinite(alt[idx]))))
        alt[bad] = np.nan
        self.clock.check()
        return alt


def build_windows(geometry, records, stations, config, out, clock):
    step = config['coarse_step_seconds']
    if not 0 < step <= 30 or config['fine_step_seconds'] != 1:
        raise ValueError('Invalid geometry sampling steps')
    coarse = np.unique(np.append(np.arange(0, config['horizon_seconds']+1, step, dtype=int), config['horizon_seconds']))
    times = geometry.times(coarse)
    rows = []
    profile = None
    upper_breaks = 0
    for r in records:
        for station in stations:
            clock.check()
            sid = station['station_id']
            t0 = time.monotonic()
            el = geometry.elevations(r['satnum'], sid, coarse, times)
            if profile is None:
                profile = dict(unit='one target-station 24h coarse scan', seconds=time.monotonic()-t0,
                               units=len(records)*len(stations),
                               estimated_coarse_seconds=(time.monotonic()-t0)*len(records)*len(stations),
                               uncertainty='Coarse-only estimate; fine scans and checks additional; hard deadline governs')
                json_write(out / 'profiling.json', profile)
                clock.log('PROFILE ' + json.dumps(profile))
            # Include neighbours of all coarse samples >=5 degrees; guards crossings of lower threshold.
            potentially_visible = np.isfinite(el) & (el >= 5)
            expanded = potentially_visible.copy()
            expanded[1:] |= potentially_visible[:-1]
            expanded[:-1] |= potentially_visible[1:]
            indices = np.flatnonzero(expanded)
            if len(indices) == 0:
                continue
            splits = np.split(indices, np.flatnonzero(np.diff(indices) != 1)+1)
            for component in splits:
                clock.check()
                lo = int(coarse[max(0, component[0]-1)])
                hi = int(coarse[min(len(coarse)-1, component[-1]+1)])
                seconds = np.arange(lo, hi+1, dtype=int)
                # bounded vector calls so deadline gets checked inside long day-visible spans
                chunks = []
                for offset in range(0, len(seconds), 6000):
                    clock.check()
                    chunks.append(geometry.elevations(r['satnum'], sid, seconds[offset:offset+6000]))
                fine = np.concatenate(chunks)
                legal = np.isfinite(fine) & (fine >= 10) & (fine <= 85)
                upper_breaks += int(np.sum((fine[:-1] <= 85) & (fine[1:] > 85)))
                good = np.flatnonzero(legal)
                if len(good) == 0:
                    continue
                for seq in np.split(good, np.flatnonzero(np.diff(good) != 1)+1):
                    a, b = int(seconds[seq[0]]), int(seconds[seq[-1]])
                    vals = fine[seq]
                    rows.append(dict(window_id=f'W{len(rows)+1:05d}', satnum=r['satnum'], station_id=sid,
                                     start_s=a, end_s=b, start_utc=utc_at(geometry.day,a), end_utc=utc_at(geometry.day,b),
                                     duration_s=b-a, min_elevation=float(vals.min()), max_elevation=float(vals.max())))
        if len(rows) % 15 == 0:
            csv_write(out / 'windows.csv', rows, WINDOW_FIELDS)
        clock.log(f"WINDOW progress satnum={r['satnum']} windows={len(rows)}")
    csv_write(out / 'windows.csv', rows, WINDOW_FIELDS)
    json_write(out / 'propagation_errors.json', geometry.errors)
    json_write(out / 'window_generation.json', dict(coarse_step_s=step, fine_step_s=1,
               boundary_accuracy_s=1, upper_85_entries=upper_breaks, window_count=len(rows),
               window_endpoint_convention='inclusive integer seconds; candidate endpoints included',
               coarse_guard='>=5 degrees with adjacent coarse cells expanded',
               limitation='No completeness proof for visibility spikes shorter than coarse resolution; scheduled intervals repropagated every second'))
    return rows
