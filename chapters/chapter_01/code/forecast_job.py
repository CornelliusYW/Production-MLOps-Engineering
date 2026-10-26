"""Run a small local forecasting service using synthetic data and a demo clock.

The primary method averages three daily sales observations. North's input is
late in the late-feed case; an independent, earlier forecast supplies fallback.
This is a single-writer teaching example, not a distributed scheduler.
"""
import argparse
import csv
from datetime import date, datetime, time
import hashlib
import io
import json
import math
import os
from pathlib import Path
import tempfile

HERE = Path(__file__).resolve().parent
OUTPUT_FIELDS = ['store', 'product', 'target_date', 'forecast_units', 'method', 'reason']


def timestamp(value):
    """Parse an availability or run time with an explicit time zone."""
    result = datetime.fromisoformat(value)
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError('timestamps need a time zone')
    return result


def units(value):
    """Reject quantities that cannot be used for planning."""
    result = float(value)
    if not math.isfinite(result) or result < 0:
        raise ValueError('units must be finite and nonnegative')
    return result


def read_csv(path):
    """Read rows from a UTF-8 CSV file."""
    with Path(path).open(newline='', encoding='utf-8') as stream:
        return list(csv.DictReader(stream))


def atomic_write(path, content):
    """Replace one file on the same local filesystem after writing it fully."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(content)
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def write_json(path, value):
    content = json.dumps(value, indent=2, sort_keys=True) + '\n'
    atomic_write(path, content.encode())


def prepare_inputs(case, files=HERE):
    """Load a case and simulate the delay without modifying the source CSV."""
    if case not in ('on-time', 'late-feed'):
        raise ValueError('unknown case')
    files = Path(files)
    config = json.loads((files / 'service.json').read_text(encoding='utf-8'))
    assortment = read_csv(files / 'assortment.csv')
    history = read_csv(files / 'sales_history.csv')
    fallback = read_csv(files / 'fallback_forecasts.csv')
    if case == 'late-feed':
        for row in history:
            if row['group'] == 'North':
                row['available_at'] = '2026-01-05T04:31:00+07:00'
    return config, assortment, history, fallback


def make_forecasts(config, assortment, history, fallback):
    """Choose primary or fallback quantities for each eligible store/product."""
    cutoff = timestamp(config['input_cutoff'])
    target = date.fromisoformat(config['target_date'])
    if cutoff >= datetime.combine(target, time.min, tzinfo=cutoff.tzinfo):
        raise ValueError('cutoff must precede the target day')
    days = config['history_days']
    if len(days) != 3 or len(set(days)) != 3:
        raise ValueError('the primary method needs three distinct history days')
    if any(date.fromisoformat(d) >= cutoff.date() for d in days):
        raise ValueError('history days must precede the operating day')
    eligible = {}
    for row in assortment:
        key = row['store'], row['product']
        if key in eligible:
            raise ValueError('duplicate assortment key')
        eligible[key] = row['group']
    if not eligible:
        raise ValueError('empty assortment')
    observations = {}
    for row in history:
        key = row['store'], row['product']
        if key not in eligible or row['group'] != eligible[key]:
            raise ValueError('history does not match the assortment')
        day = row['sales_date']
        if day not in days or (key, day) in observations:
            raise ValueError('unexpected or duplicate history day')
        observations[key, day] = (units(row['units']), timestamp(row['available_at']))
    alternatives = {}
    for row in fallback:
        key = row['store'], row['product']
        if key not in eligible or key in alternatives or row['group'] != eligible[key]:
            raise ValueError('fallback does not match the assortment')
        source_day = date.fromisoformat(row['source_date'])
        if source_day >= cutoff.date():
            raise ValueError('fallback source must precede the operating day')
        alternatives[key] = (
            row['target_date'],
            units(row['forecast_units']),
            timestamp(row['available_at']),
        )
    forecasts, manual = [], []
    for key in sorted(eligible):
        records = [observations.get((key, day)) for day in days]
        if any(record is None for record in records):
            reason = 'missing_history'
        elif any(record[1] > cutoff for record in records):
            reason = 'late_feed'
        else:
            reason = ''
        if not reason:
            forecast = sum(record[0] for record in records) / len(records)
            method = 'primary'
        else:
            alternative = alternatives.get(key)
            if (
                alternative is None
                or alternative[0] != target.isoformat()
                or alternative[2] > cutoff
            ):
                manual.append({'store': key[0], 'product': key[1], 'reason': reason})
                continue
            forecast, method = alternative[1], 'fallback'
        values = [
            key[0], key[1], target.isoformat(),
            f'{forecast:.2f}', method, reason,
        ]
        forecasts.append(dict(zip(OUTPUT_FIELDS, values)))
    return forecasts, manual


def run_job(case='on-time', output=None, files=HERE, now=None):
    """Save a run record and publish only a complete, on-time batch."""
    output = Path(output) if output is not None else HERE / 'service_runs' / case
    config, assortment, history, fallback = prepare_inputs(case, files)
    # A fixed clock makes the dated teaching cases repeatable; callers may
    # inject a real clock in an application instead.
    if isinstance(now, str):
        now = timestamp(now)
    elif now is None:
        now = timestamp(config['demo_time'])
    cutoff = timestamp(config['input_cutoff'])
    deadline = timestamp(config['publication_deadline'])
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError('the run clock needs a time zone')
    if not cutoff < deadline or now < cutoff:
        raise ValueError('invalid operating times')
    forecasts, manual = make_forecasts(config, assortment, history, fallback)
    snapshot = {
        'config': config,
        'assortment': assortment,
        'history': history,
        'fallback': fallback,
    }
    input_bytes = json.dumps(snapshot, sort_keys=True).encode()
    input_hash = hashlib.sha256(input_bytes).hexdigest()
    snapshot_name = f'inputs-{input_hash[:16]}.json'
    atomic_write(output / snapshot_name, input_bytes)
    result = {
        'case': case,
        'batch_id': f"meridian-{config['target_date']}",
        'target_date': config['target_date'],
        'release': config['release'],
        'input_cutoff': config['input_cutoff'],
        'publication_deadline': config['publication_deadline'],
        'run_time': now.isoformat(),
        'expected': len(assortment),
        'primary': sum(row['method'] == 'primary' for row in forecasts),
        'fallback': sum(row['method'] == 'fallback' for row in forecasts),
        'manual': manual,
        'input_snapshot': snapshot_name,
        'input_sha256': input_hash,
    }
    # This small application requires full coverage. A failed run leaves the
    # existing publication untouched; the reader also enforces the target date.
    if manual or now > deadline:
        reason = 'manual_planning_needed' if manual else 'deadline_missed'
        result.update(status='not_published', reason=reason)
        write_json(output / 'run.json', result)
        return result
    buffer = io.StringIO(newline='')
    writer = csv.DictWriter(buffer, fieldnames=OUTPUT_FIELDS, lineterminator='\n')
    writer.writeheader()
    writer.writerows(forecasts)
    content = buffer.getvalue().encode()
    digest = hashlib.sha256(content).hexdigest()
    filename = f"{result['batch_id']}-{digest[:16]}.csv"
    # Publish the finished CSV before replacing the small pointer that readers
    # follow. A crash before the pointer replacement exposes no partial batch.
    atomic_write(output / filename, content)
    publication_fields = [
        'batch_id', 'target_date', 'release', 'input_cutoff',
        'publication_deadline', 'expected', 'primary', 'fallback',
        'input_snapshot', 'input_sha256',
    ]
    publication = {name: result[name] for name in publication_fields}
    publication.update(batch_file=filename, sha256=digest, published_at=now.isoformat())
    pointer = output / 'current.json'
    previous = (
        json.loads(pointer.read_text(encoding='utf-8'))
        if pointer.exists() else None
    )
    reused = (
        previous is not None
        and previous['sha256'] == digest
        and previous['input_sha256'] == input_hash
        and previous['release'] == config['release']
    )
    if not reused:
        write_json(pointer, publication)
    result.update(status='published', reused=reused, batch_file=filename, sha256=digest)
    write_json(output / 'run.json', result)
    return result


def read_publication(output, target_date, files=HERE):
    """Read one completed batch for the application's required ordering date."""
    output = Path(output)
    publication = json.loads((output / 'current.json').read_text(encoding='utf-8'))
    if publication['target_date'] != target_date:
        raise ValueError('published forecast has the wrong target date')
    filename = publication['batch_file']
    if Path(filename).name != filename:
        raise ValueError('invalid batch filename')
    content = (output / filename).read_bytes()
    if hashlib.sha256(content).hexdigest() != publication['sha256']:
        raise ValueError('published batch contents have changed')
    rows = list(csv.DictReader(io.StringIO(content.decode())))
    expected = {
        (row['store'], row['product'])
        for row in read_csv(Path(files) / 'assortment.csv')
    }
    keys = [(row['store'], row['product']) for row in rows]
    if (
        len(keys) != len(set(keys))
        or set(keys) != expected
        or publication['expected'] != len(expected)
    ):
        raise ValueError('published coverage does not match the assortment')
    for row in rows:
        units(row['forecast_units'])
        if (
            row['target_date'] != target_date
            or row['method'] not in ('primary', 'fallback')
        ):
            raise ValueError('invalid published forecast')
    return publication, rows


def load_planning(output, target_date, files=HERE):
    """Refresh tasks by store/product/date and preserve planner decisions."""
    output = Path(output)
    publication, rows = read_publication(output, target_date, files)
    path = output / 'planning_tasks.json'
    tasks = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    created = 0
    for row in rows:
        key = '|'.join([row['store'],row['product'],target_date])
        if key not in tasks:
            created += 1
        task = tasks.setdefault(key, {})
        # Update forecast fields only; later planner decisions remain separate.
        task.update(row, batch_id=publication['batch_id'])
    write_json(path, tasks)
    return {
        'created': created,
        'refreshed': len(rows) - created,
        'total_for_date': sum(
            task['target_date'] == target_date for task in tasks.values()
        ),
        'tasks': [
            tasks['|'.join([row['store'], row['product'], target_date])]
            for row in rows
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', choices=['on-time', 'late-feed'], default='on-time')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    try:
        result = run_job(args.case, args.output)
        print(f"Demo clock: {result['run_time']}")
        print(
            f"{result['status'].upper()}: {result['primary']} primary, "
            f"{result['fallback']} fallback, {len(result['manual'])} manual"
        )
        print(f"Target date: {result['target_date']} | Batch: {result['batch_id']}")
        print(f"Output: {args.output or HERE / 'service_runs' / args.case}")
        return 0 if result['status'] == 'published' else 2
    except (ValueError, OSError, KeyError, csv.Error) as error:
        print(f'Job stopped: {error}')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
