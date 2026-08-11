"""Exon context-tuning harness.

Implements the measure -> refine -> re-measure loop from
openspec/changes/add-exon-context-harness/. One module per node of that workflow:

    probe.py    [0] what can this model actually do?
    cases.py    [A] the test suite (reused from evals/questions.yaml)
    runner.py   [B] execute the suite against the target, k samples per case
    grading.py  [C] evaluate -> pass rate per case
    triage.py   [D] classify failures into a bundle for the refiner
    refine.py   [E] propose a bounded context patch
    loop.py     [F] orchestration, rollback, termination

The goal is not perfect reliability. It is to turn "does this work?" into a measured
statistic and raise it by tuning the one thing the loop may change: the context.
"""
