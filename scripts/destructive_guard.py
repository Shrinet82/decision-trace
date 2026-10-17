"""Confirmation guard for scripts that delete every graph on the FalkorDB instance.

seed.py and restore_snapshot.py restore call reset(delete_all_graphs=True), which wipes the whole
instance, production included. They must pass this guard first:

  1. the --i-know-this-deletes-all-graphs flag,
  2. refusal when FALKORDB_GRAPH_NAME (or the target) is the production graph, unless
     --force-production is also given,
  3. the graph name typed back at a prompt.

Only then does it set DECISION_TRACE_ALLOW_DESTRUCTIVE_RESET=1 for this process, which
app.brain.memory.reset() requires before deleting all graphs or the production graph.
"""

import os
import sys
from collections.abc import Callable, Mapping

PRODUCTION_GRAPH = "c87aa0cf-1c09-5296-8518-a3e8b9a1e744"
CONFIRM_FLAG = "--i-know-this-deletes-all-graphs"
FORCE_PRODUCTION_FLAG = "--force-production"
ALLOW_ENV = "DECISION_TRACE_ALLOW_DESTRUCTIVE_RESET"


class GuardRefused(SystemExit):
    """Raised (exit code 2) when the guard does not allow the destructive run."""

    def __init__(self, message: str) -> None:
        super().__init__(2)
        self.message = message

    def __str__(self) -> str:
        return self.message


def confirm_delete_all_graphs(
    target: str,
    argv: list[str],
    *,
    env: Mapping[str, str] | None = None,
    read: Callable[[str], str] = input,
    action: str = "This run",
) -> None:
    """Return normally only when the run is confirmed; otherwise raise GuardRefused."""
    env = os.environ if env is None else env
    configured = env.get("FALKORDB_GRAPH_NAME", "")
    if CONFIRM_FLAG not in argv:
        raise GuardRefused(
            f"{action} deletes EVERY graph on the FalkorDB instance (production included).\n"
            f"Re-run with {CONFIRM_FLAG} if that is really what you want."
        )
    if PRODUCTION_GRAPH in (configured, target) and FORCE_PRODUCTION_FLAG not in argv:
        raise GuardRefused(
            f"FALKORDB_GRAPH_NAME points at the production graph {PRODUCTION_GRAPH}.\n"
            f"Refusing to wipe the instance that serves the live demo. Export a snapshot first and add "
            f"{FORCE_PRODUCTION_FLAG} only after an explicit decision to rebuild production."
        )
    expected = configured or target
    try:
        typed = read(f"Type the graph name '{expected}' to confirm deleting every graph: ")
    except EOFError:
        typed = ""
    if typed.strip() != expected:
        raise GuardRefused("The typed name did not match. Nothing was deleted.")
    os.environ[ALLOW_ENV] = "1"


def guard_or_exit(target: str, argv: list[str], action: str) -> None:
    """Command-line wrapper: print the refusal and exit with status 2."""
    try:
        confirm_delete_all_graphs(target, argv, action=action)
    except GuardRefused as refused:
        print(refused.message, file=sys.stderr)
        raise
