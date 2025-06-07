#!/usr/bin/env python
"""
QUICChat server – broadcasts messages and explicitly flushes them.

Run:
    python server.py --cert certs/cert.pem --key certs/key.pem
"""
from __future__ import annotations
import asyncio, argparse, logging
from typing import Set

from aioquic.asyncio import QuicConnectionProtocol, serve
from aioquic.quic.configuration import QuicConfiguration
from aioquic.quic.events import StreamDataReceived, ConnectionTerminated

from quic_protocol import (
    PDU, MsgType,
    Welcome, Receipt,
)

logging.basicConfig(level=logging.INFO)


class ChatSession(QuicConnectionProtocol):
    """One QUIC connection ↔ one chat participant."""
    _live: Set["ChatSession"] = set()

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self.stream_out: int | None = None          # first bidi stream ID
        ChatSession._live.add(self)

    # ------------------------------------------------------------------ #
    # Cleanup
    # ------------------------------------------------------------------ #
    def connection_lost(self, exc):
        ChatSession._live.discard(self)
        super().connection_lost(exc)

    # ------------------------------------------------------------------ #
    # QUIC event dispatcher
    # ------------------------------------------------------------------ #
    def quic_event_received(self, event):
        if isinstance(event, StreamDataReceived):
            self._handle_stream(event)
        elif isinstance(event, ConnectionTerminated):
            ChatSession._live.discard(self)

    # ------------------------------------------------------------------ #
    # Stream handler
    # ------------------------------------------------------------------ #
    def _handle_stream(self, event: StreamDataReceived):
        pdu = PDU.decode(event.data)
        logging.info("« %s", pdu)

        # Remember client's first stream for replies
        if self.stream_out is None:
            self.stream_out = event.stream_id

        # ----- HELLO / WELCOME -----------------------------------------
        if pdu.type is MsgType.HELLO:
            self._quic.send_stream_data(
                self.stream_out,
                Welcome(seq=1, server="QUICCHAT-server").encode(),
                end_stream=False,
            )
            self.transmit()                         # flush immediately

        # ----- CHAT_MESSAGE  (ACK + broadcast) -------------------------
        elif pdu.type is MsgType.MESSAGE:
            # 1) ACK back to sender
            self._quic.send_stream_data(
                self.stream_out,
                Receipt(pdu.seq).encode(),
                end_stream=False,
            )
            self.transmit()                         # flush ACK

            # 2) Fan-out to every other live session
            for peer in ChatSession._live.copy():
                if peer is self or peer.stream_out is None:
                    continue
                peer._quic.send_stream_data(
                    peer.stream_out,
                    event.data,                     # original ChatMsg bytes
                    end_stream=False,
                )
                peer.transmit()                     # flush to that peer

        # ----- BYE -----------------------------------------------------
        elif pdu.type is MsgType.BYE:
            self.close()


# ---------------------------------------------------------------------- #
# Entrypoint
# ---------------------------------------------------------------------- #
async def main(host: str, port: int, cert: str, key: str):
    cfg = QuicConfiguration(is_client=False, alpn_protocols=["chat/0"])
    cfg.load_cert_chain(cert, key)

    server = await serve(
        host, port, configuration=cfg, create_protocol=ChatSession
    )
    logging.info("Server listening on %s:%s", host, port)

    try:
        await asyncio.Event().wait()                # Ctrl-C to stop
    finally:
        server.close()
        logging.info("Server shutting down")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=4433)
    ap.add_argument("--cert", required=True)
    ap.add_argument("--key", required=True)
    args = ap.parse_args()

    asyncio.run(main(args.host, args.port, args.cert, args.key))
