"""Upload path regression tests with isolated storage and mocked RAG services.

Run from the repository root:
    python -m unittest discover -s tests -p document_upload_test.py -v

Requires the backend FastAPI/Pydantic dependencies, but no database,
embedding models, provider credentials, or network access.
"""
import asyncio
import importlib.util
import io
import logging
from pathlib import Path
import sys
import tempfile
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from fastapi import HTTPException, UploadFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


def stub(name, **members):
    module = ModuleType(name)
    module.__dict__.update(members)
    return module


class DocumentUploadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.settings = SimpleNamespace(
            UPLOAD_DIR=str(self.root / "uploads"),
            IMAGES_DIR=str(self.root / "images"),
            PDF_PROCESSING_MODE="image",
        )
        self.text_store = Mock()
        self.image_store = Mock()
        self.hybrid = Mock()
        self.ingest_text = Mock(return_value=2)
        self.ingest_images = Mock(return_value=3)
        modules = {
            "app.config": stub("app.config", get_settings=lambda: self.settings),
            "app.utils.logger": stub("app.utils.logger", get_logger=logging.getLogger),
            "app.rag.loaders": stub("app.rag.loaders", extract_text=lambda p: p.read_text(encoding="utf-8")),
            "app.rag.pipeline": stub("app.rag.pipeline", ingest_document=self.ingest_text, ingest_pdf_as_images=self.ingest_images),
            "app.rag.vector_store": stub("app.rag.vector_store", get_vector_store=lambda: self.text_store, get_image_vector_store=lambda: self.image_store),
            "app.rag.hybrid_search": stub("app.rag.hybrid_search", get_hybrid_search=lambda: self.hybrid),
            "app.auth.deps": stub("app.auth.deps", get_current_user=lambda: None),
            "app.auth.database": stub("app.auth.database", User=SimpleNamespace),
        }
        spec = importlib.util.spec_from_file_location(
            "app.routers._document_route_under_test",
            ROOT / "backend/app/routers/documents.py",
        )
        assert spec is not None and spec.loader is not None
        self.routes = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, modules):
            spec.loader.exec_module(self.routes)
        self.user = SimpleNamespace(id=7)

    def upload(self, filename, content=b"study notes", user=None):
        file = UploadFile(filename=filename, file=io.BytesIO(content))
        try:
            return asyncio.run(self.routes.upload_documents([file], user or self.user))
        finally:
            file.file.close()

    def test_normal_text_upload_preserves_response_and_ownership(self):
        result = self.upload("notes.txt")
        self.assertEqual(result.documents[0].document_name, "notes.txt")
        self.assertEqual(result.documents[0].chunks_count, 2)
        self.assertEqual((self.root / "uploads/7/notes.txt").read_bytes(), b"study notes")
        self.ingest_text.assert_called_once_with("notes.txt", "study notes", user_id=7)

    def test_persian_filename_is_preserved(self):
        name = "یادداشت فیزیک.txt"
        result = self.upload(name)
        self.assertEqual(result.documents[0].document_name, name)
        self.assertTrue((self.root / "uploads/7" / name).is_file())

    def test_pdf_uses_image_pipeline(self):
        result = self.upload("book.pdf", b"mock PDF; renderer is mocked")
        self.assertEqual(result.documents[0].chunks_count, 3)
        self.ingest_images.assert_called_once_with(
            "book.pdf", self.root / "uploads/7/book.pdf", user_id=7,
        )
        self.ingest_text.assert_not_called()

    def test_same_name_is_isolated_between_accounts(self):
        self.upload("notes.txt", b"first")
        self.upload("notes.txt", b"second", SimpleNamespace(id=8))
        self.assertEqual((self.root / "uploads/7/notes.txt").read_bytes(), b"first")
        self.assertEqual((self.root / "uploads/8/notes.txt").read_bytes(), b"second")

    def test_unsafe_names_are_rejected(self):
        names = [
            "../outside.txt", "..\\outside.txt", "nested/notes.txt",
            "nested\\notes.txt", "C:\\notes.txt", "C:notes.txt",
            str(self.root / "absolute.txt"), "", None, ".", "..",
            "bad\x00.txt", "bad\n.txt",
        ]
        for name in names:
            with self.subTest(name=name):
                with self.assertRaises(HTTPException) as caught:
                    self.upload(name)
                self.assertEqual(caught.exception.status_code, 400)
        self.ingest_text.assert_not_called()
        self.ingest_images.assert_not_called()
        self.assertFalse((self.root / "absolute.txt").exists())
        self.assertFalse((self.root / "uploads/outside.txt").exists())

    def test_unsupported_extension_is_rejected(self):
        with self.assertRaises(HTTPException) as caught:
            self.upload("program.py")
        self.assertEqual(caught.exception.status_code, 400)
        self.ingest_text.assert_not_called()

    def test_batch_validates_all_paths_before_writing(self):
        files = [
            UploadFile(filename="notes.txt", file=io.BytesIO(b"valid")),
            UploadFile(filename="../outside.txt", file=io.BytesIO(b"invalid")),
        ]
        try:
            with self.assertRaises(HTTPException) as caught:
                asyncio.run(self.routes.upload_documents(files, self.user))
            self.assertEqual(caught.exception.status_code, 400)
            self.assertFalse((self.root / "uploads/7/notes.txt").exists())
            self.ingest_text.assert_not_called()
        finally:
            for file in files:
                file.file.close()

    def make_symlink(self, link, target, directory=False):
        link.parent.mkdir(parents=True, exist_ok=True)
        try:
            link.symlink_to(target, target_is_directory=directory)
        except (OSError, NotImplementedError):
            self.skipTest("Symlink creation is not supported in this environment")

    def test_destination_symlink_cannot_overwrite_outside_file(self):
        outside = self.root / "outside.txt"
        outside.write_text("keep", encoding="utf-8")
        self.make_symlink(self.root / "uploads/7/notes.txt", outside)
        with self.assertRaises(HTTPException) as caught:
            self.upload("notes.txt", b"overwrite")
        self.assertEqual(caught.exception.status_code, 400)
        self.assertEqual(outside.read_text(encoding="utf-8"), "keep")
        self.ingest_text.assert_not_called()

    def test_user_directory_symlink_is_rejected(self):
        outside = self.root / "outside"
        outside.mkdir()
        self.make_symlink(self.root / "uploads/7", outside, directory=True)
        with self.assertRaises(HTTPException) as caught:
            self.upload("notes.txt")
        self.assertEqual(caught.exception.status_code, 400)
        self.assertFalse((outside / "notes.txt").exists())

    def test_unsafe_delete_is_rejected_before_store_changes(self):
        for name in ["..", ".", "../notes.txt", "..\\notes.txt", "C:notes.txt"]:
            with self.subTest(name=name):
                with self.assertRaises(HTTPException) as caught:
                    self.routes.delete_document(name, self.user)
                self.assertEqual(caught.exception.status_code, 400)
        self.text_store.delete_document.assert_not_called()
        self.image_store.delete_document.assert_not_called()

    def test_normal_delete_remains_user_scoped(self):
        self.upload("notes.txt")
        self.routes.delete_document("notes.txt", self.user)
        self.text_store.delete_document.assert_called_once_with("notes.txt", user_id=7)
        self.image_store.delete_document.assert_called_once_with("notes.txt", user_id=7)
        self.assertFalse((self.root / "uploads/7/notes.txt").exists())


if __name__ == "__main__":
    unittest.main()
