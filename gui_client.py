#!/usr/bin/env python
"""
Tk-based QUICChat client (aioquic ≥ 1.2) – now flushes packets.
"""
from __future__ import annotations
import argparse, asyncio, queue, threading, tkinter as tk, ssl
from typing import Any

from aioquic.asyncio import connect
from aioquic.asyncio.protocol import QuicConnectionProtocol
from aioquic.quic.configuration import QuicConfiguration
from aioquic.quic.events import StreamDataReceived, ConnectionTerminated

from quic_protocol import (
    PDU, MsgType,
    Hello, ChatMsg, Welcome, Receipt, Error,        # noqa: F401
)

# ── tiny shim to await events ────────────────────────────────────────────
class ClientProtocol(QuicConnectionProtocol):
    def __init__(self, *args: Any, **kw: Any):
        super().__init__(*args, **kw)
        self.event_q: asyncio.Queue = asyncio.Queue()

    def quic_event_received(self, event):
        self.event_q.put_nowait(event)

# ── networking coroutine ────────────────────────────────────────────────
async def quic_chat(host: str, port: int, name: str,
                    in_q: queue.Queue[str], out_q: queue.Queue[str],
                    insecure_tls: bool = True):
    cfg = QuicConfiguration(alpn_protocols=["chat/0"])
    if insecure_tls:
        cfg.verify_mode = ssl.CERT_NONE

    async with connect(host, port, configuration=cfg,
                       create_protocol=ClientProtocol) as proto:
        await proto.wait_connected()

        stream_id = proto._quic.get_next_available_stream_id()
        proto._quic.send_stream_data(stream_id, Hello(name).encode(), end_stream=False)
        proto.transmit()                             # flush HELLO
        seq = 1

        async def reader():
            while True:
                event = await proto.event_q.get()
                if isinstance(event, StreamDataReceived):
                    pdu = PDU.decode(event.data)
                    if isinstance(pdu, ChatMsg):
                        in_q.put(f"{pdu.sender}: {pdu.text}")
                    elif isinstance(pdu, Welcome):
                        in_q.put(f"✓ connected to {pdu.server}")
                    elif isinstance(pdu, Receipt):
                        in_q.put(f"✓ delivered {pdu.ack}")
                    elif isinstance(pdu, Error):
                        in_q.put(f"⚠️  {pdu.code}: {pdu.msg}")
                elif isinstance(event, ConnectionTerminated):
                    in_q.put("*** disconnected ***")
                    return

        async def writer():
            nonlocal seq
            loop = asyncio.get_running_loop()
            while True:
                text = await loop.run_in_executor(None, out_q.get)
                msg = ChatMsg(seq, name, text)
                proto._quic.send_stream_data(stream_id, msg.encode(), end_stream=False)
                proto.transmit()                     # flush CHAT_MESSAGE
                in_q.put(f"me: {text}")
                seq += 1

        await asyncio.gather(reader(), writer())

# ── Tk GUI (main thread) ────────────────────────────────────────────────
class ChatGUI:
    def __init__(self, host: str, port: int, name: str):
        self.in_q, self.out_q = queue.Queue(), queue.Queue()

        self.root = tk.Tk(); self.root.title(f"QUICChat – {name}")
        self.display = tk.Text(self.root, height=20, width=52, state="disabled")
        self.display.pack(padx=6, pady=6)
        self.entry = tk.Entry(self.root); self.entry.pack(fill="x", padx=6, pady=(0,6))
        self.entry.bind("<Return>", self._on_enter)
        self.root.after(100, self._drain_incoming)

        threading.Thread(
            target=lambda: asyncio.run(
                quic_chat(host, port, name, self.in_q, self.out_q, insecure_tls=True)
            ),
            daemon=True,
        ).start()

    def _on_enter(self, _=None):
        text = self.entry.get().strip()
        if text:
            self.out_q.put(text)
            self.entry.delete(0, tk.END)

    def _drain_incoming(self):
        while not self.in_q.empty():
            line = self.in_q.get_nowait()
            self.display.configure(state="normal")
            self.display.insert(tk.END, line + "\n")
            self.display.configure(state="disabled")
            self.display.see(tk.END)
        self.root.after(100, self._drain_incoming)

    def run(self): self.root.mainloop()

# ── CLI ──────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", required=True)
    ap.add_argument("--port", type=int, default=4433)
    ap.add_argument("--name", required=True)
    args = ap.parse_args()
    ChatGUI(args.host, args.port, args.name).run()
