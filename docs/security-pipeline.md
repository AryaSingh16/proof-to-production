# Security Pipeline Architecture & Threat Matrix

This document outlines the security controls integrated throughout the CI/CD supply chain and deployment workflow.

## Supply-Chain Pipeline Stages

```
commit / PR
   │
   ├─► 1. Lint & Unit Tests (ruff, pytest)
   ├─► 2. Secret Scanning (Gitleaks)
   └─► 3. SAST Static Analysis (Semgrep)
   │
   ▼
Docker Build
   │
   └─► 4. Container Vulnerability Scanning (Trivy, CRITICAL/HIGH fixable)
   │
   ▼
Publish & Attest (main branch only)
   │
   ├─► 5. Push image to GHCR (lowercase repository name)
   ├─► 6. SBOM Generation (Syft / anchore/sbom-action, SPDX format)
   └─► 7. Keyless Cryptographic Signing & Attestation (Cosign with GitHub OIDC)
   │
   ▼
Deploy Gate
   │
   └─► 8. Client Verification (verify-image.sh / Cosign verify before compose up)
```

---

## Security Control Threat Matrix

| Pipeline Stage / Control | Tool | What It Catches | What It Does NOT Catch |
|---|---|---|---|
| **Secret Scanning** | Gitleaks | API keys, tokens, private keys, passwords committed in git history or PRs | Secrets injected via environment variables or runtime config; encrypted secrets |
| **Static Application Security Testing (SAST)** | Semgrep | Insecure code patterns, SQL injection vectors, unsafe deserialization, insecure Dockerfile practices | Runtime zero-day logic bugs; dynamically generated malicious input |
| **Container Image Scanning** | Trivy | Known CVEs (CRITICAL/HIGH fixable) in OS packages and Python wheels | Undiscovered zero-day vulnerabilities; in-house business logic vulnerabilities |
| **Software Bill of Materials (SBOM)** | Syft | Full inventory of OS and application dependencies in standard SPDX-JSON | Vulnerabilities in components not listed in package registries or manifest files |
| **Cryptographic Image Signing** | Cosign | Tampered container images, unauthorized registry pushes, man-in-the-middle image replacements | Vulnerabilities in authorized code; malicious commits made by compromised authorized accounts |
| **Image Verification Gate** | `verify-image.sh` | Refuses execution of any image whose signature or OIDC certificate identity does not verify | Vulnerabilities present in an authentic, verified image |
| **Runtime Container Hardening** | Docker Compose | Root privilege escalation (`cap_drop: [ALL]`, `no-new-privileges`, `user: 10001`), host tampering (`read_only: true`) | Application-level Denial of Service; memory exhaustion beyond container limits |
