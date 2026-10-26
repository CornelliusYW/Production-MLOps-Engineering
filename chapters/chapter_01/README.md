# Chapter 1 From Experiment to Enterprise MLOps

This chapter connects model development to a service people can use in their daily work. The companion example runs a small morning forecasting job and supplies its output to a planning application.

We use synthetic data for eight store and product combinations across four stores. The example lets us follow a normal run, see how a late feed changes the forecasting method, and load the results again without creating duplicate planning tasks.

The [Chapter 1 files](https://github.com/CornelliusYW/Production-MLOps-Engineering/tree/main/chapters/chapter_01) are in the shared book repository. Run this exercise from its `chapters/chapter_01/code` folder.

## Start the example

Use Python 3.12 or later. The desktop application also needs Tkinter. No additional Python packages are required.

From the repository root:

```text
cd chapters/chapter_01/code
python service_demo.py
```

Keep **On-time feed** selected and click **Run morning job**. Then try **Late North feed** and use **Load planning** to follow the published forecasts into the application.

See the [code README](code/README.md) for terminal commands, expected results, input files and tests. It also explains the fixed demonstration clock, the single-writer example and the optional offline comparison.

## Topics

- From experiments to production systems.
- The enterprise ML lifecycle.
- MLOps as people, process, and platform.
- Production risks and failure patterns.
- Reference case, constraints, and success measures.
