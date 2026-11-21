"""Action ids, routes and payload shapes used by opengame.io.

Everything in this module was recovered from the live site:

* the RSC client chunks under /_next/static/immutable/chunks (createServerReference calls),
* the Next.js server action wire format captured in the browser (plain-text body for
  server references, multipart body for useActionState forms),
* the jam page bundle that drives POST /api/jam/sponsor-code.

No part of the chain depends on a browser, adb, Frida or an RPC bridge: every value
below is a plain HTTP request.
"""

from __future__ import annotations

BASE = "https://opengame.io"

# --- server action ids (Next-Action header value) ---------------------------------
SIGN_IN = "6092819032bb6918017b269ae557946028cdf22d53"
SIGN_IN_WITH_GOOGLE = "406c22d75bdc1dab1289532ce6b3971a675bca6635"
CLAIM_FROM_HANDLE_PAGE = "605ff96286ee0aded22fc192db4556cb8a1d5f9f2e"
RENAME_TO = "40194b4d7a8766c0c17d7c2cf6f25706fe222f3a55"
SAVE_JAM_INTEREST = "40c70d59bc67f324382a96cbc041ee1fc67b66521c"
SAVE_AVATAR_LOOK = "406c9f63e7bfc52580f9f57101799502bfce4fe048"
SAVE_CHARACTER_LOOK = "40df74d27444b943f91034902148e7ea913a682eb0"
SAVE_PROFILE_DETAILS = "601461909aac6b848b74520bb64ef28525a163efa7"
SAVE_WELCOME_INTEREST = "40d1f4411208330539719ab77dfc0f78f1b4879923"
WELCOME_FINISHED = "008a08d1454909055c4ee71760d1b98666afc2de34"
CONNECT_X = "406d161fea338d0390188feee5b347e49f356d789a"

# --- routes ----------------------------------------------------------------------
SIGN_IN_PATH = "/auth/sign-in"
HANDLE_PATH = "/handle"
WELCOME_PATH = "/welcome"
JAM_PATH = "/jam"
SPONSOR_CODE_PATH = "/api/jam/sponsor-code"
HANDLE_AVAILABILITY_PATH = "/api/handles/availability"
SOCIAL_BOOTSTRAP_PATH = "/api/social?resource=bootstrap&input=%7B%7D"

# --- sponsor codes ---------------------------------------------------------------
SPONSOR_FAL_25 = "fal-2"   # Batch 2, $25 in fal credits
SPONSOR_FAL_50 = "fal"     # Batch 1, $50 in fal credits
SPONSOR_ELEVENLABS = "elevenlabs"

# --- router state trees (Next-Router-State-Tree header) ---------------------------
ROUTER_TREE_SIGN_IN = (
    '%5B%22%22%2C%7B%22children%22%3A%5B%22auth%22%2C%7B%22children%22%3A%5B%22sign-in%22%2C'
    '%7B%22children%22%3A%5B%22__PAGE__%22%2C%7B%7D%2Cnull%2Cnull%2C4096%5D%7D%2Cnull%2Cnull%2C'
    '4096%5D%7D%2Cnull%2Cnull%2C4096%5D%2Cnull%2Cnul'
)
ROUTER_TREE_HANDLE = (
    '%5B%22%22%2C%7B%22children%22%3A%5B%22(onboarding)%22%2C%7B%22children%22%3A%5B%22handle%22%2C'
    '%7B%22children%22%3A%5B%22__PAGE__%22%2C%7B%7D%2Cnull%2Cnull%2C4096%5D%7D%2Cnull%2Cnull%2C'
    '4096%5D%7D%2Cnull%2Cnull%2C4096%5D%2Cnull%2Cnull%2C4112%5D'
)
ROUTER_TREE_WELCOME = (
    '%5B%22%22%2C%7B%22children%22%3A%5B%22(onboarding)%22%2C%7B%22children%22%3A%5B%22welcome%22%2C'
    '%7B%22children%22%3A%5B%22__PAGE__%22%2C%7B%7D%2Cnull%2Cnull%2C4096%5D%7D%2Cnull%2Cnull%2C'
    '4096%5D%7D%2Cnull%2Cnull%2C4096%5D%2Cnull%2Cnull%2C4112%5D'
)

# --- turnstile ------------------------------------------------------------------
TURNSTILE_SITE_KEY = "0x4AAAAAAEXt62cdsNuTd72E"
TURNSTILE_ACTION = "sign-in-code"

# --- sign-in state machine ------------------------------------------------------
OTP_LENGTH = 8
OTP_TTL_SECONDS = 600
RESEND_COOLDOWN_SECONDS = 300
MAX_CODE_ATTEMPTS = 5

INITIAL_SIGN_IN_STATE = {"step": "email", "email": "", "attempts": 0}

__all__ = [name for name in dir() if not name.startswith("_")]
