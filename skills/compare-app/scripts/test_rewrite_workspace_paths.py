"""Unit tests for compare-app's rewrite_workspace_paths.

Run: python3 skills/compare-app/scripts/test_rewrite_workspace_paths.py

These cover the corner cases where the original exact-prefix rewrite leaked raw
absolute paths into the evaluator input (chat-time path != eval-time path), and
the over-match cases a naive structural fallback introduced (Markdown links,
neutral path containing the example slug).
"""
import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "run_compare_app", Path(__file__).with_name("run_compare_app.py")
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
rewrite = _mod.rewrite_workspace_paths


def check(name, got, want):
    assert got == want, f"\n[{name}]\n  got:  {got}\n  want: {want}"
    print(f"ok  {name}")


# A neutral path that itself contains the example slug -- run dirs are
# `.../compare-app/<example>/.../evaluator-workspaces/agent-x`.
NEUTRAL = Path(
    "/U/dev/working/compare-app/attention-tomography/20260609/evaluator-workspaces/agent-a"
)
N = NEUTRAL.as_posix()


def test_exact_prefix():
    src = Path("/U/app/data/example-papers/attention-tomography")
    check("exact-prefix",
          rewrite(f"see {src}/paper/main.tex:12 ok", [src], NEUTRAL),
          f"see {N}/paper/main.tex:12 ok")


def test_cross_base_leak():
    # eval-time staging root differs in base dir from what the transcript recorded
    eval_root = Path("/U/app/data/example-papers/attention-tomography")
    txt = "ref /OTHER/machine/data/example-papers/attention-tomography/povm.py:3 here"
    check("cross-base-leak",
          rewrite(txt, [eval_root], NEUTRAL),
          f"ref {N}/povm.py:3 here")


def test_archive_renamed_staging():
    # staging passed as a renamed archive snapshot; transcript still says publication-staging
    staging = Path("/U/app/working/staging-archive/axion/20260609-pr29-0004883")
    nb = Path("/run/ews/agent-b")
    txt = "see `/X/app-pr11-compare-app/data/example-papers/axion/publication-staging/code/CX.m`"
    check("archive-renamed-staging",
          rewrite(txt, [staging], nb),
          "see `/run/ews/agent-b/code/CX.m`")


def test_markdown_links_no_duplication():
    # two link tokens on one line must not let a lazy match cross `](` and
    # duplicate the neutral root.
    src = Path("/U/app/data/example-papers/attention-tomography")
    B = "/U/app/data/example-papers/attention-tomography"
    txt = f"[main.tex:39]({B}/paper/main.tex:39) and [main.tex:77]({B}/paper/main.tex:77)."
    out = rewrite(txt, [src], NEUTRAL)
    assert "evaluator-workspaces/agent-a/20260609/evaluator-workspaces/agent-a" not in out, out
    check("markdown-links-no-dup",
          out,
          f"[main.tex:39]({N}/paper/main.tex:39) and [main.tex:77]({N}/paper/main.tex:77).")


def test_prose_slash_not_overmatched():
    # bare word and an inline fraction must not be rewritten
    src = Path("/U/app/data/example-papers/attention-tomography")
    txt = "the publication-staging tree, with N/2 samples, stays as prose"
    check("prose-not-overmatched", rewrite(txt, [src], NEUTRAL), txt)


def test_general_source_anchor():
    src = Path("/U/app/data/example-papers/attention-tomography")
    na = Path("/run/ews/agent-a")
    txt = "ran `/Y/app/data/example-papers/attention-tomography/code/run.py`"
    check("general-source-anchor",
          rewrite(txt, [src], na),
          "ran `/run/ews/agent-a/code/run.py`")


if __name__ == "__main__":
    for fn in [
        test_exact_prefix,
        test_cross_base_leak,
        test_archive_renamed_staging,
        test_markdown_links_no_duplication,
        test_prose_slash_not_overmatched,
        test_general_source_anchor,
    ]:
        fn()
    print("\nall rewrite_workspace_paths tests passed")
