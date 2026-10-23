# Deploying on Oracle_Cloud_ARM

The stack lives entirely under `~/containers/place`: the repo in `src/`, state in `data/`.
All commands run on the host (the Mac never runs containers).

## One-time host setup

```bash
mkdir -p ~/containers/place/data/{redis,place}
id -u                       # 1001 on this box — put that in PLACE_UID/PLACE_GID
```

The directories must be owned by the same uid the containers run as. `PLACE_UID=1001`,
`PLACE_GID=1001` on this host (ubuntu is **not** uid 1000 here).

## Sync source from the Mac

```bash
rsync -az --delete --exclude '.git' --exclude '.env' \
  --exclude '__pycache__' --exclude '.pytest_cache' \
  ~/Code/place-revival/ Oracle_Cloud_ARM:~/containers/place/src/
```

`--exclude '.env'` also protects the remote `.env` from `--delete`.

## Configure (once)

```bash
cd ~/containers/place/src
cp .env.example .env
$EDITOR .env     # PLACE_DATA_DIR=/home/ubuntu/containers/place/data
                 # PLACE_UID=1001, PLACE_GID=1001
```

## Start / update

```bash
cd ~/containers/place/src
docker compose config -q                  # CONFIG_OK before anything else
docker compose up -d --build
docker compose ps                         # 4 containers, api+gateway+redis healthy
curl -s http://127.0.0.1:8090/healthz     # {"status":"ok","redis":true,...}
curl -s -o /tmp/x.png -w '%{http_code} %{content_type}\n' \
  http://127.0.0.1:8090/place.png         # 200 image/png
file /tmp/x.png                           # PNG image data, 250 x 250
docker compose exec -T gateway nginx -t   # after up: needs the compose network to resolve `api`
```

End-to-end WebSocket check, through the gateway rather than straight at the app:

```bash
docker compose run --rm --no-deps api python -m scripts.smoke_ws ws://gateway/ws
# RESULT: PASS
```

## Logs / restart / stop

```bash
docker compose logs -f --tail=100 api worker
docker compose restart worker            # final image is flushed on SIGTERM
docker compose down                      # data survives: bind mounts only, no named volumes
```

## Disk hygiene

The box runs around 79 % full; builds are what fill it.

```bash
docker image prune -f
docker builder prune -f
```

## Putting nginx + a domain in front (not done yet)

1. Add `/etc/nginx/sites-enabled/place.jessexu.me.conf`:

   ```nginx
   server {
       server_name place.jessexu.me;

       location / {
           proxy_pass http://127.0.0.1:8090;
           proxy_http_version 1.1;
           proxy_set_header Upgrade $http_upgrade;
           proxy_set_header Connection "upgrade";
           proxy_set_header Host $host;
           proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
           proxy_set_header X-Forwarded-Proto $scheme;
           proxy_read_timeout 1h;
           proxy_send_timeout 1h;
           client_max_body_size 0;
       }
   }
   ```

2. `sudo nginx -t && sudo systemctl reload nginx`
3. Repoint DNS: `place.jessexu.me` currently CNAMEs to the deleted CloudFront distribution
   (`dc v1axi90f6a6.cloudfront.net`). Replace it with an A record to the instance's public
   IP (Cloudflare proxying is fine; WebSockets are on by default).
4. Then set `PLACE_BIND=127.0.0.1` in `.env` and `docker compose up -d`, so the raw port is
   no longer public.
5. An OCI VCN ingress rule for TCP 8090 is only needed for direct
   `http://<public-ip>:8090` access before step 3. Without it, test through an SSH tunnel:

   ```bash
   ssh -N -L 8090:127.0.0.1:8090 Oracle_Cloud_ARM &
   # then http://127.0.0.1:8090 locally
   ```

## Troubleshooting

- **`EACCES` in `docker compose logs worker` / 404 on `/place.png`** — data dir owned by the
  wrong uid. `sudo chown -R 1001:1001 ~/containers/place/data`, then restart. Do not run the
  containers as root to "fix" it.
- **502 from the gateway on first boot** — the `api` healthcheck has not passed yet; the
  gateway waits on `service_healthy`, so this normally only appears if `api` is crashing.
- **`nginx -t` fails in a throwaway container** — nginx resolves `proxy_pass` upstreams at
  parse time and `api` only exists on the compose network. Use
  `docker compose exec -T gateway nginx -t`.
- **Only one client receives updates** — something scaled `api`; keep it at one replica.
