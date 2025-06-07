"""
quic_protocol.py
================
Wire-format helpers and dataclass PDUs for the CS-544 “QUICChat” protocol.

Author : Jaspreet Singh — 2025
"""

from __future__ import annotations
import enum
import json
import time
import inspect
from dataclasses import dataclass, asdict

# ─────────────────────────────────────────────────────────────────────────────
# 1.  Enum of message types used on the wire
# ─────────────────────────────────────────────────────────────────────────────
class MsgType(str, enum.Enum):
    HELLO   = "CHAT_HELLO"
    WELCOME = "CHAT_WELCOME"
    MESSAGE = "CHAT_MESSAGE"
    RECEIPT = "CHAT_RECEIPT"
    TYPING  = "CHAT_TYPING"
    BYE     = "CHAT_BYE"
    ERROR   = "CHAT_ERROR"


# ─────────────────────────────────────────────────────────────────────────────
# 2.  Base PDU (every message has type, seq, timestamp)
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class PDU:
    type: MsgType
    seq:  int
    ts:   float

    def encode(self) -> bytes:
        """JSON-encode to bytes ready for QUIC stream write."""
        return json.dumps(asdict(self)).encode()

    # --------------------------------------------------------------------- #
    # Robust decoder that maps the JSON 'type' → correct dataclass,
    # and passes only the __init__ parameters that class accepts.
    # --------------------------------------------------------------------- #
    @staticmethod
    def decode(raw: bytes) -> "PDU":
        data = json.loads(raw.decode())

        # — map wire-type → concrete dataclass —
        _MAP = {
            MsgType.HELLO.value:   Hello,
            MsgType.WELCOME.value: Welcome,
            MsgType.MESSAGE.value: ChatMsg,
            MsgType.RECEIPT.value: Receipt,
            MsgType.TYPING.value:  Typing,
            MsgType.BYE.value:     Bye,
            MsgType.ERROR.value:   Error,
        }
        cls = _MAP.get(data["type"], PDU)

        # Unknown type → strip extras and return generic PDU
        if cls is PDU:
            slim = {k: data[k] for k in ("type", "seq", "ts")}
            return cls(**slim)                          # type: ignore[arg-type]

        # Known type → pass only args accepted by its __init__
        allowed = {
            k for k in inspect.signature(cls.__init__).parameters
            if k != "self"
        }
        filtered = {k: v for k, v in data.items() if k in allowed}
        return cls(**filtered)                         # type: ignore[arg-type]


# ─────────────────────────────────────────────────────────────────────────────
# 3.  Concrete PDUs
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class Hello(PDU):
    name: str
    def __init__(self, name: str):
        super().__init__(MsgType.HELLO, 0, time.time())
        self.name = name


@dataclass
class Welcome(PDU):
    server: str
    def __init__(self, seq: int, server: str):
        super().__init__(MsgType.WELCOME, seq, time.time())
        self.server = server


@dataclass
class ChatMsg(PDU):
    sender: str
    text:   str
    def __init__(self, seq: int, sender: str, text: str):
        super().__init__(MsgType.MESSAGE, seq, time.time())
        self.sender, self.text = sender, text


@dataclass
class Receipt(PDU):
    ack: int
    def __init__(self, ack: int):
        super().__init__(MsgType.RECEIPT, ack, time.time())
        self.ack = ack


@dataclass
class Typing(PDU):
    who: str
    status: bool
    def __init__(self, who: str, status: bool):
        super().__init__(MsgType.TYPING, 0, time.time())
        self.who, self.status = who, status


@dataclass
class Bye(PDU):
    reason: str = ""
    def __init__(self, reason: str = ""):
        super().__init__(MsgType.BYE, 0, time.time())
        self.reason = reason


@dataclass
class Error(PDU):
    code: int
    msg:  str
    def __init__(self, code: int, msg: str):
        super().__init__(MsgType.ERROR, 0, time.time())
        self.code, self.msg = code, msg
