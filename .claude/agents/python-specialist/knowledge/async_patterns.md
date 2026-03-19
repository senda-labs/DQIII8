# Async/Await — DQIII8 Patterns

## Core Rule

Async ONLY for I/O-bound work. NEVER for CPU-only work.

```python
# CORRECT — I/O bound: API calls, file reads, network
async def fetch_data(url: str) -> dict:
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            return await response.json()

# INCORRECT — CPU-only work does not benefit from async
async def process_matrix(data: list) -> list:  # async not needed
    return [x * 2 for x in data]
```

## Pattern: Parallel API Call Batch

Used in DQIII8 for multi-segment TTS and OpenRouter/Groq requests.

```python
import asyncio
import aiohttp

async def generate_tts_batch(segments: list[str], api_key: str) -> list[bytes]:
    """Generate TTS for multiple segments in parallel."""
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

## Pattern: asyncio.gather with error handling

```python
async def gather_with_fallback(coros: list) -> list:
    """gather that returns None on individual errors without aborting the batch."""
    results = await asyncio.gather(*coros, return_exceptions=True)
    return [
        None if isinstance(r, Exception) else r
        for r in results
    ]
```

## Pattern: Semaphore for Rate Limiting

Used in batch API calls with concurrency limits.

```python
async def rate_limited_batch(items: list, max_concurrent: int = 5) -> list:
    semaphore = asyncio.Semaphore(max_concurrent)

    async def _process_one(item):
        async with semaphore:
            return await process_item(item)

    return await asyncio.gather(*[_process_one(item) for item in items])
```

## Pattern: Async subprocess (FFmpeg pipeline)

```python
import asyncio

async def run_ffmpeg_async(cmd: list[str]) -> tuple[int, str, str]:
    """Launch FFmpeg non-blocking with asyncio."""
    proc = await asyncio.create_subprocess_shell(
        " ".join(cmd),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    return proc.returncode, stdout.decode("utf-8"), stderr.decode("utf-8")
```

## Pattern: Streaming Generator (avoid OOM)

Lesson: accumulating frames in List[np.ndarray] causes OOM.
Solution: generators + render_to_dir instead of accumulating in memory.

```python
# INCORRECT — accumulates everything in memory
async def render_all_frames(clips: list) -> list:
    frames = []
    for clip in clips:
        frames.extend(await render_clip(clip))  # OOM with 900 frames x 6MB
    return frames

# CORRECT — generator that frees immediately
async def render_frames_streaming(clips: list):
    for clip in clips:
        frame = await render_clip(clip)
        yield frame
        del frame  # free immediately
```

## Running Coroutines from Synchronous Code

```python
import asyncio

# In CLI scripts or main()
def main():
    result = asyncio.run(async_main())

# If an event loop is already active (Jupyter, FastAPI handlers)
import nest_asyncio
nest_asyncio.apply()
result = asyncio.get_event_loop().run_until_complete(async_main())
```

## Timeout on Async Calls

```python
async def fetch_with_timeout(url: str, timeout_s: float = 30.0) -> dict:
    try:
        async with asyncio.timeout(timeout_s):
            return await fetch_data(url)
    except asyncio.TimeoutError:
        raise TimeoutError(f"Request to {url} timed out after {timeout_s}s")
```

## Common Anti-Patterns

| Anti-pattern | Problem | Solution |
|-------------|---------|----------|
| async on CPU-only function | Overhead with no benefit | Remove async |
| await in loop without gather | Serializes calls | Use asyncio.gather |
| New session per request | Connection overhead | Reuse ClientSession |
| time.sleep() in coroutine | Blocks the event loop | await asyncio.sleep() |
| Accumulate async frames in list | OOM in video pipelines | Generator + del immediately |
