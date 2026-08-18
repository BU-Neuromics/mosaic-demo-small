"""Sections 7.3/7.4: the invariants that keep the loop honest.

These are the checks that would let a silently-wrong harness pass everything else: a refiner that
can see the holdout, a patch that cannot be undone, a prompt that varies between renders, or a
context that has quietly become an answer key.
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from exon.context.template import (
    BlockKind,
    ContextArtifact,
    ContextBlock,
    ContextPatch,
    DecodeParams,
    TemplateError,
    memorization_findings,
)
from exon.harness.cases import load_suite
from exon.harness.cli import _compare_reports, _fingerprint_path, _model_slug
from exon.harness.outcome import (
    CONTEXT_ADDRESSABLE,
    ENVIRONMENT_CLASSES,
    CaseResult,
    FailureClass,
    SampleResult,
    SuiteReport,
)
from exon.harness.probe import OutputProtocol
from exon.harness.refine import RefineError, check_patch
from exon.harness.triage import TriageError, build_bundle
from exon.schema import fetch_hippo_schema, load_capability_manifest

ENDPOINT = "http://localhost:8080/graphql"
HS = fetch_hippo_schema(ENDPOINT)
M = load_capability_manifest("evals/schema/capabilities.json")
CASES = load_suite()
failures = []


def check(name, cond, extra=""):
    print(("PASS  " if cond else "FAIL  ") + name + (f"   [{extra}]" if extra and not cond else ""))
    if not cond:
        failures.append(name)


def base_artifact(**kw):
    return ContextArtifact(
        version=kw.pop("version", 0),
        fingerprint_id=kw.pop("fingerprint_id", "fp123"),
        system_prompt=kw.pop("system_prompt", "You are Exon."),
        grounding_body=kw.pop(
            "grounding_body", "{{schema_slots}}\n{{relationship_types}}\n{{limitations}}"
        ),
        protocol=OutputProtocol.TOOL_CALL,
        decode_params=DecodeParams(),
        **kw,
    )


def block(bid, content="text", kind=BlockKind.CONSTRAINT, **kw):
    return ContextBlock(id=bid, kind=kind, content=content, rationale="because", **kw)


# ---- 7.4 render determinism --------------------------------------------------------------
art = base_artifact(blocks=[block("b2", "second", order=2), block("b1", "first", order=1)])
a1 = art.render(HS, M)
a2 = art.render(HS, M)
check("render is byte-identical across calls", a1 == a2)
check("no placeholder survives rendering", "{{" not in a1[1])
check("blocks render in stable order", a1[1].index("first") < a1[1].index("second"))

# ---- 7.4 patch algebra: apply then invert restores the prior artifact ---------------------
before = base_artifact(blocks=[block("keep"), block("drop")])
patch = ContextPatch(
    changelog="c", hypothesis="h",
    add_blocks=[block("new", "brand new")],
    remove_block_ids=["drop"],
)
after = before.apply_patch(patch)
check("apply: version bumps and parent recorded",
      after.version == 1 and after.parent_version == 0)
check("apply: block added", any(b.id == "new" for b in after.blocks))
check("apply: block removed", not any(b.id == "drop" for b in after.blocks))

inverse = ContextPatch(
    changelog="undo", hypothesis="h",
    add_blocks=[b for b in before.blocks if b.id == "drop"],
    remove_block_ids=["new"],
)
restored = after.apply_patch(inverse)
check("invert restores the same block set",
      {b.id for b in restored.blocks} == {b.id for b in before.blocks},
      f"{sorted(b.id for b in restored.blocks)}")
check("invert restores byte-identical render",
      restored.render(HS, M) == before.render(HS, M))

# ---- artifacts are append-only ----------------------------------------------------------
import tempfile

tmp = Path(tempfile.mkdtemp())
before.save(tmp)
try:
    before.save(tmp)
    check("re-saving the same version is refused", False)
except TemplateError:
    check("re-saving the same version is refused", True)
check("round-trips through disk",
      ContextArtifact.load(tmp / "v000.json").render(HS, M) == before.render(HS, M))

# ---- fingerprint binding ----------------------------------------------------------------
try:
    before.assert_fingerprint("a-different-model")
    check("context refuses a mismatched fingerprint", False)
except TemplateError:
    check("context refuses a mismatched fingerprint", True)

# ---- placeholder + size guards ----------------------------------------------------------
try:
    base_artifact(grounding_body="{{schema_slots}} only").validate()
    check("dropping a placeholder is rejected", False)
except TemplateError:
    check("dropping a placeholder is rejected", True)

try:
    base_artifact(blocks=[block("huge", "x" * 50000)]).validate(max_chars=12000)
    check("oversize context is rejected", False)
except TemplateError:
    check("oversize context is rejected", True)

# ---- memorization lint ------------------------------------------------------------------
clean = base_artifact(blocks=[block("gen", "Always include every stated constraint as a filter.")])
check("a general instruction passes the lint",
      not memorization_findings(clean, [c.id for c in CASES], [c.instruction for c in CASES]))

with_id = base_artifact(blocks=[block("cheat", "For q09 use the four brain regions.")])
found = memorization_findings(with_id, [c.id for c in CASES], [c.instruction for c in CASES])
check("naming a case id is caught", any("q09" in f for f in found), str(found))

q35 = next(c for c in CASES if c.id == "q35")
quoted = base_artifact(blocks=[block("quote", q35.instruction)])
found = memorization_findings(quoted, [c.id for c in CASES], [c.instruction for c in CASES])
check("quoting a test question verbatim is caught", bool(found), str(found)[:120])

# ---- refine bounds ----------------------------------------------------------------------
too_many = ContextPatch(
    changelog="c", hypothesis="h",
    add_blocks=[block(f"b{i}", f"c{i}") for i in range(4)],
)
cand = base_artifact().apply_patch(too_many)
try:
    check_patch(too_many, cand, CASES)
    check("patch over the block-change cap is rejected", False)
except RefineError:
    check("patch over the block-change cap is rejected", True)

ok_patch = ContextPatch(changelog="c", hypothesis="h", add_blocks=[block("one", "fine")])
try:
    check_patch(ok_patch, base_artifact().apply_patch(ok_patch), CASES)
    check("a bounded, general patch is accepted", True)
except RefineError as e:
    check("a bounded, general patch is accepted", False, str(e)[:90])

answer_key = ContextPatch(
    changelog="c", hypothesis="h",
    add_blocks=[block("ak", "For q09 always filter brain_region to the four regions.")],
)
try:
    check_patch(answer_key, base_artifact().apply_patch(answer_key), CASES)
    check("answer-key patch is rejected", False)
except RefineError:
    check("answer-key patch is rejected", True)

# ---- 7.3 holdout isolation --------------------------------------------------------------
def mk_report(splits):
    results = []
    for cid, split in splits:
        results.append(CaseResult(
            case_id=cid, split=split, capability="filter",
            samples=[SampleResult(case_id=cid, sample_index=0,
                                  outcome=FailureClass.PLAN_UNFAITHFUL,
                                  detail=f"detail for {cid}")]))
    return SuiteReport(context_version=0, fingerprint_id="fp123", model="m",
                       protocol="tool_call", results=results)

try:
    build_bundle(mk_report([("q01", "train"), ("q03", "holdout")]), CASES, base_artifact())
    check("build_bundle refuses holdout grades", False)
except TriageError:
    check("build_bundle refuses holdout grades", True)

bundle = build_bundle(mk_report([("q01", "train")]), CASES, base_artifact())
md = bundle.to_markdown()
holdout_ids = [c.id for c in CASES if c.split == "holdout"]
leaked = [i for i in holdout_ids if i in md]
check("no holdout case id appears in the serialized bundle", not leaked, str(leaked))
holdout_text = [c.instruction for c in CASES if c.split == "holdout"]
leaked_text = [t[:40] for t in holdout_text if t[:40] in md]
check("no holdout question text appears in the bundle", not leaked_text, str(leaked_text))

# ---- environment failures are withheld ---------------------------------------------------
env_report = SuiteReport(
    context_version=0, fingerprint_id="fp123", model="m", protocol="tool_call",
    results=[CaseResult(case_id="q01", split="train", capability="filter", samples=[
        SampleResult(case_id="q01", sample_index=0, outcome=FailureClass.TRUNCATED,
                     detail="num_ctx exhausted"),
        SampleResult(case_id="q01", sample_index=1, outcome=FailureClass.PROVIDER_ERROR,
                     detail="auth"),
    ])])
b = build_bundle(env_report, CASES, base_artifact())
check("a bundle of only environment failures is empty", b.is_empty())
check("...but they are reported as warnings", len(b.environment_warnings) == 2)
check("TRUNCATED is not context-addressable", FailureClass.TRUNCATED not in CONTEXT_ADDRESSABLE)
check("TRUNCATED is an environment class", FailureClass.TRUNCATED in ENVIRONMENT_CLASSES)
check("PLAN_UNFAITHFUL IS context-addressable",
      FailureClass.PLAN_UNFAITHFUL in CONTEXT_ADDRESSABLE)

# ---- "already tried" attribution --------------------------------------------------------
art_with_block = base_artifact(blocks=[
    block("tried-this", "Include every constraint.",
          addresses_failures=["plan_unfaithful"], introduced_in_iteration=1)])
b = build_bundle(mk_report([("q01", "train")]), CASES, art_with_block)
check("bundle names the block that should have prevented the failure",
      "tried-this" in b.to_markdown())

# ---- fingerprint path is a collision-free function of the exact model string ------------
haiku = "bedrock/global.anthropic.claude-haiku-4-5-20251001-v1:0"
sonnet = "bedrock/global.anthropic.claude-sonnet-5"
haiku_v2 = "bedrock/global.anthropic.claude-haiku-4-5-20260101-v1:0"
check("two different models never collide on one fingerprint path",
      _fingerprint_path(haiku) != _fingerprint_path(sonnet))
check("a version-suffix-only change produces a distinct path, not a collision",
      _fingerprint_path(haiku) != _fingerprint_path(haiku_v2))
check("the same model string always resolves to the same path (idempotent)",
      _fingerprint_path(haiku) == _fingerprint_path(haiku))
check("the slug is a pure function of the string, not a lookup (unknown model still resolves)",
      _model_slug("some/brand-new-model-nobody-added-yet") != "")


# ---- report --compare reads existing reports, spends no new tokens ----------------------
def mk_suite_report(model, samples_per_case, n_train=2, n_holdout=1, protocol="tool_call"):
    results = []
    for i in range(n_train):
        results.append(CaseResult(case_id=f"t{i}", split="train", capability="filter", samples=[
            SampleResult(case_id=f"t{i}", sample_index=k, outcome=FailureClass.PASS)
            for k in range(samples_per_case)
        ]))
    for i in range(n_holdout):
        results.append(CaseResult(case_id=f"h{i}", split="holdout", capability="filter", samples=[
            SampleResult(case_id=f"h{i}", sample_index=k, outcome=FailureClass.PASS)
            for k in range(samples_per_case)
        ]))
    return SuiteReport(
        context_version=0, fingerprint_id=f"fp-{model}", model=model, protocol=protocol,
        results=results,
    )


def write_report(tmpdir, name, report):
    p = Path(tmpdir) / name
    p.write_text(json.dumps(report.to_dict(), default=str))
    return str(p)


with tempfile.TemporaryDirectory() as tmp:
    path_a = write_report(tmp, "a.json", mk_suite_report(haiku, samples_per_case=3))
    path_b = write_report(tmp, "b.json", mk_suite_report(sonnet, samples_per_case=3))
    path_c = write_report(tmp, "c.json", mk_suite_report(sonnet, samples_per_case=1))
    path_d = write_report(
        tmp, "d.json", mk_suite_report(sonnet, samples_per_case=3, protocol="json_schema")
    )

    out = _compare_reports([path_a, path_b])
    check("compare output names both models", haiku in out and sonnet in out)
    check("matched sampling produces no mismatch warning", "WARNING" not in out)

    run_dir = Path(tmp) / "run_dir"
    run_dir.mkdir()
    (run_dir / "report.json").write_text(
        json.dumps(mk_suite_report(haiku, samples_per_case=3).to_dict(), default=str)
    )
    out_dir = _compare_reports([str(run_dir), path_b])
    check("a `run` output dir resolves via its own <dir>/report.json", haiku in out_dir)

    out_mismatch = _compare_reports([path_a, path_c])
    check("a samples-per-case mismatch is surfaced as an explicit warning",
          "WARNING" in out_mismatch and "samples-per-case" in out_mismatch)

    out_protocol = _compare_reports([path_a, path_d])
    check("differing protocols trigger the model-AND-protocol-jointly caveat",
          "model-AND-protocol" in out_protocol)

    try:
        _compare_reports([path_a])
        check("comparing fewer than 2 paths raises", False)
    except ValueError:
        check("comparing fewer than 2 paths raises", True)

    missing_dir = Path(tmp) / "empty_loop_run"
    missing_dir.mkdir()
    try:
        _compare_reports([str(missing_dir), path_a])
        check("a directory with no report.json raises rather than guessing", False)
    except FileNotFoundError:
        check("a directory with no report.json raises rather than guessing", True)

print()
if failures:
    print(f"{len(failures)} FAILED: {failures}")
    sys.exit(1)
print("all harness invariant checks pass")
