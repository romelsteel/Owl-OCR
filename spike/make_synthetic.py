"""THROWAWAY spike: render Czech test pages whose correct text is known exactly.

Usage:  spike\\.venv\\Scripts\\python.exe spike\\make_synthetic.py

Writes spike/synthetic/<name>.png and <name>.gt.txt (the ground truth).
Pages imitate the four input kinds the app must handle: clean scan, poor scan,
phone photo, screenshot. CPU only.
"""
import io
import sys
import random
import pathlib

from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps

sys.stdout.reconfigure(encoding="utf-8")

OUT = pathlib.Path(__file__).parent / "synthetic"
FONTS = pathlib.Path(r"C:\Windows\Fonts")
A4 = (2480, 3508)  # 300 dpi

PANGRAM = "Příliš žluťoučký kůň úpěl ďábelské ódy."
UPPER = "ĚŠČŘŽÝÁÍÉÚŮĎŤŇÓ ěščřžýáíéúůďťňó"

LETTER = [
    "Vážená paní doktorko Šťastná,",
    "dovoluji si Vás požádat o vystavení lékařské zprávy pro pana Řehoře Dvořáka, "
    "narozeného 17. března 1968 v Žďáru nad Sázavou. Pacient podstoupil ve dnech "
    "4.–19. září 2026 celkem dvanáct ponorů v hyperbarické komoře a při každém z nich "
    "dýchal čistý kyslík po dobu devadesáti minut.",
    "Během léčby si stěžoval na přechodné zaléhání v uších, které vždy odeznělo do "
    "několika hodin. Krevní tlak se pohyboval v rozmezí 125/80 až 138/86 mm Hg, "
    "tepová frekvence mezi 62 a 74 údery za minutu. Žádné závažné nežádoucí účinky "
    "jsme nezaznamenali.",
    "Doporučujeme pokračovat v rehabilitaci, omezit kouření a za šest týdnů přijít "
    "na kontrolní vyšetření. Účet za léčbu ve výši 18 450 Kč byl uhrazen pojišťovnou.",
    "S úctou",
    "MUDr. Čeněk Růžička, Ph.D.",
    "Ústí nad Labem, 28. září 2026",
]

TEXTBOOK = [
    "Buněčné dýchání",
    "Buněčné dýchání je soubor dějů, při nichž buňka získává energii postupným "
    "štěpením organických látek. U většiny organismů probíhá za přístupu kyslíku "
    "a jeho konečnými produkty jsou oxid uhličitý a voda.",
    "Glykolýza",
    "První fází je glykolýza, která se odehrává v cytoplazmě. Z jedné molekuly "
    "glukózy vznikají dvě molekuly pyruvátu, čistý zisk činí dvě molekuly ATP "
    "a dvě molekuly NADH. Glykolýza nevyžaduje kyslík, a proto ji nacházíme "
    "i u nejjednodušších bakterií.",
    "Krebsův cyklus",
    "Pyruvát přechází do matrix mitochondrie, kde se přeměňuje na acetylkoenzym A. "
    "Ten vstupuje do Krebsova cyklu, v němž se uhlíkatý řetězec úplně odbourá. "
    "Uvolněné elektrony přenášejí koenzymy na dýchací řetězec ve vnitřní "
    "mitochondriální membráně.",
    "Dýchací řetězec",
    "Přenos elektronů pohání čerpání protonů do mezimembránového prostoru. Vzniklý "
    "spád využívá enzym ATP-syntáza k tvorbě ATP. Na jednu molekulu glukózy tak "
    "buňka získá přibližně třicet molekul ATP, tedy patnáctkrát více než při "
    "samotné glykolýze.",
]

TABLE_ROWS = [
    ("Jméno", "Obec", "Částka", "Splatnost"),
    ("Žaneta Křížová", "Třebíč", "1 250 Kč", "5. 10. 2026"),
    ("Ďuro Šimůnek", "Přerov", "980 Kč", "12. 10. 2026"),
    ("Růžena Čápová", "Děčín", "14 300 Kč", "19. 10. 2026"),
    ("Oldřich Nývlt", "Kroměříž", "675 Kč", "26. 10. 2026"),
    ("Štěpánka Ťoupalová", "Plzeň", "2 040 Kč", "2. 11. 2026"),
]

SCREENSHOT = [
    "Nastavení účtu",
    "Přihlášený uživatel: Jiří Šebesta",
    "Poslední přihlášení: úterý 22. září 2026, 18:47",
    "Zálohování je zapnuté. Příští záloha proběhne dnes ve 23:00.",
    "Úložiště: využito 41,6 GB z 200 GB",
    "Změnit heslo    Odhlásit se    Smazat účet",
]


def font(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONTS / name), size)


def wrap(draw: ImageDraw.ImageDraw, text: str, fnt, width: int) -> list[str]:
    lines, cur = [], ""
    for word in text.split():
        trial = f"{cur} {word}".strip()
        if draw.textlength(trial, font=fnt) <= width:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def render_paragraphs(paras, body_font, size, head_font=None, page=A4, margin=260, leading=1.45):
    """Short paragraphs that match a heading in TEXTBOOK style are drawn bold."""
    img = Image.new("RGB", page, "white")
    d = ImageDraw.Draw(img)
    body = font(body_font, size)
    head = font(head_font, int(size * 1.35)) if head_font else None
    y = margin
    for p in paras:
        is_head = head is not None and len(p) < 30 and not p.endswith((".", ","))
        f = head if is_head else body
        for line in wrap(d, p, f, page[0] - 2 * margin):
            d.text((margin, y), line, font=f, fill="black")
            y += int(f.size * leading)
        y += int(size * 0.8)
    return img


def render_table(rows, page=A4, margin=260):
    img = Image.new("RGB", page, "white")
    d = ImageDraw.Draw(img)
    title_f, head_f, cell_f = font("arialbd.ttf", 64), font("arialbd.ttf", 44), font("arial.ttf", 44)
    d.text((margin, margin), "Přehled plateb za říjen", font=title_f, fill="black")
    col_w = (page[0] - 2 * margin) // len(rows[0])
    row_h, y0 = 110, margin + 170
    for r, row in enumerate(rows):
        for c, cell in enumerate(row):
            x, y = margin + c * col_w, y0 + r * row_h
            d.rectangle([x, y, x + col_w, y + row_h], outline="black", width=3)
            d.text((x + 24, y + 30), cell, font=head_f if r == 0 else cell_f, fill="black")
    return img


def render_screenshot(lines):
    img = Image.new("RGB", (1280, 720), (243, 243, 243))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, 1280, 64], fill=(32, 32, 32))
    d.text((24, 18), lines[0], font=font("segoeuib.ttf", 24), fill="white")
    y = 110
    for line in lines[1:]:
        d.text((48, y), line, font=font("segoeui.ttf", 20), fill=(20, 20, 20))
        y += 58
    return img


def poor_scan(img: Image.Image, seed: int) -> Image.Image:
    """150 dpi, slightly skewed, grey paper, speckles, soft focus, JPEG artefacts."""
    rnd = random.Random(seed)
    img = img.resize((img.width // 2, img.height // 2), Image.LANCZOS)
    img = img.rotate(1.4, resample=Image.BICUBIC, fillcolor="white", expand=False)
    img = Image.blend(img, Image.new("RGB", img.size, (226, 222, 210)), 0.35)
    px = img.load()
    for _ in range(img.width * img.height // 400):
        x, y = rnd.randrange(img.width), rnd.randrange(img.height)
        px[x, y] = (rnd.randrange(60, 140),) * 3
    img = img.filter(ImageFilter.GaussianBlur(0.9))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=45)
    return Image.open(io.BytesIO(buf.getvalue())).convert("RGB")


def phone_photo(img: Image.Image) -> Image.Image:
    """Page photographed at an angle on a dark desk, uneven light."""
    page = img.resize((img.width // 2, img.height // 2), Image.LANCZOS)
    w, h = page.size
    # perspective: top edge narrower than the bottom, as when shooting from below
    coeffs = _perspective([(0, 0), (w, 0), (w, h), (0, h)], [(90, 40), (w - 70, 0), (w, h), (0, h - 30)])
    page = page.transform((w, h), Image.PERSPECTIVE, coeffs, Image.BICUBIC, fillcolor=(45, 40, 38))
    page = page.rotate(-3.0, resample=Image.BICUBIC, fillcolor=(45, 40, 38), expand=True)
    canvas = Image.new("RGB", (page.width + 240, page.height + 240), (45, 40, 38))
    canvas.paste(page, (120, 120))
    shade = Image.linear_gradient("L").resize(canvas.size).rotate(35, expand=False)
    shade = ImageOps.autocontrast(shade).point(lambda v: 150 + v * 105 // 255)
    canvas = Image.composite(canvas, Image.new("RGB", canvas.size, "black"), shade)
    buf = io.BytesIO()
    canvas.filter(ImageFilter.GaussianBlur(0.7)).save(buf, "JPEG", quality=70)
    return Image.open(io.BytesIO(buf.getvalue())).convert("RGB")


def _perspective(src, dst):
    """Coefficients for PIL's PERSPECTIVE transform mapping dst quad back onto src."""
    import numpy as np

    a = []
    for (x, y), (u, v) in zip(dst, src):
        a.append([x, y, 1, 0, 0, 0, -u * x, -u * y])
        a.append([0, 0, 0, x, y, 1, -v * x, -v * y])
    b = [c for p in src for c in p]
    return np.linalg.solve(np.array(a, dtype=float), np.array(b, dtype=float)).tolist()


def save(name: str, img: Image.Image, truth: list[str]):
    img.save(OUT / f"{name}.png")
    (OUT / f"{name}.gt.txt").write_text("\n".join(truth) + "\n", encoding="utf-8")
    print(f"{name:28s} {img.width}x{img.height}  {sum(len(t) for t in truth)} chars")


def main():
    OUT.mkdir(exist_ok=True)
    letter = render_paragraphs(LETTER, "times.ttf", 52)
    textbook = render_paragraphs(TEXTBOOK, "georgia.ttf", 46, head_font="georgiab.ttf")
    small = render_paragraphs([PANGRAM, UPPER] + LETTER[1:4] + TEXTBOOK[1:2], "calibri.ttf", 30)
    table_truth = ["Přehled plateb za říjen"] + [" ".join(r) for r in TABLE_ROWS]

    save("01_letter_clean", letter, LETTER)
    save("02_textbook_clean", textbook, TEXTBOOK)
    save("03_small_print_clean", small, [PANGRAM, UPPER] + LETTER[1:4] + TEXTBOOK[1:2])
    save("04_table_clean", render_table(TABLE_ROWS), table_truth)
    save("05_letter_poor_scan", poor_scan(letter, seed=1), LETTER)
    save("06_textbook_poor_scan", poor_scan(textbook, seed=2), TEXTBOOK)
    save("07_letter_phone_photo", phone_photo(letter), LETTER)
    save("08_screenshot", render_screenshot(SCREENSHOT), SCREENSHOT)
    save("09_letter_rotated_90", letter.rotate(90, expand=True), LETTER)
    # blank page: the model is known to invent text here; correct output is nothing
    save("10_blank_page", Image.new("RGB", A4, "white"), [])


if __name__ == "__main__":
    main()
