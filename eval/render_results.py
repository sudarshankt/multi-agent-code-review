from __future__ import annotations

from pathlib import Path

from eval.report.render_results import write_html_report


if __name__ == "__main__":
    output = write_html_report(Path("results/final_report.json"))
    print(output)
