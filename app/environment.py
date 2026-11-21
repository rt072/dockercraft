"""Load the selected application environment profile."""

import os
from pathlib import Path

from dotenv import dotenv_values, load_dotenv

SUPPORTED_ENVIRONMENTS = {"TEST", "PROD"}
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def load_environment(project_root: Path | None = None) -> str:
    """Load a selected profile, or the legacy single .env when no profile is set.

    In profile mode, `.env` is only used to discover APP_ENV; settings are loaded
    exclusively from `.env.test` or `.env.prod`. Variables already supplied by
    the process environment take precedence over values in the profile file.
    """
    root = Path(project_root) if project_root is not None else PROJECT_ROOT
    selector_file = root / ".env"

    selected = os.environ.get("APP_ENV", "").strip()
    if not selected:
        selected = str(dotenv_values(selector_file).get("APP_ENV") or "").strip()

    if not selected:
        load_dotenv(selector_file, override=False)
        return "LEGACY"

    environment = selected.upper()
    if environment not in SUPPORTED_ENVIRONMENTS:
        allowed = ", ".join(sorted(SUPPORTED_ENVIRONMENTS))
        raise RuntimeError(f"Invalid APP_ENV '{selected}'. Expected one of: {allowed}.")

    profile_file = root / f".env.{environment.lower()}"
    if not profile_file.is_file():
        raise RuntimeError(
            f"APP_ENV={environment} requires {profile_file.name}; "
            "create the selected profile file before starting Dockercraft."
        )

    # Set the selected mode first so a profile file cannot change the selector.
    os.environ["APP_ENV"] = environment
    load_dotenv(profile_file, override=False)
    return environment


APP_ENV = load_environment()
