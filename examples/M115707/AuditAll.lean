import Development.AutomorphicArithmetic.IntegralCasts.CapelliIdentities.SelectionLemmas
import PublishedSelector

universe v1 v2 v3 v4 v5

example : @PublishedSelector.aux1.{v1} = @UpperTheory.Reformulated.B.SelectionLemmas.aux1.{v1} := rfl
example : @PublishedSelector.aux2.{v1} = @UpperTheory.Reformulated.B.SelectionLemmas.aux2.{v1} := rfl
example : @PublishedSelector.aux3.{v1, v2, v3} = @UpperTheory.Reformulated.B.SelectionLemmas.aux3.{v1, v2, v3} := rfl
example : @PublishedSelector.hdual.{v1, v2, v3} = @UpperTheory.Reformulated.B.SelectionLemmas.hdual.{v1, v2, v3} := rfl
example : @PublishedSelector.dual.{v1, v2, v3} = @UpperTheory.Reformulated.B.SelectionLemmas.dual.{v1, v2, v3} := rfl
example : @PublishedSelector.aux6 = @UpperTheory.Reformulated.B.SelectionLemmas.aux6 := rfl
example : @PublishedSelector.aux7 = @UpperTheory.Reformulated.B.SelectionLemmas.aux7 := rfl
example : @PublishedSelector.aux8 = @UpperTheory.Reformulated.B.SelectionLemmas.aux8 := rfl
example : @PublishedSelector.hform = @UpperTheory.Reformulated.B.SelectionLemmas.hform := rfl
example : @PublishedSelector.laurent_T_neg_one_mul_T_one.{v1, v2} = @UpperTheory.Reformulated.B.SelectionLemmas.laurent_T_neg_one_mul_T_one.{v1, v2} := rfl
example : @PublishedSelector.aux11.{v1, v2} = @UpperTheory.Reformulated.B.SelectionLemmas.aux11.{v1, v2} := rfl
example : @PublishedSelector.aux12.{v1, v2} = @UpperTheory.Reformulated.B.SelectionLemmas.aux12.{v1, v2} := rfl
example : @PublishedSelector.locS.{v1, v2} = @UpperTheory.Reformulated.B.SelectionLemmas.locS.{v1, v2} := rfl
example : @PublishedSelector.hcompl.{v1, v2} = @UpperTheory.Reformulated.B.SelectionLemmas.hcompl.{v1, v2} := rfl
example : @PublishedSelector.loc.{v1, v2, v3} = @UpperTheory.Reformulated.B.SelectionLemmas.loc.{v1, v2, v3} := rfl
example : @PublishedSelector.IsLocBasis = @UpperTheory.Reformulated.B.SelectionLemmas.IsLocBasis := rfl
example : @PublishedSelector.complex_normed_instance_compat = @UpperTheory.Reformulated.B.SelectionLemmas.complex_normed_instance_compat := rfl
example : @PublishedSelector.padic_embedding_algebra_compat = @UpperTheory.Reformulated.B.SelectionLemmas.padic_embedding_algebra_compat := rfl
example : @PublishedSelector.matLat = @UpperTheory.Reformulated.B.SelectionLemmas.matLat := rfl
example : @PublishedSelector.vw = @UpperTheory.Reformulated.B.SelectionLemmas.vw := rfl
example : @PublishedSelector.gramR = @UpperTheory.Reformulated.B.SelectionLemmas.gramR := rfl
example : @PublishedSelector.quotGram = @UpperTheory.Reformulated.B.SelectionLemmas.quotGram := rfl
example : @PublishedSelector.main = @UpperTheory.Reformulated.B.SelectionLemmas.main := rfl

open Lean Elab Command in
run_cmd
  let env ← getEnv
  let rec binders : Expr → List (Name × BinderInfo)
    | .forallE n _ body bi => (n.eraseMacroScopes, bi) :: binders body
    | _ => []
  let pairs := [
    (``PublishedSelector.aux1, ``UpperTheory.Reformulated.B.SelectionLemmas.aux1),
    (``PublishedSelector.aux2, ``UpperTheory.Reformulated.B.SelectionLemmas.aux2),
    (``PublishedSelector.aux3, ``UpperTheory.Reformulated.B.SelectionLemmas.aux3),
    (``PublishedSelector.hdual, ``UpperTheory.Reformulated.B.SelectionLemmas.hdual),
    (``PublishedSelector.dual, ``UpperTheory.Reformulated.B.SelectionLemmas.dual),
    (``PublishedSelector.aux6, ``UpperTheory.Reformulated.B.SelectionLemmas.aux6),
    (``PublishedSelector.aux7, ``UpperTheory.Reformulated.B.SelectionLemmas.aux7),
    (``PublishedSelector.aux8, ``UpperTheory.Reformulated.B.SelectionLemmas.aux8),
    (``PublishedSelector.hform, ``UpperTheory.Reformulated.B.SelectionLemmas.hform),
    (``PublishedSelector.laurent_T_neg_one_mul_T_one, ``UpperTheory.Reformulated.B.SelectionLemmas.laurent_T_neg_one_mul_T_one),
    (``PublishedSelector.aux11, ``UpperTheory.Reformulated.B.SelectionLemmas.aux11),
    (``PublishedSelector.aux12, ``UpperTheory.Reformulated.B.SelectionLemmas.aux12),
    (``PublishedSelector.locS, ``UpperTheory.Reformulated.B.SelectionLemmas.locS),
    (``PublishedSelector.hcompl, ``UpperTheory.Reformulated.B.SelectionLemmas.hcompl),
    (``PublishedSelector.loc, ``UpperTheory.Reformulated.B.SelectionLemmas.loc),
    (``PublishedSelector.IsLocBasis, ``UpperTheory.Reformulated.B.SelectionLemmas.IsLocBasis),
    (``PublishedSelector.complex_normed_instance_compat, ``UpperTheory.Reformulated.B.SelectionLemmas.complex_normed_instance_compat),
    (``PublishedSelector.padic_embedding_algebra_compat, ``UpperTheory.Reformulated.B.SelectionLemmas.padic_embedding_algebra_compat),
    (``PublishedSelector.matLat, ``UpperTheory.Reformulated.B.SelectionLemmas.matLat),
    (``PublishedSelector.vw, ``UpperTheory.Reformulated.B.SelectionLemmas.vw),
    (``PublishedSelector.gramR, ``UpperTheory.Reformulated.B.SelectionLemmas.gramR),
    (``PublishedSelector.quotGram, ``UpperTheory.Reformulated.B.SelectionLemmas.quotGram),
    (``PublishedSelector.main, ``UpperTheory.Reformulated.B.SelectionLemmas.main)]
  let mut mismatches : Nat := 0
  for (p, q) in pairs do
    let some a := env.find? p | throwError "original missing: {p}"
    let some b := env.find? q | throwError "replacement missing: {q}"
    unless a.levelParams == b.levelParams && binders a.type == binders b.type do
      mismatches := mismatches + 1
      logInfo m!"public parameters differ for {q}: {a.levelParams}, {repr (binders a.type)} vs {b.levelParams}, {repr (binders b.type)}"
  if mismatches > 0 then throwError "{mismatches} public parameter mismatches"
  logInfo m!"Matched public binder names, visibility and universes for {pairs.length} declarations"

#print axioms UpperTheory.Reformulated.B.SelectionLemmas.main
