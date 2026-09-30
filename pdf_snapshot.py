"""Local PDF-to-image-PDF converter. Run without arguments for the Windows UI."""
from __future__ import annotations

import argparse
from contextlib import closing
import getpass
import math
import os
from pathlib import Path
import queue
import tempfile
import threading
import warnings

import pypdfium2 as pdfium
from pypdf import PdfReader
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas


class Cancelled(Exception):
    pass


def convert_pdf(source, destination=None, *, dpi=300, password="", progress=None,
                cancelled=None):
    """Render visible pages, including annotations/forms, into a new unencrypted PDF.

    The source and existing destinations are never overwritten. Progress receives
    (completed_pages, total_pages). No external processes or network calls are used.
    """
    source = Path(source).expanduser().resolve(strict=True)
    destination = (Path(destination).expanduser() if destination else
                   source.with_name(source.stem + "-printable.pdf")).resolve()
    if source == destination:
        raise ValueError("Choose an output filename different from the original PDF.")
    if destination.suffix.lower() != ".pdf":
        raise ValueError("The output filename must end in .pdf.")
    if destination.exists():
        raise FileExistsError("The output already exists. Choose a new filename.")
    if not destination.parent.is_dir():
        raise ValueError("The output folder does not exist.")
    if not isinstance(dpi, int) or not 72 <= dpi <= 600:
        raise ValueError("Resolution must be an integer between 72 and 600 DPI.")

    def check_cancelled():
        if cancelled and cancelled():
            raise Cancelled("Conversion cancelled. No output was saved.")

    temporary = None
    try:
        with pdfium.PdfDocument(str(source), password=password) as document:
            # A failed XFA initialization must not silently create an incomplete copy.
            with warnings.catch_warnings():
                warnings.simplefilter("error", pdfium.PdfiumWarning)
                document.init_forms()
            total = len(document)
            if not total:
                raise ValueError("The PDF has no pages.")
            # PDFium reports dimensions in canvas units, without the PDF /UserUnit.
            with source.open("rb") as source_stream:
                metadata = PdfReader(source_stream)
                if metadata.is_encrypted and not metadata.decrypt(password):
                    raise ValueError("The PDF open password is incorrect.")
                units = [float(page.get("/UserUnit", 1)) for page in metadata.pages]
            if len(units) != total:
                raise ValueError("The PDF has inconsistent page information.")
            fd, temporary = tempfile.mkstemp(prefix=".pdf-snapshot-", suffix=".tmp",
                                             dir=destination.parent)
            os.close(fd)
            output = canvas.Canvas(temporary, pageCompression=1)
            output.setTitle(source.stem + " - printable image copy")
            output.setCreator("PDF Snapshot (local page rendering)")
            if progress:
                progress(0, total)
            for index in range(total):
                check_cancelled()
                with closing(document[index]) as page:
                    unit = units[index]
                    width, height = (value * unit for value in page.get_size())
                    if not all(math.isfinite(v) and v > 0 for v in (unit, width, height)):
                        raise ValueError(f"Page {index + 1} has invalid dimensions.")
                    pixels = math.ceil(width * dpi / 72) * math.ceil(height * dpi / 72)
                    if pixels > 60_000_000:
                        raise ValueError(f"Page {index + 1} is too large at {dpi} DPI. "
                                         "Choose a lower resolution (for example, 150 DPI).")
                    with closing(page.render(scale=dpi / 72 * unit, draw_annots=True,
                                     may_draw_forms=True,
                                     fill_color=(255, 255, 255, 255))) as bitmap:
                        with bitmap.to_pil() as image:
                            check_cancelled()
                            output.setPageSize((width, height))
                            # Lossless image data; no JPEG recompression or OCR layer.
                            output.drawImage(ImageReader(image), 0, 0, width, height)
                            output.showPage()
                if progress:
                    progress(index + 1, total)
            check_cancelled()
            output.save()
        with open(temporary, "rb") as stream:
            verified = PdfReader(stream)
            if verified.is_encrypted or len(verified.pages) != total:
                raise ValueError("Output validation failed.")
        check_cancelled()
        # Publish only after success. Both variants reject an existing destination,
        # including a file created by another process during conversion.
        if os.name == "nt":
            os.rename(temporary, destination)
        else:
            os.link(temporary, destination)
            os.unlink(temporary)
        temporary = None
        return destination
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)


def launch_gui(initial_file=None):
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    root = tk.Tk()
    root.title("PDF Snapshot")
    root.geometry("710x520")
    root.minsize(710, 520)
    frame = ttk.Frame(root, padding=24)
    frame.pack(fill="both", expand=True)
    frame.columnconfigure(1, weight=1)
    ttk.Label(frame, text="Create a printable image copy", font=("Segoe UI", 17, "bold")).grid(
        row=0, column=0, columnspan=3, sticky="w", pady=(0, 8))
    ttk.Label(frame, text="All processing stays on this computer. Your original PDF is preserved.").grid(
        row=1, column=0, columnspan=3, sticky="w", pady=(0, 22))

    source = tk.StringVar()
    target = tk.StringVar()
    password = tk.StringVar()
    resolution = tk.StringVar(value="300")
    status = tk.StringVar(value="Choose a PDF to begin.")
    events = queue.Queue()
    stop = threading.Event()
    running = False
    close_requested = False

    def choose_source():
        chosen = filedialog.askopenfilename(title="Choose the original PDF",
                                           filetypes=[("PDF documents", "*.pdf")])
        if chosen:
            source.set(chosen)
            path = Path(chosen)
            target.set(str(path.with_name(path.stem + "-printable.pdf")))
            password.set("")

    def choose_target():
        chosen = filedialog.asksaveasfilename(title="Save the printable PDF as",
            defaultextension=".pdf", filetypes=[("PDF documents", "*.pdf")],
            initialfile=Path(target.get()).name if target.get() else "printable.pdf",
            confirmoverwrite=False)
        if chosen:
            target.set(chosen)

    controls = []
    for row, label, variable, command in [
        (2, "Original PDF", source, choose_source),
        (3, "Save copy as", target, choose_target),
    ]:
        ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w", padx=(0, 12), pady=8)
        entry = ttk.Entry(frame, textvariable=variable)
        entry.grid(row=row, column=1, sticky="ew", pady=8)
        button = ttk.Button(frame, text="Browse...", command=command)
        button.grid(row=row, column=2, padx=(10, 0), pady=8)
        controls.extend((entry, button))
    ttk.Label(frame, text="Open password").grid(row=4, column=0, sticky="w", pady=8)
    password_entry = ttk.Entry(frame, textvariable=password, show="*")
    password_entry.grid(row=4, column=1, sticky="ew", pady=8)
    ttk.Label(frame, text="If needed").grid(row=4, column=2)
    controls.append(password_entry)
    ttk.Label(frame, text="Resolution (DPI)").grid(row=5, column=0, sticky="w", pady=8)
    dpi_box = ttk.Combobox(frame, textvariable=resolution, values=(150, 200, 300, 600),
                           state="readonly", width=10)
    dpi_box.grid(row=5, column=1, sticky="w", pady=8)
    ttk.Label(frame, text="300 DPI is a good default. Higher resolution creates larger files.\n"
              "Text, links, and form fields become images; appearance may vary by PDF.").grid(
        row=6, column=0, columnspan=3, sticky="w", pady=(10, 14))
    bar = ttk.Progressbar(frame, mode="determinate")
    bar.grid(row=7, column=0, columnspan=3, sticky="ew")
    ttk.Label(frame, textvariable=status, wraplength=640).grid(
        row=8, column=0, columnspan=3, sticky="w", pady=8)
    actions = ttk.Frame(frame)
    actions.grid(row=9, column=0, columnspan=3, sticky="e", pady=8)

    def set_busy(value):
        nonlocal running
        running = value
        for control in controls:
            control.configure(state="disabled" if value else "normal")
        dpi_box.configure(state="disabled" if value else "readonly")
        create_button.configure(state="disabled" if value else "normal")
        cancel_button.configure(state="normal" if value else "disabled")

    def start():
        if not source.get().strip() or not target.get().strip():
            messagebox.showerror("Choose files", "Choose an original PDF and an output filename.")
            return
        settings = (source.get(), target.get(), int(resolution.get()), password.get())
        stop.clear()
        bar["value"] = 0
        status.set("Opening PDF...")
        set_busy(True)

        def work():
            try:
                result = convert_pdf(settings[0], settings[1], dpi=settings[2], password=settings[3],
                    progress=lambda done, total: events.put(("progress", (done, total))),
                    cancelled=stop.is_set)
                events.put(("done", result))
            except Cancelled as exc:
                events.put(("cancelled", str(exc)))
            except Exception as exc:
                events.put(("error", str(exc)))
        threading.Thread(target=work, daemon=False).start()

    def cancel():
        stop.set()
        status.set("Cancelling after the current operation...")
        cancel_button.configure(state="disabled")

    def close():
        nonlocal close_requested
        if running:
            close_requested = True
            cancel()
        else:
            root.destroy()

    def poll():
        try:
            while True:
                kind, value = events.get_nowait()
                if kind == "progress":
                    done, total = value
                    bar.configure(maximum=total, value=done)
                    if not stop.is_set():
                        status.set(f"Rendered {done} of {total} pages" +
                                   (". Saving PDF..." if done == total else "..."))
                else:
                    set_busy(False)
                    password.set("")
                    if close_requested:
                        root.destroy()
                        return
                    if kind == "done":
                        status.set("Printable copy saved.")
                        messagebox.showinfo("Copy ready", f"Saved:\n{value}\n\n"
                                            "Open this copy in Adobe Reader to print it.")
                    elif kind == "cancelled":
                        status.set(value)
                    else:
                        status.set("Conversion failed. Your original PDF was preserved.")
                        messagebox.showerror("Could not convert PDF", value +
                            "\n\nIf an open password is required, enter it and try again. "
                            "For an existing output, choose a new filename.")
        except queue.Empty:
            pass
        root.after(100, poll)

    create_button = ttk.Button(actions, text="Create printable copy", command=start)
    create_button.pack(side="left", padx=(0, 10))
    cancel_button = ttk.Button(actions, text="Cancel", command=cancel, state="disabled")
    cancel_button.pack(side="left")
    if initial_file:
        path = Path(initial_file).resolve()
        source.set(str(path))
        target.set(str(path.with_name(path.stem + "-printable.pdf")))
    root.protocol("WM_DELETE_WINDOW", close)
    root.after(100, poll)
    root.mainloop()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", nargs="?", help="Source PDF")
    parser.add_argument("-o", "--output", help="New output PDF (must not already exist)")
    parser.add_argument("--dpi", type=int, default=300, help="72-600 DPI; default: 300")
    parser.add_argument("--ask-password", action="store_true", help="Prompt for the open password")
    parser.add_argument("--gui", action="store_true", help="Open the file picker interface")
    args = parser.parse_args()
    if args.gui or not args.input:
        launch_gui(args.input)
        return 0
    try:
        result = convert_pdf(args.input, args.output, dpi=args.dpi,
            password=getpass.getpass("PDF open password: ") if args.ask_password else "",
            progress=lambda done, total: print(f"Rendered {done}/{total} pages", flush=True))
        print(f"Saved: {result}")
        return 0
    except (Exception, KeyboardInterrupt) as exc:
        print(f"Conversion failed: {exc}", file=__import__("sys").stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
