Owl OCR 0.1.0 is the first public release: offline OCR for Windows built on Baidu's open-source
Unlimited-OCR model, made for scanned Czech documents and fine with English.

## Download

- `OwlOCR-0.1.0-setup.exe`: installs for your user only, no administrator rights needed.
- `OwlOCR-0.1.0-portable-win64.zip`: unpack anywhere and run `OwlOCR.exe`.
- `SHA256SUMS.txt`: checksums of both files.

Windows SmartScreen warns about the installer because it is not code-signed: click
**More info** and then **Run anyway**. The README explains why and shows how to check the checksum.

## What you need

An NVIDIA graphics card with at least 8 GB of memory (10 GB or more for Quality mode) and
driver 570.65 or newer, or a PC with at least 16 GB of RAM and no suitable graphics card: the
processor-only mode is included in this release (the setup wizard tells you which mode your
computer gets). Processor-only mode is slow: about 30 s for a short page on a fast processor;
dense pages and slower PCs take several times longer. On the first start the wizard downloads
the reading engine once: about 10 GB, 16 GB of disk space. After that Owl OCR works offline.

## In this release

- Scanned and born-digital PDFs, photos, screenshots and images; Markdown, text, Word and
  searchable PDF; copy to clipboard.
- Markdown export can link pictures in the Obsidian style (Settings, "Image links").
- Queue with pause, resume and cancel that survives closing the app.
- Quality and Fast modes, review screen, dictionary marks (Czech and English), Czech and English
  interface.
- About 3 wrong words in 100 on real Czech scans. The text is read by a machine: check it
  before you quote it. See the README for the details and the known limits.

## Česky

První veřejná verze Owl OCR: offline OCR pro Windows postavené na otevřeném modelu Unlimited-OCR
od Baidu, dělané pro naskenované české dokumenty. Instalátor (`OwlOCR-0.1.0-setup.exe`) nepotřebuje
práva správce, přenosná verze je v zipu. Program běží na grafické kartě NVIDIA, případně jen na
procesoru (na rychlém procesoru trvá krátká stránka asi 30 s, husté stránky a pomalejší počítače
několikrát déle). Odkazy na obrázky v Markdownu můžete nastavit ve stylu Obsidianu. Při prvním
spuštění se jednou stáhne asi 10 GB. Podrobnosti jsou v souboru README.cs.md.
