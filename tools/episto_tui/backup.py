from __future__ import annotations
import shutil
from datetime import datetime
from pathlib import Path


def backup_before_write(buch_root: Path, original_path: Path) -> Path | None:
    """Sichert `original_path` nach notizen\\_backup\\<name>.<Zeitstempel><ext>
    (bei Namenskollision <name>.<Zeitstempel>-<n><ext>), bevor die Datei
    ueberschrieben wird. Gibt None zurueck, wenn die Datei noch nicht
    existiert (nichts zu sichern)."""
    if not original_path.exists():
        return None
    backup_dir = buch_root / "notizen" / "_backup"
    backup_dir.mkdir(parents=True, exist_ok=True)
    zeitstempel = datetime.now().strftime("%Y%m%d-%H%M%S")
    ziel = backup_dir / f"{original_path.stem}.{zeitstempel}{original_path.suffix}"
    # Zwei Speichervorgaenge in derselben Sekunde ergaeben denselben Namen;
    # das zweite Backup wuerde dann das erste (den echten Originalinhalt)
    # still ueberschreiben. Daher -1, -2, ... anhaengen, bis der Name frei ist.
    zaehler = 1
    while ziel.exists():
        ziel = backup_dir / f"{original_path.stem}.{zeitstempel}-{zaehler}{original_path.suffix}"
        zaehler += 1
    shutil.copy2(original_path, ziel)
    return ziel
