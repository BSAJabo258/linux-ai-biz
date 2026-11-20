# Integrations: how each platform connects, why it fails, what worked

`bau connect status` · `bau connect doctor <platform>` · `bau connect report <platform>`
(code: `src/bau/integrations.py`, tests: `tests/test_integrations.py`)

Every fact below was read on **2026-11-18** from the official page named next to it. A fact
the page did not state is marked **NOT STATED**; nothing here is filled in from memory.

## 1. What BAU really has (repository inventory, 2026-11-18)

| Integration | Status | Code | Auth type | Callback / port | Token store | Tests |
|---|---|---|---|---|---|---|
| Fanvue | **working**: connected 2026-11-18; doctor all green live | `fanvue.py` `FanvueClient`, `login` | OAuth 2.0 code + PKCE S256, `client_secret_basic` | `http://127.0.0.1:3456/callback`, listener only during sign-in | `BAU_HOME/secrets/fanvue.json` (`credentials.py`) | `test_fanvue.py`, `test_credentials.py`, `test_integrations.py` |
| TikTok | code complete, **not connected** (no app keys on the desktop) | `tiktok.py` `TikTokClient`, `login` | OAuth 2.0 code + PKCE S256 (hex, desktop) | `http://127.0.0.1:3455/callback/` | `BAU_HOME/secrets/tiktok.json` | `test_tiktok.py`, `test_integrations.py` |
| Ayrshare (Instagram + TikTok posting) | code complete, key-gated | `week.py` | API key, `Authorization: Bearer` | none | `/etc/bau/platforms.env` `AYRSHARE_API_KEY` | `test_week.py` |
| Anthropic (model) | working when a key is set | `models/providers.py` | API key (`ANTHROPIC_API_KEY`); **not** a Claude subscription login | none | `/etc/bau/models.env` | model tests |
| Local llama.cpp | working | `models/providers.py` | none (127.0.0.1:8080) | none | none | model tests |
| SearXNG | local search | `web.py` | none (127.0.0.1:8888) | none | none | `test_web.py` |
| bau-voice | working | `assistant.py` | none (127.0.0.1:8767) | none | none | voice tests |
| Inkbox email (`bau-agent@inkboxmail.com`) | via the owner's Claude connector, **not** in BAU's code | none | connector OAuth | none | Claude | none |
| REA (Reverse Engineer Anything) | catalogued only (`data/toolbox.yaml`), not installed | none | none | none | none | none |
| YouTube, Gmail, Facebook, Instagram (direct), Threads, X, Microsoft mail, n8n, Coinbase CDP | **absent**: no code | none | none | none | none | none |

Only the first two use a callback and a port, so the doctor covers exactly those. The absent
platforms are documented in §3 so that their adapters, when the owner asks for one, start from
checked facts. Building them was not asked for in any merged requirement, so nothing was built.

## 2. The Fanvue failure (2026-11-10 → 2026-11-18), found

| Compared | Value |
|---|---|
| Address BAU sends (terminal and Jarvis card, same `fanvue.login`) | `http://127.0.0.1:3456/callback` |
| Address registered on the Fanvue app | **missing until 2026-11-18**: the root cause |
| Port Jarvis listens on | 3456 on 127.0.0.1, only while a sign-in waits (`tiktok.oauth_callback`) |
| Port forwarded by the host | none on the desktop. The laptop station's SSH tunnel carries **only** Jarvis (8766), so a sign-in started from the laptop's browser comes back to the laptop's 127.0.0.1:3456, where nothing listens |
| Token-exchange redirect | the same string as the authorize request (`fanvue.login`, one variable) |
| Token store | before PR #203 owner-only (0600), unreadable by the `bau` autopilot; now shared through the `bau` group |
| What Fanvue does with an unregistered address | its own error page, `invalid_request ... 'redirect_uri' does not match`; it never calls back, so BAU only timed out |

What changed, so it cannot cost days again:
- **Before the browser opens**, `bau fanvue login` and Jarvis's Connect Fanvue card run the
  pre-flight. It asks Fanvue's authorize page (no browser, no sign-in, only the public client
  id) whether it accepts the app and the address. Live answers read 2026-11-18:
  registered → `302 https://www.fanvue.com/oauth/login?login_challenge=…`;
  unregistered → `302 https://www.fanvue.com/oauth/error?error=invalid_request…redirect_uri…`;
  unknown client id → the same page with `error=invalid_client`.
  If it fails, BAU stops and says the exact address and where to register it.
- After Jarvis opens Fanvue, the page checks that **this browser** can reach the listener. On
  the laptop it says "Sign in at the desktop's own browser" instead of a five-minute timeout.
- Every stage is recorded (§5). A consent screen is never called a working connection: the
  card and the terminal both call `GET /v1/users/me` before saying verified.

## 3. Endpoint and callback matrix (official pages, read 2026-11-18)

| Platform | Authorize | Token | Revoke | PKCE | Redirect rules | Scopes BAU needs |
|---|---|---|---|---|---|---|
| Fanvue | `https://auth.fanvue.com/oauth2/auth` | `https://auth.fanvue.com/oauth2/token` (form, HTTP Basic; `client_secret_post` refused) | no API; the user revokes in Settings → Account → Third Party Apps Consent | required, S256, base64url | exact match to the app's Authentication tab; loopback rules NOT STATED (127.0.0.1 works live) | `openid offline_access offline read:self read:media write:media write:creator write:post read:insights` (space) |
| TikTok desktop | `https://www.tiktok.com/v2/auth/authorize/` | `https://open.tiktokapis.com/v2/oauth/token/` (form) | `https://open.tiktokapis.com/v2/oauth/revoke/` | required, S256, **hex** | localhost/127.0.0.1, port required (wildcard allowed), static path, max 10 | `user.info.basic,video.publish,video.upload,video.list` (comma) |
| TikTok web | same | same | same | NOT STATED | https only | — |
| Google (YouTube, Gmail) | `https://accounts.google.com/o/oauth2/v2/auth` | `https://oauth2.googleapis.com/token` | `https://oauth2.googleapis.com/revoke` | desktop: "always use PKCE", S256 | desktop loopback `http://127.0.0.1:<port>`; exact match incl. trailing slash | `…/auth/youtube.upload`; `…/auth/gmail.readonly` (restricted), `…/auth/gmail.send` (sensitive) |
| Microsoft | `https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize` | `…/{tenant}/oauth2/v2.0/token` | NOT STATED | recommended, S256 | `http://localhost` for system browsers; port rules NOT STATED | `offline_access`, `https://graph.microsoft.com/mail.read`; Mail.Send NOT STATED on that page |
| X | `https://x.com/i/oauth2/authorize` | `https://api.x.com/2/oauth2/token` (form) | NOT STATED | S256 or plain | NOT STATED | `tweet.read tweet.write users.read media.write offline.access` |
| Facebook Login | `https://www.facebook.com/v27.0/dialog/oauth` | `https://graph.facebook.com/v27.0/oauth/access_token` (GET) | NOT STATED | NOT STATED | Valid OAuth Redirect URIs | user vs Page vs app tokens are different things |
| Instagram Login | `https://www.instagram.com/oauth/authorize` | `https://api.instagram.com/oauth/access_token`; long-lived `https://graph.instagram.com/access_token`; refresh `…/refresh_access_token` | NOT STATED | NOT STATED | NOT STATED | `instagram_business_basic`, `instagram_business_content_publish`, `…_manage_comments`, `…_manage_messages` (old names retired 2025-01-27) |
| Threads | `https://threads.com/oauth/authorize` | `https://graph.threads.com/oauth/access_token` | NOT STATED | NOT STATED | NOT STATED | `threads_basic`, `threads_content_publish`, … |
| n8n REST | — (API key) | — | delete the key in Settings → n8n API | — | — | header `X-N8N-API-KEY`, path `/api/v1`; key scopes from 2.14.0 |
| Coinbase CDP | — (API key + Wallet Secret) | — | revoke the key in the CDP Portal | — | — | `CDP_API_KEY_ID`, `CDP_API_KEY_SECRET`, `CDP_WALLET_SECRET`; Python `cdp-sdk`; testnet `base-sepolia` |

Lifetimes: Fanvue access "short-lived, read `expires_in`", refresh **rotates and is
single-use** (reuse after the grace window kills the whole chain). TikTok access 2 h, refresh
180 days, rotates. X access 2 h, code valid 30 s. Instagram long-lived 60 days, refresh after
24 h. Google sends a refresh token only on the first consent.

Sources: Fanvue
[implementation guide](https://api.fanvue.com/docs/authentication/implementation-guide)
("Build the authorisation URL", "Token exchange", "Token refresh", "How to authenticate the
token request", "Error handling"), [scopes](https://api.fanvue.com/docs/authentication/scopes)
("Scope table", "System scopes", "Insufficient scope errors"),
[overview](https://api.fanvue.com/docs/authentication/overview) ("Refresh tokens rotate and are
single-use"), [API policy](https://legal.fanvue.com/api-policy) (1.1, 1.3, 6, 7.2); the npm
page of `@fanvue/builder-sdk` refused the fetch (403), so its variable names are UNVERIFIED and
BAU keeps its own (`FANVUE_CLIENT_ID`, `FANVUE_CLIENT_SECRET`). TikTok
[login-kit-desktop](https://developers.tiktok.com/doc/login-kit-desktop),
[login-kit-web](https://developers.tiktok.com/doc/login-kit-web),
[get a token](https://developers.tiktok.com/doc/oauth-get-a-user-access-token),
[token management](https://developers.tiktok.com/doc/oauth-user-access-token-management),
[revoke](https://developers.tiktok.com/doc/oauth-revoke-a-user-access-token). Google
[web server](https://developers.google.com/identity/protocols/oauth2/web-server),
[native app](https://developers.google.com/identity/protocols/oauth2/native-app),
[YouTube auth](https://developers.google.com/youtube/v3/guides/authentication),
[Gmail scopes](https://developers.google.com/workspace/gmail/api/auth/scopes). Microsoft
[auth code flow](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-auth-code-flow).
X [authorization code](https://docs.x.com/fundamentals/authentication/oauth-2-0/authorization-code).
Meta [manual flow](https://developers.facebook.com/docs/facebook-login/guides/advanced/manual-flow),
[Instagram business login](https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login/business-login),
[Threads tokens](https://developers.facebook.com/docs/threads/get-started/get-access-tokens-and-permissions).
n8n [authentication](https://docs.n8n.io/api/authentication/). Coinbase
[Wallet API quickstart](https://docs.cdp.coinbase.com/wallet-api/v2/introduction/quickstart).
General rules: RFC 6749, RFC 7636 (PKCE), RFC 9700 (OAuth security BCP), RFC 8414.

## 4. Connection states

`NOT_CONFIGURED` (app keys missing) → `READY_TO_AUTHORIZE` → attempt →
`AUTHENTICATED` (token saved; consent alone stops here) → `API_VERIFIED` (a real API call
answered after this sign-in). Also `REFRESH_REQUIRED` (access expired, renewed on next use),
`EXPIRED`, `REVOKED` (API 401 or a refused refresh), `PERMISSION_DENIED` (access_denied, API
403, or scopes missing from the grant), `CONFIGURATION_ERROR` (sign-in unreadable for this
account), `NETWORK_ERROR`, `PROVIDER_ERROR`, `NEEDS_OWNER_ACTION`.

## 5. The flight recorder

`BAU_HOME/integrations/attempts.jsonl`: one line per stage of every attempt —
`preflight`, `authorize_url`, `listener`, `callback` (state valid? code received? the
platform's error), `token_exchange` (separate from the callback), `stored`, `api_check`
(HTTP status, account). Each failed stage has `next`. `bau connect report <platform>` prints
the last attempt to paste anywhere. Codes, tokens, client secrets, cookies, passwords, wallet
secrets and private keys are removed (`integrations.redact`) before anything is written or
printed. After a verified connection, `BAU_HOME/integrations/<platform>.known_good.json` keeps
the address, port, granted scopes and the steps that worked; the next pre-flight warns if the
address changed.

## 6. Port and redirect troubleshooting

| What you see | Stage | Cause | Fix |
|---|---|---|---|
| Fanvue's page: `invalid_request … redirect_uri` | pre-flight / callback never comes | address not registered | add exactly `http://127.0.0.1:3456/callback` on the Fanvue app's Authentication tab, **Save** |
| `invalid_client` | pre-flight | wrong client id | `sudo bau keys set FANVUE_CLIENT_ID FANVUE_CLIENT_SECRET` |
| "already in use" | pre-flight | an older sign-in still waiting, or another program | `ss -ltnp 'sport = :3456'`, wait 5 minutes or stop it |
| Jarvis says "This browser cannot reach the sign-in listener" | page | Jarvis opened on the laptop (tunnel carries only 8766) | sign in at the desktop |
| "state mismatch" | callback | an old tab, or a forged answer | start again from BAU |
| `invalid_grant` | token exchange | code reused/expired, or PKCE mismatch | sign in again |
| API 401 after it worked | api_check | revoked in Fanvue, or the refresh chain broke | `bau fanvue login` |
| API 403 `Insufficient scopes` | api_check | the app lacks a scope | add it on the app, sign in again |

Never change a redirect address on a platform's portal without the owner.

## 7. REA investigation procedure (any integration)

REA itself (`morluto/rea`) is only catalogued; this is the procedure BAU follows with or
without it.
1. Name the target and the exact symptom (`bau connect report <platform>`).
2. Read the platform's official docs and its official SDK; record URL, section and date.
3. Read BAU's adapter (`fanvue.py`, `tiktok.py`) and the inventory in §1.
4. Compare expected and recorded behaviour stage by stage (attempts.jsonl).
5. Reproduce safely: `bau connect doctor <platform>`; a stand-in platform in a test.
6. Fix the smallest root cause; add a test that fails without the fix.
7. Save what worked (`known_good`) and add the finding to §2/§6 here.
Only public docs, open-source code and systems the owner may inspect; never a platform's
hidden API, never around a login, rate limit or licence.

## 8. What only the owner can do

- `bau fanvue status --check` on the desktop: the first real API proof since the sign-in
  (records `API_VERIFIED`).
- TikTok: create the app, add Login Kit (Desktop) with `http://127.0.0.1:3455/callback/`,
  then `sudo bau keys set TIKTOK_CLIENT_KEY TIKTOK_CLIENT_SECRET` and `bau tiktok login`.
- Say which absent platform to build next (YouTube, Gmail, Meta, Threads, X, Microsoft, n8n,
  Coinbase CDP). Each needs its own developer app made by the owner; wallet keys never go into
  a model's prompt, and payments keep the owner's approval.
