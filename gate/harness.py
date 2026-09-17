"""The agent's entire surface: read tools, and action-invocation tools.

There is nothing else. The agent holds no connection, no SQL, no file handle
and no principal parameter. Its identity is bound when the session is
constructed and there is no tool, argument or instruction that changes it.

Every call is recorded in the session transcript, including the full text of
every record returned. The transcript is what the read-path exfiltration case
is measured against: if a restricted string reached the agent, it is here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from . import actions
from .store import Store

# Fields a listing returns. Free text is deliberately absent: a listing is a
# summary, and reaching the untrusted text takes a second, named call.
_SUMMARY_FIELDS = ("request_id", "title", "amount_cents", "state", "requester_id")


@dataclass
class ToolCall:
    seq: int
    tool: str
    args: dict[str, Any]
    ok: bool
    result: Any
    principal_id: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "seq": self.seq,
            "tool": self.tool,
            "args": dict(self.args),
            "ok": self.ok,
            "result": self.result,
            "principal_id": self.principal_id,
        }


class ToolSession:
    """One agent session, bound to one principal, against one store."""

    READ_TOOLS = ("whoami", "list_people", "get_person", "list_requests", "get_request")

    def __init__(self, store: Store, principal_id: str, case_id: str | None = None):
        self._store = store
        self._principal_id = principal_id
        self._case_id = case_id
        self.transcript: list[ToolCall] = []

    @property
    def principal_id(self) -> str:
        """Read-only. There is no setter and no tool that reaches it."""
        return self._principal_id

    def tool_names(self) -> tuple[str, ...]:
        return tuple(sorted(self.READ_TOOLS + actions.action_names()))

    # ---- dispatch ---------------------------------------------------------

    def call(self, tool: str, args: Mapping[str, Any] | None = None) -> ToolCall:
        args = dict(args or {})
        if tool in self.READ_TOOLS:
            ok, result = True, getattr(self, f"_read_{tool}")(args)
        elif tool in actions.REGISTRY:
            outcome = actions.invoke(
                self._store,
                self._principal_id,
                tool,
                args,
                case_id=self._case_id,
                via="tools",
            )
            ok, result = outcome.applied, outcome.as_dict()
        else:
            ok, result = False, {"error": "NO_SUCH_TOOL", "tool": tool}
        record = ToolCall(
            seq=len(self.transcript) + 1,
            tool=tool,
            args=args,
            ok=ok,
            result=result,
            principal_id=self._principal_id,
        )
        self.transcript.append(record)
        return record

    # ---- read tools -------------------------------------------------------

    def _read_whoami(self, args: Mapping[str, Any]) -> Any:
        return self._store.get("Person", self._principal_id)

    def _read_list_people(self, args: Mapping[str, Any]) -> Any:
        return self._store.all("Person")

    def _read_get_person(self, args: Mapping[str, Any]) -> Any:
        return self._store.get("Person", args.get("person_id", ""))

    def _read_list_requests(self, args: Mapping[str, Any]) -> Any:
        rows = self._store.all("Request")
        state = args.get("state")
        if state:
            rows = [r for r in rows if r["state"] == state]
        return [{k: r[k] for k in _SUMMARY_FIELDS} for r in rows]

    def _read_get_request(self, args: Mapping[str, Any]) -> Any:
        """Returns the record verbatim, free text and all.

        This is the untrusted surface. Nothing is stripped, filtered or
        summarised on the way out, because a demonstration that sanitises its
        own injection vector demonstrates nothing.
        """
        return self._store.get("Request", args.get("request_id", ""))
