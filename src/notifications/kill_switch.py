"""
InvestAid - E-mail Kill-Switch
Overvåger indbakken via IMAP og stopper al handel hvis brugeren svarer STOP.

Sådan virker det:
1. EmailNotifier gemmer Message-ID på alle alarm-mails der sendes
2. KillSwitch poller IMAP indbakken hvert minut
3. Hvis den finder et svar til en af vores alarm-mails med kodeordet STOP,
   sættes trading_halted = True i databasen
4. PortfolioManager tjekker flaget før enhver handling
5. Bekræftelses-mail sendes til brugeren

Konfiguration i .env:
    EMAIL_IMAP_HOST=imap.gmail.com      # Optional, default Gmail
    EMAIL_KILL_WORD=STOP                # Optional, default STOP
"""

import imaplib
import logging
import os
import email
import threading
import time
from datetime import datetime, timedelta
from email.header import decode_header
from typing import Optional

from sqlalchemy import Boolean, Column, DateTime, Integer, String, text

logger = logging.getLogger(__name__)

# Globalt in-memory flag — tjekkes af PortfolioManager
_kill_switch_active: bool = False
_kill_switch_lock = threading.Lock()
_tracked_message_ids: set[str] = set()


def is_kill_switch_active() -> bool:
    """Returner True hvis brugeren har sendt STOP-kommandoen."""
    with _kill_switch_lock:
        # Tjek også databasen for persistens på tværs af genstarter
        return _kill_switch_active or _load_halted_from_db()


def activate_kill_switch(reason: str = "e-mail kill-switch") -> None:
    """Aktiver kill-switchen og gem i database."""
    global _kill_switch_active
    with _kill_switch_lock:
        _kill_switch_active = True
    _save_halted_to_db(reason)
    logger.critical(f"KILL-SWITCH AKTIVERET: {reason}")


def reset_kill_switch() -> None:
    """Nulstil kill-switchen (kun ved manuel genstart)."""
    global _kill_switch_active
    with _kill_switch_lock:
        _kill_switch_active = False
    _clear_halted_in_db()
    logger.info("Kill-switch nulstillet")


def track_message_id(message_id: str) -> None:
    """Registrer et Message-ID der skal overvåges for svar."""
    if message_id:
        _tracked_message_ids.add(message_id)
        logger.debug(f"Overvåger Message-ID: {message_id}")


# ------------------------------------------------------------------ #
#  Database persistens                                                 #
# ------------------------------------------------------------------ #

def _load_halted_from_db() -> bool:
    try:
        from src.database import engine
        with engine.connect() as conn:
            result = conn.execute(
                text("SELECT value FROM system_flags WHERE key = 'trading_halted' LIMIT 1")
            )
            row = result.fetchone()
            return row is not None and row[0] == "true"
    except Exception:
        return False


def _save_halted_to_db(reason: str) -> None:
    try:
        from src.database import engine
        with engine.connect() as conn:
            conn.execute(text("""
                INSERT INTO system_flags (key, value, updated_at, notes)
                VALUES ('trading_halted', 'true', :ts, :reason)
                ON CONFLICT(key) DO UPDATE SET
                    value = 'true', updated_at = :ts, notes = :reason
            """), {"ts": datetime.utcnow().isoformat(), "reason": reason})
            conn.commit()
    except Exception as e:
        logger.error(f"Kunne ikke gemme kill-switch i database: {e}")


def _clear_halted_in_db() -> None:
    try:
        from src.database import engine
        with engine.connect() as conn:
            conn.execute(text("""
                INSERT INTO system_flags (key, value, updated_at, notes)
                VALUES ('trading_halted', 'false', :ts, 'manuel nulstilling')
                ON CONFLICT(key) DO UPDATE SET
                    value = 'false', updated_at = :ts, notes = 'manuel nulstilling'
            """), {"ts": datetime.utcnow().isoformat()})
            conn.commit()
    except Exception as e:
        logger.error(f"Kunne ikke nulstille kill-switch i database: {e}")


def _ensure_system_flags_table() -> None:
    """Opret system_flags tabel hvis den ikke eksisterer."""
    try:
        from src.database import engine
        with engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS system_flags (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT,
                    notes TEXT
                )
            """))
            conn.commit()
    except Exception as e:
        logger.error(f"Kunne ikke oprette system_flags tabel: {e}")


# ------------------------------------------------------------------ #
#  IMAP Polling                                                        #
# ------------------------------------------------------------------ #

class KillSwitchMonitor:
    """
    Overvåger e-mail indbakken via IMAP for STOP-kommandoer.
    Kører i en baggrundstråd.
    """

    def __init__(
        self,
        imap_host: str,
        email_address: str,
        password: str,
        kill_word: str = "STOP",
        poll_interval_seconds: int = 60,
    ):
        self.imap_host = imap_host
        self.email_address = email_address
        self.password = password
        self.kill_word = kill_word.strip().upper()
        self.poll_interval = poll_interval_seconds
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._notifier = None

    def set_notifier(self, notifier) -> None:
        """Sæt EmailNotifier til at sende bekræftelsesmails."""
        self._notifier = notifier

    def start(self) -> None:
        """Start IMAP-polling i baggrundstråd."""
        _ensure_system_flags_table()

        if not self.email_address or not self.password:
            logger.info("Kill-switch IMAP monitor deaktiveret (ingen e-mail konfigureret)")
            return

        self._running = True
        self._thread = threading.Thread(
            target=self._poll_loop,
            name="KillSwitchMonitor",
            daemon=True,
        )
        self._thread.start()
        logger.info(
            f"Kill-switch monitor startet (tjekker indbakken hvert "
            f"{self.poll_interval}s for kodeordet '{self.kill_word}')"
        )

    def stop(self) -> None:
        self._running = False

    def _poll_loop(self) -> None:
        while self._running:
            try:
                self._check_inbox()
            except Exception as e:
                logger.error(f"Kill-switch IMAP fejl: {e}")
            time.sleep(self.poll_interval)

    def _check_inbox(self) -> None:
        """Forbind til IMAP og søg efter STOP-svar."""
        if is_kill_switch_active():
            return  # Allerede aktiveret

        with imaplib.IMAP4_SSL(self.imap_host) as imap:
            imap.login(self.email_address, self.password)
            imap.select("INBOX")

            # Søg efter ulæste mails de seneste 24 timer
            since_date = (datetime.now() - timedelta(hours=24)).strftime("%d-%b-%Y")
            _, msg_nums = imap.search(None, f'(UNSEEN SINCE "{since_date}")')

            if not msg_nums or not msg_nums[0]:
                return

            for num in msg_nums[0].split():
                _, msg_data = imap.fetch(num, "(RFC822)")
                if not msg_data or not msg_data[0]:
                    continue

                raw = msg_data[0][1]
                msg = email.message_from_bytes(raw)

                # Tjek om dette er et svar til en af vores alarm-mails
                in_reply_to = msg.get("In-Reply-To", "")
                references = msg.get("References", "")

                is_reply_to_us = (
                    any(mid in in_reply_to for mid in _tracked_message_ids)
                    or any(mid in references for mid in _tracked_message_ids)
                    or msg.get("X-InvestAid-Reply") == "true"
                )

                # Også tjek generelt for InvestAid-svar selv uden match
                # (f.eks. hvis brugeren videresender eller skriver manuelt)
                subject_raw = msg.get("Subject", "")
                subject = self._decode_header(subject_raw).upper()
                is_investaid_subject = "INVESTAID" in subject

                if not (is_reply_to_us or is_investaid_subject):
                    continue

                # Tjek mail-indholdet for kodeordet
                body = self._get_body(msg).strip().upper()
                sender = msg.get("From", "ukendt")

                if self.kill_word in body or self.kill_word in subject:
                    logger.critical(
                        f"STOP-kommando modtaget fra: {sender} — aktiverer kill-switch"
                    )

                    # Annullér alle åbne ordrer
                    self._cancel_all_orders()

                    # Aktiver kill-switch
                    activate_kill_switch(reason=f"E-mail fra {sender}")

                    # Markér mailen som læst
                    imap.store(num, "+FLAGS", "\\Seen")

                    # Send bekræftelse
                    if self._notifier:
                        self._notifier.send_kill_switch_confirmation(sender)

                    return  # Stop søgning — kill-switch er aktiv

    def _cancel_all_orders(self) -> None:
        """Annullér alle ventende ordrer via broker."""
        try:
            from src.broker.alpaca_client import create_client_from_config
            broker = create_client_from_config()
            if broker.is_connected:
                count = broker.cancel_all_orders()
                logger.info(f"Kill-switch: annullerede {count} åbne ordrer")
        except Exception as e:
            logger.error(f"Kunne ikke annullere ordrer ved kill-switch: {e}")

    @staticmethod
    def _decode_header(value: str) -> str:
        parts = decode_header(value)
        decoded = []
        for part, charset in parts:
            if isinstance(part, bytes):
                decoded.append(part.decode(charset or "utf-8", errors="replace"))
            else:
                decoded.append(part)
        return " ".join(decoded)

    @staticmethod
    def _get_body(msg: email.message.Message) -> str:
        """Udtræk tekstindhold fra e-mail."""
        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                ct = part.get_content_type()
                if ct == "text/plain":
                    payload = part.get_payload(decode=True)
                    if payload:
                        body += payload.decode("utf-8", errors="replace")
        else:
            payload = msg.get_payload(decode=True)
            if payload:
                body = payload.decode("utf-8", errors="replace")
        return body


def create_monitor_from_config() -> KillSwitchMonitor:
    """Opret KillSwitchMonitor fra miljøvariabler."""
    return KillSwitchMonitor(
        imap_host=os.getenv("EMAIL_IMAP_HOST", "imap.gmail.com"),
        email_address=os.getenv("EMAIL_SENDER", ""),
        password=os.getenv("EMAIL_PASSWORD", ""),
        kill_word=os.getenv("EMAIL_KILL_WORD", "STOP"),
        poll_interval_seconds=int(os.getenv("EMAIL_KILL_SWITCH_INTERVAL", "60")),
    )
