import asyncio
import struct
import socket
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

OBFUSCATION_KEY = b'SecureGatewayKey2026!'

def obfuscate(data: bytes) -> bytes:
    if not data:
        return data
    key_len = len(OBFUSCATION_KEY)
    return bytes([b ^ OBFUSCATION_KEY[i % key_len] for i, b in enumerate(data)])

async def pipe_data(reader: asyncio.StreamReader, writer: asyncio.StreamWriter, obfuscate_func=None):
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
    except Exception as e:
        logging.debug(f"Stream closed: {e}")
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass

async def handle_socks5(local_reader, local_writer, client_addr):
    try:
        header = obfuscate(await local_reader.readexactly(2))
        ver, nmethods = struct.unpack("!BB", header)
        if ver != 0x05:
            raise ValueError("Invalid SOCKS version")
        
        methods = obfuscate(await local_reader.readexactly(nmethods))
        if 0x00 not in methods:
            local_writer.write(obfuscate(struct.pack("!BB", 0x05, 0xFF)))
            await local_writer.drain()
            return
        
        local_writer.write(obfuscate(struct.pack("!BB", 0x05, 0x00)))
        await local_writer.drain()

        req_header = obfuscate(await local_reader.readexactly(4))
        ver, cmd, rsv, atyp = struct.unpack("!BBBB", req_header)
        if cmd != 0x01:
            local_writer.write(obfuscate(struct.pack("!BBBB", 0x05, 0x07, 0x00, 0x01)))
            await local_writer.drain()
            return

        if atyp == 0x01:
            addr_data = obfuscate(await local_reader.readexactly(4))
            dst_addr = socket.inet_ntoa(addr_data)
        elif atyp == 0x03:
            domain_len = obfuscate(await local_reader.readexactly(1))[0]
            dst_addr = obfuscate(await local_reader.readexactly(domain_len)).decode('utf-8')
        elif atyp == 0x04:
            addr_data = obfuscate(await local_reader.readexactly(16))
            dst_addr = socket.inet_ntop(socket.AF_INET6, addr_data)
        else:
            local_writer.write(obfuscate(struct.pack("!BBBB", 0x05, 0x08, 0x00, 0x01)))
            await local_writer.drain()
            return

        dst_port_data = obfuscate(await local_reader.readexactly(2))
        dst_port = struct.unpack("!H", dst_port_data)[0]
        logging.info(f"CONNECT request to {dst_addr}:{dst_port}")

        try:
            target_reader, target_writer = await asyncio.wait_for(
                asyncio.open_connection(dst_addr, dst_port), timeout=10.0
            )
        except Exception as e:
            logging.error(f"Failed to connect to target {dst_addr}:{dst_port}: {e}")
            local_writer.write(obfuscate(struct.pack("!BBBB", 0x05, 0x05, 0x00, 0x01)))
            await local_writer.drain()
            return

        local_writer.write(obfuscate(struct.pack("!BBBB", 0x05, 0x00, 0x00, 0x01) + b'\x00\x00\x00\x00' + b'\x00\x00'))
        await local_writer.drain()

        task1 = asyncio.create_task(pipe_data(local_reader, target_writer, obfuscate_func=obfuscate))
        task2 = asyncio.create_task(pipe_data(target_reader, local_writer, obfuscate_func=obfuscate))
        await asyncio.gather(task1, task2)

    except asyncio.IncompleteReadError:
        logging.warning("Connection closed prematurely during handshake")
    except Exception as e:
        logging.error(f"Error handling client {client_addr}: {e}")
    finally:
        try:
            local_writer.close()
            await local_writer.wait_closed()
        except Exception:
            pass

async def main():
    server = await asyncio.start_server(handle_socks5, '0.0.0.0', 1080)
    addr = server.sockets[0].getsockname()
    logging.info(f'Obfuscated SOCKS5 Proxy listening on {addr[0]}:{addr[1]}')
    async with server:
        await server.serve_forever()

if __name__ == '__main__':
    asyncio.run(main())
