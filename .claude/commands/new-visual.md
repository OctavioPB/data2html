Add a new chart type (mark): $ARGUMENTS (e.g. "scatter" or "heatmap").

Follow the `report-spec` and `html-renderer` skills:
1. Define which encoding it requires (dimensions, measures, color) and propose the rule in `spec/compat.py`.
   Wait for approval: it changes the contract.
2. Add the value to `Mark`, the rule to `allowed_marks` and compatibility tests (accepts and rejects).
3. Implement the rendering in the HTML renderer and in the studio with the same mapping.
4. Regenerate the JSON Schema and add an example visual in `examples/reports/`.
