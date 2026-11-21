'''IMAP mailbox reader: pulls the OpenGame sign-in code out of the forwarded inbox.

The mailbox is shared by every alias of the operator, so the reader works on
message UIDs: the caller snapshots the inbox before asking for a code and only
messages newer than that snapshot are considered.  Without the snapshot the
previous (already used) code would be returned and the sign-in would fail.
'''

from __future__ import annotations

import email
import imaplib
import re
import time
from email.header import decode_header, make_header

CODE_RE = re.compile(r'sign-in code:\s*([0-9]{8})', re.I)
CODE_RE_LOOSE = re.compile(r'\b([0-9]{8})\b')


def _decode(value: str) -> str:
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return value


class ImapMailbox:
    '''Poll an IMAP inbox for the newest OpenGame sign-in code for one address.'''

    def __init__(self, host: str, user: str, password: str, port: int = 993, folder: str = 'INBOX'):
        self.host = host
        self.user = user
        self.password = password
        self.port = port
        self.folder = folder

    def _connect(self):
        box = imaplib.IMAP4_SSL(self.host, self.port, timeout=30)
        box.login(self.user, self.password)
        box.select(self.folder)
        return box

    @staticmethod
    def _uids(box) -> list[int]:
        typ, data = box.uid('search', None, 'ALL')
        if typ != 'OK' or not data or not data[0]:
            return []
        return [int(part) for part in data[0].split()]

    def latest_uid(self) -> int:
        '''Highest UID currently in the folder (0 when the folder is empty).'''

        box = self._connect()
        try:
            uids = self._uids(box)
            return max(uids) if uids else 0
        finally:
            try:
                box.logout()
            except Exception:
                pass

    @staticmethod
    def _headers(box, uid: int) -> str:
        typ, fetched = box.uid('fetch', str(uid), '(BODY.PEEK[HEADER.FIELDS (TO SUBJECT DATE)])')
        if typ != 'OK' or not fetched or not isinstance(fetched[0], tuple):
            return ''
        return fetched[0][1].decode('utf-8', 'replace')

    def wait_for_sign_in_code(
        self,
        email_address: str,
        timeout: int = 180,
        poll: float = 3.0,
        after_uid: int = 0,
    ) -> str | None:
        '''Return the 8 digit code mailed to this address (None on timeout).

        Only messages with a UID greater than ``after_uid`` are looked at, so a
        code that was already used is never returned twice.
        '''
        deadline = time.time() + timeout
        box = self._connect()
        try:
            while time.time() < deadline:
                for uid in sorted(self._uids(box), reverse=True):
                    if uid <= after_uid:
                        break
                    header = self._headers(box, uid)
                    if not header or email_address.lower() not in header.lower():
                        continue
                    subject = ''
                    for line in header.splitlines():
                        if line.lower().startswith('subject:'):
                            subject = _decode(line.split(':', 1)[1].strip())
                    if 'welcome' in subject.lower():
                        continue
                    match = CODE_RE.search(subject) or CODE_RE.search(header)
                    if match:
                        return match.group(1)
                time.sleep(poll)
        finally:
            try:
                box.logout()
            except Exception:
                pass
        return None

    def wait_for_welcome(self, email_address: str, timeout: int = 120, poll: float = 3.0) -> bool:
        '''True when the 'Welcome to OpenGame' mail for this address shows up.'''
        deadline = time.time() + timeout
        box = self._connect()
        try:
            while time.time() < deadline:
                for uid in sorted(self._uids(box), reverse=True):
                    header = self._headers(box, uid)
                    if header and email_address.lower() in header.lower() and 'welcome' in header.lower():
                        return True
                time.sleep(poll)
        finally:
            try:
                box.logout()
            except Exception:
                pass
        return False


def parse_code_from_message(raw: bytes) -> str | None:
    '''Extract the code from a full RFC822 message.'''
    msg = email.message_from_bytes(raw)
    parts = []
    for part in msg.walk():
        if part.get_content_type() in ('text/plain', 'text/html'):
            try:
                parts.append(part.get_payload(decode=True).decode('utf-8', 'replace'))
            except Exception:
                continue
    blob = '\n'.join(parts)
    match = CODE_RE.search(blob) or CODE_RE_LOOSE.search(blob)
    return match.group(1) if match else None
