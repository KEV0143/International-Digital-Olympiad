import argparse
import re
import sys
from collections import Counter
from pathlib import Path

from utils.reporting.catalog import definitions
from utils.reporting.terminal import console
from utils.validation import require_assertions

require_assertions()

ROOT = Path(__file__).resolve().parents[2]
START, END = "<!-- SCENARIOS:START -->", "<!-- SCENARIOS:END -->"
PAGES = {"Calendars": "CAL", "Modals": "MOD", "Ads": "ADS", "Form Fields": "FF"}


def validate_coverage(source, cases):
    counts = {
        prefix: Counter(
            case_id.split("-")[1][0]
            for case_id in {case[0].split("[", 1)[0] for case in cases}
            if case_id.startswith(prefix + "-")
        )
        for prefix in PAGES.values()
    }
    for title, prefix in PAGES.items():
        row = re.search(
            rf"^\| \[{re.escape(title)}\]\([^)]*\) \| (\d+) \| (\d+) \| (\d+) \| (\d+) \|$",
            source,
            re.MULTILINE,
        )
        assert row, f"В README нет строки покрытия для {title}"
        actual = tuple(map(int, row.groups()))
        values = counts[prefix]
        expected = (values["P"], values["N"], values["S"], sum(values.values()))
        assert actual == expected, f"Покрытие {title} в README {actual}, в тестах {expected}"
    total = re.search(
        r"^\| \*\*Всего\*\* \| \*\*(\d+)\*\* \| \*\*(\d+)\*\* "
        r"\| \*\*(\d+)\*\* \| \*\*(\d+)\*\* \|$",
        source,
        re.MULTILINE,
    )
    assert total, "В README нет итоговой строки покрытия"
    actual = tuple(map(int, total.groups()))
    expected = tuple(sum(counts[prefix][kind] for prefix in PAGES.values()) for kind in "PNS")
    assert actual == (*expected, sum(expected)), (
        f"Итог покрытия в README {actual}, в тестах {expected}"
    )


def catalog():
    cases = [row for _, _, row in definitions(ROOT)]
    ids = [case[0] for case in cases]
    assert len(ids) == len(set(ids)), "Повторяющиеся ID"
    expected = {
        "CAL": {"P": 10, "N": 5},
        "MOD": {"P": 10, "N": 5},
        "ADS": {"P": 9, "N": 4},
        "FF": {"P": 7, "N": 2, "S": 1},
    }
    counts = {
        prefix: Counter(
            case_id.split("-")[1][0]
            for case_id in {case[0].split("[", 1)[0] for case in cases}
            if case_id.startswith(prefix + "-")
        )
        for prefix in expected
    }
    for prefix, expected_counts in expected.items():
        assert dict(counts[prefix]) == expected_counts, (prefix, counts[prefix])
    assert len(cases) == 55, f"Ожидались 55 вариантов сценариев, найдено {len(cases)}"
    return cases


def main():
    parser = argparse.ArgumentParser(description="Обновление и проверка каталога сценариев README")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    sections = []
    cases = catalog()
    for prefix, title in (
        ("CAL", "Calendars"),
        ("MOD", "Modals"),
        ("ADS", "Ads"),
        ("FF", "Form Fields"),
    ):
        sections.extend(
            [
                f"### {title}",
                "",
                "| ID | Сценарий | Шаги и данные | Ожидаемый результат |",
                "|---|---|---|---|",
            ]
        )
        for case in sorted(cases):
            if case[0].startswith(prefix + "-"):
                sections.append("| " + " | ".join(s.replace("|", "\\|") for s in case) + " |")
        sections.append("")
    path = ROOT / "README.md"
    source = path.read_text(encoding="utf-8")
    before, rest = source.split(START, 1)
    _, after = rest.split(END, 1)
    updated = before + START + "\n\n" + "\n".join(sections) + END + after
    if args.check:
        assert source == updated, "README устарел: python -m tools.documentation.generate_scenarios"
        validate_coverage(source, cases)
        console.write(
            f"Каталог | вариантов: {len(cases)}, квоты PDF и README согласованы", status="+"
        )
    else:
        path.write_text(updated, encoding="utf-8")
        console.write(f"README | вариантов: {len(cases)}", status="+")
    return 0


if __name__ == "__main__":
    sys.exit(main())
