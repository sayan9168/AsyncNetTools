import asyncio
import struct
import socket
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

PROXY_HOST = 'YOUR_VPS_IP_HERE' # <-- এখানে আপনার সার্ভারের IP দিন
PROXY_PORT = 1080
OBFUSCATION_KEY = b'SecureGatewayKey2026!'
LISTEN_HOST = '127.0.0.1'
LISTEN_PORT = 8080

def obfuscate(data: bytes) -> bytes:
    if not data:
        return data
    key_len = len(OBFUSCATION_KEY)
    return bytes([b ^ OBFUSCATION_KEY[i % key_len] for i, b in enumerate(data)])

async def pipe_data(reader, writer, obfuscate_func=None):
    try:
        while True:
            data = await reader.read(8192)
            if not data:
                break
            if obfuscate_func:
                data = obfuscate_func(data)
            writer.write(data)
            await writer.drain()
    except asyncio.CancelledError:
        pass
    except Exception:
        pass
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass

async def handle_remote_connection(local_reader, local_writer, client_addr, dst_addr, dst_port):
    try:
        proxy_reader, proxy_writer = await asyncio.wait_for(
            asyncio.open_connection(PROXY_HOST, PROXY_PORT), timeout=10.0
        )
        
        greeting = struct.pack("!BB", 0x05, 0x01) + b'\x00'
        proxy_writer.write(obfuscate(greeting))
        await proxy_writer.drain()
        
        resp = obfuscate(await proxy_reader.readexactly(2))
        if resp[0] != 0x05 or resp[1] != 0x00:
            raise ValueError("Proxy handshake failed")
            
        try:
            socket.inet_aton(dst_addr)
            atyp = 0x01
            addr_data = socket.inet_aton(dst_addr)
        except socket.error:
            atyp = 0x03
            addr_data = struct.pack("!B", len(dst_addr)) + dst_addr.encode('utf-8')
            
        req = struct.pack("!BBBB", 0x05, 0x01, 0x00, atyp) + addr_data + struct.pack("!H", dst_port)
        proxy_writer.write(obfuscate(req))
        await proxy_writer.drain()
        
        resp_header = obfuscate(await proxy_reader.readexactly(4))
        if resp_header[1] != 0x00:
            raise ValueError(f"Proxy connection failed: {resp_header[1]}")
            
        if resp_header[3] == 0x01:
            await proxy_reader.readexactly(4 + 2)
        elif resp_header[3] == 0x03:
            domain_len = obfuscate(await proxy_reader.readexactly(1))[0]
            await proxy_reader.readexactly(domain_len + 2)
        elif resp_header[3] == 0x04:
            await proxy_reader.readexactly(16 + 2)
            
        task1 = asyncio.create_task(pipe_data(local_reader, proxy_writer, obfuscate_func=obfuscate))
        task2 = asyncio.create_task(pipe_data(proxy_reader, local_writer, obfuscate_func=obfuscate))
        await asyncio.gather(task1, task2)
        
    except Exception as e:
        logging.error(f"Remote connection error for {client_addr}: {e}")
    finally:
        try:
            local_writer.close()
            await local_writer.wait_closed()
        except Exception:
            pass

async def handle_local_client(local_reader, local_writer, client_addr):
    try:
        header = await local_reader.readexactly(2)
        ver, nmethods = struct.unpack("!BB", header)
        if ver != 0x05:
            return
        await local_reader.readexactly(nmethods)
        local_writer.write(struct.pack("!BB", 0x05, 0x00))
        await local_writer.drain()

        req_header = await local_reader.readexactly(4)
        ver, cmd, rsv, atyp = struct.unpack("!BBBB", req_header)
        if cmd != 0x01:
            local_writer.write(struct.pack("!BBBB", 0x05, 0x07, 0x00, 0x01))
            await local_writer.drain()
            return

        if atyp == 0x01:
            addr_data = await local_reader.readexactly(4)
            dst_addr = socket.inet_ntoa(addr_data)
        elif atyp == 0x03:
            domain_len = (await local_reader.readexactly(1))[0]
            dst_addr = (await local_reader.readexactly(domain_len)).decode('utf-8')
        elif atyp == 0x04:
            addr_data = await local_reader.readexactly(16)
            dst_addr = socket.inet_ntop(socket.AF_INET6, addr_data)
        else:
            local_writer.write(struct.pack("!BBBB", 0x05, 0x08, 0x00, 0x01))
            await local_writer.drain()
            return

        dst_port_data = await local_reader.readexactly(2)
        dst_port = struct.unpack("!H", dst_port_data)[0]
        await handle_remote_connection(local_reader, local_writer, client_addr, dst_addr, dst_port)

    except Exception as e:
        logging.error(f"Local client error {client_addr}: {e}")
    finally:
        try:
            local_writer.close()
            await local_writer.wait_closed()
        except Exception:
            pass

async def main():
    server = await asyncio.start_server(handle_local_client, LISTEN_HOST, LISTEN_PORT)
    addr = server.sockets[0].getsockname()
    logging.info(f'Local SOCKS5 Listener on {addr[0]}:{addr[1]} -> Remote Proxy {PROXY_HOST}:{PROXY_PORT}')
    async with server:
        await server.serve_forever()

if __name__ == '__main__':
    asyncio.run(main())
