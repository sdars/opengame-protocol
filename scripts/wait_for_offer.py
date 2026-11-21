#!/usr/bin/env python3
'''Watch the jam sponsor offer until the pool refills, then take the coupon.

The sponsor offer is a server side pool (``/api/jam/sponsor-code``).  When it is
empty the API answers ``{"kind": "exhausted"}``; when a batch is refilled it
answers ``{"kind": "coupon", "id": "FAL-OPENGAME-XXXXXX"}``.  This script
polls that endpoint over plain HTTP until the pool has something, claims it and
writes the code to disk.

The session is re-created from the stored account record: the sign-in flow is
mail-code based, so a dead session is repaired by pulling a fresh code from the
mailbox.  No browser, no adb, no Frida, no RPC bridge.

Examples
--------
    /root/Knight/.venv/bin/python scripts/wait_for_offer.py \
        --resume tmp/逆向分析/2026-11-21/runs/account_958889.json \
        --poll 180 --hours 12
'''

from __future__ import annotations

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

from opengame_protocol import actions as A
from opengame_protocol import proxy as proxy_pool
from opengame_protocol.client import OpenGameClient, extract_sponsor_code
from opengame_protocol.mailbox import ImapMailbox

NEXT_PATH = '/jam?perk=%s#sponsors'


def log(message: str) -> None:
    print('[%s] %s' % (time.strftime('%H:%M:%S'), message), flush=True)


def restore_session(client: OpenGameClient, record: dict, mailbox: ImapMailbox, args) -> bool:
    '''Put a valid session cookie on the client, signing in again if needed.'''

    token = record.get('session_token')
    if token:
        client.session.cookies.set('sb-auth-auth-token', token, domain='opengame.io', path='/')
    email = record.get('email', '')
    if client.signed_in() and email:
        return True
    if not email:
        return bool(client.signed_in())
    after_uid = mailbox.latest_uid()
    state = client.send_code(email, NEXT_PATH % args.sponsor)
    log('re-auth send -> %s' % json.dumps(state)[:160])
    if state.get('step') != 'code':
        return False
    code = mailbox.wait_for_sign_in_code(email, timeout=args.imap_timeout, after_uid=after_uid)
    if not code:
        return False
    state = client.verify_code(email, code, NEXT_PATH % args.sponsor)
    log('re-auth verify -> %s' % json.dumps(state)[:160])
    return bool(client.signed_in())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--resume', required=True, help='account record produced by claim_coupon.py')
    parser.add_argument('--sponsor', default=A.SPONSOR_FAL_25)
    parser.add_argument('--poll', type=int, default=180, help='seconds between polls')
    parser.add_argument('--hours', type=float, default=12.0, help='how long to keep polling')
    parser.add_argument('--proxy-off', action='store_true')
    parser.add_argument('--proxy-offset', type=int, default=0)
    parser.add_argument('--proxy-env', default=proxy_pool.DEFAULT_ENV_PATH)
    parser.add_argument('--imap-host', default='imap.aoog.de')
    parser.add_argument('--imap-user', default='chatgpt@958889.xyz')
    parser.add_argument('--imap-password', default='845679Ars')
    parser.add_argument('--imap-timeout', type=int, default=180)
    parser.add_argument('--out', default='', help='where to write the captured coupon')
    args = parser.parse_args()

    record = json.load(open(args.resume, encoding='utf-8'))
    mailbox = ImapMailbox(args.imap_host, args.imap_user, args.imap_password)

    proxy = None
    if not args.proxy_off:
        env = proxy_pool.load_env(args.proxy_env)
        proxy = proxy_pool.proxy_url(env, args.proxy_offset)

    limit = time.time() + args.hours * 3600
    round_no = 0
    while time.time() < limit:
        round_no += 1
        client = OpenGameClient(proxy=proxy)
        if not restore_session(client, record, mailbox, args):
            log('no session, retrying in %ss' % args.poll)
            time.sleep(args.poll)
            continue
        opened = client.sponsor_code(args.sponsor, 'open')
        kind = (opened or {}).get('kind') if isinstance(opened, dict) else None
        log('#%d open -> %s' % (round_no, json.dumps(opened, ensure_ascii=False)[:200]))
        if kind in ('coupon', 'code'):
            code = extract_sponsor_code(opened)
            claimed = client.sponsor_code(args.sponsor, 'claim')
            read_back = client.sponsor_code(args.sponsor, 'open')
            log('claim -> %s' % json.dumps(claimed, ensure_ascii=False)[:200])
            log('read back -> %s' % json.dumps(read_back, ensure_ascii=False)[:200])
            result = dict(record)
            result.update(
                {
                    'captured_at': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
                    'sponsor_response': opened,
                    'sponsor_claim': claimed,
                    'sponsor_read_back': read_back,
                    'coupon_code': code,
                    'session_token': client.auth_token() or record.get('session_token'),
                }
            )
            out = args.out or os.path.splitext(args.resume)[0] + '_coupon.json'
            with open(out, 'w', encoding='utf-8') as handle:
                json.dump(result, handle, indent=2, ensure_ascii=False)
            print(json.dumps(result, indent=2, ensure_ascii=False))
            log('coupon captured: %s -> %s' % (code, out))
            return 0
        time.sleep(args.poll)
    log('offer still empty after %.1fh' % args.hours)
    return 6


if __name__ == '__main__':
    raise SystemExit(main())
