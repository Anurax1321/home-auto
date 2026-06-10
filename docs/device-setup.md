# Device control: accounts, auth, and setup

This is the checklist of everything **you** need to set up (accounts, keys, and
secrets) before home-auto can control your Tesla (Phase 2) and your thermostat
(Phase 3). Nothing here is code. As you complete each section you'll end up with
a handful of secrets; put them in `.env` (never in `config.yaml`, never commit
them). The "What home-auto will read" box at the end of each section lists the
exact env var names we'll use.

> Researched June 2026. Tesla and Amazon change these flows often. If a step
> looks different from what's described, follow the official site and tell me so
> I can update the integration.

---

## Part 1: Tesla (Phase 2, charging control)

### What you need first
- A Tesla vehicle on your Tesla account, with **MFA enabled** (required for dev access).
- A **domain you control** to host one public-key file. Options if you don't have one:
  - A static host: GitHub Pages, Cloudflare Pages (free, permanent, recommended).
  - `fleetkey.cc` (free hobbyist hosting, but it's a third party holding a security file).
- A **credit card** for the Tesla developer billing dashboard (usage is ~$3-4/month for occasional use; see Costs).

### One-time setup steps
1. **Enable MFA** on your Tesla account.
2. **Create a Tesla developer app** at https://developer.tesla.com (sign in with your Tesla account).
   - Grant types: **Authorization Code and Machine-to-Machine**.
   - Redirect URI: e.g. `https://<your-domain>/callback` (a localhost URI is fine for personal use).
   - You'll receive a **Client ID** and **Client Secret**.
3. **Generate an EC key pair** (NIST P-256 / prime256v1):
   ```bash
   openssl ecparam -genkey -name prime256v1 -noout -out tesla-private-key.pem
   openssl ec -in tesla-private-key.pem -pubout -out tesla-public-key.pem
   ```
   Keep `tesla-private-key.pem` secret (this is a credential). Hand me only its path.
4. **Host the public key** at exactly:
   ```
   https://<your-domain>/.well-known/appspecific/com.tesla.3p.public-key.pem
   ```
   This must stay reachable permanently (the Tesla app validates it on pairing).
5. **Register your domain with Tesla** (Partner Account). Done with two `curl` calls
   (get a machine-to-machine token, then POST your domain). I can script this once
   you have the Client ID/Secret and the key hosted.
6. **Authorize your app against your own account** (OAuth Authorization Code flow), once,
   to get a **refresh token**. Required scopes:
   - `openid`, `offline_access` (refresh token)
   - `vehicle_device_data` (read state)
   - `vehicle_cmds` (wake + general commands)
   - `vehicle_charging_cmds` (charging commands)
7. **Pair the virtual key** with the car: open `https://www.tesla.com/_ak/<your-domain>`
   on a phone that has the Tesla app, standing near the car, and approve the prompt.
8. **Set a billing threshold** and add a card in the developer dashboard (e.g. a $10/month
   cap is a safe guardrail).

### Important notes / gotchas
- **Signed commands are mandatory** on 2021+ vehicles. We'll use the `tesla-fleet-api`
  Python library's signed-command support (no separate Go proxy needed).
- **Refresh tokens are single-use and expire ~every 3 months.** home-auto must save the
  new refresh token on every refresh; we'll persist it like other runtime state.
- **Waking the car costs ~$0.02 and takes 15-30s.** We will NOT wake every poll. Pattern:
  read state cheaply, only wake + command when we actually want to start/stop charging.
- **Free alternative (BLE):** same library and key pair, paired via an NFC card tap; works
  only when the PC is within ~3m of the car, but it's zero-cost and needs no domain. Tell me
  if your charging PC is near the car and you'd prefer this.

### Costs (pay-per-use, as of 2025+)
- Command: ~$0.001, data read: ~$0.002, wake: ~$0.02. Realistic single-car use: ~$3-4/month.

### What home-auto will read (put in `.env`)
```
TESLA_CLIENT_ID=...
TESLA_CLIENT_SECRET=...
TESLA_REFRESH_TOKEN=...           # from the one-time OAuth authorization
TESLA_VIN=...                     # your car's VIN
TESLA_PRIVATE_KEY_PATH=/secure/path/tesla-private-key.pem
TESLA_DOMAIN=your-domain.com      # where the public key is hosted
TESLA_REGION=na                   # na or eu
```

---

## Part 2: Thermostat (Phase 3, via Alexa)

### The reality (read this first)
Your **Amazon Smart Thermostat** is built on Honeywell/Resideo technology but is an
**Alexa-only walled garden**:
- It does **not** appear in the Honeywell Home / Resideo app and **cannot** use the
  Resideo developer API. (So `pyhtcc` / SomeComfort / Honeywell API do not apply.)
- There is **no usable official "control Alexa from your server" API** for a hobbyist
  (the Alexa Smart Home Skill API is the wrong direction; Alexa Smart Properties is
  enterprise-only).
- Unofficial Alexa libraries (AlexaPy, etc.) can read temperature unreliably but cannot
  dependably set the thermostat, and break often.

**The one confirmed-working path** to read AND set this thermostat is a local bridge:

```
home-auto  ->  Home Assistant REST API  ->  HA HomeKit Device  ->  Homebridge
            ->  homebridge-alexa-smarthome plugin  ->  Amazon cloud  ->  thermostat
```

Home Assistant exposes the thermostat as a standard `climate` entity; home-auto just
calls HA's clean, stable REST API. This is the recommended pick.

### What you need first
- **Home Assistant** running on your network (Docker, HA OS, or Core). This becomes the
  device hub for this and future devices (smart plugs, etc.).
- **Node.js 18+** and **Homebridge** on a machine on your network (can be the same PC).
- Your **Amazon account** login (the Homebridge plugin signs in to Alexa; expect a
  one-time CAPTCHA/OTP during setup).

### One-time setup steps
1. **Install Home Assistant** and open its web UI.
2. **Install Homebridge** (`npm install -g homebridge`) and the plugin
   `homebridge-alexa-smarthome` (`npm install -g homebridge-alexa-smarthome`).
3. **Sign the plugin in to Amazon** (in the Homebridge UI). Approve any OTP/CAPTCHA.
   It will discover your Alexa devices, including the thermostat.
4. In Home Assistant: **Settings > Devices & Services > Add Integration > HomeKit Device**.
   It auto-discovers the thermostat (over mDNS) and creates a `climate.*` entity.
   Note that entity id (e.g. `climate.amazon_thermostat`).
5. In Home Assistant: **Profile > Security > Long-Lived Access Tokens > Create Token**.
   Copy the token (shown once).

### What works vs not (through this bridge)
- Readable: current temperature, heat/cool setpoints, HVAC mode.
- Writable: setpoints, HVAC mode (heat/cool/auto/off).
- Not reliable: "is the compressor running right now" (known bug, always shows idle),
  humidity, schedules. Latency on writes is ~2-5s.

### Gotchas
- The Amazon login in the Homebridge plugin **periodically needs re-auth** (Amazon
  invalidates sessions). We'll add a health check/alert so you know when to re-login.
- This whole path is unofficial; Amazon could break it. The clean long-term fix is a
  thermostat with a real API (**Ecobee**, or a **Resideo/Honeywell Home Matter** model
  like the X2S/X8S). Say the word if you'd consider that and I'll fold it in as a
  first-class adapter instead.

### What home-auto will read (put in `.env`)
```
HA_URL=http://homeassistant.local:8123
HA_TOKEN=...                          # the long-lived access token
HA_THERMOSTAT_ENTITY=climate.amazon_thermostat
```

---

## How to hand me the secrets
- Fill the values into `.env` (copy from `.env.example`, which I'll extend with these keys).
- Do **not** paste secrets into chat or `config.yaml`. home-auto reads secrets only from
  the environment, never logs them, and never returns them from the API.
- Once `.env` is filled, tell me which parts are done and I'll wire up and test that adapter.
