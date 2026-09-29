from html.parser import HTMLParser

from owlocr.jobs.queue import JobQueue
from owlocr.jobs.runner import Runner
from owlocr.web.server import create_app
from tests.owl_helpers import static_text, ui_strings

SCRIPTS = ("i18n.js", "owl.js", "review.js", "app.js")


class PageScan(HTMLParser):
    """Collects ids, i18n keys and any visible text written directly into the HTML body."""

    SKIP = ("script", "style", "svg", "title")

    def __init__(self):
        super().__init__()
        self.ids, self.keys, self.visible = set(), set(), []
        self._skip = 0
        self._in_body = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "body":
            self._in_body = True
        if tag in self.SKIP:
            self._skip += 1
        if "id" in a:
            self.ids.add(a["id"])
        for name in ("data-i18n", "data-i18n-title", "data-i18n-placeholder", "data-i18n-aria"):
            if name in a:
                self.keys.add(a[name])

    def handle_endtag(self, tag):
        if tag in self.SKIP:
            self._skip -= 1

    def handle_data(self, data):
        if self._in_body and not self._skip and data.strip():
            self.visible.append(data.strip())


def scan_page() -> PageScan:
    scan = PageScan()
    scan.feed(static_text("index.html"))
    return scan


def test_index_ends_with_closing_script_tag():
    assert static_text("index.html").rstrip().endswith("</script></body></html>")


def test_index_loads_every_script_and_the_stylesheet():
    text = static_text("index.html")
    for name in SCRIPTS:
        assert f'<script src="static/{name}"></script>' in text
    assert '<link rel="stylesheet" href="static/style.css">' in text


def test_no_visible_text_is_hard_coded():
    assert scan_page().visible == []


def test_every_html_key_is_translated():
    keys = set(ui_strings()["en"])
    assert sorted(scan_page().keys - keys) == []


def test_screens_exist():
    ids = scan_page().ids
    for view in ("viewQueue", "viewReview", "viewSettings", "viewAbout", "viewWizard"):
        assert view in ids
    for control in ("btnStopEngine", "modeSwitch", "langSel", "drop", "jobList", "confirmDlg"):
        assert control in ids


def test_stylesheet_has_both_themes():
    css = static_text("style.css")
    assert ":root" in css and '[data-theme="dark"]' in css and "[hidden]" in css


def test_server_serves_page_and_assets(tmp_path):
    """GET / is index.html served by Flask (whole file, closing tag intact), plus the stylesheet."""
    queue = JobQueue(tmp_path / "queue.json")
    runner = Runner(queue, lambda: None, dict)
    client = create_app(runner, queue).test_client()
    page = client.get("/")
    assert page.status_code == 200 and page.data.rstrip().endswith(b"</script></body></html>")
    css = client.get("/static/style.css")
    assert css.status_code == 200 and b"data-theme" in css.data
    runner.shutdown()
