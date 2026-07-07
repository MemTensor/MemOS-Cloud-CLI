"""Main CLI application — the entrypoint for `memos`."""
from __future__ import annotations

# Force UTF-8 stdio before anything else touches sys.stdout/stderr.  The
# PyInstaller-frozen ``memos.exe`` on Simplified Chinese Windows otherwise
# binds stdio to CP936/GBK, corrupting CJK text (issue #15).  Importing this
# module has no effect when the streams are already UTF-8 (Linux/macOS or a
# console that opted in via ``PYTHONUTF8=1``).
#
# Why the call lives *here* even though ``__main__.py`` and the PyInstaller
# runtime hook also call it:
#   * ``pyproject.toml`` registers ``memos = memos_cli.main:app`` as the
#     console_scripts entry point, so ``pip install`` users run ``memos``
#     which imports this module *without* going through ``__main__.py``.
#   * Library users doing ``from memos_cli.main import app`` in their own
#     scripts likewise skip ``__main__.py``.
# The call is guarded by an idempotency flag in ``encoding_bootstrap`` so the
# repeated invocation from the other entry paths is a cheap no-op. The
# ``# noqa: E402`` on the following imports is intentional: this side-effect
# must run before ``typer``/``rich`` capture stdio references.
from memos_cli.encoding_bootstrap import ensure_utf8_stdio

ensure_utf8_stdio()

import click  # noqa: E402
import typer  # noqa: E402
from rich.console import Console  # noqa: E402
from typer.core import TyperGroup  # noqa: E402

from memos_cli import __version__  # noqa: E402
from memos_cli.completion import register_completion_compat
from memos_cli.commands.init import init_cmd, uninstall_cmd
from memos_cli.commands.config_cmd import config_app
from memos_cli.commands.memory import add, extract, feedback, rerank, search, chat, get, delete, origin
from memos_cli.commands.message import message, status
from memos_cli.commands.kb import kb_app
from memos_cli.state import set_runtime_options
console = Console()
err_console = Console(stderr=True)

register_completion_compat()


class CommandFirstTyperGroup(TyperGroup):
    """Typer group that shows commands before options in help output."""

    HELP_COMMAND_ORDER = [
        "init",
        "uninstall",
        "config",
        "add",
        "search",
        "get",
        "origin",
        "delete",
        "extract",
        "rerank",
        "feedback",
        "chat",
        "message",
        "status",
        "kb",
    ]

    def format_help(self, ctx: click.Context, formatter: click.HelpFormatter) -> None:
        self.format_usage(ctx, formatter)
        self.format_help_text(ctx, formatter)
        self.format_commands(ctx, formatter)
        self.format_options(ctx, formatter)
        self.format_epilog(ctx, formatter)

    def format_options(self, ctx: click.Context, formatter: click.HelpFormatter) -> None:
        opts = []
        for param in self.get_params(ctx):
            rv = param.get_help_record(ctx)
            if rv is not None:
                opts.append(rv)

        if opts:
            with formatter.section("Options"):
                formatter.write_dl(opts)

    def list_commands(self, ctx: click.Context) -> list[str]:
        commands = super().list_commands(ctx)
        order_index = {name: index for index, name in enumerate(self.HELP_COMMAND_ORDER)}
        return sorted(commands, key=lambda name: (order_index.get(name, len(order_index)), name))

app = typer.Typer(
    name="memos",
    cls=CommandFirstTyperGroup,
    help=f"◆ MemOS CLI v{__version__}\n\nThe Memory OS for AI Agents",
    no_args_is_help=True,
    rich_markup_mode=None,
    pretty_exceptions_enable=False,
    add_completion=False,
    subcommand_metavar="<command> [options]",
    options_metavar="",
)


@app.callback(invoke_without_command=True)
def main_callback(
    ctx: typer.Context,
    version: bool = typer.Option(False, "--version", help="Show version and exit."),
    api_key: str | None = typer.Option(
        None, "--api-key", help="Override API key from config."
    ),
    base_url: str | None = typer.Option(
        None, "--base-url", help="Override API base URL from config."
    ),
):
    """MemOS CLI - Universal memory interface for AI agents."""
    if version is True or (isinstance(version, str) and version.lower() == "true"):
        console.print(f"MemOS CLI v{__version__}")
        raise typer.Exit()

    set_runtime_options(
        api_key=api_key,
        base_url=base_url,
        framework=None,
    )

    if ctx.invoked_subcommand:
        _fire_telemetry(
            ctx.invoked_subcommand,
            extra={
                "override_api_key": bool(api_key),
                "override_base_url": bool(base_url),
            },
        )


def _fire_telemetry(command_name: str, extra: dict | None = None):
    """Fire telemetry event (non-blocking)."""
    try:
        from memos_cli.telemetry import capture_event
        props = {"command": command_name}
        if extra:
            props.update(extra)
        capture_event(f"cli.{command_name}", props)
    except Exception:
        pass


# Register subcommands
app.command("init", rich_help_panel="Setup")(init_cmd)
app.command("uninstall", rich_help_panel="Setup")(uninstall_cmd)
app.add_typer(config_app, rich_help_panel="Configuration")

# Memory commands (P0)
app.command(rich_help_panel="Memory Operations")(add)
app.command(rich_help_panel="Memory Operations")(extract)
app.command(rich_help_panel="Memory Operations")(feedback)
app.command(rich_help_panel="Memory Operations")(search)
app.command(rich_help_panel="Memory Operations")(get)
app.command(rich_help_panel="Memory Operations")(origin)
app.command(rich_help_panel="Memory Operations")(delete)

# Advanced commands (P1)
app.command(rich_help_panel="Advanced")(rerank)
app.command(rich_help_panel="Advanced")(chat)

# Message commands
app.command(rich_help_panel="Message")(message)
app.command(rich_help_panel="Message")(status)

# Knowledge Base sub-app
app.add_typer(kb_app, rich_help_panel="Knowledge Base")



if __name__ == "__main__":
    app()
