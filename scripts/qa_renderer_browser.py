#!/usr/bin/env python3
"""Chrome DevTools-pipe renderer QA with offline loading and no package dependency."""

from __future__ import annotations

import argparse
import base64
import json
import os
import select
import shutil
import struct
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple


def default_chrome() -> Path:
    """Locate Chrome across platforms: CHROME_PATH, then macOS, then PATH."""
    override = os.environ.get("CHROME_PATH")
    if override:
        return Path(override)
    macos = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    if macos.is_file():
        return macos
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):
        found = shutil.which(name)
        if found:
            return Path(found)
    return macos


DEFAULT_VIEWPORTS = ((320, 812), (375, 812), (430, 900), (1440, 900))


AUDIT_EXPRESSION = r"""(() => {
  scrollTo(0,0);
  const root=document.documentElement;
  const bodyStyle=getComputedStyle(document.body);
  const links=[...document.querySelectorAll('a[href]')];
  const headings=[...document.querySelectorAll('h1,h2,h3,h4,h5,h6')].map(node => Number(node.tagName.slice(1)));
  const headingJumps=headings.filter((level,index) => index && level > headings[index-1] + 1).length;
  const resources=performance.getEntriesByType('resource').map(entry => entry.name);
  const sections=[...document.querySelectorAll('[data-section]')];
  const svgs=[...document.querySelectorAll('svg')];
  return {
    ready:true,
    viewportWidth:innerWidth,
    viewportHeight:innerHeight,
    scrollWidth:root.scrollWidth,
    clientWidth:root.clientWidth,
    horizontalOverflow:Math.max(0,root.scrollWidth-root.clientWidth),
    bodyFontPx:parseFloat(bodyStyle.fontSize),
    bodyLineHeightPx:parseFloat(bodyStyle.lineHeight),
    minLinkHeight:links.length ? Math.min(...links.map(link => link.getBoundingClientRect().height)) : 999,
    sectionCount:sections.length,
    nonEmptySections:sections.filter(section => section.textContent.trim().length > 0).length,
    headingJumps,
    resourceRequests:resources,
    svgSemantics:svgs.every(svg => svg.querySelector('title') && svg.querySelector('desc')),
    timeSemantics:[...document.querySelectorAll('time')].every(node => Boolean(node.getAttribute('datetime'))),
    mainCount:document.querySelectorAll('main').length,
    h1Count:document.querySelectorAll('h1').length,
    coreTextLength:document.body.innerText.length
  };
})()"""


class ChromePipe:
    def __init__(self, chrome: Path, profile: Path) -> None:
        to_child_read, to_child_write = os.pipe()
        from_child_read, from_child_write = os.pipe()

        def map_pipes() -> None:
            os.dup2(to_child_read, 3)
            os.dup2(from_child_write, 4)

        command = [
            str(chrome), "--headless=new", "--disable-gpu", "--no-first-run",
            "--disable-default-apps", "--disable-default-browser-check",
            "--disable-background-networking", "--disable-background-mode",
            "--disable-component-update", "--disable-component-extensions-with-background-pages",
            "--disable-extensions", "--disable-sync", "--disable-breakpad",
            "--disable-crash-reporter", "--metrics-recording-only", "--no-service-autorun",
            "--password-store=basic", "--use-mock-keychain", "--safebrowsing-disable-auto-update",
            "--disable-features=OptimizationHints,MediaRouter,AutofillServerCommunication,CertificateTransparencyComponentUpdater,Translate,PushMessaging",
            "--user-data-dir=" + str(profile), "--remote-debugging-pipe", "about:blank",
        ]
        self.process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            pass_fds=tuple(sorted(set((to_child_read, from_child_write, 3, 4)))),
            preexec_fn=map_pipes,
        )
        os.close(to_child_read)
        os.close(from_child_write)
        self.write_fd = to_child_write
        self.read_fd = from_child_read
        self.buffer = b""
        self.next_id = 1
        self.events: List[Mapping[str, Any]] = []

    def command(self, method: str, params: Optional[Mapping[str, Any]] = None, session_id: Optional[str] = None, timeout: float = 10.0) -> Mapping[str, Any]:
        command_id = self.next_id
        self.next_id += 1
        message: Dict[str, Any] = {"id": command_id, "method": method, "params": dict(params or {})}
        if session_id:
            message["sessionId"] = session_id
        self._write(json.dumps(message, separators=(",", ":")).encode("utf-8") + b"\0")
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            response = self._read(deadline - time.monotonic())
            if response.get("id") == command_id:
                if "error" in response:
                    raise RuntimeError("CDP %s failed: %s" % (method, response["error"]))
                return response.get("result", {})
            self.events.append(response)
        raise TimeoutError("CDP command timed out: %s" % method)

    def wait_event(self, method: str, session_id: Optional[str] = None, timeout: float = 10.0) -> Mapping[str, Any]:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            for index, event in enumerate(self.events):
                if event.get("method") == method and (session_id is None or event.get("sessionId") == session_id):
                    return self.events.pop(index)
            self.events.append(self._read(deadline - time.monotonic()))
        raise TimeoutError("CDP event timed out: %s" % method)

    def _write(self, data: bytes) -> None:
        view = memoryview(data)
        while view:
            written = os.write(self.write_fd, view)
            view = view[written:]

    def _read(self, timeout: float) -> Mapping[str, Any]:
        while b"\0" not in self.buffer:
            ready, _, _ = select.select([self.read_fd], [], [], max(0, timeout))
            if not ready:
                raise TimeoutError("CDP pipe read timed out")
            chunk = os.read(self.read_fd, 65536)
            if not chunk:
                raise RuntimeError("Chrome closed the DevTools pipe")
            self.buffer += chunk
        raw, self.buffer = self.buffer.split(b"\0", 1)
        return json.loads(raw.decode("utf-8"))

    def close(self) -> None:
        for fd in (self.write_fd, self.read_fd):
            try:
                os.close(fd)
            except OSError:
                pass
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=3)


def png_dimensions(path: Path) -> Tuple[int, int]:
    data = path.read_bytes()[:24]
    if len(data) != 24 or data[:8] != b"\x89PNG\r\n\x1a\n":
        raise RuntimeError("screenshot is not a PNG")
    return struct.unpack(">II", data[16:24])


def validate_report(report: Mapping[str, Any], width: int, errors: Sequence[str]) -> List[str]:
    checks = {
        "viewport width": report.get("viewportWidth") == width,
        "horizontal overflow": report.get("horizontalOverflow", 999) <= 1,
        "body font": report.get("bodyFontPx", 0) >= 16,
        "line height": report.get("bodyLineHeightPx", 0) / max(report.get("bodyFontPx", 1), 1) >= 1.45,
        "touch targets": report.get("minLinkHeight", 0) >= 44,
        "12 sections": report.get("sectionCount") == 12 and report.get("nonEmptySections") == 12,
        "heading order": report.get("headingJumps") == 0,
        "zero resource requests": report.get("resourceRequests") == [],
        "svg semantics": bool(report.get("svgSemantics")),
        "time semantics": bool(report.get("timeSemantics")),
        "landmarks": report.get("mainCount") == 1 and report.get("h1Count") == 1,
        "console errors": not errors,
        "core readable": report.get("coreTextLength", 0) > 300,
    }
    return [name for name, passed in checks.items() if not passed]


def console_errors(events: Sequence[Mapping[str, Any]]) -> List[str]:
    errors = []
    for event in events:
        if event.get("method") == "Runtime.exceptionThrown":
            errors.append("runtime exception")
        if event.get("method") == "Log.entryAdded" and event.get("params", {}).get("entry", {}).get("level") == "error":
            errors.append(str(event["params"]["entry"].get("text", "log error")))
    return errors


def run_qa(html_path: Path, output: Path, chrome: Path, viewports: Sequence[Tuple[int, int]]) -> Mapping[str, Any]:
    if not chrome.is_file():
        raise RuntimeError("Chrome executable is absent: %s" % chrome)
    output.mkdir(parents=True, exist_ok=True)
    target = output / "trip.html"
    shutil.copy2(html_path, target)
    profile = output / "chrome-profile"
    browser = ChromePipe(chrome, profile)
    reports = []
    failures: List[str] = []
    screenshots: List[str] = []
    try:
        target_id = browser.command("Target.createTarget", {"url": "about:blank"})["targetId"]
        session_id = browser.command("Target.attachToTarget", {"targetId": target_id, "flatten": True})["sessionId"]
        for method in ("Page.enable", "Runtime.enable", "Network.enable", "Log.enable"):
            browser.command(method, session_id=session_id)
        browser.command(
            "Network.emulateNetworkConditions",
            {"offline": True, "latency": 0, "downloadThroughput": 0, "uploadThroughput": 0, "connectionType": "none"},
            session_id=session_id,
        )

        for width, height in viewports:
            browser.events.clear()
            browser.command(
                "Emulation.setDeviceMetricsOverride",
                {"width": width, "height": height, "deviceScaleFactor": 1, "mobile": width < 768},
                session_id=session_id,
            )
            browser.command("Page.navigate", {"url": target.resolve().as_uri()}, session_id=session_id)
            browser.wait_event("Page.loadEventFired", session_id=session_id)
            evaluated = browser.command(
                "Runtime.evaluate",
                {"expression": AUDIT_EXPRESSION, "returnByValue": True, "awaitPromise": True},
                session_id=session_id,
            )
            report = dict(evaluated["result"]["value"])
            errors = console_errors(browser.events)
            report["requestedViewport"] = [width, height]
            report["consoleErrors"] = errors
            failures.extend("%dx%d %s" % (width, height, item) for item in validate_report(report, width, errors))
            reports.append(report)

            if width in (375, 1440):
                captured = browser.command(
                    "Page.captureScreenshot",
                    {"format": "png", "fromSurface": True, "captureBeyondViewport": False},
                    session_id=session_id,
                )
                screenshot = output / ("renderer-%dx%d.png" % (width, height))
                screenshot.write_bytes(base64.b64decode(captured["data"]))
                screenshots.append(str(screenshot))
                if png_dimensions(screenshot) != (width, height):
                    failures.append("%dx%d screenshot dimensions differ" % (width, height))

        printed = browser.command(
            "Page.printToPDF",
            {"printBackground": True, "displayHeaderFooter": False, "preferCSSPageSize": True},
            session_id=session_id,
        )
        pdf = output / "renderer-print.pdf"
        pdf.write_bytes(base64.b64decode(printed["data"]))
        if pdf.stat().st_size < 1000 or not pdf.read_bytes().startswith(b"%PDF"):
            failures.append("print PDF failed")
        browser.command("Target.closeTarget", {"targetId": target_id})
    finally:
        browser.close()
        shutil.rmtree(profile, ignore_errors=True)

    result = {
        "chrome": str(chrome),
        "network": "offline-before-file-navigation",
        "viewports": reports,
        "screenshots": screenshots,
        "print_pdf": str(output / "renderer-print.pdf"),
        "failures": failures,
    }
    (output / "qa-report.json").write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def parse_viewports(value: str) -> Sequence[Tuple[int, int]]:
    result = []
    for item in value.split(","):
        width, height = item.lower().split("x", 1)
        result.append((int(width), int(height)))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Run offline Chrome QA against a rendered Trip HTML")
    parser.add_argument("html", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--chrome", type=Path, default=None)
    parser.add_argument("--viewports", default=",".join("%dx%d" % item for item in DEFAULT_VIEWPORTS))
    args = parser.parse_args()
    chrome = args.chrome or default_chrome()
    result = run_qa(args.html.resolve(), args.output.resolve(), chrome, parse_viewports(args.viewports))
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 1 if result["failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
