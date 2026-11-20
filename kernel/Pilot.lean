/-
  Pilot.lean — statement-level anchor for the independent-kernel pilot.

  This file imports *only* Mathlib (never the project's `Main`) and references
  the two declarations whose declaration-level dependency cone this pilot
  exports and hands to an independent kernel checker:

  * `RiemannHypothesis` — the statement definition that `Audit.lean` anchors
    on (its first line is `example : _root_.RiemannHypothesis :=
    _root_.riemannHypothesis`), and
  * `riemannZeta` — the completed Riemann zeta function its statement
    is about.

  It proves nothing; it exists so the export has a small, Mathlib-only root
  module whose environment pins down exactly the cone we mean.
-/
import Mathlib

#check @RiemannHypothesis
#check @riemannZeta
