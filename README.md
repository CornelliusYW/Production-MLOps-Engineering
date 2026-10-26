# Production MLOps Engineering

Companion code for the book by Cornellius Yudha Wijaya. This repository keeps the book's code in one place, with a separate folder for each chapter. Each chapter explains what to install, how to run its examples and what results to expect.

## Chapters

| Chapter | Example |
| --- | --- |
| [1 From Experiment to Enterprise MLOps](chapters/chapter_01/README.md) | Run a forecasting service, handle a late feed and load forecasts into planning |

Further chapter folders will be added as their examples are prepared.

## Get the code

```text
git clone https://github.com/CornelliusYW/Production-MLOps-Engineering.git
cd Production-MLOps-Engineering
```

You can also download the repository as a ZIP from its **Code** menu.

## Start with Chapter 1

Download a copy of the repository or clone it, then open a terminal in the repository root. Use Python 3.12 or later, with Tkinter for the desktop application. Chapter 1 uses only the Python standard library.

```text
cd chapters/chapter_01/code
python service_demo.py
```

The [Chapter 1 instructions](chapters/chapter_01/code/README.md) include a terminal workflow for computers without a graphical desktop.

## Folder structure

```text
chapters/
    chapter_01/
        README.md
        code/
            README.md
            forecast_job.py
            planning_app.py
            service_demo.py
            ... input files and tests
```

Keep each chapter's scripts beside its supplied data and settings. Run outputs are saved locally and excluded from Git.

## Tests

From the repository root, run Chapter 1's tests with:

```text
python -m unittest discover -s chapters/chapter_01/code -p "test_*.py" -v
```

The included GitHub Actions workflow is configured to run these tests on Windows and Linux with Python 3.12 and 3.13. Desktop interaction is not part of that automated run.

## Report a problem

When opening an issue, include the chapter, your operating system and Python version, the command you ran, and the error or unexpected result. This helps us reproduce the problem with the supplied example.
