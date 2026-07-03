"""
One-off script to stop local runs and the scheduled GitHub Actions run
from repeatedly colliding over reports/<today>.md.

Root cause: both your local `python main.py run` and the daily CI job
write to the same filename (reports/YYYY-MM-DD.md), and until now that
file wasn't gitignored - so any time you ran the pipeline locally on a
day CI had already run, `git add -A` would try to commit a conflicting
version of that file.

Fix: gitignore future daily reports (reports/*.md) so local runs never
get added to git automatically, and make the CI workflow force-add its
own report despite the gitignore rule (`git add -f`), so scheduled runs
still get committed as before. This only affects *future* dates - today's
already-tracked report stays tracked (see note printed at the end).

Usage: put this file in the ROOT of your startup-scout-ai_repo folder
(next to main.py) and run:

    python apply_report_conflict_fix.py

Then:

    git add -A
    git commit -m "Gitignore daily reports locally; CI force-adds its own to avoid recurring merge conflicts"
    git push
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main():
    gitignore_path = ROOT / ".gitignore"
    content = gitignore_path.read_text(encoding="utf-8")
    if "reports/*.md" in content:
        print(f"{gitignore_path} already has the reports/*.md rule, skipping")
    else:
        content = content.rstrip("\n") + "\nreports/*.md\n"
        gitignore_path.write_text(content, encoding="utf-8")
        print(f"Updated {gitignore_path}")

    workflow_path = ROOT / ".github" / "workflows" / "daily.yml"
    content = workflow_path.read_text(encoding="utf-8")
    old = "          git add reports/ data/"
    new = "          git add -f reports/ data/"
    if new in content:
        print(f"{workflow_path} already force-adds reports/data, skipping")
    elif old in content:
        workflow_path.write_text(content.replace(old, new), encoding="utf-8")
        print(f"Updated {workflow_path}")
    else:
        print(f"WARNING: expected line not found in {workflow_path} - check manually")

    print(
        "\nDone.\n"
        "Note: reports/2026-07-03.md is already tracked in git from earlier "
        "commits, so gitignore won't hide further local changes to that "
        "specific file today. Every date from now on is covered. If you "
        "want today's file untracked too, run:\n"
        "    git rm --cached reports/2026-07-03.md\n"
        "(this only removes it from git tracking, the file stays on disk)."
    )


if __name__ == "__main__":
    main()

# END OF FILE
