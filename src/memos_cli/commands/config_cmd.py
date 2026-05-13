"""Configuration commands for MemOS CLI."""
from __future__ import annotations

import typer
from rich.console import Console

from memos_cli.config import load_config, save_config
from memos_cli.telemetry import build_source_identifier, detect_framework

console = Console()

config_app = typer.Typer(name="config", help="Manage MemOS configuration.")


@config_app.command("show")
def config_show():
    """Show current configuration."""
    config = load_config()
    framework = config.defaults.framework or detect_framework()
    source = build_source_identifier(framework)
    
    console.print("[bold blue]Current Configuration:[/]\n")
    console.print(f"  API Key: {config.platform.api_key[:8]}..." if config.platform.api_key else "  API Key: [dim]Not set[/]")
    console.print(f"  Base URL: {config.platform.base_url}")
    console.print(f"  Source: {source}")
    console.print(f"  Framework: {framework}" if framework else "  Framework: [dim]Not detected[/]")
    
    if config.defaults.user_id or config.defaults.agent_id:
        console.print("\n[bold]Defaults:[/]")
        if config.defaults.user_id:
            console.print(f"  User ID: {config.defaults.user_id}")
        if config.defaults.conversation_id:
            console.print(f"  Conversation ID: {config.defaults.conversation_id}")
        if config.defaults.agent_id:
            console.print(f"  Agent ID: {config.defaults.agent_id}")
        if config.defaults.app_id:
            console.print(f"  App ID: {config.defaults.app_id}")
        if config.defaults.run_id:
            console.print(f"  Run ID: {config.defaults.run_id}")


@config_app.command("get")
def config_get(key: str = typer.Argument(..., help="Configuration key to get")):
    """Get a specific configuration value."""
    config = load_config()
    
    keys = key.split(".")
    value = config
    
    try:
        for k in keys:
            value = getattr(value, k)
        
        console.print(f"{key} = {value}")
    except AttributeError:
        console.print(f"[red]Error:[/] Invalid configuration key: {key}")
        raise typer.Exit(1)


@config_app.command("set")
def config_set(
    key: str = typer.Argument(..., help="Configuration key to set"),
    value: str = typer.Argument(..., help="Value to set"),
):
    """Set a specific configuration value."""
    config = load_config()
    
    keys = key.split(".")
    
    try:
        obj = config
        for k in keys[:-1]:
            obj = getattr(obj, k)
        
        setattr(obj, keys[-1], value)
        save_config(config)
        
        console.print(f"[green]✓[/] Set {key} = {value}")
    except AttributeError:
        console.print(f"[red]Error:[/] Invalid configuration key: {key}")
        raise typer.Exit(1)
