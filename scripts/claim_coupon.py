#!/usr/bin/env python3
'''End to end, pure protocol run: register, onboard and take a jam sponsor coupon.

Every step is plain HTTP:

    sign-in page -> e-mail code (IMAP) -> session cookie -> handle -> jam interest
    -> avatar look -> character look -> profile -> sponsor code -> read back

There is no browser, no adb, no Frida and no RPC bridge anywhere in the chain.

Examples
--------
    /root/Knight/.venv/bin/python scripts/claim_coupon.py --domain fublcy.asia
    /root/Knight/.venv/bin/python scripts/claim_coupon.py --wait --poll 120
    /root/Knight/.venv/bin/python scripts/claim_coupon.py --resume runs/account.json
'''

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

from opengame_protocol import actions as A
from opengame_protocol import proxy as proxy_pool
from opengame_protocol.client import OpenGameClient, extract_sponsor_code
from opengame_protocol.identity import build_identity, random_handle
from opengame_protocol.mailbox import ImapMailbox

NEXT_PATH = '/jam?perk=%s#sponsors'

AVATAR_LOOKS = ['circle.classic.white', 'circle.classic.black', 'square.classic.white']
CHARACTER_LOOKS = [
    'c3.classic.regular.hoodie.jeans.backpack.jumpcourt.avatar.avatar.chalk.avatar',
    'c3.classic.regular.hoodie.jeans.backpack.jumpcourt.avatar.avatar.sand.avatar',
]
INTERESTS = [
    {'experience': 'intermediate', 'genres': ['puzzle-casual', 'platformer']},
    {'experience': 'experienced', 'genres': ['action-adventure', 'rpg']},
    {'experience': 'intermediate', 'genres': ['strategy', 'simulation-management']},
]


def log(message: str) -> None:
    print('[%s] %s' % (time.strftime('%H:%M:%S'), message), flush=True)


def sign_in(client: OpenGameClient, mailbox: ImapMailbox, args: argparse.Namespace, email: str) -> bool:
    '''Ask for the e-mail code and exchange it for a session cookie.'''
    after_uid = mailbox.latest_uid()
    state = client.send_code(email, NEXT_PATH % args.sponsor)
    log('send code -> %s' % json.dumps(state)[:200])
    if state.get('step') != 'code':
        log('no code sent: %s' % json.dumps(state)[:300])
        return False
    code = mailbox.wait_for_sign_in_code(email, timeout=args.imap_timeout, after_uid=after_uid)
    if not code:
        log('no code arrived within %ss' % args.imap_timeout)
        return False
    log('code from mailbox: %s' % code)
    state = client.verify_code(email, code, NEXT_PATH % args.sponsor)
    log('verify -> %s' % json.dumps(state)[:200])
    return bool(client.signed_in())


def onboard(client: OpenGameClient, identity: dict, rng: random.Random) -> bool:
    '''Claim the handle, save the jam interest and fill in the profile.'''
    answers = rng.choice(INTERESTS)
    interest = client.save_interest(
        {
            'participating': True,
            'experience': answers['experience'],
            'genres': answers['genres'],
            'engines': [],
            'agents': [],
            'tools': [],
            'listed': True,
        }
    )
    log('jam interest -> %s' % json.dumps(client.action_result(interest, ('ok', 'error')) or {})[:160])

    handle = identity['handle']
    for _ in range(6):
        if client.handle_available(handle).get('status') == 'available':
            break
        handle = random_handle(rng)
    identity['handle'] = handle
    claim = client.claim_handle(handle, None)
    log('claim handle %s -> %s' % (handle, json.dumps(claim)[:200]))
    if claim.get('status') not in ('taken', 'redirect'):
        return False

    client.save_avatar_look(rng.choice(AVATAR_LOOKS))
    client.save_character_look(rng.choice(CHARACTER_LOOKS))
    time.sleep(1.0)
    draft = client.welcome_account()
    log('current draft: %s' % json.dumps(draft)[:160])
    result = client.save_profile(
        display_name=identity['display_name'],
        bio=identity['bio'],
        site_url='',
        github_handle='',
    )
    log('save profile -> %s' % json.dumps(result)[:200])
    client.finish_welcome()
    log('profile: @%s / %s' % (client.handle(), client.display_name()))
    return True


def take_coupon(client: OpenGameClient, sponsor: str, wait: bool, poll: int, deadline_hours: float):
    '''Ask the jam API for the sponsor code and read it back.'''
    opened = client.sponsor_code(sponsor, 'open')
    log('sponsor open -> %s' % json.dumps(opened)[:300])
    code = extract_sponsor_code(opened)
    if code:
        claimed = client.sponsor_code(sponsor, 'claim')
        log('sponsor claim -> %s' % json.dumps(claimed)[:300])
        if isinstance(claimed, dict) and claimed.get('code'):
            code = claimed['code']
        read_back = client.sponsor_code(sponsor, 'open')
        log('sponsor read back -> %s' % json.dumps(read_back)[:300])
        return code, opened, read_back
    kind = (opened or {}).get('kind') if isinstance(opened, dict) else None
    if kind in ('sign-in', 'handle'):
        # the server asks the visitor to sign in / pick a handle first
        log('offer needs %s first: %s' % (kind, (opened or {}).get('href')))
    if not wait:
        return None, opened, None
    limit = time.time() + deadline_hours * 3600
    log('offer unavailable, polling every %ss for %.1fh' % (poll, deadline_hours))
    while time.time() < limit:
        time.sleep(poll)
        opened = client.sponsor_code(sponsor, 'open')
        kind = (opened or {}).get('kind')
        log('poll -> %s' % json.dumps(opened)[:200])
        if kind in ('coupon', 'code'):
            claimed = client.sponsor_code(sponsor, 'claim')
            log('sponsor claim -> %s' % json.dumps(claimed)[:300])
            code = extract_sponsor_code(opened) or (claimed or {}).get('code')
            read_back = client.sponsor_code(sponsor, 'open')
            log('sponsor read back -> %s' % json.dumps(read_back)[:300])
            return code, opened, read_back
    return None, opened, None


def run(args: argparse.Namespace) -> int:
    rng = random.Random(args.seed) if args.seed else random.Random()
    identity = build_identity(args.domain, rng)
    if args.email:
        identity['email'] = args.email
    if args.name:
        identity['display_name'] = args.name

    proxy = None
    exit_ip = None
    if not args.proxy_off:
        env = proxy_pool.load_env(args.proxy_env)
        proxy = proxy_pool.proxy_url(env, args.proxy_offset)
        try:
            exit_ip = proxy_pool.exit_ip(proxy)
            log('exit IP: %s' % exit_ip)
        except Exception as exc:
            log('exit IP lookup failed (%s), continuing' % exc)

    client = OpenGameClient(proxy=proxy)
    mailbox = ImapMailbox(args.imap_host, args.imap_user, args.imap_password)

    if args.resume and os.path.exists(args.resume):
        resumed = json.load(open(args.resume, encoding='utf-8'))
        identity['email'] = resumed.get('email', identity['email'])
        identity['handle'] = resumed.get('handle', identity['handle'])
        identity['display_name'] = resumed.get('display_name', identity['display_name'])
        token = resumed.get('session_token')
        if token:
            client.session.cookies.set('sb-auth-auth-token', token, domain='opengame.io', path='/')
            log('resumed session for %s' % identity['email'])

    if not client.signed_in():
        log('identity: %s <%s> handle=%s' % (identity['display_name'], identity['email'], identity['handle']))
        if not sign_in(client, mailbox, args, identity['email']):
            return 4
        log('session established')
        if not onboard(client, identity, rng):
            return 5

    code, opened, read_back = take_coupon(
        client, args.sponsor, args.wait, args.poll, args.wait_hours
    )

    record = {
        'created_at': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
        'email': identity['email'],
        'password': identity['password'],
        'display_name': identity['display_name'],
        'handle': identity['handle'],
        'bio': identity['bio'],
        'sponsor': args.sponsor,
        'sponsor_response': opened,
        'sponsor_read_back': read_back,
        'coupon_code': code,
        'exit_ip': exit_ip,
        'session_token': client.auth_token(),
    }
    if args.out:
        with open(args.out, 'w', encoding='utf-8') as handle_out:
            json.dump(record, handle_out, indent=2, ensure_ascii=False)
        log('account written to %s' % args.out)
    print(json.dumps(record, indent=2, ensure_ascii=False))
    return 0 if code else 6


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--domain', default='fublcy.asia', help='mail domain used for the new account')
    parser.add_argument('--email', default='', help='use this address instead of a generated one')
    parser.add_argument('--name', default='', help='override the display name')
    parser.add_argument('--sponsor', default=A.SPONSOR_FAL_25, help='sponsor id (fal-2 = $25 fal coupon)')
    parser.add_argument('--proxy-off', action='store_true', help='talk to the site directly')
    parser.add_argument('--proxy-offset', type=int, default=0, help='pool port offset (one exit IP per port)')
    parser.add_argument('--proxy-env', default=proxy_pool.DEFAULT_ENV_PATH)
    parser.add_argument('--imap-host', default='imap.aoog.de')
    parser.add_argument('--imap-user', default='chatgpt@958889.xyz')
    parser.add_argument('--imap-password', default='845679Ars')
    parser.add_argument('--imap-timeout', type=int, default=180)
    parser.add_argument('--wait', action='store_true', help='keep polling the offer until a code is available')
    parser.add_argument('--poll', type=int, default=120, help='seconds between polls in --wait mode')
    parser.add_argument('--wait-hours', type=float, default=72.0, help='how long --wait mode keeps polling')
    parser.add_argument('--resume', default='', help='reuse the account and session from a previous run file')
    parser.add_argument('--out', default='', help='write the account record here')
    parser.add_argument('--seed', type=int, default=0)
    args = parser.parse_args()
    try:
        return run(args)
    except Exception as exc:  # noqa: BLE001 - every failure is reported the same way
        log('failed: %s: %s' % (type(exc).__name__, exc))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
