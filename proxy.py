import asyncio, struct, ipaddress, socket

server_ip = '12.34.56.78'

async def handle_connect(reader, writer, host, port, family):
    dest_reader, dest_writer = await asyncio.open_connection(host, port, family=family)
    writer.write(b'\x05\x00\x00\x01\x01\x02\x03\04\x77\x77')

    async def read1():
        while not reader.at_eof():
            data = await reader.read(255)
            if data:
                dest_writer.write(data)
        dest_writer.close()

    async def read2():
        while not dest_reader.at_eof():
            data = await dest_reader.read(255)
            if data:
                writer.write(data)
        writer.close()

    await asyncio.gather(read1(), read2())

def try_bind(sock):
    for p in range(55000, 60000):
        try:
            sock.bind(('0.0.0.0', p))
            break
        except Exception as e:
            pass

async def handle_bind(reader, writer, family):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setblocking(False)
        try_bind(s)
        s.listen()
        _, port = s.getsockname()
        ip = socket.inet_aton('82.146.41.108')
        writer.write(b'\x05\x00\x00\x01' + ip + struct.pack('>H', port))
        conn, (addr, port) = await asyncio.get_running_loop().sock_accept(s)

        with conn:
            writer.write(b'\x05\x00\x00\x01' + ip + struct.pack('>H', port))
            async def read1():
                while not reader.at_eof():
                    data = await reader.read(255)
                    if data:
                        await asyncio.get_running_loop().sock_sendall(conn, data)
                conn.close()

            async def read2():
                while not reader.at_eof():
                    data = await asyncio.get_running_loop().sock_recv(conn, 255)
                    if not data:
                        return writer.close()
                    writer.write(data)

            await asyncio.gather(read1(), read2())

async def handle_udp(reader, writer, port, family):
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as server:
        server.setblocking(False)
        peer, _ = writer.transport.get_extra_info('peername')
        try_bind(server)
        _, bound_port = server.getsockname()
        ip = socket.inet_aton(server_ip)
        writer.write(b'\x05\x00\x00\x01' + ip + struct.pack('>H', bound_port))
        loop = asyncio.get_running_loop()
        client_port = [None]

        def udp_reader():
            def read1(data):
                if not data:
                    return server.close()

                _, _, frag, atyp, *_ = data
                if frag or atyp not in (1, 3, 4):
                    return

                if atyp == 1:
                    host = str(ipaddress.IPv4Address(data[4:8]))
                    data = data[8:]
                elif atyp == 3:
                    n, = data[4]
                    host = data[5:5 + n].decode()
                    data = data[5 + n:]
                elif atyp == 4:
                    host = str(ipaddress.IPv6Address(data[4:20]))
                    data = data[20:]

                dest_port, = struct.unpack('>H', data[:2])
                data = data[2:]
                server.sendto(data, (host, dest_port))

            def read2(data, port):
                if not data:
                    return server.close()
                ip = socket.inet_aton(server_ip)
                header = struct.pack('>HBB4sH', 0, 0, 1, ip, port)
                server.sendto(header + data, (peer, port))

            data, (ip, port) = server.recvfrom(270)
            if ip == peer:
                client_port[0] = port
                read1(data)
            else:
                read2(data, client_port[0])
            
        loop.add_reader(server, udp_reader) 

        while not reader.at_eof():
            await asyncio.sleep(0.01)

        loop.remove_reader(server) 

async def handle_client(reader, writer):
    _, n = await reader.read(2)
    methods = await reader.read(n)

    if 2 not in methods:
        return writer.close()

    writer.write(b'\x05\x02')

    _, n = await reader.read(2)
    username = await reader.read(n)

    n, = await reader.read(1)
    password = await reader.read(n)

    if username not in [b'x86monkey', b'goosedb'] or password != b'danikloh':
        writer.write(b'\x01\xff')
        return writer.close()

    writer.write(b'\x01\x00')

    _, cmd, _ = await reader.read(3)

    if cmd not in [1, 2, 3]:
        return writer.close()

    family = 2
    atyp = (await reader.read(1))[0]
    if atyp == 1:
        host = str(ipaddress.IPv4Address(await reader.read(4)))
    if atyp == 3:
        n, = await reader.read(1)
        host = (await reader.read(n)).decode()
    if atyp == 4:
        host = str(ipaddress.IPv6Address(await reader.read(16)))
        family = 10

    port, = struct.unpack('>H', await reader.read(2))

    try:
        if cmd == 1:
            await handle_connect(reader, writer, host, port, family)
        elif cmd == 2:
            await handle_bind(reader, writer, family)
        elif cmd == 3:
            await handle_udp(reader, writer, port, family)
            return writer.close()
    finally:
        writer.close()


async def main():
    server = await asyncio.start_server(handle_client, '0.0.0.0', 8080)
    async with server:
        await server.serve_forever()

if __name__ == '__main__':
    asyncio.run(main())

