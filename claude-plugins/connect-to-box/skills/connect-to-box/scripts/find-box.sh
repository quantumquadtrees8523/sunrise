#!/usr/bin/env bash
# find-box.sh
#
# Works out what Home Assistant box you are dealing with and how you could get a
# shell on it. Read-only: never writes to the box, never authenticates, never
# needs a shell on it.
#
#   ./find-box.sh                         # discover the box by mDNS
#   ./find-box.sh homeassistant.local     # or name it yourself
#   MCP_PATH=/api/mcp/sunrise ./find-box.sh   # also check that MCP endpoint's OAuth discovery
#
# Exit codes: 0 found and reachable, 1 found but blocked (reason printed), 2 nothing found.
# Prints KEY=value lines at the end (FIND_BOX_*) for callers to parse.

set -u
MCP_PATH="${MCP_PATH:-/api/mcp}"

BOLD=""; DIM=""; RED=""; YEL=""; GRN=""; OFF=""
if [ -t 1 ]; then
  BOLD=$(printf '\033[1m'); DIM=$(printf '\033[2m'); RED=$(printf '\033[31m')
  YEL=$(printf '\033[33m'); GRN=$(printf '\033[32m'); OFF=$(printf '\033[0m')
fi
head2(){ printf '\n%s%s%s\n' "$BOLD" "$*" "$OFF"; }
ok()   { printf '  %s+%s %s\n' "$GRN" "$OFF" "$*"; }
warn() { printf '  %s!%s %s\n' "$YEL" "$OFF" "$*"; }
bad()  { printf '  %sx%s %s\n' "$RED" "$OFF" "$*"; }
info() { printf '  %s-%s %s\n' "$DIM" "$OFF" "$*"; }

# --- discovery ---------------------------------------------------------------
# A subnet scan is NOT reliable: parallel nc sweeps miss open ports, and a box
# can sit on a different VLAN. mDNS is how Home Assistant advertises itself.
discover_macos() {
  command -v dns-sd >/dev/null 2>&1 || return 1
  ( dns-sd -B _home-assistant._tcp local & BPID=$!; sleep 4; kill $BPID 2>/dev/null ) 2>/dev/null \
    | awk '/_home-assistant/ {for(i=7;i<=NF;i++) printf "%s%s", $i, (i<NF?" ":"\n")}' \
    | sed 's/[[:space:]]*$//' | sort -u | grep -v '^$'
}
resolve_macos() { # $1 = instance name -> prints the TXT line
  ( dns-sd -L "$1" _home-assistant._tcp local & BPID=$!; sleep 4; kill $BPID 2>/dev/null ) 2>/dev/null \
    | grep -E 'version=|can be reached at' | tr '\n' ' '
}
discover_linux() {
  command -v avahi-browse >/dev/null 2>&1 || return 1
  avahi-browse -rpt _home-assistant._tcp 2>/dev/null | awk -F';' '/^=/ {print $7}' | sort -u
}
txt_field() { printf '%s' "$1" | tr ' ' '\n' | grep "^$2=" | head -1 | cut -d= -f2-; }

# Sequential on purpose. A parallel sweep gives false negatives.
port_open() { nc -z -G 2 -w 2 "$1" "$2" >/dev/null 2>&1; }
http_code() { curl -sk -m 8 -o /dev/null -w '%{http_code}' "$1" 2>/dev/null; }

head2 "connect-to-box: find the box"

USER_HOST="${1:-}"; HOST=""; NAME=""
HA_VERSION=""; INTERNAL_URL=""; EXTERNAL_URL=""

# Always try mDNS, even with an address given: HA does not expose its version
# to an unauthenticated caller, so the TXT record is the only free source.
head2 "1. mDNS"
INSTANCES=$(discover_macos || discover_linux || true)
if [ -z "${INSTANCES:-}" ]; then
  warn "No Home Assistant advertised on this network."
  info "Not conclusive: it may be on another VLAN, or mDNS may be blocked."
  [ -z "$USER_HOST" ] && { info "Re-run with the address:  $0 homeassistant.local"; exit 2; }
else
  COUNT=$(printf '%s\n' "$INSTANCES" | grep -c . )
  ok "found $COUNT instance(s): $(printf '%s' "$INSTANCES" | tr '\n' ',' | sed 's/,$//')"
  NAME=$(printf '%s\n' "$INSTANCES" | head -1)
  [ "$COUNT" -gt 1 ] && warn "using the first one: $NAME (ask the owner which box they mean)"
  TXT=$(resolve_macos "$NAME")
  HA_VERSION=$(txt_field "$TXT" version)
  INTERNAL_URL=$(txt_field "$TXT" internal_url)
  EXTERNAL_URL=$(txt_field "$TXT" external_url)
  HOST=$(printf '%s' "$INTERNAL_URL" | sed -E 's#^https?://##; s#[:/].*##')
  [ -n "$HA_VERSION" ]   && ok   "version      $HA_VERSION"
  [ -n "$INTERNAL_URL" ] && info "internal_url $INTERNAL_URL"
  [ -n "$EXTERNAL_URL" ] && info "external_url $EXTERNAL_URL"
fi
[ -n "$USER_HOST" ] && HOST="$USER_HOST"
[ -z "$HOST" ] && { bad "Could not determine a hostname."; exit 2; }

head2 "2. The box: $HOST"
IP=$(ping -c1 -W 2000 "$HOST" 2>/dev/null | head -1 | sed -nE 's/.*\(([0-9.]+)\).*/\1/p')
[ -n "$IP" ] && ok "resolves to $IP" || warn "could not resolve $HOST by ping"
if [ -z "$HA_VERSION" ]; then
  for base in "https://$HOST" "http://$HOST:8123"; do
    [ "$(http_code "$base/manifest.json")" = "200" ] && { ok "Home Assistant answers at $base"; break; }
  done
  warn "version unknown (mDNS gave none) - ask the owner to check Settings > About"
fi

head2 "3. Open ports (sequential)"
OPEN=""
for spec in "22:ssh" "80:http" "443:https" "8123:home assistant" "4357:HA OS observer" \
            "8443:code-server / alt-https" "8080:code-server / web" "3000:code-server / web" \
            "7681:ttyd" "9000:portainer" "9443:portainer" "10000:webmin" \
            "2375:DOCKER API (unauthenticated!)" "2376:docker api tls"; do
  P=${spec%%:*}; LABEL=${spec#*:}
  if port_open "$HOST" "$P"; then ok "$P open  ($LABEL)"; OPEN="$OPEN $P"
  else info "$P closed ($LABEL)"; fi
done
case " $OPEN " in *" 2375 "*)
  bad "Port 2375 is an unauthenticated Docker API: anyone on the LAN can own this box."
  info "Tell the owner. Do NOT quietly use it as your way in." ;;
esac

head2 "4. Install type"
case " $OPEN " in
  *" 4357 "*) INSTALL_TYPE="os"
              ok "Home Assistant OS (observer on 4357)"
              info "-> add-on store exists: the Terminal & SSH add-on gives a shell with no host password" ;;
  *)          INSTALL_TYPE="container_or_core"
              warn "NOT Home Assistant OS - Container, Core or Supervised"
              info "-> no add-on store, no Terminal add-on: you need a real shell on the host" ;;
esac
SSH_BANNER=""
case " $OPEN " in *" 22 "*)
  SSH_BANNER=$(nc -w 3 "$HOST" 22 </dev/null 2>/dev/null | head -1 | tr -d '\r')
  [ -n "$SSH_BANNER" ] && info "ssh banner: $SSH_BANNER  (compare with /etc/os-release in any shell you find)" ;;
esac

head2 "5. HTTPS"
# Asking for https://<ip> fails the handshake whenever the cert is for a NAME,
# which is normal behind a reverse proxy. Reverse DNS is the source that works.
NAMES=""
RDNS=$(dig +short -x "${IP:-$HOST}" 2>/dev/null | head -1 | sed 's/\.$//')
[ -z "$RDNS" ] && RDNS=$(host "${IP:-$HOST}" 2>/dev/null | sed -nE 's/.*pointer (.*)\.$/\1/p' | head -1)
if [ -n "$RDNS" ]; then
  info "reverse DNS says '$RDNS'"
  case "$RDNS" in *.*) NAMES="$RDNS" ;; *) NAMES="$RDNS.local $RDNS" ;; esac
fi
MDNS_HOST=$(printf '%s' "$INTERNAL_URL" | sed -E 's#^https?://##; s#[:/].*##')
case " $NAMES " in *" $MDNS_HOST "*) ;; *) [ -n "$MDNS_HOST" ] && NAMES="$NAMES $MDNS_HOST" ;; esac
CANDS=""
for n in $NAMES "$HOST"; do
  [ -z "$n" ] && continue
  case " $CANDS " in *" https://$n "*) continue ;; esac
  CANDS="$CANDS https://$n"
done
[ -n "$EXTERNAL_URL" ] && case " $CANDS " in *" $EXTERNAL_URL "*) ;; *) CANDS="$CANDS $EXTERNAL_URL" ;; esac

HTTPS_BASE=""; OAUTH="unknown"; PRIVATE_CA=""
for cand in $CANDS; do
  C=$(http_code "$cand/manifest.json")
  case "$C" in
    200) ok "$cand -> $C"; [ -z "$HTTPS_BASE" ] && HTTPS_BASE="$cand" ;;
    000) info "$cand -> no TLS handshake (name mismatch, or nothing listening)" ;;
    *)   warn "$cand -> $C (a redirect usually means a login gate in front of HA, not HA)" ;;
  esac
done
if [ -n "$HTTPS_BASE" ]; then
  ISS=$(curl -sk -m 8 "$HTTPS_BASE/.well-known/oauth-authorization-server" 2>/dev/null \
        | tr ',' '\n' | grep '"issuer"' | cut -d'"' -f4)
  PR=$(http_code "$HTTPS_BASE/.well-known/oauth-protected-resource$MCP_PATH")
  if [ "$PR" = "404" ]; then
    bad "oauth-protected-resource$MCP_PATH -> 404: an MCP client has nowhere to start OAuth"
    info "   use a long-lived token in an Authorization: Bearer header"; OAUTH="no"
  elif [ -z "$ISS" ]; then
    warn "OAuth discovery publishes NO issuer - MCP Authenticate will likely fail"; OAUTH="no"
  elif printf '%s' "$ISS" | grep -qE '127\.0\.0\.1|localhost'; then
    bad "OAuth issuer is $ISS - a proxy rewrites Host; sign-in would go to your own machine"; OAUTH="no"
  else
    ok "OAuth issuer $ISS"; OAUTH="yes"
  fi
  SNI=$(printf '%s' "$HTTPS_BASE" | sed -E 's#^https?://##; s#[:/].*##')
  CA=$(printf '' | openssl s_client -connect "$HOST:443" -servername "$SNI" 2>/dev/null \
       | openssl x509 -noout -issuer 2>/dev/null | sed 's/^issuer=//')
  if printf '%s' "$CA" | grep -qiE 'caddy|self[- ]?signed|local authority'; then
    PRIVATE_CA="$CA"
    warn "cert is from a private CA: $CA"
    info "   Claude Code will refuse it until NODE_EXTRA_CA_CERTS points at the root, set in the"
    info "   environment Claude is LAUNCHED from (shell profile). settings.json env does not work."
  fi
else
  warn "No working HTTPS endpoint found. Anything needing HTTPS (MCP) is an owner setup step."
fi

head2 "6. Ways onto the box"
if [ "$INSTALL_TYPE" = "os" ]; then
  ok "Terminal & SSH add-on in the Home Assistant UI (owner installs it)"
fi
case " $OPEN " in *" 22 "*) ok "ssh $HOST  (needs a key, or the owner running ssh-copy-id with the HOST password)" ;; esac
for p in 8443 8080 3000 7681 9000 9443 10000; do
  case " $OPEN " in *" $p "*) info "port $p may be a leftover browser shell - check it is on the HOST, not in a container" ;; esac
done
warn "The Home Assistant web password is NOT the host account password."

printf '\n'
echo "FIND_BOX_NAME=$NAME"
echo "FIND_BOX_HOST=$HOST"
echo "FIND_BOX_IP=${IP:-}"
echo "FIND_BOX_HA_VERSION=$HA_VERSION"
echo "FIND_BOX_INTERNAL_URL=$INTERNAL_URL"
echo "FIND_BOX_EXTERNAL_URL=$EXTERNAL_URL"
echo "FIND_BOX_INSTALL_TYPE=$INSTALL_TYPE"
echo "FIND_BOX_OPEN_PORTS=$(echo $OPEN)"
echo "FIND_BOX_SSH_BANNER=$SSH_BANNER"
echo "FIND_BOX_HTTPS_BASE=$HTTPS_BASE"
echo "FIND_BOX_OAUTH=$OAUTH"
echo "FIND_BOX_PRIVATE_CA=$PRIVATE_CA"
exit 0
