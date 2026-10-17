"""`python -m gym` prints the commands other agents will call."""

from __future__ import annotations


def main() -> None:
    print(
        "\n".join(
            [
                "checkout-guard gym",
                "  python -m gym.dataset --check",
                "  python -m gym.testset --check",
                "  python -m gym.train --round 1 --n-train 1500 --n-dev 300",
                "  python -m gym.train --round 1 --n-train 1500 --n-dev 300 --sweep train/configs/sweep.example.yaml --submit",
                "  python -m gym.distill --round 1 --max-usd 50",
                "  python -m gym.render_specs --specs-dir DIR --out DIR --source attacker-round1",
                "  python -m gym.serve --port 8765",
            ]
        )
    )


if __name__ == "__main__":
    main()
