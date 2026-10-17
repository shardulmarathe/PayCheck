"""`python -m gym` prints the commands other agents will call."""

from __future__ import annotations


def main() -> None:
    print(
        "\n".join(
            [
                "checkout-guard gym",
                "  python -m gym.dataset --check",
                "  python -m gym.testset --check",
                "  python -m gym.train --n 50 --out data/trainset",
                "  python -m gym.render_specs --specs-dir DIR --out DIR --source attacker-round1",
                "  python -m gym.serve --port 8765",
            ]
        )
    )


if __name__ == "__main__":
    main()
