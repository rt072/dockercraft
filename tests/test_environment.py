"""Tests for environment profile selection."""

import os

import pytest

from app.environment import load_environment


def test_selected_profile_loads_without_merging_selector_file(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("APP_ENV=TEST\nSHOULD_NOT_LOAD=selector-only\n")
    (tmp_path / ".env.test").write_text("PROFILE_SETTING=test-value\n")
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("SHOULD_NOT_LOAD", raising=False)
    monkeypatch.delenv("PROFILE_SETTING", raising=False)

    assert load_environment(tmp_path) == "TEST"
    assert os.environ["APP_ENV"] == "TEST"
    assert os.environ["PROFILE_SETTING"] == "test-value"
    assert "SHOULD_NOT_LOAD" not in os.environ


def test_process_environment_overrides_profile_values(tmp_path, monkeypatch):
    (tmp_path / ".env.prod").write_text("PROFILE_SETTING=from-file\n")
    monkeypatch.setenv("APP_ENV", "prod")
    monkeypatch.setenv("PROFILE_SETTING", "from-process")

    assert load_environment(tmp_path) == "PROD"
    assert os.environ["PROFILE_SETTING"] == "from-process"


def test_invalid_environment_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_ENV", "staging")

    with pytest.raises(RuntimeError, match="Invalid APP_ENV"):
        load_environment(tmp_path)


def test_missing_selected_profile_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_ENV", "TEST")

    with pytest.raises(RuntimeError, match="requires .env.test"):
        load_environment(tmp_path)


def test_unset_environment_keeps_legacy_dotenv_behavior(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("LEGACY_SETTING=from-dotenv\n")
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("LEGACY_SETTING", raising=False)

    assert load_environment(tmp_path) == "LEGACY"
    assert os.environ["LEGACY_SETTING"] == "from-dotenv"
