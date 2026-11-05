#!/usr/bin/env bash
set -euo pipefail
context=kind-readiness-security
identity=system:serviceaccount:readiness-diag-lab:readiness-collector
check() {
  local expected=$1 namespace=$2 verb=$3 resource=$4 result
  result=$(kubectl --context "$context" auth can-i "$verb" "$resource" \
    --namespace "$namespace" --as "$identity" 2>/dev/null) || [[ "$result" == no ]]
  [[ "$result" == "$expected" ]] || { echo "Unexpected permission: $namespace $verb $resource ($result)"; exit 1; }
}
check yes readiness-diag-lab get pods
check yes readiness-diag-lab get pods/log
check yes readiness-diag-lab list events
check no readiness-diag-lab get secrets
check no readiness-diag-lab list pods
check no readiness-diag-lab create pods
check no readiness-diag-lab patch pods
check no readiness-diag-lab delete pods
check no readiness-diag-lab create pods/exec
check no readiness-diag-lab create roles.rbac.authorization.k8s.io
check no default get pods
check no default list events
