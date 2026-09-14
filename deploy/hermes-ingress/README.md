# Optional Hermes dashboard ingress

Recorded topology: Launchpad HTTPS -> existing Traefik -> nginx `127.0.0.1:18890` -> forwarded dashboard `127.0.0.1:18789`. Verify the topology and ports on another host. This loopback layout needs host networking; an isolated container cannot reach host services through its own localhost.

From this directory, render only the hostname variable, preserving nginx variables such as `$host`:

```bash
export HERMES_PUBLIC_HOST=hermes.example.com
envsubst '${HERMES_PUBLIC_HOST}' < nginx.conf.template > nginx.conf
```

Use the actual HTTPS ingress hostname. Keep the rendered configuration local. The recorded nginx image digest is `nginx@sha256:dc5069ad14f19660b141b21236140b91656bf89bbc3e2417c70ae650cd66104c`. Mount configuration at `/etc/nginx/nginx.conf` and a separately provisioned password hash file at `/etc/nginx/hermes.htpasswd`, read-only. Never commit the password file.

Run `nginx -t` in an isolated test container before applying configuration. Provision authentication before enabling the HTTPS route. The workshop application hostname did not enforce the expected platform login; nginx therefore enforces Basic authentication itself.

Validate missing/wrong credentials -> 401; valid credentials -> dashboard; wrong Host -> 421; unapproved Origin -> 403; authenticated chat/WebSocket traffic works. Retain loopback bindings, TLS and Host/Origin checks. This template does not deploy or restart anything by itself.
