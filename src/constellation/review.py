import os
import sqlite3
from pathlib import Path
from typing import Annotated, Any, Literal, TypedDict

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

Decision = Literal["approve", "skip"]
DEFAULT_CHECKPOINT = Path.home() / ".cache" / "constellation" / "review.sqlite"

def _merge(old: dict[str, Decision], new: dict[str, Decision]) -> dict[str, Decision]:
    return {**old, **new}  # a reducer: new answers are added to the saved ones instead of replacing them

class ReviewState(TypedDict):
    suggestions: list[str]  # ids only: the checkpoint must never hold item text, descriptions or reasons
    decisions: Annotated[dict[str, Decision], _merge]

def _next_undecided(state: ReviewState) -> str | None:
    return next((s for s in state["suggestions"] if s not in state.get("decisions", {})), None)

def _ask(state: ReviewState) -> dict[str, dict[str, Decision]]:
    pending = _next_undecided(state)
    assert pending is not None  # the loop edge only routes here while something is undecided
    # interrupt() saves the state and stops the graph; the caller sees `pending` in result["__interrupt__"].
    # Command(resume=answer) later re-enters this node, and interrupt() returns `answer`.
    answer: Decision = interrupt(pending)
    return {"decisions": {pending: answer}}

def _more(state: ReviewState) -> str:
    return "ask" if _next_undecided(state) else END

def build_review_graph(checkpointer: BaseCheckpointSaver[Any]) -> Any:  # shortcut: Any for the compiled graph, its generics are noise here
    graph = StateGraph(ReviewState)
    graph.add_node("ask", _ask)
    graph.add_conditional_edges(START, _more, ["ask", END])
    graph.add_conditional_edges("ask", _more, ["ask", END])
    return graph.compile(checkpointer=checkpointer)

def open_checkpointer(path: Path | None = None) -> SqliteSaver:
    path = path or DEFAULT_CHECKPOINT
    path.parent.mkdir(parents=True, exist_ok=True)
    os.close(os.open(path, os.O_WRONLY | os.O_CREAT, 0o600))
    os.chmod(path, 0o600)
    return SqliteSaver(sqlite3.connect(path, check_same_thread=False))

def thread_id(file: Path) -> str:
    """One checkpoint thread per scan file, so answers build up across sittings and re-scans."""
    return f"review:{file.resolve()}"
