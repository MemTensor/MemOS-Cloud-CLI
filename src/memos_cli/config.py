"""Configuration management for MemOS CLI."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
import yaml

DEFAULT_USER_ID = "memos-cli"
DEFAULT_CONVERSATION_ID = "memos-cli-default"


class PlatformConfig(BaseModel):
    """Platform API configuration."""
    api_key: str = ""
    base_url: str = "https://memos.memtensor.cn/api/openmem/v1"


class DefaultsConfig(BaseModel):
    """Default entity IDs."""
    user_id: str | None = DEFAULT_USER_ID
    conversation_id: str | None = DEFAULT_CONVERSATION_ID
    framework: str | None = None
    agent_id: str | None = None
    app_id: str | None = None
    run_id: str | None = None


class MemOSConfig(BaseModel):
    """Main configuration model."""
    platform: PlatformConfig = Field(default_factory=PlatformConfig)
    defaults: DefaultsConfig = Field(default_factory=DefaultsConfig)

    model_config = ConfigDict(validate_assignment=True)


CONFIG_DIR = Path.home() / ".memos"
CONFIG_FILE = CONFIG_DIR / "config.yaml"


def _string_or_none(value) -> str | None:
    """Normalize config scalar values while preserving missing/null values."""
    if value is None:
        return None
    return str(value)


def _load_file_config(data) -> MemOSConfig:
    """Load a config dict without letting one invalid value discard the whole file."""
    config = MemOSConfig()
    if not isinstance(data, dict):
        return config

    platform_data = data.get("platform")
    if isinstance(platform_data, dict):
        api_key = _string_or_none(platform_data.get("api_key"))
        if api_key is not None:
            config.platform.api_key = api_key

        base_url = _string_or_none(platform_data.get("base_url"))
        if base_url is not None:
            config.platform.base_url = base_url

    defaults_data = data.get("defaults")
    if isinstance(defaults_data, dict):
        for key in DefaultsConfig.model_fields:
            if key in defaults_data:
                setattr(config.defaults, key, _string_or_none(defaults_data.get(key)))

    return config


def load_config() -> MemOSConfig:
    """Load configuration from file and environment variables."""
    config = MemOSConfig()
    
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                if data:
                    config = _load_file_config(data)
        except UnicodeDecodeError:
            # Config file was written by an older build using the system
            # codepage (e.g. GBK on Chinese Windows). Fall back to a lossy
            # re-read so the user does not lose all saved settings — better
            # to surface a warning than silently discard the whole file.
            try:
                with open(
                    CONFIG_FILE, "r", encoding="utf-8", errors="replace"
                ) as f:
                    data = yaml.safe_load(f)
                # Always fire the "not valid UTF-8" warning once the fallback
                # read itself succeeds, even if YAML parsing or config
                # loading below raises — the file *was* decoded, just not
                # cleanly. Emitting the correct diagnostic here keeps the
                # generic message below reserved for actual I/O failures.
                print(
                    f"warning: {CONFIG_FILE} is not valid UTF-8; "
                    "loaded with lossy decoding. Re-save to migrate to UTF-8.",
                    file=sys.stderr,
                )
                if data:
                    config = _load_file_config(data)
            except Exception:
                print(
                    f"warning: could not decode {CONFIG_FILE}; "
                    "using defaults for this session.",
                    file=sys.stderr,
                )
        except Exception:
            pass
    
    # Environment variables override config file
    if api_key := os.getenv("MEMOS_API_KEY"):
        config.platform.api_key = api_key
    if base_url := os.getenv("MEMOS_BASE_URL"):
        config.platform.base_url = base_url
    if user_id := os.getenv("MEMOS_USER_ID"):
        config.defaults.user_id = user_id
    if conversation_id := os.getenv("MEMOS_CONVERSATION_ID"):
        config.defaults.conversation_id = conversation_id
    if framework := os.getenv("MEMOS_FRAMEWORK"):
        config.defaults.framework = framework
    if agent_id := os.getenv("MEMOS_AGENT_ID"):
        config.defaults.agent_id = agent_id
    if app_id := os.getenv("MEMOS_APP_ID"):
        config.defaults.app_id = app_id
    if run_id := os.getenv("MEMOS_RUN_ID"):
        config.defaults.run_id = run_id
    
    return config


def save_config(config: MemOSConfig) -> None:
    """Save configuration to file."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        yaml.dump(config.model_dump(), f, default_flow_style=False, allow_unicode=True)
    
    # Set secure permissions
    CONFIG_FILE.chmod(0o600)


def get_config_path() -> Path:
    """Get configuration file path."""
    return CONFIG_FILE
