## What this is

`compose.yaml` runs the SSO-gated Community database, and `compose.demo.yaml` supplies a local Keycloak demo. `k8s/` supplies the Kubernetes/Rancher configuration. SSO controls admission; all admitted users have full database access.

## How to use it

1. Clone: `git clone https://github.com/djlongy/neo4j-community-sso.git`
2. Enter the checkout: `cd neo4j-community-sso`
3. Start the self-contained demo: `./demo.sh`
4. Display its generated password: `./demo.sh password`
5. Open `http://localhost:7476/browser/` and sign in as `demo`.
6. Check login, denial and database traffic: `python3 tests/check_sso.py`
7. For Kubernetes, follow [k8s/README.md](k8s/README.md).

You know it works when the integration check prints six PASS lines.
