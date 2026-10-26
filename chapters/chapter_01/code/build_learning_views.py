"""Run three real evaluations and make local HTML learning views.

Python 3.10+; standard library only. Outputs are created in a new directory
so an earlier run is never overwritten. Open its HTML files in a browser.
"""
import argparse
import csv
import html
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent


def write_rows(path, rows):
    with path.open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def make_page(title, body):
    return '''<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Chapter 1 learning view</title><style>
*{box-sizing:border-box}body{margin:0;background:#fff;color:#132f43;
font:30px/1.4 Arial,sans-serif}main{padding:44px 56px;max-width:2000px}
.eyebrow{font-size:25px;letter-spacing:1px;font-weight:bold;color:#4a6171}
h1{font-size:48px;line-height:1.15;margin:12px 0 28px;color:#000}
h2{font-size:32px;margin:24px 0 10px;color:#000}p{margin:12px 0}
pre{font:29px/1.45 Consolas,monospace;margin:10px 0;white-space:pre-wrap;
overflow-wrap:anywhere;background:#f1f5f8;padding:18px 22px;color:#102b40}
table{border-collapse:collapse;width:100%;margin:12px 0 20px}
th,td{padding:14px 18px;border:2px solid #d9d9d9;text-align:left}
th{background:#173b55;color:#fff}td:nth-child(n+2){text-align:center}
.pass{color:#176346;font-weight:bold}.fail{color:#a62e23;font-weight:bold}
.note{font-weight:bold}.footer{font-size:25px;color:#4a6171;margin-top:24px}
</style><main><div class="eyebrow">CHAPTER 1 · LOCAL RESULTS VIEWER</div>
<h1>''' + html.escape(title) + '</h1>' + body + '''
<p class="footer">Original illustrative data · Precomputed forecasts · No model trained or deployed</p>
</main></html>'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=HERE / 'learning_views')
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    with (HERE / 'forecasts.csv').open(newline='', encoding='utf-8') as stream:
        original = list(csv.DictReader(stream))
    late = [dict(row) for row in original]
    late[0]['features_available_at'] = '2026-01-05T04:31:00+07:00'
    regression = [dict(row) for row in original]
    for row in regression:
        row['candidate_units'] = str(float(row['actual_units']) +
                                     (11 if row['segment'] == 'North' else 0))
    write_rows(out / 'late_features.csv', late)
    write_rows(out / 'segment_regression.csv', regression)
    runs = {}
    for name, data, expected_exit in [
        ('success', HERE / 'forecasts.csv', 0),
        ('late_data', out / 'late_features.csv', 1),
        ('segment_regression', out / 'segment_regression.csv', 2),
    ]:
        report_path = out / f'{name}_report.json'
        command = [sys.executable, str(HERE / 'evaluate_forecasts.py'),
                   '--data', str(data), '--output', str(report_path)]
        result = subprocess.run(command, text=True, capture_output=True, check=False)
        if result.returncode != expected_exit:
            raise RuntimeError(f'{name}: unexpected exit {result.returncode}: {result.stderr}')
        report = json.loads(report_path.read_text()) if report_path.exists() else None
        if name == 'late_data' and report is not None:
            raise RuntimeError('Invalid input must not create a comparison report')
        if name != 'late_data' and report is None:
            raise RuntimeError('Completed comparison must create a report')
        runs[name] = {'exit_status': result.returncode, 'stdout': result.stdout,
                      'stderr': result.stderr, 'report': report}
        (out / f'{name}_console.txt').write_text(result.stdout + result.stderr, encoding='utf-8')

    def segment_table(report):
        rows = ''
        for name, values in report['segments'].items():
            passed = values['no_mae_regression']
            rows += (f'<tr><td>{html.escape(name)}</td>'
                     f'<td>{values["baseline"]["mae"]:.1f}</td>'
                     f'<td>{values["candidate"]["mae"]:.1f}</td>'
                     f'<td class="{"pass" if passed else "fail"}">{"PASS" if passed else "FAIL"}</td></tr>')
        return ('<table><tr><th>Segment</th><th>Baseline MAE</th>'
                '<th>Candidate MAE</th><th>No regression</th></tr>' + rows + '</table>')

    success = runs['success']
    body = '<h2>1 Read the captured command output</h2><pre>' + html.escape(success['stdout']) + '</pre>'
    body += '<h2>2 Check both segments in the saved report</h2>' + segment_table(success['report'])
    body += '<p class="note">3 PASS applies to the offline policy. Production approval remains NOT ASSESSED.</p>'
    (out / 'success.html').write_text(make_page('A successful offline comparison', body), encoding='utf-8')

    body = ('<h2>1 Compare the first row’s declared times</h2><table>'
            '<tr><th>Field</th><th>Local time on 5 January 2026</th></tr>'
            '<tr><td>Input cutoff</td><td>04:30:00 +07:00</td></tr>'
            '<tr><td>Feature available</td><td class="fail">04:31:00 +07:00</td></tr></table>'
            '<p>The feature arrives one minute after the allowed cutoff.</p>'
            '<h2>2 Read the captured error</h2><pre>' + html.escape(runs['late_data']['stderr']) + '</pre>'
            '<p class="note">Exit status 1 · No new comparison report created</p>'
            '<h2>3 Investigate the input boundary</h2>'
            '<p>Check the source and availability rule before rerunning. A score cannot repair an invalid input.</p>')
    (out / 'late_data.html').write_text(make_page('Late input stops the evaluation', body), encoding='utf-8')

    failed = runs['segment_regression']
    report = failed['report']
    body = ('<h2>1 Read the overall result</h2><pre>' + html.escape(failed['stdout']) + '</pre>'
            '<h2>2 Find the segment that blocks the candidate</h2>' + segment_table(report) +
            '<p class="note">3 North MAE rises from 10 to 11. The 56% overall improvement does not satisfy every gate.</p>'
            '<p>Exit status 2 · A completed comparison report records the failed policy.</p>')
    (out / 'segment_regression.html').write_text(make_page('An improved average can hide a regression', body), encoding='utf-8')
    (out / 'run_results.json').write_text(json.dumps(runs, indent=2) + '\n', encoding='utf-8')
    print(f'Created three learning views in {out}')
    print('Verified exit statuses: success 0, late data 1, segment regression 2')


if __name__ == '__main__':
    main()
