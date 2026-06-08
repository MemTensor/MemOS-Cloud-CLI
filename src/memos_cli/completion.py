"""Shell completion compatibility helpers for MemOS CLI."""
from __future__ import annotations

import os
import shlex

from click.parser import split_arg_string
from click.shell_completion import CompletionItem, ZshComplete, add_completion_class


class TyperCompatibleZshComplete(ZshComplete):
    """Accept Typer-style zsh env vars when an older script is already installed."""

    name = "zsh"

    def get_completion_args(self) -> tuple[list[str], str]:
        typer_args = os.getenv("_TYPER_COMPLETE_ARGS")
        if typer_args is not None:
            cwords = split_arg_string(typer_args)
            args = cwords[1:-1] if len(cwords) > 1 else []
            incomplete = cwords[-1] if cwords else ""
            return args, incomplete
        return super().get_completion_args()

    def complete(self) -> str:
        """Return shell code for old Typer zsh scripts, default output otherwise."""
        if os.getenv("_TYPER_COMPLETE_ARGS") is None:
            return super().complete()

        args, incomplete = self.get_completion_args()
        completions = self.get_completions(args, incomplete)
        return self._render_typer_zsh_response(completions)

    def _render_typer_zsh_response(self, completions: list[CompletionItem]) -> str:
        plain_values = [item.value for item in completions if item.type == "plain"]
        dir_values = [item.value for item in completions if item.type == "dir"]
        file_values = [item.value for item in completions if item.type == "file"]

        commands: list[str] = []
        if plain_values:
            quoted = " ".join(shlex.quote(value) for value in plain_values)
            commands.append(f"compadd -- {quoted}")
        if dir_values:
            quoted = " ".join(shlex.quote(value) for value in dir_values)
            commands.append(f"compadd -S / -- {quoted}")
        if file_values:
            quoted = " ".join(shlex.quote(value) for value in file_values)
            commands.append(f"compadd -- {quoted}")
        return "\n".join(commands)


def register_completion_compat() -> None:
    """Register shell completion compatibility overrides."""
    add_completion_class(TyperCompatibleZshComplete, name="zsh")
