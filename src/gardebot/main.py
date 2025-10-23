"""Main Description."""

from gardebot.common.logging_configuration import get_logger

LOGGER = get_logger(__name__)


def main() -> None:
    """Main entry point for the application."""
    LOGGER.info("Executing entrypoint.")


def cli() -> None:
    """Cli-Entrypoint."""
    main()


if __name__ == "__main__":
    cli()
