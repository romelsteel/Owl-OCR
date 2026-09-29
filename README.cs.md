# Owl OCR

Owl OCR převádí skeny, fotky stránek, snímky obrazovky a PDF na text přímo ve vašem počítači
s Windows. Používá otevřený model [Unlimited-OCR](https://huggingface.co/baidu/Unlimited-OCR)
od společnosti Baidu, po jednorázovém stažení funguje bez internetu a vaše dokumenty nikam
neposílá.

*English: [README.md](README.md)*

## Co umí

- Čte naskenovaná PDF (vznikl kvůli českým knihám a dopisům), PDF, která už text obsahují, fotky
  stránek, snímky obrazovky a další obrázky (PNG, JPG, WEBP, BMP, TIFF).
- Ukládá Markdown, prostý text, Word (.docx) a prohledávatelné PDF, nebo zkopíruje text do schránky.
- Fronta pro mnoho souborů i celé složky: průběh, pozastavení, pokračování, zrušení. Dlouhou knihu
  lze číst na několikrát; zavřením aplikace se fronta neztratí.
- Dva režimy: **Kvalita** (výchozí na grafických kartách s 10 GB a více) a **Rychlý** (méně
  grafické paměti; na drobném písmu o něco méně přesný).
- Kontrolní obrazovka ukazuje sken vedle přečteného textu, označí slova, která slovník
  nezná, a text jde před uložením opravit.
- Rozhraní v češtině a angličtině.
- U Markdownu si v Nastavení → Odkazy na obrázky můžete zvolit běžné odkazy Markdownu nebo
  odkazy pro Obsidian pro obrázky uložené vedle textu; hotová úloha, která obrázky obsahuje,
  ukazuje tlačítko „Otevřít složku s obrázky“.

## Hardware

| Způsob čtení | Co je potřeba | Výchozí režim | Čas na stránku knihy |
|---|---|---|---|
| Grafická karta, plná kvalita | NVIDIA řady RTX 30, 40 nebo 50 (nebo profesionální karta stejných generací), tedy s výpočetní schopností 8.0 nebo vyšší, s alespoň 10 GB grafické paměti | Kvalita | asi 25 až 45 s, husté stránky až 110 s (změřeno na RTX 4080 SUPER) |
| Grafická karta, úsporný režim | NVIDIA karta generace RTX 20, nebo jakákoli novější karta s 8 až 10 GB grafické paměti (alespoň 8 GB a nesplňující předchozí řádek) | Rychlý | na grafické kartě zhruba stejně jako Kvalita (zvlášť neměřeno) |
| Jen procesor | jakýkoli 64bitový počítač s Windows 10/11 a alespoň 16 GB operační paměti | Rychlý | asi 30 s u krátké stránky na rychlém procesoru; husté stránky a pomalejší počítače trvají několikrát déle (změřeno na Intel Core Ultra 7 265K) |
| Nepodporováno | méně než 16 GB operační paměti a žádná vhodná grafická karta | | |

Grafická karta potřebuje ovladač NVIDIA **570.65 nebo novější**. Se starším ovladačem vás
Owl OCR požádá o aktualizaci a mezitím může číst procesorem. Průvodce nastavením to všechno
zjistí a vybere za vás.

## První spuštění: jednorázové stažení

Při prvním spuštění průvodce nastavením jednou stáhne čtecí engine:

| Část | Velikost |
|---|---|
| uv (instalační nástroj) a Python 3.11 | asi 45 MB |
| PyTorch pro grafické karty (nebo pro procesor) | asi 2,9 GB (0,1 GB) |
| Další knihovny | několik set MB |
| Model Unlimited-OCR | 6,7 GB |

Celkem asi **10 GB stahování** a **16 GB místa na disku**. Při 100 Mbit/s trvá stahování zhruba
čtvrt hodiny; na rychlém připojení se samotný model stáhl asi za minutu. Průvodce jde pozastavit
a pokračuje tam, kde skončil, i po zavření aplikace. Engine můžete uložit na jiný disk, a pokud už
model stažený máte, zvolte „Engine už mám“ – soubory se jen zkontrolují a znovu se nestahují.

Další spuštění už nic nestahují a fungují bez internetu.

## Slovníky pro kontrolu pravopisu (volitelné)

Po zkoušce průvodce nabídne český slovník (asi 3,6 MB) a anglický (asi 0,5 MB); oba jsou zaškrtnuté a kterýkoli můžete odškrtnout.
Nejsou součástí Owl OCR: stahují se zvlášť z projektu
[LibreOffice dictionaries](https://github.com/LibreOffice/dictionaries) v pevně daných verzích a
platí pro ně jejich vlastní licence (čeština: GNU GPL, angličtina: SCOWL), které se ukládají
vedle nich. Se slovníkem Owl OCR opraví typické chyby čtení, například `ď` a `ť`, a na kontrolní
obrazovce označí neznámá slova. Bez slovníku Owl OCR funguje stejně, jen tyto kontroly vynechá.
V Nastavení → Slovníky je můžete kdykoli nainstalovat nebo odebrat.

## Instalace

Na stránce [Releases](https://github.com/romelsteel/owl-ocr/releases) stáhněte buď:

- `OwlOCR-<verze>-setup.exe`: nainstaluje se jen pro vašeho uživatele do
  `%LOCALAPPDATA%\Programs\OwlOCR`, bez práv správce, se zástupcem v nabídce Start; nebo
- `OwlOCR-<verze>-portable-win64.zip`: rozbalte kamkoli a spusťte `OwlOCR.exe`.

Soubor `SHA256SUMS.txt` obsahuje kontrolní součty obou souborů. V PowerShellu:
`Get-FileHash .\OwlOCR-<verze>-setup.exe -Algorithm SHA256`.

### „Systém Windows ochránil váš počítač“

Owl OCR není digitálně podepsaný (certifikát stojí každý rok peníze), a proto Windows SmartScreen
při prvním spuštění instalátoru nebo `OwlOCR.exe` zobrazí modré varování. Klikněte na **Další informace**,
zkontrolujte název souboru a klikněte na **Přesto spustit**.

Pokud chcete, porovnejte nejdřív kontrolní součet SHA256 souboru se `SHA256SUMS.txt`.

## Jak přesný je Owl OCR?

Změřeno na vývojářově počítači v režimu Kvalita:

- Vygenerované české stránky se známým textem: 0,3 % až 2,6 % chybných znaků, včetně špatných
  skenů, fotky z telefonu a snímku obrazovky. Nejtěžší je drobné písmo; režim Rychlý tam má 6,5 %
  chybných znaků.
- Skutečné skeny české učebnice botaniky: asi **3 chybná slova ze 100** (1,7 až 4,5 podle
  stránky), zatímco textová vrstva, kterou PDF už mělo, měla asi 10 chyb ze 100. Většinou jde
  o jediný chybný nebo chybějící háček či čárku. Část chyb Owl OCR opraví pravidly a slova, která
  slovník nezná, označí.

**Upřímné upozornění:** model občas nahradí skutečné slovo jiným skutečným slovem („významcové“
místo „výtrusnice“). To žádný slovník nepozná. Text přečetl stroj a nikdo ho nezkontroloval:
než ho budete citovat, zkontrolujte ho. Kontrolní obrazovka to usnadní.

Stránky otočené o 90 stupňů se před čtením samy natočí. Rukopis a jiná písma než latinka
nejsou podporovány.

## Prohledávatelné PDF: omezení

Model hlásí polohu každého **bloku** textu, ne každého slova. Prohledávatelné PDF proto umisťuje
neviditelný text po blocích: hledání i kopírování fungují, ale zvýraznění nalezeného slova pokryje
jen přibližně správnou oblast, ne přesně to slovo.

## Soukromí

- Dokumenty se čtou ve vašem počítači a nikdy ho neopustí. Owl OCR nemá účet, telemetrii ani
  cloudovou službu.
- Internet se použije jen pro stahování, které sami spustíte: jednorázové stažení enginu v průvodci
  nastavením (huggingface.co, nebo modelscope.cn, když to nejde, download.pytorch.org,
  pypi.org / files.pythonhosted.org a github.com a servery, na které tyto adresy přesměrují) a volitelné slovníky pro kontrolu pravopisu
  (raw.githubusercontent.com) z průvodce nebo z Nastavení → Slovníky.

## Kde má Owl OCR své soubory

| Co | Kde |
|---|---|
| Program (instalátor) | `%LOCALAPPDATA%\Programs\OwlOCR` |
| Engine, model, fronta, záznamy | `%LOCALAPPDATA%\OwlOCR` nebo složka zvolená v průvodci |
| Nastavení | `%APPDATA%\OwlOCR` |
| Výsledky | vedle zdrojového souboru, nebo ve složce z Nastavení |

V Nastavení → Engine jde engine zkontrolovat, přeinstalovat (nic, co je v pořádku, se znovu
nestahuje), přesunout do jiné složky nebo odebrat. Zvolíte-li kořen disku nebo složku, která není
prázdná, Owl OCR tam vytvoří podsložku `OwlOCR`.

## Odinstalace

Nastavení Windows → Aplikace → Owl OCR → Odinstalovat. Odinstalátor se zeptá, zda smazat také
engine (asi 10 GB), frontu a nastavení. Vaše dokumenty a soubory, které Owl OCR uložil vedle nich,
se nikdy nemažou.

Přenosná verze: smažte rozbalenou složku a potom `%LOCALAPPDATA%\OwlOCR` (nebo zvolenou složku
pro data) a `%APPDATA%\OwlOCR`.

## Sestavení ze zdrojového kódu

Windows, Python 3.11 a (pro instalátor) [Inno Setup 6](https://jrsoftware.org/isdl.php):

```
py -3.11 -m pip install -r requirements-dev.txt
py -3.11 -m pytest
py packaging\build.py
```

První sestavení vytvoří `build\venv` z `requirements.txt` a `requirements-build.txt`
(PyInstaller 6.21.0).
Sestavení vytvoří `dist\OwlOCR\`, přenosný zip, instalátor a `SHA256SUMS.txt`.

## Licence

Owl OCR je vydán pod licencí MIT (`LICENSE`). Model Unlimited-OCR zveřejnila společnost Baidu pod
licencí MIT; jeden z jeho souborů (`modeling_deepseekv2.py`) je pod licencí Apache 2.0
(`licenses/Apache-2.0.txt`). Na počítačích bez vhodné grafické karty Owl OCR upraví
`modeling_unlimitedocr.py`, aby běžel i bez ní; upravený soubor to na začátku uvádí.
Veškerý přibalený software třetích stran je uveden v `packaging/THIRD_PARTY_NOTICES.md` (v nainstalované aplikaci vedle `OwlOCR.exe`).
