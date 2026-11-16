#!/usr/bin/env python3
"""One-off bounded PISRS G1 positive-evidence probe. Run on PIKI only."""
import getpass
import hashlib
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import sys
import time
import unicodedata
import uuid
import warnings

import requests

BASE = "https://pisrs.si/extapi"
ZDR_SOP = "2013-01-0784"
ZDR_MOPED = "ZAKO5944"
ZDR_OLD_SHA = "d7a47fcafcf3faed5b185088751a7af76c76c95db8eaf0b02b6b4876da04d2b8"
ZVPOT_SOP = "2022-01-3083"
ZVPOT_MOPED = "ZAKO7054"
CELEX = "32011L0083"
CODE = 13022
LIMIT = 6
MAX_BODY = 4 * 1024 * 1024


def norm(value):
    return " ".join(unicodedata.normalize("NFC", value).casefold().split())


class Visible(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hidden = 0
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in {"head", "script", "style"}:
            self.hidden += 1

    def handle_endtag(self, tag):
        if tag in {"head", "script", "style"}:
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def base_markers(raw):
    try:
        html = raw.decode("utf-8-sig")
        parser = Visible()
        parser.feed(html)
        txt = norm(" ".join(parser.parts))
        article = re.search(r"\b162\s*\.\s*člen\s*\(?izraba letnega dopusta\)?(.*?)\b163\s*\.\s*člen\b", txt)
        return bool(article and re.search(r"\(4\).*31\s*\.\s*decembra naslednjega leta", article[1])) and not re.search(
            r"\b142\s*\.\s*a\s*člen\b|pravica do odklopa|\b2019/1152\b|neuradno prečiščeno besedilo\s+(predpisa|zakona)", txt
        )
    except (UnicodeError, ValueError):
        return False


def exact_row(rows, **match):
    found = [r for r in rows if isinstance(r, dict) and all(r.get(k) == v for k, v in match.items())]
    return found[0] if len(found) == 1 else None


def main():
    if os.uname().nodename.split(".")[0] != "piki" or not sys.stdin.isatty() or os.geteuid() == 0:
        raise SystemExit("NOT_RUN: execute as non-root in an interactive PIKI terminal")
    if input("Potrdi en sam omejen preizkus do 6 PISRS GET [yes/skip]: ").strip() != "yes":
        raise SystemExit("G1 NOT_RUN: no new GET")
    pace = input("Najmanjši razmik zahtevkov v sekundah [Enter=3]: ").strip() or "3"
    if not re.fullmatch(r"[1-9][0-9]{0,2}", pace):
        raise SystemExit("G1 NOT_RUN: invalid pacing")
    pace = int(pace)
    root = Path("/data/projects/.pisrs-g1-evidence")
    if root.exists() and (root.is_symlink() or not root.is_dir() or root.stat().st_uid != os.geteuid() or root.stat().st_mode & 0o077):
        raise SystemExit("G1 NOT_RUN: unsafe evidence directory")
    old_umask = os.umask(0o077)
    try:
        root.mkdir(mode=0o700, parents=False, exist_ok=True)
        run = root / ("run-" + uuid.uuid4().hex)
        run.mkdir(mode=0o700)
    finally:
        os.umask(old_umask)
    warnings.simplefilter("error", getpass.GetPassWarning)
    try:
        token = getpass.getpass("Obstoječi PISRS žeton (skriti vnos): ")
    except (EOFError, KeyboardInterrupt, getpass.GetPassWarning):
        token = ""
    if not token or any(c.isspace() for c in token):
        raise SystemExit("G1 NOT_RUN: no valid credential")
    count, last = 0, None

    def store(label, raw):
        fd = os.open(run / (label + ".body"), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        print(label, "bytes", len(raw), "sha256", hashlib.sha256(raw).hexdigest())

    with requests.Session() as session:
        session.trust_env = True
        session.headers.update({
            "User-Agent": "OpenLegalCore-PISRS-G1-positive-evidence/2026-11-16",
            "Accept": "application/json, text/html", "Accept-Encoding": "identity",
            "X-API-KEY": token, "Authorization": "Bearer " + token,
        })

        def read(label, path, mime, params=None):
            nonlocal count, last
            if count >= LIMIT:
                raise RuntimeError("request cap reached")
            if last is not None:
                time.sleep(max(0, pace - (time.monotonic() - last)))
            count += 1
            last = time.monotonic()
            with session.get(BASE + path, params=params, verify=True, allow_redirects=False, timeout=(8, 30), stream=True) as response:
                print(label, "HTTP", response.status_code)
                if response.status_code != 200 or response.headers.get("Content-Type", "").split(";", 1)[0].lower() != mime or response.headers.get("Content-Encoding", "identity").lower() != "identity":
                    raise RuntimeError("unexpected HTTP / content-type / content-encoding")
                raw = bytearray()
                for chunk in response.iter_content(65536):
                    raw.extend(chunk)
                    if len(raw) > MAX_BODY or time.monotonic() - last > 45:
                        raise RuntimeError("bounded body/time exceeded")
                store(label, raw)
            if mime == "text/html":
                return bytes(raw)
            data = json.loads(raw)
            if not isinstance(data, dict) or data.get("error") or not isinstance(data.get("data"), list) or any(not isinstance(x, dict) for x in data["data"]):
                raise RuntimeError("unexpected JSON envelope")
            return data["data"]

        try:
            zdr = read("zdr-catalog", "/predpis/register-predpisov", "application/json", {"sop": ZDR_SOP, "page": 1, "pageSize": 2})
            zr = exact_row(zdr, sop=ZDR_SOP, mopedId=ZDR_MOPED)
            if zr and type(zr.get("id")) is int and zr["id"] > 0:
                html = read("zdr-base", "/besedilo/" + str(zr["id"]), "text/html")
                digest = hashlib.sha256(html).hexdigest()
                print("ZDR_BASE", "PASS_BOUNDED" if base_markers(html) else "NOT_VERIFIED", "PRIOR_SHA_MATCH", digest == ZDR_OLD_SHA)
            else:
                print("ZDR_BASE NOT_VERIFIED: unique qualified base locator absent")
            rs = read("zvpot-catalog", "/predpis/register-predpisov", "application/json", {"sop": ZVPOT_SOP, "page": 1, "pageSize": 2})
            rr = exact_row(rs, sop=ZVPOT_SOP, mopedId=ZVPOT_MOPED)
            rs_edge = bool(rr and isinstance(rr.get("zveza"), list) and any(isinstance(v, dict) and v.get("celex") == CELEX for v in rr["zveza"]))
            print("RS_TO_EU", "PASS_BOUNDED" if rs_edge else "NOT_VERIFIED")
            eu = read("eu-catalog", "/predpis-eu", "application/json", {"celex": CELEX, "page": 1, "pageSize": 2})
            er = exact_row(eu, celex=CELEX)
            eu_edge = bool(er and isinstance(er.get("zveza"), list) and any(isinstance(v, dict) and v.get("mopedID") == ZVPOT_MOPED for v in er["zveza"]))
            print("EU_TARGET", "PASS_BOUNDED" if er else "NOT_VERIFIED")
            print("EU_TO_RS", "PASS_BOUNDED" if eu_edge else "NOT_VERIFIED")
            codes = read("sifranti-index", "/sifranti", "application/json")
            candidate = [c for c in codes if isinstance(c.get("naziv"), str) and norm(c["naziv"]) == "vrsta akta rs" and type(c.get("id")) is int and c["id"] > 0]
            if len(candidate) == 1:
                list_id = candidate[0]["id"]
                print("CODE_LIST_ID", list_id, "PASS_BOUNDED")
                values = read("sifranti-vrednosti", "/sifranti/" + str(list_id), "application/json")
                item = exact_row(values, id=CODE)
                print("CODE_13022", "PASS_BOUNDED" if item and isinstance(item.get("naziv"), str) and norm(item["naziv"]) == "pravilnik" else "NOT_VERIFIED")
            else:
                print("CODE_LIST_ID NOT_VERIFIED: unique dictionary ID absent")
        except (requests.RequestException, RuntimeError, ValueError, KeyboardInterrupt):
            print("G1 NOT_VERIFIED: stopped without retry")
        finally:
            print("NEW_GET_REQUESTS", str(count) + "/" + str(LIMIT))
            print("LOCAL_PRIVATE_EVIDENCE", run)


if __name__ == "__main__":
    main()
