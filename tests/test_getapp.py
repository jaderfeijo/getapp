import contextlib
import gzip
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "lib"))

from getapp import actions, cli, fuzzy, runner, search as search_mod       # noqa: E402
from getapp.model import Item                                                # noqa: E402
from getapp.sources import apt, flatpak, snap, web                           # noqa: E402

APT_FIXTURE = """vlc - multimedia player and streamer
vlc-bin - binaries from VLC
libvlc5 - core library for the VLC media player
firefox-esr - Mozilla Firefox web browser - Extended Support Release
gedit - popular text editor for the GNOME desktop environment
vim - Vi IMproved - enhanced vi editor
vim-common - Vi IMproved - Common files
libreoffice-writer - office productivity suite -- word processor
"""
FLATPAK_FIXTURE = "org.videolan.VLC\tVLC\tVLC media player, the open-source multimedia player\n" \
                  "org.mozilla.firefox\tFirefox\tFast, Private & Safe Web Browser\n" \
                  "com.slack.Slack\tSlack\tBusiness communication\n"


class Sandbox(unittest.TestCase):
    """Every test gets its own cache / data folders and no network."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = Path(self.tmp.name)
        env = {"GETAPP_CACHE_DIR": str(t / "cache"), "GETAPP_DATA_HOME": str(t / "share"), "GETAPP_CONFIG_DIR": str(t / "config"),
               "GETAPP_NO_REFRESH": "1", "GETAPP_OFFLINE": "1"}
        patcher = mock.patch.dict(os.environ, env)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.tmp.cleanup)
        cache = t / "cache"
        cache.mkdir(parents=True)
        (cache / "apt.txt").write_text(APT_FIXTURE)
        (cache / "apt.low").write_text(APT_FIXTURE.lower())
        (cache / "apt.names").write_text("\n".join(l.partition(" - ")[0] for l in APT_FIXTURE.lower().splitlines()) + "\n")
        (cache / "flatpak.tsv").write_text(FLATPAK_FIXTURE)
        for module, name in ((apt.AptSource, "installed_ids"),):
            p = mock.patch.object(module, name, lambda self: {"gedit"})
            p.start()
            self.addCleanup(p.stop)
        p = mock.patch.object(flatpak.FlatpakSource, "installed_ids", lambda self: {"com.slack.Slack"})
        p.start()
        self.addCleanup(p.stop)
        p = mock.patch.object(flatpak.FlatpakSource, "available", lambda self: True)
        p.start()
        self.addCleanup(p.stop)


class FuzzyTests(unittest.TestCase):
    def test_parse_query_source_prefixes(self):
        self.assertEqual(fuzzy.parse_query("flatpak: slack"), (["slack"], "flatpak"))
        self.assertEqual(fuzzy.parse_query("apt:vim editor"), (["vim", "editor"], "apt"))
        self.assertEqual(fuzzy.parse_query("Text  Editor"), (["text", "editor"], None))
        self.assertEqual(fuzzy.parse_query("http://x.com"), (["http://x.com"], None))     # not a source prefix

    def test_match_quality_order(self):
        scores = [fuzzy.match_token("vim", *args) for args in (("vim", "vim", ""), ("vim-gtk", "vim-gtk", ""),
                  ("gvim", "gvim", ""), ("x", "x", "an vim fork"), ("x", "x", "reviming"))]
        self.assertEqual(scores, sorted(scores, reverse=True))
        self.assertTrue(all(s is not None for s in scores))

    def test_every_word_must_match(self):
        self.assertIsNone(fuzzy.score_item(["text", "nomatch"], "gedit", "gedit", "text editor"))
        self.assertIsNotNone(fuzzy.score_item(["text", "edit"], "gedit", "gedit", "text editor"))

    def test_typo_tolerance_prefers_tight_matches(self):
        tight = fuzzy.score_item(["frefox"], "firefox", "firefox", "")
        loose = fuzzy.score_item(["frefox"], "freeze-fox-extra", "freeze-fox-extra", "")
        self.assertIsNotNone(tight)
        self.assertGreater(tight, loose or 0)
        self.assertIsNone(fuzzy.score_item(["zzz"], "firefox", "firefox", ""))

    def test_libraries_rank_below_applications(self):
        app = fuzzy.score_item(["vlc"], "vlc", "vlc", "")
        lib = fuzzy.score_item(["vlc"], "libvlc5", "libvlc5", "")
        self.assertGreater(app, lib)
        self.assertTrue(fuzzy.is_noise("libssl3t64") and fuzzy.is_noise("foo-dev") and not fuzzy.is_noise("libreoffice-writer"))


class AptTests(Sandbox):
    def test_search_and_installed_mark(self):
        results = dict((i.id, i) for _, i in apt.AptSource().search(["editor"]))
        self.assertIn("gedit", results)
        self.assertTrue(results["gedit"].installed)
        self.assertFalse(results["vim"].installed)

    def test_name_hits_beat_description_hits(self):
        ranked = sorted(apt.AptSource().search(["vlc"]), key=lambda r: -r[0])
        self.assertEqual(ranked[0][1].id, "vlc")
        self.assertEqual(ranked[-1][1].id, "libvlc5")

    def test_typo_fallback_and_get(self):
        self.assertIn("firefox-esr", [i.id for _, i in apt.AptSource().search(["frefox"])])
        self.assertEqual(apt.AptSource().get("vim").summary, "Vi IMproved - enhanced vi editor")
        self.assertIsNone(apt.AptSource().get("nope"))

    def test_commands(self):
        item = Item("apt", "vim", "vim")
        self.assertEqual(apt.AptSource().install_cmds(item)[0].argv, ["apt-get", "install", "-y", "vim"])
        self.assertTrue(apt.AptSource().install_cmds(item)[0].root)


class FlatpakTests(Sandbox):
    def test_parse_appstream(self):
        xml = b"""<components><component type="desktop-application"><id>org.x.App</id><name>App</name>
        <name xml:lang="de">Anwendung</name><summary>Does things</summary><summary xml:lang="de">Tut Dinge</summary></component>
        <component type="runtime"><id>org.x.Runtime</id><name>R</name></component></components>"""
        rows = flatpak.FlatpakSource.parse_appstream(io.BytesIO(xml))
        self.assertEqual(rows, [("org.x.App", "App", "Does things")])

    def test_search_marks_installed(self):
        found = {i.id: i for _, i in flatpak.FlatpakSource().search(["slack"])}
        self.assertTrue(found["com.slack.Slack"].installed)
        self.assertEqual(found["com.slack.Slack"].summary, "Business communication")

    def test_commands_add_flathub_then_install(self):
        cmds = flatpak.FlatpakSource().install_cmds(Item("flatpak", "org.videolan.VLC", "VLC"))
        self.assertEqual(cmds[-1].argv[-2:], ["flathub", "org.videolan.VLC"])
        self.assertIn("remote-add", cmds[-2].argv)

    def test_user_scope_needs_no_root(self):
        with mock.patch.dict(os.environ, {"GETAPP_FLATPAK_SCOPE": "user"}):
            cmds = flatpak.FlatpakSource().install_cmds(Item("flatpak", "a.b.C", "C"))
        self.assertFalse(any(c.root for c in cmds))


class SnapTests(Sandbox):
    SAMPLE = {"results": [{"name": "spotify", "revision": {"confinement": "strict", "version": "1.2"},
                           "snap": {"title": "spotify", "summary": "Music for everyone",
                                    "publisher": {"display-name": "Spotify", "validation": "verified"}}},
                          {"name": "code", "revision": {"confinement": "classic", "version": "1"},
                           "snap": {"title": "Visual Studio Code", "summary": "Code editing", "publisher": {"display-name": "Microsoft"}}}]}

    def test_parse_results(self):
        items = snap.SnapSource.parse_results(self.SAMPLE)
        self.assertEqual([i.id for i in items], ["spotify", "code"])
        self.assertTrue(items[0].extra["verified"])
        self.assertEqual(items[1].extra["confinement"], "classic")

    def test_search_uses_the_store_results(self):
        with mock.patch.object(snap, "_cached", return_value=self.SAMPLE):
            ids = [i.id for _, i in snap.SnapSource().search(["spotify"])]
        self.assertIn("spotify", ids)

    def test_short_queries_do_not_call_the_store(self):
        with mock.patch.object(snap, "_cached", side_effect=AssertionError("network")) as cached:
            self.assertEqual(snap.SnapSource().search(["sp"]), [])
        cached.assert_not_called()

    def test_offline_and_empty_cache_is_quiet(self):
        self.assertEqual(snap.SnapSource().search(["spotify"]), [])

    def test_classic_flag_and_snapd_prerequisite(self):
        item = Item("snap", "code", "Code", extra={"confinement": "classic"})
        with mock.patch.object(snap, "have", return_value=False):
            cmds = snap.SnapSource().install_cmds(item)
        self.assertEqual(cmds[0].argv, ["apt-get", "install", "-y", "snapd"])
        self.assertEqual(cmds[1].argv, ["snap", "install", "code", "--classic"])


class WebTests(Sandbox):
    def test_slugify_and_urls(self):
        self.assertEqual(web.slugify("Google Calendar!"), "google-calendar")
        self.assertEqual(web.normalize_url("github.com/x"), "https://github.com/x")
        for bad in ("javascript:alert(1)", "https://a b.com", "file:///etc/passwd", "data:text/html,x"):
            with self.assertRaises(ValueError):
                web.normalize_url(bad)

    def test_window_class_matches_chromium(self):
        self.assertEqual(web.window_class("https://github.com"), "chrome-github.com__-Default")
        self.assertEqual(web.window_class("https://example.com/a/b?x=1#f"), "chrome-example.com__a_b-Default")
        self.assertEqual(web.window_class("https://user@Host.org:8080/"), "chrome-host.org__-Default")

    def test_desktop_entry_is_safe_and_marked(self):
        text = web.desktop_text("My App", 'https://x.com/?q="a"&b=$HOME%20', "chromium", "icon")
        self.assertIn(web.MARKER, text)
        self.assertIn('Exec=chromium --app="https://x.com/?q=\\"a\\"&b=\\$HOME%%20"', text)
        self.assertEqual(text.count("\nExec="), 1)

    def test_typed_address_becomes_a_web_app(self):
        item = web.WebSource().custom_item(["github.com/foo"])
        self.assertEqual(item.extra["url"], "https://github.com/foo")
        self.assertIsNone(web.WebSource().custom_item(["vlc"]))
        self.assertIsNone(web.WebSource().custom_item(["notaurl"]))

    def test_catalog_search_and_user_catalog(self):
        self.assertIn("web:github", [i.key for _, i in web.WebSource().search(["github"])])
        cfg = Path(os.environ["GETAPP_CONFIG_DIR"]); cfg.mkdir(parents=True)
        (cfg / "webapps.tsv").write_text("My Intranet\thttps://intranet.example.org\tCompany portal\n")
        self.assertIn("web:my-intranet", [i.key for _, i in web.WebSource().search(["intranet"])])

    def test_install_then_remove_roundtrip(self):
        src = web.WebSource()
        item = src.get("excalidraw")
        with mock.patch.object(web, "find_browser", return_value="chromium"):
            self.assertEqual(runner.run(src.install_cmds(item), out=io.StringIO()), 0)
        self.assertIn("excalidraw", [i.id for i in src.installed_items()])
        self.assertTrue(src.get("excalidraw").installed)
        self.assertEqual(runner.run(src.remove_cmds(src.installed_items()[0]), out=io.StringIO()), 0)
        self.assertEqual(src.installed_items(), [])

    def test_missing_browser_adds_a_chromium_install_step(self):
        with mock.patch.object(web, "find_browser", return_value=None):
            cmds = web.WebSource().install_cmds(web.WebSource().get("excalidraw"))
        self.assertEqual(cmds[0].argv, ["apt-get", "install", "-y", "chromium"])


class SearchTests(Sandbox):
    def keys(self, query):
        return [i.key for i in search_mod.search(query)]

    def test_merged_ranking_and_ties(self):
        keys = self.keys("vlc")
        self.assertLess(keys.index("flatpak:org.videolan.VLC"), keys.index("apt:vlc"))      # equal score: flatpak before apt
        self.assertLess(keys.index("apt:vlc"), keys.index("apt:libvlc5"))

    def test_source_filter(self):
        self.assertTrue(all(k.startswith("apt:") for k in self.keys("apt: vlc")))
        self.assertEqual(self.keys("flatpak: slack"), ["flatpak:com.slack.Slack"])

    def test_empty_query_shows_the_catalog(self):
        keys = self.keys("")
        self.assertTrue(keys and all(k.startswith("web:") for k in keys))

    def test_format_line(self):
        line = search_mod.format_line(Item("apt", "gedit", "gedit", "editor", installed=True), color=False)
        key, display = line.split("\t")
        self.assertEqual(key, "apt:gedit")
        self.assertIn("✓", display)
        self.assertNotIn("\033", display)

    def test_resolve(self):
        self.assertEqual(search_mod.resolve("apt:vim").id, "vim")
        self.assertEqual(search_mod.resolve("flatpak:org.mozilla.firefox").name, "Firefox")
        self.assertIsNone(search_mod.resolve("nonsense:thing"))


class RunnerAndActionTests(Sandbox):
    def test_root_commands_get_sudo(self):
        with mock.patch("os.geteuid", return_value=1000):
            self.assertEqual(runner.Cmd(["apt-get", "install", "x"], root=True).shown(), "sudo apt-get install x")
        with mock.patch("os.geteuid", return_value=0):
            self.assertEqual(runner.Cmd(["apt-get", "install", "x"], root=True).shown(), "apt-get install x")

    def test_run_stops_at_the_first_failure(self):
        out = io.StringIO()
        code = runner.run([runner.Cmd(["false"]), runner.Cmd(["echo", "never"])], out=out)
        self.assertNotEqual(code, 0)
        self.assertNotIn("never", out.getvalue().replace("echo never", ""))

    def test_dry_run_prints_but_does_not_run(self):
        out = io.StringIO()
        with mock.patch("subprocess.call", side_effect=AssertionError("ran")):
            self.assertEqual(actions.perform("apt:vim", "install", dry_run=True, out=out), 0)
        self.assertIn("apt-get install -y vim", out.getvalue())
        self.assertIn("dry run", out.getvalue())

    def test_already_installed_and_unknown(self):
        out = io.StringIO()
        self.assertEqual(actions.perform("apt:gedit", "install", dry_run=True, out=out), 0)
        self.assertIn("already installed", out.getvalue())
        self.assertEqual(actions.perform("apt:nope", "install", dry_run=True, out=out), 1)

    def test_declining_the_prompt_cancels(self):
        out = io.StringIO()
        with mock.patch("builtins.input", return_value="n"), mock.patch("subprocess.call", side_effect=AssertionError("ran")):
            self.assertEqual(actions.perform("apt:vim", "install", out=out), 1)
        self.assertIn("Cancelled", out.getvalue())

    def test_yes_runs_the_commands(self):
        out = io.StringIO()
        with mock.patch("subprocess.call", return_value=0) as call:
            self.assertEqual(actions.perform("apt:vim", "install", yes=True, out=out), 0)
        self.assertEqual(call.call_args[0][0][-3:], ["install", "-y", "vim"])


class CliTests(Sandbox):
    def run_cli(self, *argv):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = cli.main(list(argv))
        return code, buf.getvalue()

    def test_search_plain(self):
        code, out = self.run_cli("search", "--plain", "vlc")
        self.assertEqual(code, 0)
        self.assertTrue(out.splitlines()[0].startswith("flatpak:org.videolan.VLC\t"))
        self.assertNotIn("\033", out)

    def test_preview_of_every_source(self):
        for key in ("apt:vim", "flatpak:com.slack.Slack", "web:github"):
            code, out = self.run_cli("preview", key)
            self.assertEqual(code, 0)
            self.assertTrue(out.strip())

    def test_install_dry_run(self):
        code, out = self.run_cli("--dry-run", "install", "web:github")
        self.assertEqual(code, 0)
        self.assertIn("create the launcher for GitHub", out)


if __name__ == "__main__":
    unittest.main()
