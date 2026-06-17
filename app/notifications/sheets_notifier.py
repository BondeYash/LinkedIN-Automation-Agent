"""Google Sheets notifier — appends each draft as a row in a shared sheet.

The human edits a STATUS column in the sheet; the approval poller (or a manual
sync) reads it back to drive the decision. Disabled unless a service-account
credentials file and a spreadsheet id are configured.
"""

from __future__ import annotations

from app.core.config import Settings, get_settings
from app.models.enums import NotificationChannel
from app.notifications.base import NotifyPayload

_HEADER = ["post_id", "headline", "topic", "trend_score", "status", "approve_link", "reject_link"]


class SheetsNotifier:
    channel = NotificationChannel.SHEETS

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._ws = None

    def enabled(self) -> bool:
        return bool(self.settings.sheets_credentials_file and self.settings.sheets_spreadsheet_id)

    def _worksheet(self):
        if self._ws is None:
            import gspread  # lazy: only when this channel is actually used

            client = gspread.service_account(filename=self.settings.sheets_credentials_file)
            sheet = client.open_by_key(self.settings.sheets_spreadsheet_id)
            try:
                self._ws = sheet.worksheet(self.settings.sheets_worksheet)
            except Exception:
                self._ws = sheet.add_worksheet(self.settings.sheets_worksheet, rows=1000, cols=len(_HEADER))
                self._ws.append_row(_HEADER)
        return self._ws

    def send(self, payload: NotifyPayload) -> None:
        p = payload.post
        topic = p.topic.name if p.topic else ""
        self._worksheet().append_row(
            [
                p.id,
                p.headline or "",
                topic,
                p.trend_score or 0.0,
                p.status.value,
                payload.links.get("approve", ""),
                payload.links.get("reject", ""),
            ]
        )
