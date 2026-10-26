"""Evaluate illustrative forecasts; offline gates never grant production approval.

Requires Python 3.10+ and only the standard library. Exit status: 0 = gates
passed, 2 = valid comparison failed gates, 1 = invalid input or output error.
"""
import argparse
import csv
from datetime import date, datetime, time
import hashlib
import json
import math
from pathlib import Path
import platform
import sys

HERE = Path(__file__).resolve().parent
KEY_FIELDS = ("store", "product", "target_date")
VALUE_FIELDS = ("actual_units", "baseline_units", "candidate_units")
FIELDS = set(KEY_FIELDS + VALUE_FIELDS + (
    "segment", "input_cutoff", "features_available_at",
))


def read_csv(path, fields):
    with Path(path).open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        headers = reader.fieldnames or []
        if len(headers) != len(fields) or set(headers) != set(fields):
            raise ValueError(f"{Path(path).name}: unexpected CSV columns")
        rows = list(reader)
    if not rows:
        raise ValueError(f"{Path(path).name}: empty population")
    for row in rows:
        if set(row) != set(fields) or any(
            value is None or not value.strip() for value in row.values()
        ):
            raise ValueError(f"{Path(path).name}: incomplete or malformed row")
    return rows


def parse_time(value):
    result = datetime.fromisoformat(value)
    if result.utcoffset() is None:
        raise ValueError("timestamps must include a time zone offset")
    return result


def key_for(row):
    date.fromisoformat(row["target_date"])
    return tuple(row[name] for name in KEY_FIELDS)


def load_policy(path):
    policy = json.loads(Path(path).read_text(encoding="utf-8"))
    if set(policy) != {"min_mae_improvement", "segments"}:
        raise ValueError("policy must define improvement and segments")
    minimum = policy["min_mae_improvement"]
    if type(minimum) not in (int, float) or not math.isfinite(minimum):
        raise ValueError("improvement must be a finite number")
    if not 0 <= minimum <= 1:
        raise ValueError("improvement must be between zero and one")
    segments = policy["segments"]
    if not isinstance(segments, list) or not segments or any(
        not isinstance(item, str) or not item.strip() for item in segments
    ) or len(set(segments)) != len(segments):
        raise ValueError("segments must be unique nonempty strings")
    return policy


def validated_rows(data_path, population_path, policy):
    expected = {}
    for row in read_csv(population_path, set(KEY_FIELDS + ("segment",))):
        key = key_for(row)
        if key in expected:
            raise ValueError("duplicate expected population key")
        expected[key] = row["segment"]
    if set(expected.values()) != set(policy["segments"]):
        raise ValueError("expected population does not match policy segments")
    rows = read_csv(data_path, FIELDS)
    observed = set()
    for row in rows:
        key = key_for(row)
        if key in observed:
            raise ValueError("duplicate prediction key")
        observed.add(key)
        if key not in expected or row["segment"] != expected[key]:
            raise ValueError("unexpected prediction key or segment")
        for name in VALUE_FIELDS:
            value = float(row[name])
            if not math.isfinite(value) or value < 0:
                raise ValueError(f"{name} must be finite and nonnegative")
            row[name] = value
        available = parse_time(row["features_available_at"])
        cutoff = parse_time(row["input_cutoff"])
        if available > cutoff:
            raise ValueError("feature available after cutoff")
        target_start = datetime.combine(
            date.fromisoformat(row["target_date"]),
            time.min,
            tzinfo=cutoff.tzinfo,
        )
        if cutoff >= target_start:
            raise ValueError("cutoff must precede target day")
    if observed != set(expected):
        raise ValueError("missing expected population keys")
    return rows


def metrics(rows, prediction_field):
    if not rows:
        raise ValueError("cannot evaluate an empty segment")
    errors = [row[prediction_field] - row["actual_units"] for row in rows]
    absolute_sum = math.fsum(abs(value) for value in errors)
    actual_sum = math.fsum(row["actual_units"] for row in rows)
    return {
        "rows": len(rows),
        "actual_units": actual_sum,
        "mae": absolute_sum / len(rows),
        "wape_percent": 100 * absolute_sum / actual_sum if actual_sum else None,
        "bias_percent": 100 * math.fsum(errors) / actual_sum if actual_sum else None,
    }


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def evaluate(data_path, population_path, policy_path):
    policy = load_policy(policy_path)
    rows = validated_rows(data_path, population_path, policy)
    baseline = metrics(rows, "baseline_units")
    candidate = metrics(rows, "candidate_units")
    # A perfect baseline cannot be improved. Represent the non-improvement
    # explicitly and fail the gate if the candidate worsens it.
    if baseline["mae"] == 0:
        improvement = 0.0 if candidate["mae"] == 0 else None
    else:
        improvement = 1 - candidate["mae"] / baseline["mae"]
    segment_results = {}
    for segment in policy["segments"]:
        subset = [row for row in rows if row["segment"] == segment]
        old = metrics(subset, "baseline_units")
        new = metrics(subset, "candidate_units")
        segment_results[segment] = {
            "baseline": old,
            "candidate": new,
            "no_mae_regression": new["mae"] <= old["mae"],
        }
    passed = improvement is not None and improvement >= policy["min_mae_improvement"]
    passed = passed and all(item["no_mae_regression"] for item in segment_results.values())
    return {
        "report_schema_version": 1,
        "data_scope": "illustrative precomputed predictions; no model trained",
        "python_version": platform.python_version(),
        "sha256": {
            "data": sha256(data_path),
            "expected_population": sha256(population_path),
            "policy": sha256(policy_path),
            "evaluator": sha256(__file__),
        },
        "policy": policy,
        "baseline": baseline,
        "candidate": candidate,
        "mae_improvement_fraction": improvement,
        "segments": segment_results,
        "offline_gates": "pass" if passed else "fail",
        "production_approval": "not_assessed",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=HERE / "forecasts.csv")
    parser.add_argument("--population", type=Path, default=HERE / "expected_population.csv")
    parser.add_argument("--policy", type=Path, default=HERE / "policy.json")
    parser.add_argument("--output", type=Path, default=Path("report.json"))
    args = parser.parse_args()
    try:
        if args.output.exists():
            raise ValueError("output exists; choose a new --output path")
        report = evaluate(args.data, args.population, args.policy)
        encoded = json.dumps(report, indent=2, allow_nan=False) + "\n"
        # Exclusive creation prevents confusing a stale report with a new run.
        with args.output.open("x", encoding="utf-8") as stream:
            stream.write(encoded)
    except (ValueError, OSError, csv.Error, TypeError, OverflowError) as error:
        print(f"Evaluation error: {error}", file=sys.stderr)
        return 1
    print(f"Rows: {report['candidate']['rows']}")
    print(f"Baseline MAE: {report['baseline']['mae']:.4f}")
    print(f"Candidate MAE: {report['candidate']['mae']:.4f}")
    improvement = report["mae_improvement_fraction"]
    text = "undefined (perfect baseline)" if improvement is None else f"{improvement:.2%}"
    print(f"MAE improvement: {text}")
    wape = report["candidate"]["wape_percent"]
    text = "undefined (zero actual units)" if wape is None else f"{wape:.4f}%"
    print(f"Candidate WAPE: {text}")
    print(f"Offline gates: {report['offline_gates'].upper()}")
    print("Production approval: NOT ASSESSED")
    return 0 if report["offline_gates"] == "pass" else 2


if __name__ == "__main__":
    sys.exit(main())
