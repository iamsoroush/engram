"""HTTP response plumbing shared by capture/share media routes."""

from fastapi import Response


def ranged_file_response(content: bytes, media_type: str, filename: str, range_header: str | None = None) -> Response:
    """Return file content with byte-range support for mobile media playback.

    Honors a single ``Range: bytes=start-end`` request header, replying with ``206 Partial
    Content`` for a valid range or ``416 Range Not Satisfiable`` for a malformed/out-of-bounds
    one. With no ``Range`` header the full body is returned. Used by the authenticated
    capture-file-content route and the public share-media route.
    """
    headers = {
        "Accept-Ranges": "bytes",
        "Content-Disposition": f'inline; filename="{filename}"',
    }
    content_length = len(content)
    if not range_header:
        headers["Content-Length"] = str(content_length)
        return Response(content=content, media_type=media_type, headers=headers)

    unit, _, range_value = range_header.partition("=")
    start_text, _, end_text = range_value.partition("-")
    if unit != "bytes" or not start_text:
        headers["Content-Range"] = f"bytes */{content_length}"
        return Response(status_code=416, media_type=media_type, headers=headers)

    try:
        start = int(start_text)
        end = int(end_text) if end_text else content_length - 1
    except ValueError:
        headers["Content-Range"] = f"bytes */{content_length}"
        return Response(status_code=416, media_type=media_type, headers=headers)

    if start >= content_length or end < start:
        headers["Content-Range"] = f"bytes */{content_length}"
        return Response(status_code=416, media_type=media_type, headers=headers)

    end = min(end, content_length - 1)
    partial = content[start : end + 1]
    headers["Content-Length"] = str(len(partial))
    headers["Content-Range"] = f"bytes {start}-{end}/{content_length}"
    return Response(content=partial, status_code=206, media_type=media_type, headers=headers)
