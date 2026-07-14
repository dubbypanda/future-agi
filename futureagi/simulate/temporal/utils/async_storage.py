"""Async storage helpers for Temporal activities."""

from __future__ import annotations

from typing import Optional

import httpx
import structlog

logger = structlog.get_logger(__name__)

# Max file size: 100MB
MAX_AUDIO_FILE_SIZE = 100 * 1024 * 1024

# Timeout settings
DOWNLOAD_TIMEOUT = 200.0  # seconds


async def download_audio_from_url_async(
    audio_url: Optional[str],
    max_retries: int = 5,
    timeout: float = DOWNLOAD_TIMEOUT,
    *,
    provider: Optional[str] = None,
    api_key: Optional[str] = None,
    call_id: Optional[str] = None,
    artifact_type: Optional[str] = None,
) -> bytes:
    """Async download of an audio file to bytes; routes Vapi through the auth endpoint."""
    from tracer.utils.vapi_recording import VapiRecordingService

    if VapiRecordingService.is_authenticated_download(provider, api_key, call_id, artifact_type):
        return await VapiRecordingService.download_artifact_async(
            call_id=call_id,
            artifact_type=artifact_type,
            api_key=api_key,
            timeout_seconds=timeout,
        )

    if not audio_url:
        raise ValueError("audio_url is required for unauthenticated download")

    last_error: Optional[Exception] = None
    async with httpx.AsyncClient(timeout=timeout) as client:
        for attempt in range(max_retries):
            try:
                logger.debug(f"Downloading audio (attempt {attempt + 1}): {audio_url}")
                async with client.stream("GET", audio_url) as response:
                    response.raise_for_status()
                    chunks = []
                    total_size = 0
                    async for chunk in response.aiter_bytes(chunk_size=8192):
                        chunks.append(chunk)
                        total_size += len(chunk)
                        if total_size > MAX_AUDIO_FILE_SIZE:
                            raise ValueError(
                                f"Audio file exceeds maximum size of "
                                f"{MAX_AUDIO_FILE_SIZE / (1024 * 1024):.1f}MB"
                            )
                    audio_data = b"".join(chunks)
                    logger.info(
                        f"Downloaded audio: {len(audio_data)} bytes from {audio_url}"
                    )
                    return audio_data

            except (httpx.HTTPError, httpx.StreamError) as e:
                last_error = e
                logger.warning(
                    f"Download attempt {attempt + 1} failed for {audio_url}: {e}"
                )
                if attempt < max_retries - 1:
                    import asyncio

                    await asyncio.sleep(2**attempt)
                continue

    raise last_error or httpx.HTTPError(f"Failed to download {audio_url}")


async def _convert_audio_url_to_s3_async_with_size(
    call_id: str,
    audio_url: Optional[str],
    url_type: str = "audio",
    *,
    provider: Optional[str] = None,
    api_key: Optional[str] = None,
    artifact_type: Optional[str] = None,
) -> tuple[str, int]:
    """Internal worker: download + upload, reports bytes uploaded.

    Returns ``(s3_url_or_original_on_failure, bytes_uploaded_to_s3)``.
    ``bytes_uploaded_to_s3`` is 0 when the source URL was already on S3
    or the upload did not succeed.
    """
    from tracer.utils.vapi_recording import VapiRecordingService

    vapi_authenticated = VapiRecordingService.is_authenticated_download(
        provider, api_key, call_id, artifact_type
    )

    if not audio_url and not vapi_authenticated:
        return audio_url, 0

    if audio_url and ("amazonaws.com" in str(audio_url) or "minio" in str(audio_url)):
        logger.info(f"{url_type} URL is already S3: {audio_url}")
        return audio_url, 0

    try:
        logger.info(
            f"Converting {url_type} URL to S3: "
            f"{audio_url or f'vapi:{artifact_type}:{call_id}'}"
        )

        audio_bytes = await download_audio_from_url_async(
            audio_url,
            provider=provider,
            api_key=api_key,
            call_id=call_id,
            artifact_type=artifact_type,
        )

        import asyncio

        loop = asyncio.get_running_loop()

        def do_upload():
            from tfc.utils.storage import upload_audio_to_s3

            object_key = f"call-recordings/{call_id}/{url_type}.mp3"
            audio_data = {"bytes": audio_bytes}
            return upload_audio_to_s3(audio_data, object_key=object_key)

        s3_url = await loop.run_in_executor(None, do_upload)
        logger.info(f"Successfully converted {url_type} URL to S3: {s3_url}")
        return s3_url, len(audio_bytes)

    except Exception as e:
        logger.error("s3_conversion_failed", url_type=url_type, provider=provider, artifact_type=artifact_type, call_id=call_id, error=str(e), exc_info=True)
        return audio_url, 0


async def convert_audio_url_to_s3_async(
    call_id: str,
    audio_url: Optional[str],
    url_type: str = "audio",
    *,
    provider: Optional[str] = None,
    api_key: Optional[str] = None,
    artifact_type: Optional[str] = None,
) -> str:
    """Async convert_audio_url_to_s3. Returns the S3 URL, or the original
    URL if the conversion failed. See
    :func:`convert_audio_url_to_s3_async_with_size` for the semantics of
    the auth kwargs.
    """
    s3_url, _ = await _convert_audio_url_to_s3_async_with_size(
        call_id,
        audio_url,
        url_type,
        provider=provider,
        api_key=api_key,
        artifact_type=artifact_type,
    )
    return s3_url


async def convert_audio_url_to_s3_async_with_size(
    call_id: str,
    audio_url: Optional[str],
    url_type: str = "audio",
    *,
    provider: Optional[str] = None,
    api_key: Optional[str] = None,
    artifact_type: Optional[str] = None,
) -> tuple[str, int]:
    """Like :func:`convert_audio_url_to_s3_async` but also reports uploaded bytes.

    Returns ``(s3_url_or_original_on_failure, bytes_uploaded)``.
    ``bytes_uploaded`` is 0 when nothing was uploaded (already-on-S3 or
    failure), so billing sites can sum it directly without re-checking
    the URL.
    """
    return await _convert_audio_url_to_s3_async_with_size(
        call_id,
        audio_url,
        url_type,
        provider=provider,
        api_key=api_key,
        artifact_type=artifact_type,
    )
