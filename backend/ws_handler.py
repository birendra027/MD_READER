from fastapi import WebSocket, WebSocketDisconnect
from backend.md_converter import convert
async def websocket_handler(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            md_text = await websocket.receive_text()
            html = convert(md_text)
            await websocket.send_text(html)
    except WebSocketDisconnect:
        print("WebSocket disconnected")