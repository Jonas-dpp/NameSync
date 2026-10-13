# NameSync 🤝✨

Eine leichtgewichtige, datenschutzfreundliche Web-App zur gemeinsamen Namensfindung. Egal ob für ein Projekt, ein Haustier oder ein Baby – NameSync hilft Gruppen dabei, Namensvorschläge zu sammeln, Favoriten zu finden und die größten Überschneidungen aufzudecken.

Entwickelt mit **Python** und **Streamlit**. 

## 🚀 Features

* **Kein Account-Zwang:** Nutzer benötigen weder E-Mail noch Passwort. Die Teilnahme erfolgt über einen simplen Einladungslink (UUID).
* **Gruppengröße:** Ausgelegt für kleine bis mittlere Gruppen (2 bis 32 Personen).
* **Intelligentes Ranking:** Die App wertet aus, welche Namen am häufigsten vorgeschlagen wurden, und visualisiert die Ergebnisse.
* **Überschneidungs-Analyse:** Zeigt an, welche Nutzer die größte Übereinstimmung bei ihren Namensvorschlägen haben ("Match-Faktor").
* **Admin-Rechte:** Der Ersteller der Gruppe erhält automatisch Übersichtsrechte, um die Gruppe zu verwalten.
* **Privacy First (Auto-Cleanup):** Um Datenmüll zu vermeiden, werden alle Gruppen und deren Inhalte **automatisch nach 7 Tagen gelöscht**, sobald die App aus dem Ruhezustand aufgeweckt wird.

## 🛠️ Technologien

* **Frontend & Backend:** [Streamlit](https://streamlit.io/) (Python)
* **Datenbank:** SQLite (lokal & serverless)
* **Datenverarbeitung:** Pandas

## 💻 Installation & Lokaler Start

Voraussetzung: Python 3.9 oder neuer ist auf deinem System installiert.

1. **Repository klonen**
   ```bash
   git clone https://github.com/DEIN_USERNAME/name-sync.git
   cd name-sync
   ```

2. **Virtuelle Umgebung erstellen und aktivieren (empfohlen)**
   ```bash
   python -m venv venv
   # Windows:
   venv\Scripts\activate
   # macOS/Linux:
   source venv/bin/activate
   ```

3. **Abhängigkeiten installieren**
   ```bash
   pip install -r requirements.txt
   ```
   *(Hinweis: Die `requirements.txt` sollte mindestens `streamlit` und `pandas` enthalten).*

4. **App starten**
   ```bash
   streamlit run app.py
   ```
   Die App öffnet sich nun automatisch in deinem Standard-Browser unter `http://localhost:8501`.

## 📖 Funktionsweise

1. **Gruppe erstellen:** Ein Nutzer klickt auf der Startseite auf "Neue Gruppe erstellen". Die Datenbank bereinigt in diesem Moment alte Einträge (> 7 Tage).
2. **Link teilen:** Es wird eine eindeutige URL (z.B. `?group=abc123xyz`) generiert. Der Ersteller ist durch seinen Session-State als Admin authentifiziert.
3. **Namen sammeln:** Der Ersteller teilt den Link. Teilnehmer öffnen die URL, geben einen Anzeigenamen ein und können sofort ihre Namensvorschläge in eine Liste eintragen.
4. **Ergebnisse auswerten:** Im Dashboard werden die beliebtesten Namen und die prozentualen Überschneidungen zwischen den Mitgliedern in Echtzeit angezeigt.

## 🤝 Mitwirken

Pull Requests sind willkommen! Für größere Änderungen eröffne bitte zuerst ein Issue, um zu diskutieren, was du ändern möchtest.

## 📄 Lizenz

Dieses Projekt ist unter der MIT-Lizenz lizenziert - siehe die [LICENSE](LICENSE) Datei für Details.
