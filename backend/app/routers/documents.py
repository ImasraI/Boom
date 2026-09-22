import shutil
from pathlib import Path
from typing import List

from fastapi import UploadFile, APIRouter, HTTPException, File, Depends

from app.config import get_settings
from app.utils.logger import get_logger
from app.schemas import (
    DocumentInfo,
    DocumentListResponse,
    DeleteResponse,
    UploadResponse,
)
from app.rag.loaders import extract_text
from app.rag.pipeline import ingest_document, ingest_pdf_as_images
from app.rag.vector_store import get_vector_store, get_image_vector_store
from app.rag.hybrid_search import get_hybrid_search

# Auth dependencies – every document route now requires a logged-in user
from ..auth.deps import get_current_user
from ..auth.database import User


# Create router for document-related endpoints
router = APIRouter(prefix="/api/documents", tags=["documents"])

# Initialize application logger
logger = get_logger(__name__)

# Supported document formats
ALLOWED_EXTENSIONS = {".txt", ".md", ".pdf"}


def _user_upload_dir(user_id: int) -> Path:
    """Each user gets their own folder under UPLOAD_DIR, so files never
    collide or leak between accounts."""
    settings = get_settings()
    upload_dir = Path(settings.UPLOAD_DIR) / str(user_id)
    upload_dir.mkdir(parents=True, exist_ok=True)
    return upload_dir


# Upload and process documents
@router.post("/upload", response_model=UploadResponse)
async def upload_documents(
    files: List[UploadFile] = File(...),
    current_user: User = Depends(get_current_user),
) -> UploadResponse:

    # Store uploads for this user only, isolated from every other account
    upload_dir = _user_upload_dir(current_user.id)

    # Store information about processed documents
    results: List[DocumentInfo] = []

    for file in files:

        # Get the file extension
        if file.filename:
            suffix = Path(file.filename).suffix.lower()

            # Check if the file format is supported
            if suffix not in ALLOWED_EXTENSIONS:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"File format {file.filename} is not supported. "
                        f"Allowed formats: {sorted(ALLOWED_EXTENSIONS)}"
                    )
                )

            # Path-traversal guard: only the bare filename is used, so a
            # crafted name like "../../app/main.py" can never escape the
            # user's own upload folder.
            safe_name = Path(file.filename).name
            if safe_name in ("", ".", ".."):
                raise HTTPException(status_code=400, detail="Invalid file name")

            # Size cap (MAX_UPLOAD_MB in .env): read nothing beyond the cap.
            max_bytes = get_settings().MAX_UPLOAD_MB * 1024 * 1024
            content = await file.read(max_bytes + 1)
            if len(content) > max_bytes:
                raise HTTPException(
                    status_code=413,
                    detail=f"فایل بزرگ‌تر از حد مجاز ({get_settings().MAX_UPLOAD_MB} مگابایت) است",
                )

            # Save the uploaded file inside this user's own folder
            destination = upload_dir / safe_name
            destination.write_bytes(content)

            try:
                settings = get_settings()

                if suffix == ".pdf" and settings.PDF_PROCESSING_MODE == "image":
                    # New pipeline: render each page as an image and embed
                    # it directly, skipping text extraction/OCR entirely.
                    chunks_count = ingest_pdf_as_images(
                        file.filename, destination, user_id=current_user.id
                    )
                else:
                    # Original pipeline: extract text and add document
                    # chunks to vector database, tagged with this user's id
                    raw_text = extract_text(destination)
                    chunks_count = ingest_document(
                        file.filename, raw_text, user_id=current_user.id
                    )

            except Exception as exc:
                # Log unexpected processing errors
                logger.exception(f"Error processing file: {file.filename}")

                raise HTTPException(
                    status_code=500,
                    detail=f"Error processing file {file.filename}: {exc}"
                ) from exc

            # Add document information to the response
            results.append(
                DocumentInfo(
                    document_name=file.filename,
                    chunks_count=chunks_count
                )
            )

    return UploadResponse(
        message=f"{len(results)} files added to vector database",
        documents=results
    )


# Get the list of stored documents for the current user
@router.get("", response_model=DocumentListResponse)
def list_documents(
    current_user: User = Depends(get_current_user),
) -> DocumentListResponse:

    # Documents can live in either the text-chunk store or the page-image
    # store depending on how each PDF was ingested; merge both name lists.
    vector_store = get_vector_store()
    image_vector_store = get_image_vector_store()

    names = set(vector_store.list_documents(user_id=current_user.id))
    names.update(image_vector_store.list_documents(user_id=current_user.id))

    return DocumentListResponse(documents=sorted(names))


# Delete a document from the vector database (and disk) for the current user
@router.delete("/{document_name}", response_model=DeleteResponse)
def delete_document(
    document_name: str,
    current_user: User = Depends(get_current_user),
) -> DeleteResponse:

    # Delete the document's chunks from both stores – scoped to this user,
    # so nobody can delete a document that belongs to a different account.
    # A document only ever lives in one of the two, but it's safe/cheap to
    # call delete on both since a no-op delete is a no-op.
    vector_store = get_vector_store()
    image_vector_store = get_image_vector_store()

    vector_store.delete_document(document_name, user_id=current_user.id)
    image_vector_store.delete_document(document_name, user_id=current_user.id)
    get_hybrid_search().refresh(current_user.id)

    # Also remove the physical file(s) from disk. Previously this step was
    # missing entirely, so the raw file kept sitting on disk even after
    # "deleting" it.
    upload_dir = _user_upload_dir(current_user.id)
    file_path = upload_dir / document_name
    try:
        file_path.unlink(missing_ok=True)
    except Exception:
        logger.exception(
            f"Could not remove uploaded file '{document_name}' from disk "
            f"for user {current_user.id}."
        )

    # Remove any rendered page images for this document (image pipeline)
    settings = get_settings()
    images_dir = (
        Path(settings.IMAGES_DIR) / str(current_user.id) / Path(document_name).stem
    )
    if images_dir.exists():
        try:
            shutil.rmtree(images_dir)
        except Exception:
            logger.exception(
                f"Could not remove page images for '{document_name}' "
                f"for user {current_user.id}."
            )

    return DeleteResponse(
        message=f"{document_name} deleted successfully"
    )
