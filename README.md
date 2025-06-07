# QUICCHAT
# QUICChat – CS-544 Project

A fully-functional peer-to-peer chat system built on **QUIC** using [aioquic](https://github.com/aiortc/aioquic).  
It demonstrates handshake validation, duplicate-free messaging with ACK + auto-retransmit, typing indicators, and both GUI & headless clients.

---

## Directory layout
```text
quicchat/
├── server.py            # QUICChat broadcast server
├── gui_client.py        # Tk-based client with typing indicator
├── quic_protocol.py     # Dataclass PDU definitions & codec
├── requirements.txt     # aioquic, pytest, etc.
├── certs/               # Self-signed TLS cert/key live here
└── README.md            # (this file)
