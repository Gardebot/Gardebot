"""Main Description."""

import logging

LOGGER = logging.getLogger(__name__)


def main() -> None:
    """Main entry point for the application."""
    LOGGER.info("Executing entrypoint.")


def cli() -> None:
    """Cli-Entrypoint."""
    main()


if __name__ == "__main__":
    cli()
