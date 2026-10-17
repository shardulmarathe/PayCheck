"""``python -m visa`` prints the demo command."""

from __future__ import annotations


def main() -> None:
    print(
        "\n".join(
            [
                "Signed agent check (Visa Trusted Agent Protocol)",
                "  python -m visa.demo",
            ]
        )
    )


if __name__ == "__main__":
    main()
