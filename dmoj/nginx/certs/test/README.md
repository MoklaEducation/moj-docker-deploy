# Test TLS Certificates

Place test TLS certificate and key files in this directory for local/test-machine runs.

Expected filenames (used by nginx.test.conf):
- code.test.local.crt
- code.test.local.key

Recommended provisioning options:
1. mkcert (best for browser-trusted local development)
   - Install mkcert on test machine.
   - Run:
     - mkcert -cert-file code.test.local.crt -key-file code.test.local.key code.test.local

2. OpenSSL self-signed (quick fallback)
   - Run:
     - openssl req -x509 -nodes -newkey rsa:2048 -days 365 \
       -keyout code.test.local.key \
       -out code.test.local.crt \
       -subj "/CN=code.test.local" \
       -addext "subjectAltName=DNS:code.test.local"

3. Let's Encrypt staging (public test host)
   - Prefer this only when DNS points to the test machine and HTTP challenge is reachable.
   - Use Certbot with staging CA first, then switch to production CA.

Notes:
- Do not commit private keys.
- This folder is intended for per-machine certificate material.
