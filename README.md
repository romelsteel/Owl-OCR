# Owl OCR

Owl OCR turns scans, photos of pages, screenshots and PDFs into text on your own Windows PC.
It uses Baidu's open-source [Unlimited-OCR](https://huggingface.co/baidu/Unlimited-OCR) model,
works offline after a one-time download, and never sends your documents anywhere.

*Česky: [README.cs.md](README.cs.md)*

## What it does

- Reads scanned PDFs (it was built for Czech books and letters), PDFs that already contain text,
  photos of pages, screenshots and other images (PNG, JPG, WEBP, BMP, TIFF).
- Writes Markdown, plain text, Word (.docx) and a searchable PDF, or copies the text to the clipboard.
- A queue for many files and whole folders: progress, pause, resume, cancel. A long book can be
  read over several sittings; closing the app keeps the queue.
- Two modes: **Quality** (the default on graphics cards with 10 GB or more) and **Fast** (less
  graphics memory; slightly less accurate on small print).
- A review screen shows the scan next to the recognised text, marks words the dictionary does
  not know, and lets you correct the text before exporting.
- Czech and English user interface.
- For Markdown, Settings → Image links lets you choose standard Markdown links or Obsidian
  links for the pictures saved next to the text; a finished job that has pictures shows an
  "Open images folder" button.

## Hardware

| Setup | What you need | Default mode | Time per book page |
|---|---|---|---|
| Graphics card, full quality | NVIDIA RTX 30, 40 or 50 series (or a professional card of the same generations), i.e. compute capability 8.0 or higher, with at least 10 GB of graphics memory | Quality | about 25 to 45 s, dense pages up to 110 s (measured on an RTX 4080 SUPER) |
| Graphics card, memory-saving | NVIDIA card of the RTX 20 generation, or any newer card with 8 to 10 GB of graphics memory (at least 8 GB, and not qualifying for the row above) | Fast | about the same as Quality on a graphics card (not measured separately) |
| Processor only | any 64-bit Windows 10/11 PC with at least 16 GB of RAM | Fast | about 30 s for a short page on a fast processor; dense pages and slower PCs take several times longer (measured on an Intel Core Ultra 7 265K) |
| Not supported | less than 16 GB of RAM and no suitable graphics card | | |

The graphics card needs NVIDIA driver **570.65 or newer**. With an older driver Owl OCR asks you to
update it and can read with the processor in the meantime. The setup wizard detects all of this
and chooses for you.

## First start: the one-time download

On the first start a setup wizard downloads the reading engine once:

| Part | Size |
|---|---|
| uv (installer tool) and Python 3.11 | about 45 MB |
| PyTorch for graphics cards (or for the processor) | about 2.9 GB (0.1 GB) |
| Other libraries | a few hundred MB |
| Unlimited-OCR model | 6.7 GB |

That is about **10 GB of download** and **16 GB of disk space**. At 100 Mbit/s the download
takes roughly a quarter of an hour; on a fast connection the model alone downloaded in about a
minute. The wizard can be paused and continues where it stopped, even after closing the app.
You can put the engine on another drive, and if you already have the model downloaded, choose
"I already have the engine" so it is only checked, not downloaded again.

Later starts download nothing and work without internet.

## Spell-check dictionaries (optional)

After the self-test the wizard offers a Czech dictionary (about 3.6 MB) and an English
one (about 0.5 MB); both are ticked, and you can untick either. They are not part of Owl OCR: they are downloaded separately from the
[LibreOffice dictionaries](https://github.com/LibreOffice/dictionaries) project at pinned versions
and come under their own licences (Czech: GNU GPL, English: SCOWL), which are stored next to them.
With a dictionary Owl OCR repairs typical reading errors such as `ď` and `ť` and marks unknown
words in the review screen. Without one Owl OCR works just the same, only these checks are
skipped. Settings → Dictionaries installs or removes them at any time.

## Installing

Download from the [Releases](https://github.com/romelsteel/owl-ocr/releases) page either:

- `OwlOCR-<version>-setup.exe`: installs for your user only, into
  `%LOCALAPPDATA%\Programs\OwlOCR`, without administrator rights, with a Start menu entry; or
- `OwlOCR-<version>-portable-win64.zip`: unpack anywhere and run `OwlOCR.exe`.

`SHA256SUMS.txt` lists the checksums of both files. In PowerShell:
`Get-FileHash .\OwlOCR-<version>-setup.exe -Algorithm SHA256`.

### "Windows protected your PC"

Owl OCR is not code-signed (a certificate costs money every year), so Windows SmartScreen shows a
blue warning the first time you start the installer or `OwlOCR.exe`. Click **More info**, check that the file
name is right, then click **Run anyway**.

If you prefer, compare the file's SHA256 checksum with `SHA256SUMS.txt` first.

## How accurate is it?

Measured on the developer's PC with Quality mode:

- Generated Czech pages with known text: 0.3 % to 2.6 % of characters wrong (character error rate),
  including poor scans, a phone photo and a screenshot. Small print is the hardest case; Fast mode
  gets 6.5 % wrong there.
- Real scans of a Czech botany textbook: about **3 wrong words in 100** (between 1.7 and 4.5 per
  page), against about 10 in 100 for the text layer the PDF already had. Most errors are a single
  wrong or missing accent. Owl OCR repairs some of them with rules and marks words the dictionary
  does not know.

**Honest caveat:** sometimes the model replaces a real word with another real word
("významcové" instead of "výtrusnice"). No dictionary can detect that. The text has been read by a
machine and has not been checked: check it before you quote it. The review screen makes that easier.

Pages turned by 90 degrees are rotated automatically before reading. Handwriting and non-Latin
scripts are not supported.

## Searchable PDF: a limitation

The model reports the position of each **block** of text, not of each word. The searchable PDF
therefore places the invisible text block by block: searching and copying work, but a highlighted
search hit covers roughly the right area rather than exactly the word.

## Privacy

- Your documents are read on your PC and never leave it. Owl OCR has no account, no telemetry and
  no cloud service.
- The internet is used only for downloads you start: the one-time engine download in the setup
  wizard (huggingface.co, or modelscope.cn if that fails, download.pytorch.org,
  pypi.org / files.pythonhosted.org and github.com, and the servers these redirect to) and the optional spell-check dictionaries
  (raw.githubusercontent.com), from the wizard or Settings → Dictionaries.

## Where Owl OCR keeps its files

| What | Where |
|---|---|
| Program (installer) | `%LOCALAPPDATA%\Programs\OwlOCR` |
| Engine, model, queue, logs | `%LOCALAPPDATA%\OwlOCR` or the folder you chose in the wizard |
| Settings | `%APPDATA%\OwlOCR` |
| Results | next to the source file, or the folder set in Settings |

Settings → Engine can verify the engine, reinstall it (nothing intact is downloaded again), move
it to another folder, or remove it. If you pick a drive root or a folder that is not empty,
Owl OCR creates an `OwlOCR` subfolder there.

## Uninstalling

Windows Settings → Apps → Owl OCR → Uninstall. The uninstaller asks whether to delete the engine
(about 10 GB), the queue and the settings as well. Your documents and the files Owl OCR wrote next
to them are never deleted.

Portable version: delete the unpacked folder, then `%LOCALAPPDATA%\OwlOCR` (or your chosen data
folder) and `%APPDATA%\OwlOCR`.

## Building from source

Windows, Python 3.11 and (for the installer) [Inno Setup 6](https://jrsoftware.org/isdl.php):

```
py -3.11 -m pip install -r requirements-dev.txt
py -3.11 -m pytest
py packaging\build.py
```

The first build creates `build\venv` from `requirements.txt` and `requirements-build.txt`
(PyInstaller 6.21.0).
The build writes `dist\OwlOCR\`, the portable zip, the installer and `SHA256SUMS.txt`.

## Licence

Owl OCR is released under the MIT License (`LICENSE`). The Unlimited-OCR model is published by
Baidu under the MIT License; one of its files (`modeling_deepseekv2.py`) is under the Apache
License 2.0 (`licenses/Apache-2.0.txt`). On processor-only computers Owl OCR modifies
`modeling_unlimitedocr.py` so it can run without a graphics card; the modified file says so.
All bundled third-party software is listed in `packaging/THIRD_PARTY_NOTICES.md` (next to `OwlOCR.exe` in the installed app).
