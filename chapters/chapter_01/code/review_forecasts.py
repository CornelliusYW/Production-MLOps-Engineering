"""A local desktop reviewer that runs the Chapter 1 evaluator.

Python 3.10+ with Tkinter. Uses the standard library, no server or cloud account.
Every click of Run evaluation creates a fresh directory of inputs and evidence.
"""
import argparse
import csv
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import tkinter as tk
from tkinter import ttk

HERE = Path(__file__).resolve().parent
CASES = ('Original data', 'Late feature', 'Segment regression')


def prepare_case(case, destination):
    with (HERE / 'forecasts.csv').open(newline='', encoding='utf-8') as stream:
        reader = csv.DictReader(stream)
        fields = reader.fieldnames
        rows = list(reader)
    if case == 'Late feature':
        rows[0]['features_available_at'] = '2026-01-05T04:31:00+07:00'
    elif case == 'Segment regression':
        for row in rows:
            row['candidate_units'] = str(float(row['actual_units']) +
                                         (11 if row['segment'] == 'North' else 0))
    name = {'Original data': 'forecasts.csv', 'Late feature': 'late_features.csv',
            'Segment regression': 'segment_regression.csv'}[case]
    path = destination / name
    with path.open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return path, rows


class ReviewApp:
    def __init__(self, root, output):
        self.root, self.output = root, output
        root.title('Chapter 1 Forecast Evaluation')
        root.configure(bg='white')
        root.geometry('1040x800+30+30')
        root.minsize(1000, 760)
        style = ttk.Style(root)
        style.theme_use('clam')
        style.configure('TFrame', background='white')
        style.configure('TLabel', background='white', foreground='#102B40', font=('Arial', 16))
        style.configure('Title.TLabel', font=('Arial', 25, 'bold'), foreground='black')
        style.configure('Status.TLabel', font=('Arial', 18, 'bold'))
        style.configure('TButton', font=('Arial', 16), padding=(10, 6))
        style.configure('TRadiobutton', background='white', font=('Arial', 16), padding=(6, 3))
        style.configure('Treeview', font=('Arial', 20), rowheight=42,
                        background='white', fieldbackground='white', foreground='#102B40')
        style.configure('Treeview.Heading', font=('Arial', 16, 'bold'), padding=7)
        self.case = tk.StringVar(value=CASES[0])
        frame = ttk.Frame(root, padding=16)
        frame.pack(fill='both', expand=True)
        ttk.Label(frame, text='Forecast evaluation', style='Title.TLabel').pack(anchor='w')
        ttk.Label(frame, text='Chapter 1 companion  |  Illustrative precomputed forecasts').pack(anchor='w', pady=(3, 8))
        controls = ttk.Frame(frame)
        controls.pack(fill='x', pady=(0, 8))
        for case in CASES:
            ttk.Radiobutton(controls, text=case, variable=self.case, value=case).pack(side='left')
        ttk.Button(controls, text='Run evaluation', command=self.run).pack(side='right')
        self.input_info = ttk.Label(frame, text='Select a case, then run the evaluation.')
        self.input_info.pack(anchor='w', pady=(0, 8))
        ttk.Label(frame, text='Evaluator output', style='Status.TLabel').pack(anchor='w')
        self.console = tk.Text(frame, height=7, wrap='word', font=('Consolas', 22),
                               bg='#F1F5F8', fg='#102B40', relief='solid', borderwidth=1,
                               padx=12, pady=8, highlightthickness=0)
        self.console.pack(fill='x', pady=(5, 8))
        self.console.configure(state='disabled')
        self.console.tag_configure('error', foreground='#A62E23')
        self.report_label = ttk.Label(frame, text='No run yet.', style='Status.TLabel')
        self.report_label.pack(anchor='w', pady=(2, 8))
        ttk.Label(frame, text='Segment checks from the saved report', style='Status.TLabel').pack(anchor='w')
        self.table = ttk.Treeview(frame, columns=('segment', 'baseline', 'candidate', 'gate'),
                                  show='headings', height=2, selectmode='none')
        for name, title in zip(self.table['columns'],
                               ('Segment', 'Baseline MAE', 'Candidate MAE', 'No regression')):
            self.table.heading(name, text=title)
            self.table.column(name, width=220, anchor='w' if name=='segment' else 'center')
        self.table.tag_configure('pass', foreground='#176346')
        self.table.tag_configure('fail', foreground='#A62E23')
        self.table.pack(fill='x', pady=(5, 8))
        self.note = ttk.Label(frame, text='Production approval is not assessed by this example.',
                              wraplength=970)
        self.note.pack(anchor='w', pady=(2, 4))
        self.run_count = 0

    def run(self):
        self.output.mkdir(parents=True, exist_ok=True)
        destination = Path(tempfile.mkdtemp(prefix='run_', dir=self.output))
        case = self.case.get()
        try:
            data, rows = prepare_case(case, destination)
            report_path = destination / 'report.json'
            command = [sys.executable, str(HERE / 'evaluate_forecasts.py'),
                       '--data', str(data), '--output', str(report_path)]
            options = {'creationflags': subprocess.CREATE_NO_WINDOW} if sys.platform=='win32' else {}
            result = subprocess.run(command, text=True, capture_output=True, check=False, **options)
            report = json.loads(report_path.read_text(encoding='utf-8')) if report_path.exists() else None
            evidence = {'case': case, 'exit_status': result.returncode, 'stdout': result.stdout,
                        'stderr': result.stderr, 'data_file': data.name, 'report': report}
            (destination / 'run.json').write_text(json.dumps(evidence, indent=2)+'\n', encoding='utf-8')
        except (OSError, ValueError, csv.Error) as error:
            self.report_label.configure(text=f'Unable to run evaluation: {error}', foreground='#A62E23')
            return
        first = rows[0]
        self.input_info.configure(text=f'Input: {data.name}\n'
                                  f'First row: cutoff {first["input_cutoff"][11:]}  |  '
                                  f'available {first["features_available_at"][11:]}')
        self.console.configure(state='normal')
        self.console.delete('1.0', 'end')
        self.console.insert('end', result.stdout)
        self.console.insert('end', result.stderr, 'error')
        self.console.configure(state='disabled')
        for item in self.table.get_children():
            self.table.delete(item)
        if report is not None:
            for segment, values in report['segments'].items():
                passed = values['no_mae_regression']
                self.table.insert('', 'end', values=(segment, f'{values["baseline"]["mae"]:.1f}',
                                  f'{values["candidate"]["mae"]:.1f}', 'PASS' if passed else 'FAIL'),
                                  tags=('pass' if passed else 'fail',))
        status = 'Comparison report saved' if report is not None else 'No comparison report created'
        self.report_label.configure(text=f'Exit status {result.returncode}  |  {status}',
                                     foreground='#176346' if result.returncode==0 else '#A62E23')
        self.note.configure(text=('Production approval: NOT ASSESSED. Review the complete operating workflow.'
                                  if report is not None else
                                  'Input validation stopped scoring. Check the source and its availability rule.'))
        self.run_count += 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=HERE / 'review_runs')
    args = parser.parse_args()
    root = tk.Tk()
    ReviewApp(root, args.output.resolve())
    root.mainloop()


if __name__ == '__main__':
    main()
