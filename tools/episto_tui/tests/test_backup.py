from episto_tui.backup import backup_before_write


def test_backup_kopiert_vorhandene_datei(tmp_path):
    original = tmp_path / "quelle" / "kapitel.md"
    original.parent.mkdir(parents=True)
    original.write_text("Originalinhalt", encoding="utf-8")

    ziel = backup_before_write(tmp_path, original)

    assert ziel is not None
    assert ziel.exists()
    assert ziel.read_text(encoding="utf-8") == "Originalinhalt"
    assert ziel.parent == tmp_path / "notizen" / "_backup"
    assert original.read_text(encoding="utf-8") == "Originalinhalt"


def test_backup_gibt_none_zurueck_wenn_datei_fehlt(tmp_path):
    original = tmp_path / "quelle" / "nicht-vorhanden.md"
    ziel = backup_before_write(tmp_path, original)
    assert ziel is None


def test_backup_dateiname_enthaelt_zeitstempel(tmp_path):
    original = tmp_path / "notizen" / "tags.json"
    original.parent.mkdir(parents=True)
    original.write_text("{}", encoding="utf-8")

    ziel = backup_before_write(tmp_path, original)

    assert ziel.name.startswith("tags.")
    assert ziel.name.endswith(".json")
    assert ziel.name != "tags.json"


def test_backup_kollision_in_derselben_sekunde_ueberschreibt_nichts(tmp_path, monkeypatch):
    """I-2: zwei Backups mit identischem Zeitstempel (zwei Speichervorgaenge in
    derselben Sekunde) muessen zwei verschiedene Dateien ergeben -- das erste
    Backup (der echte Originalinhalt) darf nie ueberschrieben werden."""
    import datetime as _dt
    from episto_tui import backup as backup_modul

    class _EingefroreneZeit(_dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 9, 27, 12, 0, 0)

    monkeypatch.setattr(backup_modul, "datetime", _EingefroreneZeit)

    original = tmp_path / "quelle" / "kapitel.md"
    original.parent.mkdir(parents=True)
    original.write_text("Original", encoding="utf-8")
    erstes = backup_before_write(tmp_path, original)

    original.write_text("Zwischenstand", encoding="utf-8")
    zweites = backup_before_write(tmp_path, original)

    original.write_text("Dritter Stand", encoding="utf-8")
    drittes = backup_before_write(tmp_path, original)

    assert len({erstes, zweites, drittes}) == 3
    assert erstes.name == "kapitel.20260927-120000.md"
    assert zweites.name == "kapitel.20260927-120000-1.md"
    assert drittes.name == "kapitel.20260927-120000-2.md"
    assert erstes.read_text(encoding="utf-8") == "Original"
    assert zweites.read_text(encoding="utf-8") == "Zwischenstand"
    assert drittes.read_text(encoding="utf-8") == "Dritter Stand"
