# Neo4j Community SSO

## TL;DR

Gate Neo4j Community Browser and Bolt WebSockets with OIDC SSO. Run the local demo with `./demo.sh`.

First run: [QUICKSTART.md](QUICKSTART.md).

## Requirements

- Docker Engine with Compose v2.24 or newer, Bash, curl and Python 3.10+ for the demo.
- Kubernetes 1.29+ with native sidecar support enabled, and kubectl with Kustomize, for the [Kubernetes configuration](k8s/README.md).
- An OIDC provider with authorization-code + PKCE support, verified email and a groups claim for your deployment.

## Config

For your own provider, copy [.env.example](.env.example) to `.env`. The full Compose configuration is in [compose.yaml](compose.yaml).

| Req | Name | Purpose |
|---|---|---|
| Required | `PUBLIC_URL`, `BOLT_ADDRESS` | Public HTTPS URL and the same hostname with its port for Browser's WebSocket connection |
| Required | `OIDC_ISSUER_URL`, `OIDC_CLIENT_ID` | Your issuer and registered client |
| When confidential client | `OIDC_CLIENT_SECRET` | Your client secret; public PKCE clients use the documented placeholder |
| Required | `ALLOWED_GROUPS` | Exact group names admitted to the application, comma-separated |
| Optional | `EMAIL_DOMAINS` | Restrict verified email domains; `*` admits any domain within the allowed groups |
| Required | `COOKIE_SECRET` | A generated URL-safe key; the example includes the generation command |
| When behind TLS proxy | `TRUSTED_PROXY_IPS` | Source CIDRs allowed to provide forwarded headers |

Register the exact callback `${PUBLIC_URL}/oauth2/callback` at your IdP. Use `openid email profile` scopes and include `groups` in the ID token. Keep `.env` private; it is excluded from git.

## Usage

From a checkout, start the self-contained loopback demo:

```sh
./demo.sh
```

Open `http://localhost:7476/browser/`. Run `./demo.sh password` to see the generated password, then sign in as `demo`. The `outsider` account has the same demo password but no allowed group and is denied. If Browser asks for database credentials, choose **No authentication** and connect to `bolt://localhost:7476`.

For an existing IdP, configure `.env` and run `docker compose up -d --wait`. Put a TLS reverse proxy in front of the loopback listener, preserving Host, forwarded scheme and WebSocket upgrades. Keep secure cookies enabled. The standalone demo does not require that proxy.

## Ports and volumes

Compose publishes only the SSO listener on loopback port 7476; the demo also publishes Keycloak on loopback port 9480. Neither the Neo4j HTTP port nor raw Bolt port is published. The database network is internal.

The `data` volume holds Neo4j data; the demo's `identity` volume holds Keycloak data. `./demo.sh down` retains both. Removing a volume destroys its data. Keep `.env.demo` across restarts so its generated passwords and cookie key match the persisted identity data.

## Preconditions

- Your browser and the proxy can reach your IdP, with trusted certificates for HTTPS. Do not disable certificate verification.
- Your deployed public hostname resolves to the TLS proxy or Kubernetes ingress.
- Third-party extensions and containers with access to private backends are trusted.

## Behaviour

SSO enforces admission on both HTTP and Bolt WebSocket handshakes. nginx directs an authenticated WebSocket upgrade to Bolt and normal HTTP to Neo4j.

Neo4j's own authentication is disabled inside that boundary. **Every admitted user has full database/admin access**, irrespective of group names. Identity is available in proxy authentication logs, not as a distinct Neo4j database user. Do not publish or route around the private backends.

The proxy cookie lasts one hour and refreshes after five minutes. `/oauth2/sign_out` clears the proxy cookie; it does not end the IdP session. Established WebSockets are not reauthorized on every query, so sign-out, group removal or cookie expiry does not immediately terminate them.

The Kubernetes configuration runs the three application containers in one pod, with native proxy sidecars and pod-local backend listeners. It exposes only the SSO listener, uses read-only image filesystems with bounded writable volumes, and keeps the database on one persistent volume. A single replica and Recreate updates mean planned downtime. During shutdown, Neo4j waits ten seconds for endpoint removal; Kubernetes keeps the proxies running until Neo4j exits, within a 90-second pod grace period.

## Out of scope

- Native OIDC inside Neo4j, per-user database roles, impersonation or RBAC.
- SSO for native TCP Bolt clients; this entry point accepts HTTP and WebSockets.
- Multi-node availability, backups and production identity-provider operation.

## Expected result

The demo admits `demo`, denies `outsider`, serves Browser and accepts queries through the same authenticated endpoint. Run:

```sh
python3 tests/check_sso.py
```

Expect six PASS lines covering anonymous denial, PKCE login, both HTTP APIs, Bolt WebSocket negotiation and group denial. This check automates Keycloak's login form; use your own provider's login test for other IdPs.

The same checks pass on RKE2 1.36.4 through nginx ingress with trusted HTTPS and persistent Ceph storage. The RKE test also verifies backend-port isolation and persistence across pod recreation. This is protocol-level validation; interactive Browser query execution is not part of the automated check. CI separately runs `bash tests/check_k8s.sh` with pinned Kustomize, kubeconform, kube-linter, Polaris and Pluto versions.
