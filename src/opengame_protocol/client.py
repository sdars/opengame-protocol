"""Pure HTTP client for opengame.io.

Three request shapes walk the whole flow:

1. ``useActionState`` form actions (the sign-in card) are sent as
   ``multipart/form-data`` with React hidden fields:

       _1_$ACTION_REF_2 = ""
       _1_$ACTION_2:0   = {"id": "<action id>", "bound": "$@1"}
       _1_$ACTION_2:1   = <previous state as JSON>
       _1_$ACTION_KEY   = <32 hex chars>
       _1_<field>       = <field value>
       0                = [<previous state>, "$K1"]

2. Plain server references (``createServerReference``) are sent as a JSON array of
   the arguments in a ``text/plain;charset=UTF-8`` body with the ``Next-Action``
   header.  Example: claimFromHandlePage('cobaltpine7', null) is the body
   ``['cobaltpine7', null]``.

3. Plain JSON endpoints (``/api/jam/sponsor-code``) are ordinary POSTs.

Everything here is plain HTTP.  No browser, no adb, no Frida, no RPC bridge.
"""

from __future__ import annotations

import io
import json
import re
import time
import uuid
from typing import Any, Iterable

import requests

from . import actions as A

USER_AGENT = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
    'Chrome/157.0.0.0 Safari/537.36'
)

DQ = chr(34)


class ProtocolError(RuntimeError):
    """Raised when the server answers something the client cannot use."""


def _multipart(fields: dict[str, Any], boundary: str) -> bytes:
    buf = io.BytesIO()
    disposition = 'Content-Disposition: form-data; name=' + DQ + '%s' + DQ + '\r\n\r\n'
    for name, value in fields.items():
        buf.write(('--%s\r\n' % boundary).encode())
        buf.write((disposition % name).encode())
        buf.write(str(value).encode('utf-8'))
        buf.write(b'\r\n')
    buf.write(('--%s--\r\n' % boundary).encode())
    return buf.getvalue()


def parse_flight(text: str) -> list[Any]:
    """Pull the JSON records out of a React Flight (text/x-component) response.

    The payload is a sequence of ``<id>:<json>`` lines.  Values may reference each
    other with ``$@<id>``; those are resolved one level deep, which is enough for
    the action results this client consumes.
    """

    records: dict[int, Any] = {}
    order: list[int] = []
    for line in text.splitlines():
        match = re.match(r'^(\d+):(.*)$', line.strip())
        if not match:
            continue
        row = int(match.group(1))
        body = match.group(2)
        if body in ('', '[', '{}'):
            continue
        try:
            records[row] = json.loads(body)
        except ValueError:
            continue
        order.append(row)

    def resolve(value: Any) -> Any:
        if isinstance(value, str):
            ref = re.fullmatch(r'\$@(\d+)', value)
            if ref:
                return resolve(records.get(int(ref.group(1))))
            return value
        if isinstance(value, dict):
            return {key: resolve(item) for key, item in value.items()}
        if isinstance(value, list):
            return [resolve(item) for item in value]
        return value

    return [resolve(records[row]) for row in order]


def find_dicts(payload: Iterable[Any], wanted: tuple[str, ...]) -> list[dict]:
    """Collect every dict in a parsed flight payload carrying one of ``wanted``."""

    found: list[dict] = []
    stack = list(payload)
    while stack:
        item = stack.pop()
        if isinstance(item, dict):
            if any(key in item for key in wanted):
                found.append(item)
            stack.extend(item.values())
        elif isinstance(item, list):
            stack.extend(item)
    return found


def extract_sponsor_code(payload: Any) -> str | None:
    '''Pull the usable sponsor code out of an /api/jam/sponsor-code answer.

    The jam bundle renders two different shapes:

      * ``kind == "coupon"`` - a coupon id (``FAL-OPENGAME-XXXXXX``) in ``id``;
      * ``kind == "code"``   - a claim link in ``url``.

    ``kind == "exhausted"`` / ``"refused"`` carry no code at all, and
    ``"sign-in"`` / ``"handle"`` point at the page the visitor has to visit
    first.
    '''

    if not isinstance(payload, dict):
        return None
    kind = payload.get('kind')
    if kind == 'coupon':
        return payload.get('id') or payload.get('code') or None
    if kind == 'code':
        return payload.get('url') or payload.get('code') or None
    for key in ('code', 'id', 'url', 'value'):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    return None


class OpenGameClient:
    """A browser-shaped but browser-free HTTP session against opengame.io."""

    def __init__(self, proxy: str | None = None, user_agent: str = USER_AGENT):
        self.session = requests.Session()
        self.session.headers.update(
            {
                'User-Agent': user_agent,
                'Accept-Language': 'en-US,en;q=0.9',
                'Sec-Ch-Ua': '"Chromium";v="157", "Not=A?Brand";v="99"',
                'Sec-Ch-Ua-Mobile': '?0',
                'Sec-Ch-Ua-Platform': '"Windows"',
            }
        )
        if proxy:
            self.session.proxies.update({'http': proxy, 'https': proxy})

    # ------------------------------------------------------------------ helpers
    @property
    def base(self) -> str:
        return A.BASE

    def url(self, path: str) -> str:
        return path if path.startswith('http') else A.BASE + path

    def get(self, path: str, **kwargs: Any) -> requests.Response:
        return self.session.get(self.url(path), timeout=kwargs.pop('timeout', 45), **kwargs)

    def auth_token(self) -> str | None:
        return self.session.cookies.get('sb-auth-auth-token')

    def signed_in(self) -> bool:
        return bool(self.auth_token())

    # ------------------------------------------------------------ server action
    def server_action(
        self,
        path: str,
        action_id: str,
        args: Any,
        router_tree: str | None = None,
        referer: str | None = None,
    ) -> requests.Response:
        """Call a plain server reference: JSON args in a text/plain body."""

        headers = {
            'Accept': 'text/x-component',
            'Content-Type': 'text/plain;charset=UTF-8',
            'Next-Action': action_id,
            'Origin': A.BASE,
            'Referer': referer or self.url(path),
        }
        if router_tree:
            headers['Next-Router-State-Tree'] = router_tree
        return self.session.post(
            self.url(path),
            data=json.dumps(args, separators=(',', ':'), ensure_ascii=False).encode('utf-8'),
            headers=headers,
            timeout=45,
        )

    def action_result(self, response: requests.Response, wanted: tuple[str, ...]) -> dict | None:
        """Pull the action return value out of a flight response."""

        records = parse_flight(response.text)
        candidates = find_dicts(records, wanted)
        if not candidates:
            return None
        return candidates[-1]

    # ------------------------------------------------------------------- sign-in
    def _sign_in_form(self, fields: dict[str, str], state: dict[str, Any]) -> requests.Response:
        boundary = '----WebKitFormBoundary' + uuid.uuid4().hex[:24]
        body = _multipart(
            {
                '_1_$ACTION_REF_2': '',
                '_1_$ACTION_2:0': json.dumps({'id': A.SIGN_IN, 'bound': '$@1'}),
                '_1_$ACTION_2:1': json.dumps(state),
                '_1_$ACTION_KEY': uuid.uuid4().hex,
                **{('_1_%s' % key): value for key, value in fields.items()},
                '0': json.dumps([state, '$K1']),
            },
            boundary,
        )
        headers = {
            'Next-Action': A.SIGN_IN,
            'Accept': 'text/x-component',
            'Content-Type': 'multipart/form-data; boundary=%s' % boundary,
            'Next-Router-State-Tree': A.ROUTER_TREE_SIGN_IN,
            'Origin': A.BASE,
            'Referer': self.url(A.SIGN_IN_PATH),
        }
        return self.session.post(self.url(A.SIGN_IN_PATH), data=body, headers=headers, timeout=45)

    def sign_in_page(self, next_path: str) -> requests.Response:
        query = '?next=%s' % requests.utils.quote(next_path, safe='')
        return self.get(A.SIGN_IN_PATH + query)

    def send_code(self, email: str, next_path: str) -> dict:
        """Ask OpenGame to mail an 8 digit sign-in code."""

        self.sign_in_page(next_path)
        response = self._sign_in_form(
            {
                'next': next_path,
                'email': email,
                'cf-turnstile-response': '',
                'og-turnstile-state': '',
                'intent': 'send',
            },
            dict(A.INITIAL_SIGN_IN_STATE),
        )
        return self._sign_in_state(response)

    def verify_code(self, email: str, code: str, next_path: str) -> dict:
        """Exchange the 8 digit code for a session cookie."""

        state = {'step': 'code', 'email': email, 'attempts': 0}
        response = self._sign_in_form(
            {
                'next': next_path,
                'code': code,
                'cf-turnstile-response': '',
                'og-turnstile-state': '',
                'intent': 'verify',
            },
            state,
        )
        return self._sign_in_state(response)

    def _sign_in_state(self, response: requests.Response) -> dict:
        # a successful verify answers with a react fragment (a redirect) and drops
        # the session cookie, there is no state object in that response
        if self.signed_in():
            return {'step': 'signed-in', 'ok': True}
        records = parse_flight(response.text)
        states = [
            item
            for item in find_dicts(records, ('step',))
            if isinstance(item.get('step'), str)
        ]
        if states:
            return states[-1]
        if response.status_code >= 400:
            raise ProtocolError(
                'sign-in failed: HTTP %s %s' % (response.status_code, response.text[:200])
            )
        raise ProtocolError('unexpected sign-in response: %s' % response.text[:400])

    # -------------------------------------------------------------------- handle
    def handle_available(self, handle: str) -> dict:
        response = self.get(A.HANDLE_AVAILABILITY_PATH + '?handle=' + requests.utils.quote(handle))
        try:
            return response.json()
        except ValueError:
            return {'status': 'unknown', 'raw': response.text[:200]}

    def claim_handle(self, handle: str, errand: str | None = None) -> dict:
        response = self.server_action(
            A.HANDLE_PATH,
            A.CLAIM_FROM_HANDLE_PAGE,
            [handle, errand],
            router_tree=A.ROUTER_TREE_HANDLE,
        )
        result = self.action_result(response, ('status', 'handle', 'to', 'error'))
        if result is None:
            raise ProtocolError('claim handle: no action result (%s)' % response.text[:300])
        return result

    def save_interest(self, answers: dict) -> requests.Response:
        return self.server_action(
            A.HANDLE_PATH,
            A.SAVE_JAM_INTEREST,
            [answers],
            router_tree=A.ROUTER_TREE_HANDLE,
        )

    # ------------------------------------------------------------------- welcome
    def save_avatar_look(self, look: str) -> requests.Response:
        return self.server_action(
            A.WELCOME_PATH + '?step=avatar',
            A.SAVE_AVATAR_LOOK,
            [look],
            router_tree=A.ROUTER_TREE_WELCOME,
        )

    def save_character_look(self, look: str) -> requests.Response:
        return self.server_action(
            A.WELCOME_PATH + '?step=character',
            A.SAVE_CHARACTER_LOOK,
            [look],
            router_tree=A.ROUTER_TREE_WELCOME,
        )

    def save_profile_details(
        self,
        display_name: str,
        bio: str = '',
        site_url: str = '',
        github_handle: str = '',
        baseline: dict | None = None,
    ) -> requests.Response:
        payload = {
            'displayName': display_name,
            'bio': bio,
            'siteUrl': site_url,
            'githubHandle': github_handle,
        }
        if baseline is None:
            baseline = self.welcome_account()
        return self.server_action(
            A.WELCOME_PATH + '?step=profile',
            A.SAVE_PROFILE_DETAILS,
            [payload, baseline],
            router_tree=A.ROUTER_TREE_WELCOME,
        )

    def save_profile(
        self,
        display_name: str,
        bio: str = '',
        site_url: str = '',
        github_handle: str = '',
        attempts: int = 3,
    ) -> dict:
        '''Save the profile details, retrying when the draft moved under us.

        The server compares the submitted profile with the draft it handed out
        and refuses with 'Your profile changed since this page loaded' when they
        differ.  Reading the draft again and sending it as the baseline resolves
        that race.
        '''
        last: dict = {}
        for _ in range(attempts):
            baseline = self.welcome_account()
            response = self.server_action(
                A.WELCOME_PATH + '?step=profile',
                A.SAVE_PROFILE_DETAILS,
                [
                    {
                        'displayName': display_name,
                        'bio': bio,
                        'siteUrl': site_url,
                        'githubHandle': github_handle,
                    },
                    baseline,
                ],
                router_tree=A.ROUTER_TREE_WELCOME,
            )
            result = self.action_result(response, ('ok', 'error', 'field')) or {}
            last = result
            if result.get('ok'):
                return result
            time.sleep(1.0)
        return last

    def finish_welcome(self) -> requests.Response:
        return self.server_action(
            A.WELCOME_PATH + '?step=profile',
            A.WELCOME_FINISHED,
            [],
            router_tree=A.ROUTER_TREE_WELCOME,
        )

    # ------------------------------------------------------------------- account
    def viewer(self) -> dict:
        response = self.get(A.SOCIAL_BOOTSTRAP_PATH)
        try:
            return response.json()
        except ValueError:
            return {}

    def display_name(self) -> str:
        return self.viewer().get('data', {}).get('viewer', {}).get('displayName') or ''

    def handle(self) -> str:
        return self.viewer().get('data', {}).get('viewer', {}).get('handle') or ''

    def welcome_account(self) -> dict:
        '''Read the onboarding account state from the welcome page payload.

        The server hands the client a draft (displayName, bio, siteUrl,
        githubHandle) and the saved jam interest.  The draft is the baseline the
        saveProfileDetails action compares against, so it has to be read before
        the profile is written.
        '''
        return self._rsc_object('draft')

    def interest_answers(self) -> dict:
        return self._rsc_object('interest')

    def _rsc_object(self, key: str) -> dict:
        '''Read one flat object out of the RSC payload embedded in a page.

        The payload is escaped inside the inline script, so the captured text is
        unescaped before it is parsed.
        '''
        response = self.get(A.WELCOME_PATH + '?step=profile')
        match = re.search(r'\\?"%s\\?":(\{[^{}]*\})' % re.escape(key), response.text)
        if not match:
            return {}
        blob = match.group(1).replace('\\"', '"').replace('\\/', '/')
        try:
            return json.loads(blob)
        except ValueError:
            return {}

    # -------------------------------------------------------------- sponsor code
    def sponsor_code(self, sponsor: str, action: str, claimed_here: bool = False) -> dict | None:
        body: dict[str, Any] = {'sponsor': sponsor, 'action': action}
        if claimed_here:
            body['claimedHere'] = True
        headers = {
            'Content-Type': 'application/json',
            'Origin': A.BASE,
            'Referer': '%s%s?perk=%s#sponsors' % (A.BASE, A.JAM_PATH, sponsor),
        }
        response = self.session.post(
            self.url(A.SPONSOR_CODE_PATH),
            data=json.dumps(body),
            headers=headers,
            timeout=45,
        )
        if response.status_code == 204:
            return None
        try:
            return response.json()
        except ValueError:
            raise ProtocolError(
                'sponsor-code %s -> HTTP %s %s' % (action, response.status_code, response.text[:200])
            )

    def sponsor_code_value(self, sponsor: str, action: str = 'open') -> str | None:
        '''Convenience wrapper: run one sponsor-code call and extract the code.'''

        return extract_sponsor_code(self.sponsor_code(sponsor, action))


__all__ = [
    'OpenGameClient',
    'ProtocolError',
    'parse_flight',
    'find_dicts',
    'extract_sponsor_code',
    'sponsor_code_value',
]
