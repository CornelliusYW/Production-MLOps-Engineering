"""Read completed forecasts into local planning tasks; no supplier orders."""
import argparse
import csv
from pathlib import Path
import sys

from forecast_job import HERE, load_planning


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', choices=['on-time', 'late-feed'], default='on-time')
    parser.add_argument('--target-date', default='2026-01-06')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    output = args.output or HERE / 'service_runs' / args.case
    try:
        result = load_planning(output, args.target_date)
    except (ValueError, OSError, KeyError, csv.Error) as error:
        print(f'Planning load stopped: {error}', file=sys.stderr)
        return 1
    print(
        f"New tasks: {result['created']} | "
        f"Refreshed tasks: {result['refreshed']} | "
        f"Tasks for date: {result['total_for_date']}"
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
