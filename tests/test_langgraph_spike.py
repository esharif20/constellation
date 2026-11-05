"""Spike for #22: the two LangGraph behaviours the scan graph relies on (langgraph 1.2.x)."""

import operator
import sqlite3
from typing import Annotated, Any, TypedDict

import pytest
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import START, StateGraph
from langgraph.types import Send


class _State(TypedDict, total=False):
    jobs: list[str]
    done: Annotated[list[str], operator.add]
    joined: Annotated[list[str], operator.add]


def _fan_out_graph(on_work: Any, checkpointer: Any = None) -> Any:
    def plan(state: _State) -> dict[str, Any]:
        return {}

    def route(state: _State) -> Any:
        return [Send("work", {"job": j}) for j in state["jobs"]] or "finish"

    def work(state: dict[str, str]) -> dict[str, Any]:
        on_work(state["job"])
        return {"done": [state["job"]]}

    def finish(state: _State) -> dict[str, Any]:
        return {}

    def side(state: _State) -> dict[str, Any]:
        return {}

    def join(state: _State) -> dict[str, Any]:
        return {"joined": ["x"]}

    graph = StateGraph(_State)
    for node in (plan, work, finish, side, join):
        graph.add_node(node)
    graph.add_edge(START, "plan")
    graph.add_edge(START, "side")
    graph.add_conditional_edges("plan", route)
    graph.add_edge("work", "finish")
    graph.add_edge(["side", "finish"], "join")  # multi-source edge: join waits for both
    return graph.compile(checkpointer=checkpointer)


@pytest.mark.parametrize("jobs", [[], ["a", "b"]])
def test_a_multi_source_join_runs_once_whether_or_not_the_fan_out_was_skipped(jobs):
    result = _fan_out_graph(lambda job: None).invoke({"jobs": jobs})

    assert result["joined"] == ["x"]  # ran exactly once, also when the conditional edge skipped the Send branches
    assert sorted(result.get("done", [])) == jobs


def test_sqlite_checkpointer_keeps_finished_send_branches_when_a_sibling_raises(tmp_path):
    calls: list[str] = []
    broken = {"on": True}

    def work(job: str) -> None:
        calls.append(job)
        if job == "b" and broken["on"]:
            raise RuntimeError("boom")

    saver = SqliteSaver(sqlite3.connect(tmp_path / "spike.sqlite", check_same_thread=False))
    graph = _fan_out_graph(work, saver)
    config: Any = {"configurable": {"thread_id": "t"}, "max_concurrency": 1}  # one at a time, so "a" finishes before "b" raises

    with pytest.raises(RuntimeError):
        graph.invoke({"jobs": ["a", "b", "c"]}, config)
    broken["on"] = False
    result = graph.invoke(None, config)  # resume the same thread

    assert calls.count("a") == 1  # the finished branch was not run again
    assert sorted(result["done"]) == ["a", "b", "c"]
