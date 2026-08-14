"""`python -m sage` / the `sage` console script."""

import uvicorn

from sage.config import get_settings


def main() -> None:
    """Serve the app using the configured host and port."""
    settings = get_settings()
    uvicorn.run(
        "sage.main:app",
        host=settings.host,
        port=settings.port,
        log_config=None,
    )


if __name__ == "__main__":
    main()
