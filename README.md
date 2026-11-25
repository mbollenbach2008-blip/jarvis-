# jarvis-

## 🏫 Schulmanager-Morgenbericht

Jeden Schultag (Mo–Fr) um **06:45 Uhr** (Sommerzeit 07:45 Uhr) meldet sich Jarvis bei
[Schulmanager Online](https://login.schulmanager-online.de) an und erstellt einen Bericht mit:

- 📚 Stundenplan des Tages inkl. Entfall & Vertretungen
- ✏️ offenen Hausaufgaben
- 📝 Klausuren der nächsten 14 Tage
- ✉️ Elternbriefen der letzten 7 Tage

Der Bericht wird als **GitHub-Issue** gepostet (→ Push-Benachrichtigung in der GitHub-App)
und steht zusätzlich in der Zusammenfassung des Actions-Laufs.

### Einrichtung (einmalig)

1. Im Repo auf **Settings → Secrets and variables → Actions → New repository secret**:
   - `SCHULMANAGER_EMAIL` – dein Schulmanager-Benutzername/E-Mail
   - `SCHULMANAGER_PASSWORD` – dein Passwort
2. Optional unter **Variables**: `SCHULMANAGER_STUDENT` = Vorname des Kindes, falls mehrere Kinder verknüpft sind.
3. Testen: **Actions → Schulmanager Morgenbericht → Run workflow**.

> Wichtig: Das Repo sollte **privat** sein, da die Issues Schuldaten enthalten.

### Lokal ausführen

```bash
SCHULMANAGER_EMAIL=... SCHULMANAGER_PASSWORD=... python3 schulmanager/morning_report.py
```

### Uhrzeit ändern

In `.github/workflows/schulmanager-morning.yml` die Zeile `cron: "45 5 * * 1-5"` anpassen
(Angabe in UTC; `* * *` am Ende statt `1-5` = auch am Wochenende).

### Hinweis

Schulmanager bietet keine offizielle API. Das Skript nutzt dieselben Schnittstellen wie die
Weboberfläche. Ändert Schulmanager diese, kann einzelnes nicht mehr laden – das wird dann im
Bericht vermerkt, der Rest läuft weiter. Bei 2-Faktor-Anmeldung oder Login über die Schule (SSO)
funktioniert der automatische Login nicht.
