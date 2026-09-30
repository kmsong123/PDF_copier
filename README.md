# PDF Snapshot

Creates a new, printable PDF by rendering each visible page into a losslessly
embedded image. All conversion runs locally. No uploads, accounts, or Adobe
installation are needed. The original and existing output files are never overwritten.

## On this computer

1. Double-click **Start PDF Snapshot.cmd**.
2. Browse to the original PDF and choose a new output filename.
3. Leave resolution at **300 DPI**, or choose 150 DPI for smaller files.
4. Click **Create printable copy**.
5. Open the saved `-printable.pdf` in Adobe Reader and print it. Select **Actual size**
   if you want to preserve the original page dimensions; printer margins still apply.

You can also drag one PDF onto the launcher to prefill the source.
The launcher uses the Python runtime already installed with Codex on this PC.
The console window behind the interface is normal; close the interface to exit.

## What is preserved

- Page order, visible crop, orientation, and physical page sizes, including mixed sizes.
- Visible text, images, and supported annotations and form appearances, rendered at
  the chosen resolution on a white background.
- The output contains images only, with no PDF encryption or printing restriction.

This is a visual copy, not a byte-identical document. Text is no longer searchable
or selectable; links, form interactivity, layers, tags, bookmarks, and digital
signature verification are not retained. Rasterization can change fine details
or colors, so check the resulting pages before printing. It captures the default
visible state, not annotations currently unsaved in another application.

Standard PDF permission restrictions do not prevent this renderer from making
an image copy. If a password is needed to **open** the PDF, enter it in the password
box. The tool does not recover unknown passwords or support Adobe-only DRM.
Specialized dynamic/XFA forms may be unsupported or render differently.

Images are compressed without JPEG quality loss. Large or image-heavy documents
can produce large files and use substantial memory. Pages above 60 million pixels
are rejected; lower the DPI for oversized drawings. Cancellation takes effect
between operations. Temporary output is removed on handled errors or cancellation.
After a forced shutdown, a `.pdf-snapshot-*.tmp` file may remain in the output folder.

## Setup on another computer

Install Python 3.10 or newer with Tk support, then run in this folder:

```powershell
py -3 -m pip install -r requirements.txt
```

Double-click the launcher afterward. Python/Tk installers and the one-time package
installation need internet access; document conversion does not.

## Command line

Use a Python environment containing the packages in `requirements.txt`:

```powershell
python pdf_snapshot.py "input.pdf"
python pdf_snapshot.py "input.pdf" -o "printable.pdf" --dpi 300
python pdf_snapshot.py "input.pdf" --ask-password
```

On this computer, if `python` is not on PATH:

```powershell
& "$env:USERPROFILE\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" .\pdf_snapshot.py "input.pdf"
```

Passwords are prompted for or entered in the interface, not put into command-line
arguments or saved to settings. The tool never sends a job to a printer itself.

## Verification

Run `python -m unittest discover -s tests -v` to exercise restricted and
password-protected inputs, page geometry, image fidelity, forms, cancellation,
and protection against overwriting files.
