import os
import shutil
import tempfile
from pathlib import Path, PureWindowsPath
from typing import List

from fastapi import UploadFile, APIRouter, HTTPException, File, Depends

from app.config import get_settings
from app.utils.logger import get_logger
from app.schemas import DocumentListResponse, DeleteResponse, UploadResponse, DocumentInfo
from app.rag.loaders import extract_text
from app.rag.pipeline import ingest_document, ingest_pdf_as_images
from app.rag.vector_store import get_vector_store, get_image_vector_store
from app.rag.hybrid_search import get_hybrid_search
from ..auth.deps import get_current_user
from ..auth.database import User

router = APIRouter(prefix="/api/documents", tags=["documents"])
logger = get_logger(__name__)
ALLOWED_EXTENSIONS = {".txt", ".md", ".pdf"}


def _document_name(name: str | None) -> str:
    """Accept a display filename, never a client-controlled filesystem path.

    Check both Windows and POSIX syntax regardless of the server OS.
    Ordinary Unicode names (including Persian) remain unchanged.
    """
    if (
        not name
        or name in {".", ".."}
        or name.endswith((" ", "."))
        or any(char in name for char in '/\\:<>"|?*')
        or any(ord(char) < 32 or ord(char) == 127 for char in name)
        or PureWindowsPath(name).is_reserved()
        or Path(name).name != name
    ):
        raise HTTPException(status_code=400, detail="Invalid document filename")
    return name


def _child_path(parent: Path, name: str) -> Path:
    """Reject symlinks and any existing path resolving outside its parent."""
    parent = parent.resolve()
    candidate = parent / name
    if candidate.is_symlink() or candidate.resolve().parent != parent:
        raise HTTPException(status_code=400, detail="Invalid document storage path")
    return candidate


def _user_storage_dir(root: str, user_id: int) -> Path:
    return _child_path(Path(root), str(user_id))


def _user_upload_dir(user_id: int) -> Path:
    upload_dir = _user_storage_dir(get_settings().UPLOAD_DIR, user_id)
    upload_dir.mkdir(parents=True, exist_ok=True)
    return upload_dir


def _write_upload(destination: Path, content: bytes) -> None:
    """Replace the directory entry atomically instead of following a file link.

    Temporary files live in the same directory so os.replace is atomic.
    User storage directories must not be writable by untrusted OS users.
    """
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(content)
        os.replace(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


@router.post("/upload", response_model=UploadResponse)
async def upload_documents(
    files: List[UploadFile] = File(...),
    current_user: User = Depends(get_current_user),
) -> UploadResponse:
    upload_dir = _user_upload_dir(current_user.id)

    # Validate every name before writing any file from this request.
    validated = []
    for file in files:
        name = _document_name(file.filename)
        suffix = Path(name).suffix.lower()
        if suffix not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"File format {name} is not supported. Allowed formats: {sorted(ALLOWED_EXTENSIONS)}",
            )
        destination = _child_path(upload_dir, name)
        validated.append((file, name, suffix, destination))

    results: List[DocumentInfo] = []
    for file, name, suffix, destination in validated:
        content = await file.read()
        _write_upload(destination, content)
        try:
            settings = get_settings()
            if suffix == ".pdf" and settings.PDF_PROCESSING_MODE == "image":
                chunks_count = ingest_pdf_as_images(name, destination, user_id=current_user.id)
            else:
                raw_text = extract_text(destination)
                chunks_count = ingest_document(name, raw_text, user_id=current_user.id)
        except Exception as exc:
            logger.exception("Error processing file: %s", name)
            raise HTTPException(
                status_code=500,
                detail=f"Error processing file {name}: {exc}",
            ) from exc
        results.append(DocumentInfo(document_name=name, chunks_count=chunks_count))

    return UploadResponse(
        message=f"{len(results)} files added to vector database",
        documents=results,
    )


@router.get("", response_model=DocumentListResponse)
def list_documents(
    current_user: User = Depends(get_current_user),
) -> DocumentListResponse:
    vector_store = get_vector_store()
    image_vector_store = get_image_vector_store()
    names = set(vector_store.list_documents(user_id=current_user.id))
    names.update(image_vector_store.list_documents(user_id=current_user.id))
    return DocumentListResponse(documents=sorted(names))


@router.delete("/{document_name}", response_model=DeleteResponse)
def delete_document(
    document_name: str,
    current_user: User = Depends(get_current_user),
) -> DeleteResponse:
    # Check filesystem targets before changing either vector store.
    document_name = _document_name(document_name)
    upload_dir = _user_upload_dir(current_user.id)
    file_path = _child_path(upload_dir, document_name)
    settings = get_settings()
    image_user_dir = _user_storage_dir(settings.IMAGES_DIR, current_user.id)
    images_dir = _child_path(image_user_dir, Path(document_name).stem)

    vector_store = get_vector_store()
    image_vector_store = get_image_vector_store()
    vector_store.delete_document(document_name, user_id=current_user.id)
    image_vector_store.delete_document(document_name, user_id=current_user.id)
    get_hybrid_search().refresh(current_user.id)

    try:
        file_path.unlink(missing_ok=True)
    except Exception:
        logger.exception(
            "Could not remove uploaded file '%s' for user %s.",
            document_name, current_user.id,
        )
    if images_dir.exists():
        try:
            shutil.rmtree(images_dir)
        except Exception:
            logger.exception(
                "Could not remove page images for '%s' for user %s.",
                document_name, current_user.id,
            )
    return DeleteResponse(message=f"{document_name} deleted successfully")
