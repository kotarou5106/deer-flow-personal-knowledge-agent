# Knowledge Workflow Guide

Use ingestion when the source is new or changed. Use search when the user needs known facts or citations. Use analysis when the user needs synthesis, tradeoffs, conclusions, or unresolved questions.

For workflow work, create the run with `workflow_create`, advance with `workflow_advance`, inspect with `workflow_get`, and persist outputs with `workflow_generate_artifact`. A workflow that pauses for approval is not complete.

Use validation tools before relying on artifacts, workflow completion, provenance, or approval state.
