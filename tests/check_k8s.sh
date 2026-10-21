#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
workdir=$(mktemp -d)
trap 'rm -rf "$workdir"' EXIT
kustomize build k8s > "$workdir/rendered.yaml" 2> "$workdir/build.stderr"
cat "$workdir/build.stderr" >&2
if grep -q '^# Warning:' "$workdir/build.stderr"; then
  exit 1
fi
kubeconform -strict -summary -kubernetes-version 1.29.0 "$workdir/rendered.yaml"
kube-linter lint "$workdir/rendered.yaml" --include no-readiness-probe
polaris audit --audit-path "$workdir/rendered.yaml" \
  --checks automountServiceAccountToken,linuxHardening \
  --disallow-exemptions --set-exit-code-below-score 100 --format pretty --only-show-failed-tests
pluto detect-files -d "$workdir" --target-versions k8s=v1.36.4
