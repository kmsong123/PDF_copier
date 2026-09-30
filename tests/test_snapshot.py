import hashlib
from contextlib import closing
import sys
import tempfile
import unittest
from pathlib import Path

import pypdfium2 as pdfium
from PIL import ImageChops
from pypdf import PdfReader, PdfWriter
from pypdf.constants import UserAccessPermissions
from pypdf.generic import FloatObject, NameObject, RectangleObject
from reportlab.pdfgen import canvas

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pdf_snapshot import Cancelled, convert_pdf


def make_fixture(folder):
    base = folder / "base.pdf"
    c = canvas.Canvas(str(base), pagesize=(360, 480))
    c.setFillColorRGB(0.08, 0.2, 0.4)
    c.rect(20, 395, 320, 65, fill=1, stroke=0)
    c.setFillColorRGB(1, 1, 1)
    c.setFont("Helvetica-Bold", 20)
    c.drawString(35, 425, "PDF Snapshot test")
    c.setFillColorRGB(0, 0, 0)
    c.setFont("Helvetica", 11)
    c.drawString(30, 365, "Page 1: text, colors, transparency, and a form")
    c.acroForm.textfield(name="name", value="Visible form value", x=30, y=305,
                         width=285, height=25, fontSize=13)
    for index in range(4):
        c.setFillColorRGB(index / 4, 0.55, 1 - index / 4)
        c.rect(30 + index * 75, 220, 70, 45, fill=1, stroke=0)
    c.setFillAlpha(0.4)
    c.setFillColorRGB(1, 0, 0)
    c.circle(125, 220, 40, fill=1, stroke=0)
    c.setFillAlpha(1)
    c.setFillColorRGB(0, 0, 0)
    c.setFont("Helvetica", 8)
    c.drawString(30, 90, "Small text should remain readable at printing resolution.")
    c.showPage()
    c.setPageSize((360, 240))
    c.setFont("Helvetica-Bold", 18)
    c.drawString(25, 200, "Page 2: rotated 90 degrees")
    c.setStrokeColorRGB(0, 0.6, 0.3)
    c.rect(10, 10, 340, 220)
    c.line(25, 35, 300, 150)
    c.showPage()
    c.setPageSize((400, 400))
    c.setFont("Helvetica", 18)
    c.drawString(60, 290, "Page 3: crop + UserUnit")
    c.setFillColorRGB(0.7, 0.2, 0.5)
    c.rect(70, 100, 160, 100, fill=1, stroke=0)
    c.showPage()
    c.save()
    writer = PdfWriter(clone_from=str(base))
    writer.pages[1].rotate(90)
    writer.pages[2].cropbox = RectangleObject((40, 50, 360, 350))
    writer.pages[2][NameObject("/UserUnit")] = FloatObject(2)
    original = folder / "fixture.pdf"
    writer.write(original)
    writer.close()
    return original


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name)
        self.source = make_fixture(self.folder)

    def tearDown(self):
        self.temp.cleanup()

    def test_restricted_pdf_geometry_forms_and_lossless_pixels(self):
        restricted = self.folder / "restricted.pdf"
        writer = PdfWriter(clone_from=str(self.source))
        writer.encrypt(user_password="", owner_password="owner-secret",
                       permissions_flag=UserAccessPermissions(0), algorithm="AES-256")
        writer.write(restricted)
        writer.close()
        before = hashlib.sha256(restricted.read_bytes()).digest()
        updates = []
        result = convert_pdf(restricted, dpi=144,
                             progress=lambda done, total: updates.append((done, total)))
        self.assertEqual(before, hashlib.sha256(restricted.read_bytes()).digest())
        self.assertEqual(updates, [(0, 3), (1, 3), (2, 3), (3, 3)])
        with result.open("rb") as stream, pdfium.PdfDocument(str(restricted)) as original:
            original.init_forms()
            output = PdfReader(stream)
            self.assertFalse(output.is_encrypted)
            self.assertEqual(len(output.pages), 3)
            self.assertFalse(output.get_fields())
            for i, (width, height, unit) in enumerate([(360, 480, 1), (240, 360, 1), (640, 600, 2)]):
                page = output.pages[i]
                self.assertAlmostEqual(float(page.mediabox.width), width, places=3)
                self.assertAlmostEqual(float(page.mediabox.height), height, places=3)
                self.assertEqual(page.extract_text(), "")
                self.assertFalse(page.get("/Annots"))
                self.assertEqual(len(page.images), 1)
                embedded = page.images[0].image.convert("RGB")
                with closing(original[i]) as source_page:
                    with closing(source_page.render(scale=2 * unit, draw_annots=True,
                                            may_draw_forms=True)) as bitmap:
                        expected = bitmap.to_pil().convert("RGB")
                        self.assertEqual(embedded.size, expected.size)
                        self.assertIsNone(ImageChops.difference(embedded, expected).getbbox())
                        expected.close()
                embedded.close()

    def test_open_password(self):
        protected = self.folder / "password.pdf"
        writer = PdfWriter(clone_from=str(self.source))
        writer.encrypt("open-secret", "owner-secret", algorithm="AES-256")
        writer.write(protected)
        writer.close()
        target = self.folder / "copy.pdf"
        with self.assertRaises(pdfium.PdfiumError):
            convert_pdf(protected, target, password="wrong", dpi=72)
        self.assertFalse(target.exists())
        convert_pdf(protected, target, password="open-secret", dpi=72)
        self.assertTrue(target.exists())

    def test_never_overwrite_source_or_existing_output(self):
        before = self.source.read_bytes()
        with self.assertRaises(ValueError):
            convert_pdf(self.source, self.source)
        self.assertEqual(before, self.source.read_bytes())
        target = self.folder / "existing.pdf"
        target.write_bytes(b"keep me")
        with self.assertRaises(FileExistsError):
            convert_pdf(self.source, target)
        self.assertEqual(target.read_bytes(), b"keep me")

    def test_cancellation_cleans_partial_output(self):
        target = self.folder / "cancelled.pdf"
        stop = [False]
        def on_progress(done, total):
            if done == 1:
                stop[0] = True
        with self.assertRaises(Cancelled):
            convert_pdf(self.source, target, dpi=72, progress=on_progress,
                        cancelled=lambda: stop[0])
        self.assertFalse(target.exists())
        self.assertEqual(list(self.folder.glob(".pdf-snapshot-*")), [])

    def test_competing_output_is_preserved(self):
        target = self.folder / "race.pdf"
        def on_progress(done, total):
            if done == total:
                target.write_bytes(b"created during conversion")
        with self.assertRaises(FileExistsError):
            convert_pdf(self.source, target, dpi=72, progress=on_progress)
        self.assertEqual(target.read_bytes(), b"created during conversion")
        self.assertEqual(list(self.folder.glob(".pdf-snapshot-*")), [])

    def test_invalid_pdf_and_resolution(self):
        for dpi in (0, 601, 300.5):
            with self.assertRaises(ValueError):
                convert_pdf(self.source, dpi=dpi)
        broken = self.folder / "broken.pdf"
        broken.write_text("not a pdf", encoding="utf-8")
        with self.assertRaises(pdfium.PdfiumError):
            convert_pdf(broken)
        self.assertEqual(list(self.folder.glob(".pdf-snapshot-*")), [])


if __name__ == "__main__":
    unittest.main()
