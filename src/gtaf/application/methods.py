"""Which segmentation the analysis currently reads (SPEC-006, D-027).

Both segmentations live side by side in the `segments` table, distinguished by `seg_method`. That is
deliberate: every figure published before D-027 was computed on `fixed` windows, and a baseline that
is overwritten cannot be compared to anything.

The consequence is that **every query touching segments must filter by method**, or it silently
counts both and doubles the corpus. This module is the single place the choice is made, so switching
methods is a one-line change with a visible effect rather than a scattered edit.
"""

from __future__ import annotations

from gtaf.domain.segment import SEG_METHOD_DRIFT, SEG_VERSION_DRIFT

# Measured in D-027: drift boundaries separate topics (gap +0.217), time-based ones anti-correlate
# (gap -0.015). Drift is the method the analysis reads.
ACTIVE_SEG_METHOD = SEG_METHOD_DRIFT
ACTIVE_SEG_VERSION = SEG_VERSION_DRIFT

# Kept for the control comparison, never written by the pipeline unless explicitly asked.
CONTROL_SEG_METHOD = "fixed"
