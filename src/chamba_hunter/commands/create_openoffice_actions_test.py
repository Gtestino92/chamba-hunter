import argparse
from pathlib import Path

from chamba_hunter.services.openoffice_shortlist_actions import (
    create_openoffice_actions_test,
)


DEFAULT_OUTPUT = Path(
    "output/chamba-openoffice-actions-test.xlsx"
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Create a non-destructive XLSX "
            "that verifies the installed "
            "OpenOffice ChambaHunter macro."
        )
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
    )

    args = parser.parse_args()

    create_openoffice_actions_test(
        args.output
    )

    print(
        "OpenOffice action test created:"
    )
    print(
        args.output.resolve()
    )
    print(
        "Open it in Calc and click PING."
    )


if __name__ == "__main__":
    main()
