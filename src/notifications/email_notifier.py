"""
InvestAid - E-mail Notifikationer
Sender automatiske mails ved handel, alarmer og daglig status.

Konfiguration i .env:
    EMAIL_SENDER=din@gmail.com
    EMAIL_PASSWORD=xxxx xxxx xxxx xxxx   # Gmail App Password
    EMAIL_RECIPIENT=din@gmail.com
    EMAIL_SMTP_HOST=smtp.gmail.com       # Optional, default Gmail
    EMAIL_SMTP_PORT=587                  # Optional, default 587

Gmail-vejledning:
    1. Slå 2-faktor-godkendelse til på din Google-konto
    2. Gå til myaccount.google.com → Sikkerhed → App-adgangskoder
    3. Opret en adgangskode til "Mail" og indsæt den i EMAIL_PASSWORD
"""

import logging
import os
import smtplib
import uuid
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

logger = logging.getLogger(__name__)


class EmailNotifier:
    def __init__(
        self,
        sender: str,
        password: str,
        recipient: str,
        smtp_host: str = "smtp.gmail.com",
        smtp_port: int = 587,
        paper_mode: bool = True,
    ):
        self.sender = sender
        self.password = password
        self.recipient = recipient
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.paper_mode = paper_mode
        self._enabled = bool(sender and password and recipient)

        if not self._enabled:
            logger.info("E-mail notifikationer deaktiveret (mangler konfiguration i .env)")

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    def _build_message(
        self,
        subject: str,
        body_html: str,
        message_id: Optional[str] = None,
    ) -> MIMEMultipart:
        mode_tag = "[PAPER] " if self.paper_mode else "[LIVE] "
        msg = MIMEMultipart("alternative")
        msg["From"] = self.sender
        msg["To"] = self.recipient
        msg["Subject"] = f"InvestAid {mode_tag}{subject}"
        msg["Message-ID"] = message_id or f"<investaid-{uuid.uuid4()}@investaid>"
        msg["X-InvestAid"] = "true"

        # Simpel text fallback
        plain = body_html.replace("<br>", "\n").replace("</p>", "\n\n")
        import re
        plain = re.sub(r"<[^>]+>", "", plain)
        msg.attach(MIMEText(plain, "plain", "utf-8"))
        msg.attach(MIMEText(body_html, "html", "utf-8"))
        return msg

    def _send(self, msg: MIMEMultipart) -> bool:
        try:
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.ehlo()
                server.starttls()
                server.login(self.sender, self.password)
                server.sendmail(self.sender, self.recipient, msg.as_string())
            logger.info(f"E-mail sendt: {msg['Subject']}")
            return True
        except Exception as e:
            logger.error(f"Fejl ved afsendelse af e-mail: {e}")
            return False

    # ------------------------------------------------------------------ #
    #  Offentlige notifikationsmetoder                                     #
    # ------------------------------------------------------------------ #

    def send_trade_notification(
        self,
        symbol: str,
        side: str,
        qty: float,
        price: Optional[float],
        strategy: str,
        notional: Optional[float] = None,
    ) -> bool:
        """Send notifikation om udført handel."""
        if not self._enabled:
            return False

        side_da = "KØB" if side == "buy" else "SÆLG"
        value_str = f"${notional:,.2f}" if notional else f"{qty:.4f} stk"
        price_str = f"${price:,.2f}" if price else "markedspris"

        body = f"""
        <p>En handel er netop blevet udført:</p>
        <table style="border-collapse:collapse;font-family:monospace;">
            <tr><td style="padding:4px 12px 4px 0"><b>Retning</b></td><td>{side_da}</td></tr>
            <tr><td style="padding:4px 12px 4px 0"><b>Symbol</b></td><td>{symbol}</td></tr>
            <tr><td style="padding:4px 12px 4px 0"><b>Beløb/antal</b></td><td>{value_str}</td></tr>
            <tr><td style="padding:4px 12px 4px 0"><b>Pris</b></td><td>{price_str}</td></tr>
            <tr><td style="padding:4px 12px 4px 0"><b>Strategi</b></td><td>{strategy}</td></tr>
            <tr><td style="padding:4px 12px 4px 0"><b>Tidspunkt</b></td>
                <td>{datetime.now().strftime("%d/%m/%Y %H:%M")}</td></tr>
        </table>
        <p style="color:#888;font-size:12px;">
            Svar på denne mail med kodeordet <b>STOP</b> for at standse al handel øjeblikkeligt.
        </p>
        """
        msg = self._build_message(f"Handel udført: {side_da} {symbol}", body)
        return self._send(msg)

    def send_risk_alert(
        self,
        alert_type: str,
        symbol: str,
        loss_pct: float,
        portfolio_value: float,
    ) -> str:
        """
        Send risiko-alarm og returner Message-ID så kill-switchen kan matche svar.
        """
        if not self._enabled:
            return ""

        message_id = f"<investaid-alert-{uuid.uuid4()}@investaid>"

        if alert_type == "stop_loss":
            subject = f"ALARM: Stop-loss aktiveret — {symbol}"
            color = "#CC0000"
            headline = f"Stop-loss aktiveret for {symbol}"
            detail = f"Positionen faldt {loss_pct:.1%} og er automatisk solgt."
        elif alert_type == "daily_loss":
            subject = f"ALARM: Daglig tabsgrænse nået"
            color = "#CC0000"
            headline = "Daglig tabsgrænse nået — handel stoppet"
            detail = (
                f"Porteføljen har mistet {loss_pct:.1%} i dag. "
                f"Al handel er automatisk stoppet for resten af dagen."
            )
        else:
            subject = f"ADVARSEL: {alert_type}"
            color = "#FF8800"
            headline = alert_type
            detail = ""

        body = f"""
        <div style="border-left:4px solid {color};padding:8px 16px;margin:8px 0">
            <h2 style="color:{color};margin:0">{headline}</h2>
        </div>
        <p>{detail}</p>
        <table style="border-collapse:collapse;font-family:monospace;">
            <tr><td style="padding:4px 12px 4px 0"><b>Porteføljeværdi</b></td>
                <td>${portfolio_value:,.2f}</td></tr>
            <tr><td style="padding:4px 12px 4px 0"><b>Tidspunkt</b></td>
                <td>{datetime.now().strftime("%d/%m/%Y %H:%M")}</td></tr>
        </table>
        <hr>
        <p style="font-size:14px">
            <b>Vil du stoppe al handel øjeblikkeligt?</b><br>
            Svar på denne mail med kodeordet <code>STOP</code> — systemet stopper
            inden for 1 minut og sender en bekræftelse.
        </p>
        """
        msg = self._build_message(subject, body, message_id=message_id)
        self._send(msg)
        return message_id

    def send_daily_status(
        self,
        portfolio_value: float,
        cash: float,
        daily_pnl: float,
        daily_pnl_pct: float,
        positions: list[dict],
        trades_today: int,
    ) -> bool:
        """Send daglig statusmail."""
        if not self._enabled:
            return False

        pnl_color = "#00AA44" if daily_pnl >= 0 else "#CC0000"
        pnl_sign = "+" if daily_pnl >= 0 else ""
        invested = portfolio_value - cash

        pos_rows = ""
        for p in positions:
            pl = p.get("unrealized_pl", 0)
            pl_color = "#00AA44" if pl >= 0 else "#CC0000"
            pos_rows += (
                f"<tr>"
                f"<td style='padding:3px 10px 3px 0'>{p['symbol']}</td>"
                f"<td style='padding:3px 10px 3px 0'>${p['market_value']:,.0f}</td>"
                f"<td style='color:{pl_color}'>{'+' if pl >= 0 else ''}{pl:,.2f} USD</td>"
                f"</tr>"
            )

        body = f"""
        <h2 style="margin-bottom:4px">Daglig status — {datetime.now().strftime("%d/%m/%Y")}</h2>
        <table style="border-collapse:collapse;font-family:monospace;margin-bottom:16px">
            <tr><td style="padding:4px 12px 4px 0"><b>Porteføljeværdi</b></td>
                <td><b>${portfolio_value:,.2f}</b></td></tr>
            <tr><td style="padding:4px 12px 4px 0"><b>Investeret</b></td>
                <td>${invested:,.2f}</td></tr>
            <tr><td style="padding:4px 12px 4px 0"><b>Likvide midler</b></td>
                <td>${cash:,.2f}</td></tr>
            <tr><td style="padding:4px 12px 4px 0"><b>Dagens P&amp;L</b></td>
                <td style="color:{pnl_color}"><b>{pnl_sign}${daily_pnl:,.2f}
                ({pnl_sign}{daily_pnl_pct:.2f}%)</b></td></tr>
            <tr><td style="padding:4px 12px 4px 0"><b>Handler i dag</b></td>
                <td>{trades_today}</td></tr>
        </table>
        {"<h3>Åbne positioner</h3><table style='border-collapse:collapse;font-family:monospace'>" + pos_rows + "</table>" if positions else "<p>Ingen åbne positioner.</p>"}
        <p style="color:#888;font-size:12px;margin-top:24px">
            Svar med <b>STOP</b> for at standse al handel øjeblikkeligt.
        </p>
        """
        msg = self._build_message(
            f"Daglig status — {pnl_sign}{daily_pnl_pct:.2f}% i dag", body
        )
        return self._send(msg)

    def send_kill_switch_confirmation(self, triggered_by_email: str) -> bool:
        """Send bekræftelse når kill-switchen er aktiveret."""
        if not self._enabled:
            return False

        body = f"""
        <div style="border-left:4px solid #CC0000;padding:8px 16px">
            <h2 style="color:#CC0000;margin:0">Handel STOPPET</h2>
        </div>
        <p>
            Kill-switchen er aktiveret. InvestAid handler ikke længere.<br>
            Alle ventende ordrer er annulleret.
        </p>
        <table style="border-collapse:collapse;font-family:monospace">
            <tr><td style="padding:4px 12px 4px 0"><b>Aktiveret af</b></td>
                <td>{triggered_by_email}</td></tr>
            <tr><td style="padding:4px 12px 4px 0"><b>Tidspunkt</b></td>
                <td>{datetime.now().strftime("%d/%m/%Y %H:%M:%S")}</td></tr>
        </table>
        <p>
            <b>Systemet kører stadig</b> — det overvåger blot ikke markedet.<br>
            For at genoptage handel skal du <b>genstarte botten manuelt</b>:
        </p>
        <pre style="background:#f4f4f4;padding:8px">python run_bot.py</pre>
        """
        msg = self._build_message("Handel STOPPET — kill-switch aktiveret", body)
        return self._send(msg)

    def send_system_error(self, error: str, context: str = "") -> bool:
        """Send alarm ved uventet systemfejl."""
        if not self._enabled:
            return False

        body = f"""
        <div style="border-left:4px solid #FF8800;padding:8px 16px">
            <h2 style="color:#FF8800;margin:0">Systemfejl</h2>
        </div>
        <p>InvestAid stødte på en uventet fejl og kan muligvis ikke handle korrekt.</p>
        <p><b>Fejl:</b> {error}</p>
        {"<p><b>Kontekst:</b> " + context + "</p>" if context else ""}
        <p><b>Tidspunkt:</b> {datetime.now().strftime("%d/%m/%Y %H:%M:%S")}</p>
        <p style="color:#888;font-size:12px">
            Svar med <b>STOP</b> for at standse al handel som en sikkerhedsforanstaltning.
        </p>
        """
        msg = self._build_message("FEJL: Systemfejl registreret", body)
        return self._send(msg)


def create_notifier_from_config() -> EmailNotifier:
    """Opret EmailNotifier fra miljøvariabler."""
    from src.config import get_config
    cfg = get_config()
    return EmailNotifier(
        sender=os.getenv("EMAIL_SENDER", ""),
        password=os.getenv("EMAIL_PASSWORD", ""),
        recipient=os.getenv("EMAIL_RECIPIENT", ""),
        smtp_host=os.getenv("EMAIL_SMTP_HOST", "smtp.gmail.com"),
        smtp_port=int(os.getenv("EMAIL_SMTP_PORT", "587")),
        paper_mode=cfg.is_paper_mode,
    )
