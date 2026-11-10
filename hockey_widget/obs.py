"""OBS WebSocket v5: test the connection and create or update the widget's browser source."""

from __future__ import annotations

import asyncio

import simpleobsws


class OBSError(Exception):
    pass


async def _session(settings: dict, work):
    url = f"ws://{settings['obs_host']}:{settings['obs_port']}"
    ws = simpleobsws.WebSocketClient(
        url=url, password=settings["obs_password"],
        identification_parameters=simpleobsws.IdentificationParameters(ignoreNonFatalRequestChecks=False))
    try:
        await asyncio.wait_for(ws.connect(), timeout=6)
        await asyncio.wait_for(ws.wait_until_identified(), timeout=6)
    except Exception as exc:
        raise OBSError(f"Connexion impossible à {url} : vérifiez qu'OBS est ouvert, "
                       "le serveur WebSocket activé et le mot de passe.") from exc
    try:
        return await work(ws)
    finally:
        await ws.disconnect()


async def _call(ws, request_type: str, data: dict | None = None) -> dict:
    response = await ws.call(simpleobsws.Request(request_type, data or {}))
    if not response.ok():
        raise OBSError(f"OBS a refusé {request_type} : {response.requestStatus.comment}")
    return response.responseData or {}


def test_connection(settings: dict) -> str:
    async def work(ws):
        info = await _call(ws, "GetVersion")
        return f"Connecté à OBS {info.get('obsVersion', '?')}"
    return asyncio.run(_session(settings, work))


def ensure_browser_source(settings: dict, url: str) -> str:
    """Creates the browser source, or points the existing one at the widget URL."""
    name = settings["obs_source"].strip() or "Score Hockey"
    source_settings = {"url": url, "width": 1100, "height": 160, "reroute_audio": False}

    async def work(ws):
        inputs = await _call(ws, "GetInputList", {"inputKind": "browser_source"})
        if any(item.get("inputName") == name for item in inputs.get("inputs", [])):
            await _call(ws, "SetInputSettings", {"inputName": name, "inputSettings": source_settings})
            return f"Source « {name} » mise à jour."
        scene = settings["obs_scene"].strip()
        if not scene:
            scene = (await _call(ws, "GetCurrentProgramScene"))["currentProgramSceneName"]
        await _call(ws, "CreateInput", {"sceneName": scene, "inputName": name,
                                        "inputKind": "browser_source", "inputSettings": source_settings})
        return f"Source « {name} » créée dans la scène « {scene} »."
    return asyncio.run(_session(settings, work))
