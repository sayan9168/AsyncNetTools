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

RELAY_HOST = 'YOUR_VPS_IP_HERE' # <-- এখানে আপনার সার্ভারের IP দিন
RELAY_PORT = 9000
LOCAL_TARGET_HOST = '127.0.0.1'
LOCAL_TARGET_PORT = 8080

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

class GatewayAgent:
    def __init__(self):
        self.server_writer = None
        self.local_channels = {}

    async def handle_local_service(self, channel_id, reader, writer):
        self.local_channels[channel_id] = writer
        try:
            while True:
                data = await reader.read(8192)
                if not data:
                    break
                await send_frame(self.server_writer, channel_id, MSG_DATA, data)
        except Exception as e:
            logging.debug(f"Local service read error (Channel {channel_id}): {e}")
        finally:
            self.local_channels.pop(channel_id, None)
            writer.close()
            if self.server_writer:
                try:
                    await send_frame(self.server_writer, channel_id, MSG_CLOSE)
                except Exception:
                    pass

    async def process_relay_frames(self, reader):
        while True:
            channel_id, msg_type, payload = await read_frame(reader)
            if msg_type == MSG_NEW_CONN:
                new_channel_id = struct.unpack('!I', payload)[0]
                try:
                    local_reader, local_writer = await asyncio.open_connection(
                        LOCAL_TARGET_HOST, LOCAL_TARGET_PORT
                    )
                    logging.info(f"Channel {new_channel_id}: Connected to local {LOCAL_TARGET_HOST}:{LOCAL_TARGET_PORT}")
                    asyncio.create_task(self.handle_local_service(new_channel_id, local_reader, local_writer))
                except Exception as e:
                    logging.error(f"Channel {new_channel_id}: Failed to connect to local target: {e}")
                    await send_frame(self.server_writer, new_channel_id, MSG_CLOSE)
            elif msg_type == MSG_DATA:
                local_writer = self.local_channels.get(channel_id)
                if local_writer:
                    local_writer.write(payload)
                    await local_writer.drain()
            elif msg_type == MSG_CLOSE:
                local_writer = self.local_channels.pop(channel_id, None)
                if local_writer:
                    local_writer.close()
            elif msg_type == MSG_HEARTBEAT:
                pass

    async def heartbeat_loop(self):
        while True:
            await asyncio.sleep(15)
            if self.server_writer:
                try:
                    await send_frame(self.server_writer, 0, MSG_HEARTBEAT)
                except Exception:
                    break

    async def run(self):
        while True:
            try:
                logging.info(f"Connecting to Relay Server {RELAY_HOST}:{RELAY_PORT}...")
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(RELAY_HOST, RELAY_PORT), timeout=10.0
                )
                self.server_writer = writer
                logging.info("Successfully connected to Relay Server.")
                hb_task = asyncio.create_task(self.heartbeat_loop())
                await self.process_relay_frames(reader)
                hb_task.cancel()
            except (ConnectionError, asyncio.TimeoutError, asyncio.IncompleteReadError) as e:
                logging.warning(f"Connection to relay lost ({e}). Reconnecting in 5 seconds...")
            except Exception as e:
                logging.error(f"Unexpected error: {e}. Reconnecting in 5 seconds...")
            finally:
                self.server_writer = None
                for w in self.local_channels.values():
                    w.close()
                self.local_channels.clear()
            await asyncio.sleep(5)

if __name__ == '__main__':
    asyncio.run(GatewayAgent().run())
