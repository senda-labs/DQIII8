# Async/Await — Patrones JARVIS

## Regla Fundamental

Async SOLO para trabajo I/O-bound. NUNCA para trabajo CPU puro.

```python
# CORRECTO — I/O bound: llamadas API, lectura de archivos, red
async def fetch_data(url: str) -> dict:
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            return await response.json()

# INCORRECTO — CPU puro no se beneficia de async
async def process_matrix(data: list) -> list:  # no async necesario
    return [x * 2 for x in data]
```

## Patrón: Batch de API Calls en Paralelo

Usado en JARVIS para TTS multi-segmento y requests a OpenRouter/Groq.

```python
import asyncio
import aiohttp

async def generate_tts_batch(segments: list[str], api_key: str) -> list[bytes]:
    """Genera TTS para múltiples segmentos en paralelo."""
    async def _one(session: aiohttp.ClientSession, text: str) -> bytes:
        async with session.post(
            "https://api.elevenlabs.io/v1/text-to-speech/voice_id",
            json={"text": text},
            headers={"xi-api-key": api_key},
        ) as resp:
            resp.raise_for_status()
            return await resp.read()

    async with aiohttp.ClientSession() as session:
        tasks = [_one(session, seg) for seg in segments]
        return await asyncio.gather(*tasks)
```

## Patrón: asyncio.gather con manejo de errores

```python
async def gather_with_fallback(coros: list) -> list:
    """gather que retorna None en errores individuales sin abortar el batch."""
    results = await asyncio.gather(*coros, return_exceptions=True)
    return [
        None if isinstance(r, Exception) else r
        for r in results
    ]
```

## Patrón: Semáforo para Rate Limiting

Usado en batch de llamadas a APIs con límites de concurrencia.

```python
async def rate_limited_batch(items: list, max_concurrent: int = 5) -> list:
    semaphore = asyncio.Semaphore(max_concurrent)

    async def _process_one(item):
        async with semaphore:
            return await process_item(item)

    return await asyncio.gather(*[_process_one(item) for item in items])
```

## Patrón: subprocess async (pipeline FFmpeg)

```python
import asyncio

async def run_ffmpeg_async(cmd: list[str]) -> tuple[int, str, str]:
    """Lanza FFmpeg de forma no bloqueante con asyncio."""
    proc = await asyncio.create_subprocess_shell(
        " ".join(cmd),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    return proc.returncode, stdout.decode("utf-8"), stderr.decode("utf-8")
```

## Patrón: Streaming Generator (evitar OOM)

Lección JARVIS: acumular frames en List[np.ndarray] causa OOM.
Solución: generators + render_to_dir en lugar de acumular en memoria.

```python
# INCORRECTO — acumula todo en memoria
async def render_all_frames(clips: list) -> list:
    frames = []
    for clip in clips:
        frames.extend(await render_clip(clip))  # OOM con 900 frames x 6MB
    return frames

# CORRECTO — generator que libera inmediatamente
async def render_frames_streaming(clips: list):
    for clip in clips:
        frame = await render_clip(clip)
        yield frame
        del frame  # liberar inmediatamente
```

## Ejecutar Coroutines desde Código Síncrono

```python
import asyncio

# En scripts CLI o main()
def main():
    result = asyncio.run(async_main())

# Si ya hay un event loop activo (Jupyter, FastAPI handlers)
import nest_asyncio
nest_asyncio.apply()
result = asyncio.get_event_loop().run_until_complete(async_main())
```

## Timeout en Llamadas Async

```python
async def fetch_with_timeout(url: str, timeout_s: float = 30.0) -> dict:
    try:
        async with asyncio.timeout(timeout_s):
            return await fetch_data(url)
    except asyncio.TimeoutError:
        raise TimeoutError(f"Request to {url} timed out after {timeout_s}s")
```

## Anti-Patrones Comunes en JARVIS

| Anti-patrón | Problema | Solución |
|-------------|---------|---------|
| async en función CPU pura | Overhead sin beneficio | Eliminar async |
| await en loop sin gather | Serializa las llamadas | Usar asyncio.gather |
| Nueva session por cada request | Overhead de conexión | Reusar ClientSession |
| time.sleep() en coroutine | Bloquea el event loop | await asyncio.sleep() |
| Acumular frames async en lista | OOM en pipelines video | Generator + del inmediato |
