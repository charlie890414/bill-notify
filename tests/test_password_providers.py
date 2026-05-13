"""Tests for PDF password provider persistence."""

import yaml

from bill_notify.password_providers import (
    CompositePasswordProvider,
    InteractivePasswordProvider,
    YamlPasswordProvider,
)


def test_composite_saves_verified_password_to_yaml(tmp_path):
    password_file = tmp_path / "pdf_passwords.yaml"
    provider = CompositePasswordProvider(
        yaml_provider=YamlPasswordProvider(),
        interactive_provider=InteractivePasswordProvider(save_path=password_file),
    )

    provider.save_password("billing@example.com", "secret")

    assert yaml.safe_load(password_file.read_text(encoding="utf-8")) == {
        "billing@example.com": "secret"
    }
    assert provider.get_password("billing@example.com") == "secret"


def test_composite_does_not_save_without_interactive_save_path(tmp_path):
    yaml_provider = YamlPasswordProvider()
    provider = CompositePasswordProvider(
        yaml_provider=yaml_provider,
        interactive_provider=InteractivePasswordProvider(),
    )

    provider.save_password("billing@example.com", "secret")

    assert yaml_provider.get_password("billing@example.com") is None
