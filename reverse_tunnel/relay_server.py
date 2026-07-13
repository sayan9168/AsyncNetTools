import asyncio
import struct
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

HEADER_FORMAT = '!IIB'
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)
MSG_DATA = 0
MSG_NEW_CONN = 1
MSG_CLOSE = 2
MSG_HEARTBEAT = 3

CONTROL_PORT = 9000
PUBLIC_PORT = 8000

async def send_frame(writer, channel_id, msg_type, payload=b''):
    header = struct.pack(HEADER_FORMAT, channel_id, len(payload), msg_type)
    writer.write(header + payload)
    await writer.drain()

async def read_frame(reader, timeout=45.0):
    try:
        header = await asyncio.wait_for(reader.readexactly(HEADER_SIZE), timeout=timeout)
        channel_id, length, msg_type = struct.unpack(HEADER_FORMAT, header)
        payload = b''
        if length > 0:
            payload = await asyncio.wait_for(reader.readexactly(length), timeout=timeout)
        return channel_id, msg_type, payload
    except asyncio.TimeoutError:
        raise ConnectionError("Frame read timeout")

class RelayServer:
    def __init__(self):
        self.agent_writer = None
        self.active_channels = {}

    async def handle_agent(self, reader, writer):
        addr = writer.get_extra_info('peername')
        logging.info(f"Internal Agent connected from {addr}")
        self.agent_writer = writer
        
        try:
            while True:
                channel_id, msg_type, payload = await read_frame(reader)
                if msg_type == MSG_DATA:
                    ext_writer = self.active_channels.get(channel_id)
                    if ext_writer:
                        ext_writer.write(payload)
                        await ext_writer.drain()
                elif msg_type == MSG_CLOSE:
                    ext_writer = self.active_channels.pop(channel_id, None)
                    if ext_writer:
                        ext_writer.close()
                elif msg_type == MSG_HEARTBEAT:
                    pass
        except (ConnectionError, asyncio.IncompleteReadError) as e:
            logging.warning(f"Agent disconnected or timed out: {e}")
        except Exception as e:
            logging.error(f"Agent handler error: {e}")
        finally:
            self.agent_writer = None
            for ext_writer in self.active_channels.values():
                ext_writer.close()
            self.active_channels.clear()
            logging.info("Cleaned up all external channels.")

    async def handle_external(self, reader, writer):
        if not self.agent_writer:
            writer.close()
            return

        channel_id = hash(writer) & 0xFFFFFFFF 
        self.active_channels[channel_id] = writer
        logging.info(f"External user connected. Assigned Channel ID: {channel_id}")

        try:
            await send_frame(self.agent_writer, 0, MSG_NEW_CONN, struct.pack('!I', channel_id))
            while True:
                data = await reader.read(8192)
                if not data:
                    break
                await send_frame(self.agent_writer, channel_id, MSG_DATA, data)
        except Exception as e:
            logging.debug(f"External connection error (Channel {channel_id}): {e}")
        finally:
            self.active_channels.pop(channel_id, None)
            writer.close()
            if self.agent_writer:
                try:
                    await send_frame(self.agent_writer, channel_id, MSG_CLOSE)
                except Exception:
                    pass

    async def run(self):
        ctrl_server = await asyncio.start_server(self.handle_agent, '0.0.0.0', CONTROL_PORT)
        pub_server = await asyncio.start_server(self.handle_external, '0.0.0.0', PUBLIC_PORT)
        logging.info(f"Relay Server started. Control Port: {CONTROL_PORT}, Public Port: {PUBLIC_PORT}")
        async with ctrl_server, pub_server:
            await asyncio.gather(ctrl_server.serve_forever(), pub_server.serve_forever())

if __name__ == '__main__':
    asyncio.run(RelayServer().run())
