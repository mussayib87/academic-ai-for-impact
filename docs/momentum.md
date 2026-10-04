# Academic Momentum

Momentum is computed from rows in `academic_momentum`, each with a student, metric, value, and observed timestamp. Seed data supplies eight weekly observations for attendance, assessment, activity, and assignment-submission trend.

`calculate_momentum` requires at least four observations. It compares early and recent halves, computes least-squares slope and percentage change, and checks variation between successive observations. Output is `IMPROVING`, `STABLE`, `DECLINING`, `VOLATILE`, or `INSUFFICIENT_DATA`, with the underlying values returned for review.

The directory uses assessment trend classification rather than the legacy static `Student.momentum` field. Classification cutoffs are simple signal heuristics, not validated institutional thresholds.