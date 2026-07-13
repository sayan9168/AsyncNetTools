# AsyncNetTools: Python Network Utilities Suite

A collection of lightweight, asynchronous, and **zero-dependency** (standard library only) Python networking tools designed for secure remote infrastructure management, NAT traversal, and bypassing restrictive network middle-boxes.

> **⚠️ Disclaimer:** These tools are provided for educational purposes and authorized network administration only. The authors are not responsible for any misuse or illegal activities. Always ensure you have explicit permission before tunneling traffic through corporate or restricted networks.

## 📑 Overview

This repository contains two primary networking utilities built entirely using Python's `asyncio` and standard libraries. No `pip install` is required!

1. **Obfuscated SOCKS5 Proxy:** A custom SOCKS5 proxy that wraps traffic in a lightweight XOR obfuscation layer. This prevents middle-boxes and DPI (Deep Packet Inspection) systems from misinterpreting or blocking standard SOCKS5 handshakes.
2. **Multiplexed Reverse Tunnel (NAT Traversal):** A reverse port-forwarding utility similar to `ssh -R`. It allows an internal agent behind a strict NAT/Firewall to expose local services to a public relay server using a custom multiplexed framing protocol over a single persistent TCP connection.

## 🚀 Features

### 1. Obfuscated SOCKS5 Gateway
* **Standard SOCKS5 Support:** Handles standard No-Auth handshakes and CONNECT commands.
* **Traffic Obfuscation:** Implements a lightweight XOR byte-shuffling layer to break protocol signatures.
* **High Performance:** Fully asynchronous using `asyncio.start_server`.
* **Dual-Ended:** Includes both the Remote Gateway (Server) and Local Listener (Client) scripts.

### 2. Reverse Tunnel & NAT Traversal
* **Custom Multiplexing:** Implements a 9-byte framing protocol (Channel ID, Length, Msg Type) to multiplex hundreds of concurrent TCP streams over a single control channel.
* **Resilient Connections:** Built-in keep-alive heartbeats to prevent NAT table timeouts.
* **Auto-Reconnection:** The internal agent automatically reconnects to the relay server if the network drops.
* **Clean Teardown:** Gracefully handles broken sockets and ensures all virtual channels are closed properly.

## 📂 Project Structure

```text
.
├── README.md
├── .gitignore
├── LICENSE
├── socks5_proxy/
│   ├── remote_gateway.py      # Server-side obfuscated SOCKS5 proxy
│   └── local_listener.py      # Client-side obfuscated SOCKS5 listener
└── reverse_tunnel/
    ├── relay_server.py        # Public-facing relay server
    └── internal_agent.py      # Internal NAT-traversal agent
```

## 🛠️ Prerequisites

* **Python 3.8+** (Uses `asyncio` features like `asyncio.run()` and `asyncio.wait_for()`).
* **No external dependencies.** (Uses only `asyncio`, `socket`, `struct`, `logging`).

## 💻 Usage Instructions

### Running the Obfuscated SOCKS5 Proxy

1. **Start the Remote Gateway** (on your public/edge server):
```bash
   python socks5_proxy/remote_gateway.py
```
2. **Start the Local Listener** (on your local workstation):
   *Update `PROXY_HOST` inside the script to your server's IP.*
```bash
   python socks5_proxy/local_listener.py
```
3. **Configure your tools** (Browser, SSH, etc.) to use `127.0.0.1:8080` as a SOCKS5 proxy.

### Running the Reverse Tunnel (NAT Traversal)

1. **Start a local test service** (on your internal machine):
```bash
   python -m http.server 8080
```
2. **Start the Relay Server** (on your public VPS):
```bash
   python reverse_tunnel/relay_server.py
```
3. **Start the Internal Agent** (on your internal machine behind NAT):
   *Update `RELAY_HOST` inside the script to your VPS IP.*
```bash
   python reverse_tunnel/internal_agent.py
```
4. **Access the internal service** from anywhere:
```bash
   curl http://<YOUR_VPS_IP>:8000
```

## 🧠 Architecture Deep Dive

### How Multiplexing Works in the Reverse Tunnel
Raw TCP is a continuous byte stream. To run multiple independent connections over one TCP socket, the `reverse_tunnel` scripts use a **Custom Framing Protocol**:

| Field | Size | Description |
| :--- | :--- | :--- |
| **Channel ID** | 4 Bytes | Unique integer identifying the virtual circuit (`0` is for control). |
| **Payload Length** | 4 Bytes | Size of the incoming data payload. |
| **Message Type** | 1 Byte | Action type (`DATA`, `NEW_CONN`, `CLOSE`, `HEARTBEAT`). |
| **Payload** | N Bytes | The actual TCP data or control parameters. |

This allows the relay server to route incoming public traffic to the correct internal local connection without data interleaving.

## 📜 License

This project is licensed under the **sayanoxv1.1** License.  
See the [LICENSE](LICENSE) file for details regarding usage, distribution, and modifications.

## 📞 Contact & Author

Developed and maintained by **Sayan**. Feel free to reach out for collaborations, questions, or enterprise support.

* 📧 **Email:** [sm6881164@gmail.com](mailto:sm6881164@gmail.com)
* 🐙 **GitHub:** [github.com/sayan9168](https://github.com/sayan9168)
* 🐦 **Twitter / X:** [@notfound_sayan](https://x.com/notfound_sayan)
* 📸 **Instagram:** [@_sayyyyan](https://instagram.com/_sayyyyan)

---
*Made with ❤️ and Python `asyncio`*
