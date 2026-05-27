$REGISTRY = "crpcgj5cfg51n3n7sseb"
$IMAGE = "cr.yandex/$REGISTRY/mp-optimizer:latest"
$CONTAINER = "mp-optimizer-api"
$SA_ID = "ajettn349p0svobb1g9c"
$DB_HOST = "rc1a-1ch8b77air222pd0.mdb.yandexcloud.net"

if (-not $env:DB_PASSWORD) {
    Write-Host "Set `$env:DB_PASSWORD before running (and `$env:AUTH_SECRET_KEY for production sessions)." -ForegroundColor Yellow
    exit 1
}

docker build --platform linux/amd64 -t $IMAGE .
if ($LASTEXITCODE -ne 0) { exit 1 }

docker push $IMAGE
if ($LASTEXITCODE -ne 0) { exit 1 }

$envString = "DB_HOST=$DB_HOST,DB_PORT=6432,DB_NAME=marketplace,DB_USER=mp_user,DB_PASSWORD=$env:DB_PASSWORD,DB_SSLMODE=verify-full,DB_SSLROOTCERT=/usr/local/share/ca-certificates/yandex-cloud-ca.crt"
if ($env:AUTH_SECRET_KEY) {
    $envString += ",AUTH_SECRET_KEY=$env:AUTH_SECRET_KEY"
}

yc serverless container revision deploy `
  --container-name $CONTAINER `
  --image $IMAGE `
  --cores 1 --memory 512MB --execution-timeout 30s --concurrency 4 `
  --service-account-id $SA_ID `
  --environment $envString

if ($LASTEXITCODE -eq 0) {
    Write-Host "Deployed. URL: https://bbal0tnkd91lbjhra64a.containers.yandexcloud.net" -ForegroundColor Green
}
