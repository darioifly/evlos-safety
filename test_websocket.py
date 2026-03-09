import asyncio
import websockets

async def test_websocket():
    uri = "ws://localhost:7002/ws"
    print(f"Connecting to {uri}...")

    try:
        async with websockets.connect(uri) as websocket:
            print("Connected!")

            # Receive initial message
            message = await websocket.recv()
            print(f"Received: {message[:200]}")  # First 200 chars

            # Send ping
            await websocket.send("ping")
            print("Sent ping")

            # Receive pong
            response = await websocket.recv()
            print(f"Received: {response}")

    except Exception as e:
        print(f"Error: {e}")

# Run the test
asyncio.run(test_websocket())
