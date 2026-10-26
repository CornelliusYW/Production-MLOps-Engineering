# Chapter 1 code

Let's run a small forecasting service and follow its results into a planning application. We will see how the job handles a late data feed and how the application can load forecasts again without creating duplicate planning tasks.

All data is synthetic. The example covers eight store and product combinations across four stores. Its primary method is the mean of three days of sales, which keeps the calculation simple while we learn how to operate the workflow.

These files belong to [Production MLOps Engineering](https://github.com/CornelliusYW/Production-MLOps-Engineering), the shared repository for all chapters. This exercise is in [chapters/chapter_01/code](https://github.com/CornelliusYW/Production-MLOps-Engineering/tree/main/chapters/chapter_01/code).

## Requirements

- Python 3.12 or later.
- A terminal. The desktop application also needs Tkinter and a graphical desktop.
- A writable copy of this folder, with the scripts and input files kept together.

No additional Python packages are required. Check your installation with:

```text
python --version
python -m tkinter
```

The second command opens a small window that you can close. If your computer uses `python3` or `py`, substitute that command consistently. See the [Tkinter documentation](https://docs.python.org/3/library/tkinter.html) if Tkinter is missing. The terminal workflow works without Tkinter.

From the repository root, open this folder:

```text
cd chapters/chapter_01/code
```

## Run the application

```text
python service_demo.py
```

The window is titled **Chapter 1 Morning Forecast Service**.

1. Keep **On-time feed** selected and click **Run morning job**. The job publishes eight primary forecasts. S001/P001 receives 100 units: the mean of 90, 100 and 110.
2. Select **Late North feed** and run again. North uses four saved fallback forecasts while South uses four primary forecasts. S001/P001 receives 90 units.
3. Click **Load planning**, then click it again. A fresh first load creates eight tasks; the next refreshes them and creates none.

If you have loaded the case before, the first click may already refresh existing tasks. Each case keeps its output between sessions.

The example uses a **fixed demo clock** of 05:00 on 5 January 2026 at UTC+07:00. Its input cutoff is 04:30 and publication deadline is 06:00 that day. It forecasts 6 January. You can run it on any day; it does not install a scheduler or wait for those dates.

## Run from the terminal

Run the on-time job, then load its forecasts into planning:

```text
python forecast_job.py
python planning_app.py
```

Run the late-feed case and load it twice:

```text
python forecast_job.py --case late-feed
python planning_app.py --case late-feed
python planning_app.py --case late-feed
```

For a fresh output folder, give the job and reader the same path:

```text
python forecast_job.py --case late-feed --output service_runs/try_02
python planning_app.py --case late-feed --output service_runs/try_02
```

Defaults are `service_runs/on-time` and `service_runs/late-feed`. Inputs are resolved beside the scripts even when the programs are called from another folder. The reader's `--target-date` defaults to `2026-01-06` and rejects another date's publication.

| Case | Primary | Fallback | Manual | S001/P001 units |
| --- | ---: | ---: | ---: | ---: |
| On-time feed | 8 | 0 | 0 | 100 |
| Late North feed | 4 | 4 | 0 | 90 |

The forecasting command returns exit code `0` when it publishes, `2` when it withholds publication because of the deadline or an uncovered item, and `1` for an input or file error. The planning command returns `0` for a successful load and `1` for a failed load. Run the forecasting job before loading planning.

## Follow the code

| File or function | What it does |
| --- | --- |
| `forecast_job.py`: `prepare_inputs` | Loads the inputs and simulates North's delay in memory |
| `forecast_job.py`: `make_forecasts` | Selects primary/fallback quantities and records items needing manual planning |
| `forecast_job.py`: `run_job` | Saves the input snapshot and run record, then publishes a complete batch before updating `current.json` |
| `forecast_job.py`: `load_planning` | Reads the published batch and creates or refreshes tasks |
| `planning_app.py` | Runs the planning reader from the terminal |
| `service_demo.py` | Provides desktop controls for the same job and reader |

The fallback branch and task-key code shown in the chapter are excerpts from `forecast_job.py`.

## Input files

| File | What it supplies |
| --- | --- |
| `service.json` | Target, cutoff, deadline, demo clock, release and history dates |
| `assortment.csv` | Eight eligible store/product pairs, independently of the sales feed |
| `sales_history.csv` | Three sales observations per pair with availability times |
| `fallback_forecasts.csv` | Forecasts saved earlier for the same target date |

Selecting **Late North feed** sets North's availability to 04:31 in memory, leaving the original CSV unchanged. A fallback must be for the requested target date and available by the cutoff. If an eligible item cannot receive either method, this example withholds the whole batch and records the item for manual planning.

## Generated files

| File | What you can learn from it |
| --- | --- |
| `inputs-*.json` | The settings and inputs selected for the run |
| `meridian-2026-01-06-*.csv` | A completed batch with quantities, methods and reasons |
| `current.json` | Which completed CSV the planning application should read |
| `run.json` | The latest attempt, including an unsuccessful publication |
| `planning_tasks.json` | The tasks created or refreshed when the reader runs |

**Store, product and target date** identify each task. Its saved `batch_id` records which batch supplied the current forecast. Loading again updates forecast fields and preserves any existing planner decision fields.

The CSV finishes before `current.json` is replaced. A failed publication leaves any earlier publication selected; the reader also checks its date, coverage and contents. Repeating the same job reuses its publication. This example assumes one writer on a local filesystem. Shared storage needs coordination for simultaneous operations.

The application supplies quantities for planning. It does not calculate order quantities, approve orders or contact suppliers. Delivery coverage also does not establish forecast accuracy or business benefit.

## Optional forecast comparison

The main walkthrough uses the service above. For a separate offline comparison with known outcomes, run:

```text
python evaluate_forecasts.py
```

This reads `forecasts.csv`, `expected_population.csv` and `policy.json`, then writes `report.json`. Existing reports are not overwritten. For another attempt:

```text
python evaluate_forecasts.py --output report_02.json
```

Expected results are baseline MAE **12.5**, candidate MAE **5**, improvement **60%**, candidate WAPE approximately **4.7059%** and signed bias **0%**. North's baseline/candidate MAE is **10/4**; South's is **15/6**. The policy requires at least 10% overall improvement with no increase in either group's MAE. Passing it is one comparison, not approval of the full service.

`review_forecasts.py` provides a desktop interface for this optional comparison. `build_learning_views.py` creates local HTML views. Their outputs go under `review_runs` and `learning_views`; they are separate from the service screenshots in the chapter.

## Tests

From this code folder:

```text
python -m unittest -v
```

The tests cover quantities, fallback selection, failed and interrupted publication, repeated loads, preserved planner decisions, invalid inputs and the optional error calculations. A command test checks the reader's response when no batch has been published. Tests use temporary folders and leave the supplied CSVs unchanged.
