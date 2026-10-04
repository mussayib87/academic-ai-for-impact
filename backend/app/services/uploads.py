from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile

IMAGE_MIME_TYPES = {
    '.png': {'image/png'},
    '.jpg': {'image/jpeg'},
    '.jpeg': {'image/jpeg'},
    '.gif': {'image/gif'},
    '.webp': {'image/webp'},
}


async def store_submission(file: UploadFile, student_id: int, assignment, settings) -> tuple[Path, str]:
    original = Path(file.filename or 'submission').name
    extension = Path(original).suffix.lower()
    allowed = {item.lower() for item in (assignment.allowed_file_types or [])}
    if not extension or extension not in allowed:
        raise ValueError('This file type is not allowed for the assignment')
    if extension in IMAGE_MIME_TYPES and (not file.content_type or file.content_type.lower() not in IMAGE_MIME_TYPES[extension]):
        raise ValueError('Image MIME type does not match the file extension')

    directory = (settings.upload_directory / f'student-{student_id}' / f'assignment-{assignment.id}').resolve()
    root = settings.upload_directory.resolve()
    if root not in directory.parents and directory != root:
        raise ValueError('Invalid upload destination')
    directory.mkdir(parents=True, exist_ok=True)
    safe_name = f'{uuid4().hex}{extension}'
    target = directory / safe_name
    total = 0
    header = b''
    try:
        with target.open('wb') as output:
            while chunk := await file.read(1024 * 1024):
                if len(header) < 32:
                    header += chunk[:32 - len(header)]
                total += len(chunk)
                if total > min(settings.max_upload_size, assignment.max_file_size):
                    raise ValueError('File exceeds the upload size limit')
                output.write(chunk)
        signatures = {
            '.pdf': header.startswith(b'%PDF-'),
            '.png': header.startswith(b'\x89PNG\r\n\x1a\n'),
            '.jpg': header.startswith(b'\xff\xd8\xff'),
            '.jpeg': header.startswith(b'\xff\xd8\xff'),
            '.gif': header.startswith((b'GIF87a', b'GIF89a')),
            '.webp': len(header) >= 12 and header.startswith(b'RIFF') and header[8:12] == b'WEBP',
            '.zip': header.startswith(b'PK\x03\x04'),
            '.docx': header.startswith(b'PK\x03\x04'),
            '.pptx': header.startswith(b'PK\x03\x04'),
            '.xlsx': header.startswith(b'PK\x03\x04'),
        }
        if extension in signatures and not signatures[extension]:
            raise ValueError('File contents do not match the selected file type')
        if extension == '.txt' and b'\x00' in header:
            raise ValueError('Text files cannot contain binary null bytes')
    except Exception:
        target.unlink(missing_ok=True)
        raise
    finally:
        await file.close()
    return target, original[:255]