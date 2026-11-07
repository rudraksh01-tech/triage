# Deploying to AWS

The web app goes to Vercel. The API, the realtime service and Redis run on one
small EC2 box with Docker Compose. Model files live in S3 so a new model ships
by uploading files, not by rebuilding images.

Rough monthly cost outside the free tier: a `t3.small` (2 vCPU, 2 GB) is about
$15; S3 for ~120 MB of artifacts is cents. A `t3.micro` (1 GB) also works if
you drop the reply drafter (`TRIAGE_INDEX_DIR` pointing at an empty folder).

## 1. Artifacts to S3

```bash
aws s3 mb s3://triage-artifacts-<you>
aws s3 sync ml/artifacts/serving   s3://triage-artifacts-<you>/v1/serving
aws s3 sync ml/artifacts/retrieval s3://triage-artifacts-<you>/v1/retrieval
```

Give the instance an IAM role with read access to that prefix only:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    { "Effect": "Allow", "Action": ["s3:ListBucket"], "Resource": "arn:aws:s3:::triage-artifacts-<you>",
      "Condition": { "StringLike": { "s3:prefix": ["v1/*"] } } },
    { "Effect": "Allow", "Action": ["s3:GetObject"], "Resource": "arn:aws:s3:::triage-artifacts-<you>/v1/*" }
  ]
}
```

## 2. The box

Amazon Linux 2023, `t3.small`, security group open on 22 (your IP only), 80 and 443.

```bash
sudo dnf install -y docker git
sudo systemctl enable --now docker
sudo usermod -aG docker ec2-user   # log out and back in
sudo mkdir -p /usr/local/lib/docker/cli-plugins
sudo curl -SL https://github.com/docker/compose/releases/download/v2.29.7/docker-compose-linux-x86_64 \
  -o /usr/local/lib/docker/cli-plugins/docker-compose && sudo chmod +x $_

git clone https://github.com/<you>/triage && cd triage
cat > .env <<EOF
TRIAGE_LLM_API_KEY=...
TRIAGE_ARTIFACTS_S3_URI=s3://triage-artifacts-<you>/v1
WEB_ORIGIN=https://triage-<you>.vercel.app
EOF
```

The API Dockerfile copies `ml/artifacts/*` into the image. With S3 in use, create
empty placeholders so the build context exists:

```bash
mkdir -p ml/artifacts/serving ml/artifacts/retrieval
docker compose up -d --build
curl localhost:8000/health
```

## 3. HTTPS

The browser needs `https://` and `wss://`. Caddy gets certificates on its own:

```bash
sudo dnf install -y caddy
sudo tee /etc/caddy/Caddyfile <<EOF
api.<your-domain> {
  reverse_proxy 127.0.0.1:8000
}
live.<your-domain> {
  reverse_proxy 127.0.0.1:8080
}
EOF
sudo systemctl enable --now caddy
```

## 4. Vercel

Import the repo, set the root directory to `web`, and add:

```
NEXT_PUBLIC_API_URL=https://api.<your-domain>
NEXT_PUBLIC_REALTIME_URL=https://live.<your-domain>
```

Without these the site still works and shows the measured sample tickets.

## Shipping a new model

```bash
python ml/src/train.py --name v2 && python ml/src/calibrate.py --run v2 && python ml/src/export.py --run v2
aws s3 sync ml/artifacts/serving s3://triage-artifacts-<you>/v2/serving
# point TRIAGE_ARTIFACTS_S3_URI at v2, then
docker compose up -d api
```

The old prefix stays in S3, so rolling back is changing one line.
