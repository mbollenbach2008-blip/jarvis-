#!/usr/bin/env python3
"""Jarvis – Schulmanager-Morgenbericht.

Meldet sich bei Schulmanager Online an und erstellt einen Markdown-Bericht mit
Stundenplan/Vertretungen, Hausaufgaben, Klausuren und neuen Elternbriefen.

Zugangsdaten kommen aus Umgebungsvariablen:
    SCHULMANAGER_EMAIL     – Benutzername oder E-Mail
    SCHULMANAGER_PASSWORD  – Passwort
    SCHULMANAGER_STUDENT   – (optional) Vorname des Kindes, falls mehrere verknüpft sind

Schulmanager hat keine offizielle API; dieses Skript nutzt dieselben Endpunkte wie
die Weboberfläche. Fällt ein einzelner Bereich aus, wird er im Bericht vermerkt,
der Rest läuft weiter.

Nur Standardbibliothek – keine Abhängigkeiten nötig.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import sys
import urllib.error
import urllib.request

BASE = "https://login.schulmanager-online.de"
UA = "Mozilla/5.0 (X11; Linux x86_64) jarvis-morning-report"
WEEKDAYS = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]


class SchulmanagerError(RuntimeError):
    pass


def _request(url: str, data: dict | None = None, token: str | None = None) -> bytes:
    headers = {"User-Agent": UA, "Accept": "application/json, text/plain, */*"}
    body = None
    if data is not None:
        body = json.dumps(data).encode()
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=body, headers=headers, method="POST" if body else "GET")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read()
    except urllib.error.HTTPError as e:
        raise SchulmanagerError(f"HTTP {e.code} bei {url}: {e.read()[:300]!r}") from e


class Schulmanager:
    def __init__(self, email: str, password: str):
        self.email = email
        self.password = password
        self.token: str | None = None
        self.user: dict = {}
        self.bundle_version: str | None = None

    # --- Anmeldung ---------------------------------------------------------
    def login(self) -> None:
        raw = _request(
            f"{BASE}/api/login",
            {"emailOrUsername": self.email, "password": self.password,
             "mobileApp": False, "institutionId": None},
        )
        data = json.loads(raw)
        if not data.get("jwt"):
            raise SchulmanagerError("Anmeldung fehlgeschlagen – Zugangsdaten prüfen.")
        self.token = data["jwt"]
        self.user = data.get("user") or {}
        self.bundle_version = self._find_bundle_version()

    def _find_bundle_version(self) -> str | None:
        """Die Web-App schickt eine 'bundleVersion' mit; wir lesen sie aus dem JS-Bundle."""
        try:
            html = _request(f"{BASE}/").decode("utf-8", "replace")
            for script in re.findall(r'src="([^"]*main[^"]*\.js)"', html):
                js = _request(f"{BASE}/{script.lstrip('/')}").decode("utf-8", "replace")
                m = re.search(r'bundleVersion\s*[:=]\s*["\']([0-9a-zA-Z._-]+)["\']', js)
                if m:
                    return m.group(1)
        except Exception:  # noqa: BLE001 – optional, Server akzeptiert meist auch ohne
            pass
        return None

    # --- Schüler ermitteln ---------------------------------------------------
    def students(self) -> list[dict]:
        u = self.user
        found = []
        if u.get("associatedStudent"):
            found.append(u["associatedStudent"])
        for parent in u.get("associatedParents") or []:
            if parent.get("student"):
                found.append(parent["student"])
        return found

    # --- API-Aufrufe ---------------------------------------------------------
    def calls(self, requests: list[dict]) -> list[dict]:
        payload = {"requests": requests}
        if self.bundle_version:
            payload["bundleVersion"] = self.bundle_version
        raw = _request(f"{BASE}/api/calls", payload, self.token)
        data = json.loads(raw)
        return data.get("results") or []

    def call(self, module: str, endpoint: str, params: dict | None = None):
        res = self.calls([{"moduleName": module, "endpointName": endpoint,
                           "parameters": params or {}}])
        if not res:
            raise SchulmanagerError(f"{module}/{endpoint}: leere Antwort")
        r = res[0]
        if r.get("status", 200) != 200:
            raise SchulmanagerError(f"{module}/{endpoint}: Status {r.get('status')}")
        return r.get("data")


# --- Formatierung --------------------------------------------------------------

def _student_ref(s: dict) -> dict:
    return {k: s[k] for k in ("id", "firstname", "lastname", "sex", "classId") if k in s}


def _names(items) -> str:
    if not items:
        return ""
    if isinstance(items, dict):
        items = [items]
    out = []
    for i in items:
        if isinstance(i, dict):
            out.append(i.get("abbreviation") or i.get("name") or i.get("lastname") or "")
        else:
            out.append(str(i))
    return ", ".join(x for x in out if x)


def format_lessons(lessons: list[dict], day: dt.date) -> list[str]:
    today = [l for l in lessons or [] if str(l.get("date", ""))[:10] == day.isoformat()]
    if not today:
        return ["_Keine Stunden eingetragen._"]
    today.sort(key=lambda l: (l.get("classHour") or {}).get("number") or 0)
    lines = ["| Std. | Fach | Lehrer | Raum | Hinweis |", "|---|---|---|---|---|"]
    for l in today:
        hour = (l.get("classHour") or {}).get("number", "?")
        actual = l.get("actualLesson") or {}
        original = l.get("originalLessons") or []
        subject = (actual.get("subject") or {}).get("abbreviation") or \
                  (actual.get("subject") or {}).get("name") or ""
        teacher = _names(actual.get("teachers"))
        room = _names(actual.get("room"))
        notes = []
        ltype = l.get("type") or ""
        if ltype and ltype not in ("regularLesson",):
            notes.append({"cancelledLesson": "❌ Entfall", "changedLesson": "🔄 Vertretung",
                          "additionalLesson": "➕ Zusatzstunde", "event": "📅 Termin"}
                         .get(ltype, ltype))
        if original and ltype not in ("regularLesson", "cancelledLesson"):
            o = original[0]
            osub = (o.get("subject") or {}).get("abbreviation") or ""
            if osub and osub != subject:
                notes.append(f"statt {osub}")
        if actual.get("comment"):
            notes.append(actual["comment"])
        if l.get("comment"):
            notes.append(l["comment"])
        if ltype == "cancelledLesson" and not subject and original:
            subject = (original[0].get("subject") or {}).get("abbreviation") or ""
        lines.append(f"| {hour} | {subject} | {teacher} | {room} | {' · '.join(notes)} |")
    return lines


def format_homework(hw, day: dt.date) -> list[str]:
    items = hw if isinstance(hw, list) else (hw or {}).get("homeworks") or []
    upcoming = []
    for h in items:
        date = str(h.get("date") or h.get("dueDate") or "")[:10]
        if date and date < day.isoformat():
            continue
        upcoming.append((date, h))
    if not upcoming:
        return ["_Keine offenen Hausaufgaben._"]
    upcoming.sort(key=lambda x: x[0])
    lines = []
    for date, h in upcoming[:15]:
        subj = h.get("subject") or ""
        if isinstance(subj, dict):
            subj = subj.get("name") or subj.get("abbreviation") or ""
        text = (h.get("homework") or h.get("text") or "").strip().replace("\n", " ")
        lines.append(f"- **{date or '?'}** {subj}: {text}")
    return lines


def format_exams(exams, day: dt.date) -> list[str]:
    items = exams if isinstance(exams, list) else []
    if not items:
        return ["_Keine Klausuren in den nächsten 14 Tagen._"]
    items.sort(key=lambda e: str(e.get("date", "")))
    lines = []
    for e in items:
        subj = (e.get("subject") or {}).get("name") or ""
        typ = (e.get("type") or {}).get("name") or "Klausur"
        lines.append(f"- **{str(e.get('date',''))[:10]}** {typ} {subj} {e.get('comment') or ''}".rstrip())
    return lines


def format_letters(letters, day: dt.date) -> list[str]:
    items = letters if isinstance(letters, list) else []
    cutoff = (day - dt.timedelta(days=7)).isoformat()
    recent = [l for l in items if str(l.get("sentDate") or l.get("createdAt") or "")[:10] >= cutoff]
    if not recent:
        return ["_Keine neuen Elternbriefe in den letzten 7 Tagen._"]
    lines = []
    for l in recent[:10]:
        date = str(l.get("sentDate") or l.get("createdAt") or "")[:10]
        unread = "🆕 " if not (l.get("studentStatuses") or [{}])[0].get("readTimestamp") else ""
        lines.append(f"- {unread}**{date}** {l.get('title', '(ohne Titel)')}")
    return lines


def build_report(sm: Schulmanager, day: dt.date, wanted: str | None) -> str:
    students = sm.students()
    if wanted:
        students = [s for s in students if s.get("firstname", "").lower() == wanted.lower()] or students
    if not students:
        raise SchulmanagerError("Kein Schüler mit diesem Konto verknüpft.")

    out = [f"# 🏫 Schulmanager – {WEEKDAYS[day.weekday()]}, {day.strftime('%d.%m.%Y')}", ""]
    for s in students:
        ref = _student_ref(s)
        if len(students) > 1:
            out += [f"## {s.get('firstname', '')} {s.get('lastname', '')}".rstrip(), ""]
        h = "###" if len(students) > 1 else "##"
        week_end = day + dt.timedelta(days=14)

        sections = [
            ("📚 Stundenplan heute",
             lambda: format_lessons(sm.call("schedules", "get-actual-lessons",
                                            {"student": ref, "start": day.isoformat(),
                                             "end": day.isoformat()}), day)),
            ("✏️ Hausaufgaben",
             lambda: format_homework(sm.call("classbook", "get-homework", {"student": ref}), day)),
            ("📝 Klausuren (14 Tage)",
             lambda: format_exams(sm.call("exams", "get-exams",
                                          {"student": ref, "start": day.isoformat(),
                                           "end": week_end.isoformat()}), day)),
            ("✉️ Elternbriefe",
             lambda: format_letters(sm.call("letters", "get-letters"), day)),
        ]
        for title, fn in sections:
            out.append(f"{h} {title}")
            try:
                out += fn()
            except Exception as e:  # noqa: BLE001
                out.append(f"_Konnte nicht geladen werden: {e}_")
            out.append("")
    return "\n".join(out)


def main() -> int:
    email = os.environ.get("SCHULMANAGER_EMAIL")
    password = os.environ.get("SCHULMANAGER_PASSWORD")
    if not email or not password:
        print("SCHULMANAGER_EMAIL und SCHULMANAGER_PASSWORD müssen gesetzt sein.", file=sys.stderr)
        return 2
    day = dt.date.fromisoformat(os.environ["REPORT_DATE"]) if os.environ.get("REPORT_DATE") else dt.date.today()

    sm = Schulmanager(email, password)
    sm.login()
    report = build_report(sm, day, os.environ.get("SCHULMANAGER_STUDENT"))
    print(report)

    out_path = os.environ.get("REPORT_FILE")
    if out_path:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
