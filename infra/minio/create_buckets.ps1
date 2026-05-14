# ============================================================
# BTC Polymarket Bot - MinIO Bucket Creation
# ============================================================
#
# Este script cria o bucket principal do data lake no MinIO.
# Execute depois que o container btc-polymarket-minio estiver rodando.
#
# Uso:
# powershell -ExecutionPolicy Bypass -File infra\minio\create_buckets.ps1
# ============================================================

$bucket = "btc-polymarket-datalake"
$network = "btc-polymarket-bot_default"

Write-Host "Creating MinIO client container and configuring alias..."

docker run --rm --network $network `
  --entrypoint /bin/sh `
  minio/mc -c "mc alias set local http://btc-polymarket-minio:9000 minioadmin minioadmin123 && mc mb --ignore-existing local/$bucket"

Write-Host "Creating logical prefixes..."

New-Item -ItemType Directory -Force -Path .tmp_minio | Out-Null
Set-Content -Path .tmp_minio\.keep -Value ""

docker run --rm --network $network `
  -v ${PWD}/.tmp_minio:/tmp_minio `
  --entrypoint /bin/sh `
  minio/mc -c "mc alias set local http://btc-polymarket-minio:9000 minioadmin minioadmin123 && mc cp /tmp_minio/.keep local/$bucket/raw/btc/.keep && mc cp /tmp_minio/.keep local/$bucket/raw/polymarket/.keep && mc cp /tmp_minio/.keep local/$bucket/features/.keep && mc cp /tmp_minio/.keep local/$bucket/models/.keep"

Remove-Item -Recurse -Force .tmp_minio

Write-Host ""
Write-Host "Buckets:"
docker run --rm --network $network `
  --entrypoint /bin/sh `
  minio/mc -c "mc alias set local http://btc-polymarket-minio:9000 minioadmin minioadmin123 && mc ls local"

Write-Host ""
Write-Host "Data lake prefixes:"
docker run --rm --network $network `
  --entrypoint /bin/sh `
  minio/mc -c "mc alias set local http://btc-polymarket-minio:9000 minioadmin minioadmin123 && mc ls --recursive local/$bucket"